"""Zwei-Faktor-Anmeldung verwalten: Status, Einrichten (auch direkt beim Login, wenn sie Pflicht ist),
Abschalten und – für Admins – bei anderen zurücksetzen (z. B. Handy verloren)."""
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _issue_token_pair, complete_login
from app.api.deps import Actor, get_current_actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, Employee
from app.schemas.auth import (
    TwoFactorChallenge,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorEnableResponse,
    TwoFactorSetupResponse,
    TwoFactorStatus,
)
from app.services import rate_limiter, two_factor_service
from app.services.audit_service import log_action
from app.services.auth_service import verify_password

router = APIRouter(tags=["two_factor"])
_optional_bearer = HTTPBearer(auto_error=False)


async def _account_for_setup(
    request: Request,
    challenge_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> tuple[Account, bool]:
    """Konto der angemeldeten Person oder (Pflicht beim Login) aus dem Challenge-Token.
    Zweiter Wert: True, wenn über das Challenge-Token (noch nicht angemeldet)."""
    if challenge_token:
        return await two_factor_service.read_challenge(db, request, challenge_token, "setup"), True
    if credentials is None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
    actor = await get_current_actor(request, credentials, db)
    if actor.account is None:
        raise AppError(403, "ACCOUNT_REQUIRED", "Nur für angemeldete Personen.")
    return actor.account, False


def _audit(db: AsyncSession, account: Account, actor_account_id: int | None, detail: str) -> None:
    if account.tenant_id is not None:
        log_action(
            db, tenant_id=account.tenant_id, actor_account_id=actor_account_id,
            action=AuditAction.TWO_FACTOR_CHANGED, entity_type="account", entity_id=account.id, detail=detail,
        )


@router.get("/auth/2fa", response_model=TwoFactorStatus)
async def two_factor_status(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> TwoFactorStatus:
    if actor.account is None:
        raise AppError(403, "ACCOUNT_REQUIRED", "Nur für angemeldete Personen.")
    return TwoFactorStatus(
        enabled=actor.account.two_factor_enabled,
        required=await two_factor_service.two_factor_required(db, actor.account),
        recovery_codes_left=two_factor_service.recovery_codes_left(actor.account),
    )


@router.post("/auth/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(
    request: Request,
    payload: TwoFactorChallenge,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorSetupResponse:
    """Schritt 1: neues Geheimnis für die Authenticator-App (QR-Code); noch nicht aktiv."""
    account, _ = await _account_for_setup(request, payload.challenge_token, credentials, db)
    secret, uri = two_factor_service.start_setup(account)
    await db.commit()
    return TwoFactorSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/auth/2fa/enable", response_model=TwoFactorEnableResponse)
async def enable_two_factor(
    request: Request,
    payload: TwoFactorEnableRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorEnableResponse:
    """Schritt 2: Code aus der App bestätigt. Andere Sitzungen enden; diese bekommt neue Tokens und
    die Wiederherstellungscodes (werden nur jetzt angezeigt)."""
    account, during_login = await _account_for_setup(request, payload.challenge_token, credentials, db)
    codes = two_factor_service.finish_setup(account, payload.code)
    _audit(db, account, account.id, "Zwei-Faktor-Anmeldung eingerichtet")
    tokens = await complete_login(db, account, "Anmeldung (Zwei-Faktor eingerichtet)") if during_login else None
    if tokens is None:
        await db.commit()
        tokens = _issue_token_pair(account)
    return TwoFactorEnableResponse(recovery_codes=codes, access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/auth/2fa/disable", response_model=TwoFactorStatus)
async def disable_two_factor(
    payload: TwoFactorDisableRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorStatus:
    """Selbst abschalten (mit Passwort) – nicht, wenn die Firma sie für die eigene Rolle vorschreibt.
    Alle Sitzungen enden; danach neu anmelden."""
    account = actor.account
    if account is None:
        raise AppError(403, "ACCOUNT_REQUIRED", "Nur für angemeldete Personen.")
    key = f"2fa-disable:{account.id}"
    rate_limiter.check_rate_limit(key, 5, 15 * 60)
    if account.password_hash is None or not verify_password(payload.password, account.password_hash):
        rate_limiter.record_failure(key)
        raise AppError(400, "PASSWORD_WRONG", "Das Passwort stimmt nicht.")
    if await two_factor_service.two_factor_required(db, account):
        raise AppError(400, "TWO_FACTOR_REQUIRED", "Die Firma schreibt die Zwei-Faktor-Anmeldung für deine Rolle vor.")
    two_factor_service.disable(account)
    _audit(db, account, account.id, "Zwei-Faktor-Anmeldung abgeschaltet")
    await db.commit()
    return TwoFactorStatus(enabled=False, required=False, recovery_codes_left=0)


async def _reset(db: AsyncSession, actor: Actor, account: Account | None) -> None:
    if account is None or account.tenant_id != actor.tenant_id:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Konto nicht gefunden.")
    if account.id == actor.account_id:
        raise AppError(400, "CANNOT_RESET_SELF", "Die eigene Zwei-Faktor-Anmeldung bitte selbst verwalten.")
    two_factor_service.disable(account)
    _audit(db, account, actor.account_id, f"Zwei-Faktor-Anmeldung von {account.display_name} zurückgesetzt")
    await db.commit()


@router.post("/employees/{employee_id}/2fa-reset", status_code=204)
async def reset_employee_two_factor(
    employee_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> None:
    """Admin setzt die Zwei-Faktor-Anmeldung eines Mitarbeiters zurück (z. B. Handy verloren). Die
    Person meldet sich danach nur mit Passwort an bzw. richtet sie neu ein, wenn sie Pflicht ist."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    await _reset(db, actor, employee.account)


@router.post("/hr-users/{account_id}/2fa-reset", status_code=204)
async def reset_account_two_factor(
    account_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> None:
    await _reset(db, actor, await db.get(Account, account_id))
