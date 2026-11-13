from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.api.deps import Actor, account_custom_permissions, get_current_actor
from app.models import Account, AccountTokenPurpose, AuditAction, Device, HrRole, Tenant
from app.services.audit_service import log_action
from app.schemas.device import DeviceEnrollRequest, DeviceEnrollResponse, DevicePairRequest, DevicePairResponse
from app.schemas.auth import (
    ChangePasswordRequest,
    DeviceLoginRequest,
    DeviceLoginResponse,
    LoginRequest,
    LoginResponse,
    TwoFactorLoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.account_tokens import PASSWORD_RESET_TTL, consume_token, issue_token
from app.services.auth_service import (
    account_can_sign_in,
    create_token,
    decode_token,
    hash_password,
    session_fingerprint,
    verify_password,
)
from app.services.email_service import resolve_smtp_config, send_email
from app.services.signup_mail import send_verification_mail
from app.services import rate_limiter
from app.services.pairing_service import card_salt, new_device_token, pairing_code_hash, token_hash
from app.services.notification_service import notify_device_rejected, notify_device_replaced
from app.services.device_enrollment import enroll_device, pending_enrollment_for_token, touch_pending_enrollment
from app.services.settings_service import device_kiosk_config
from app.services import two_factor_service

router = APIRouter(prefix="/auth", tags=["auth"])

_LOGIN_LIMIT = 8  # Fehlversuche je E-Mail+IP im Fenster
_LOGIN_IP_LIMIT = 60  # Fehlversuche je IP im Fenster
_LOGIN_WINDOW = 15 * 60


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_keys(request: Request, email: str) -> tuple[str, str]:
    ip = _client_ip(request)
    return f"login:{ip}:{email.lower()}", f"login-ip:{ip}"


def _check_login_allowed(request: Request, email: str) -> None:
    per_account, per_ip = _login_keys(request, email)
    rate_limiter.check_rate_limit(per_account, _LOGIN_LIMIT, _LOGIN_WINDOW)
    rate_limiter.check_rate_limit(per_ip, _LOGIN_IP_LIMIT, _LOGIN_WINDOW)


def _login_failed(request: Request, email: str) -> AppError:
    for key in _login_keys(request, email):
        rate_limiter.record_failure(key)
    return AppError(401, "INVALID_CREDENTIALS", "E-Mail oder Passwort falsch.")


def _require_tenant_id(request: Request) -> int:
    """Für Logins, die nicht auf dem Super-Admin-Host laufen dürfen – die
    Middleware (app/middleware/tenant.py) hat für alle anderen Hosts bereits
    entweder request.state.tenant gesetzt oder mit 404 abgebrochen."""
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Unbekannte Subdomain.")
    return tenant.id


async def reject_second_device(db: AsyncSession, device: Device) -> None:
    """Weiteres Gerät mit dem Zugang eines gebundenen Tablets: höchstens einmal pro Stunde Warnung an
    Admin/HR und Eintrag im Audit-Protokoll (sonst würde ein dauernd probierendes Gerät fluten)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    if device.rejected_at is None or now - device.rejected_at > timedelta(hours=1):
        log_action(
            db, tenant_id=device.tenant_id, actor_account_id=None,
            action=AuditAction.DEVICE_LOGIN_REJECTED, entity_type="device", entity_id=device.id,
            detail=f"Weiteres Gerät mit dem Zugang von Tablet „{device.name}“ abgewiesen",
        )
        await notify_device_rejected(db, device)
    device.rejected_at = now
    await db.commit()


@router.post("/device/login", response_model=DeviceLoginResponse)
async def device_login(
    request: Request, payload: DeviceLoginRequest, db: AsyncSession = Depends(get_db)
) -> DeviceLoginResponse:
    tenant_id = _require_tenant_id(request)
    result = await db.execute(
        select(Device).where(Device.tenant_id == tenant_id, Device.token_hash == token_hash(payload.device_token))
    )
    device = result.scalar_one_or_none()
    if device is None:
        # Per MDM registriert, aber noch nicht freigegeben: Gerät zeigt den Prüfcode und versucht es weiter.
        pending = await pending_enrollment_for_token(db, tenant_id, payload.device_token)
        if pending is not None and payload.installation_id and token_hash(payload.installation_id) == pending.installation_hash:
            verify_code = pending.verify_code
            await touch_pending_enrollment(db, pending)  # „wartet gerade“ in der Freigabeliste
            raise AppError(
                403,
                "DEVICE_PENDING",
                f"Dieses Gerät wartet auf Freigabe in der HR-Webapp unter „Tablets“. Prüfcode: {verify_code}",
            )
        raise AppError(401, "INVALID_DEVICE_TOKEN", "Unbekanntes Gerät.")

    # Ein Zugang = ein Tablet: Das erste Tablet mit Installations-ID bindet den Zugang; jedes andere
    # Gerät wird abgewiesen (Warnung an Admin/HR). Ältere Tablet-Versionen ohne ID dürfen nur, solange
    # noch nichts gebunden ist.
    installation = token_hash(payload.installation_id) if payload.installation_id else None
    if device.installation_hash is None:
        if installation is not None:
            device.installation_hash = installation
            device.bound_at = datetime.now(UTC).replace(tzinfo=None)
            # Ein noch offener QR-Code galt für den ungebundenen Eintrag – er darf das jetzt gebundene
            # Gerät nicht mehr verdrängen (wie bind_device).
            device.pairing_code_hash = None
            device.pairing_code_expires_at = None
    elif installation != device.installation_hash:
        await reject_second_device(db, device)
        raise AppError(
            401,
            "DEVICE_IN_USE",
            "Dieser Tablet-Zugang ist bereits auf einem anderen Gerät angemeldet. Zum Wechseln das Tablet in der "
            "HR-Webapp unter „Tablets“ neu koppeln.",
        )

    device.last_seen = datetime.now(UTC)
    await db.commit()

    token = create_token(
        subject=str(device.id),
        token_type="device",
        expires_delta=timedelta(hours=settings.jwt_device_token_expire_hours),
        # tv: Teil des Token-Hashes – nach neuem Koppeln/„Kopplung aufheben“ sind alte Sitzungen ungültig
        extra_claims={"location_id": device.location_id, "tenant_id": device.tenant_id, "tv": device.token_hash[:16]},
    )
    return DeviceLoginResponse(
        access_token=token,
        location_id=device.location_id,
        device_name=device.name,
        card_salt=card_salt(device.tenant_id),
        **(await device_kiosk_config(db, device)).model_dump(),
    )


@router.post("/device/enroll", response_model=DeviceEnrollResponse)
async def device_enroll(
    request: Request, payload: DeviceEnrollRequest, db: AsyncSession = Depends(get_db)
) -> DeviceEnrollResponse:
    """Selbstregistrierung per Registrierungsschlüssel aus der MDM-Start-URL (``#enroll=…``): bindet an
    einen vorbereiteten, noch nie benutzten Eintrag mit gleichem Gerätenamen oder legt eine Anfrage an,
    die Admin/HR freigeben. Ablauf und Regeln: app/services/device_enrollment.py."""
    tenant_id = _require_tenant_id(request)
    key = f"enroll:{_client_ip(request)}"
    rate_limiter.check_rate_limit(key, 10, 300, code="ENROLLMENT_LOCKED")
    try:
        return await enroll_device(
            db, tenant_id, payload.key, payload.installation_id, payload.name,
            user_agent=request.headers.get("user-agent"), client_ip=_client_ip(request),
        )
    except AppError as exc:
        if exc.code in ("ENROLLMENT_KEY_INVALID", "ENROLLMENT_KEY_EXPIRED"):
            rate_limiter.record_failure(key)
        raise


@router.post("/device/pair", response_model=DevicePairResponse)
async def device_pair(
    request: Request, payload: DevicePairRequest, db: AsyncSession = Depends(get_db)
) -> DevicePairResponse:
    """Tauscht einen kurzen Kopplungscode (Tablets → QR-Code) gegen das Geräte-Token; danach
    meldet sich das Tablet wie gewohnt mit dem Token an. Einmalig, läuft nach 15 Min. ab."""
    tenant_id = _require_tenant_id(request)
    key = f"pair:{tenant_id}"
    rate_limiter.check_rate_limit(key, 10, 300, code="PAIRING_LOCKED")
    device = (
        await db.execute(
            select(Device).where(
                Device.tenant_id == tenant_id, Device.pairing_code_hash == pairing_code_hash(payload.code)
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC).replace(tzinfo=None)
    if device is None or device.pairing_code_expires_at is None or device.pairing_code_expires_at < now:
        rate_limiter.record_failure(key)
        raise AppError(401, "PAIRING_CODE_INVALID", "Kopplungscode ungültig oder abgelaufen.")
    # Koppeln = neues Token für genau dieses Tablet: das alte Token und ein bisher gebundenes Gerät
    # sind danach ungültig (Tablet-Tausch, nur nach ausdrücklicher Bestätigung beim Erzeugen des Codes).
    installation = token_hash(payload.installation_id)
    replaced = device.installation_hash is not None and device.installation_hash != installation
    new_token = new_device_token()
    device.token_hash = token_hash(new_token)
    device.installation_hash = installation
    device.bound_at = datetime.now(UTC).replace(tzinfo=None)
    device.rejected_at = None
    device.pairing_code_hash = None
    device.pairing_code_expires_at = None
    log_action(
        db, tenant_id=tenant_id, actor_account_id=None, action=AuditAction.DEVICE_ENROLLMENT,
        entity_type="device", entity_id=device.id,
        detail=(
            f"Tablet „{device.name}“ per QR-Code mit einem anderen Gerät gekoppelt – das bisherige Gerät ist abgemeldet"
            if replaced
            else f"Tablet „{device.name}“ per QR-Code eingerichtet"
        ),
    )
    if replaced:
        await notify_device_replaced(db, device)
    await db.commit()
    return DevicePairResponse(device_token=new_token)


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """Ein Login für alle Konten (Verwaltung, Mitarbeiter, auf dem admin.-Host der Super-Admin)."""
    email = payload.email.lower()
    if getattr(request.state, "is_super_admin_host", False):
        stmt = select(Account).where(
            Account.tenant_id.is_(None), Account.role == HrRole.SUPER_ADMIN, func.lower(Account.email) == email
        )
    else:
        tenant_id = _require_tenant_id(request)
        stmt = select(Account).where(Account.tenant_id == tenant_id, func.lower(Account.email) == email)

    _check_login_allowed(request, payload.email)
    account = (await db.execute(stmt)).scalar_one_or_none()
    if account is None or not account_can_sign_in(account) or not verify_password(payload.password, account.password_hash):
        raise _login_failed(request, payload.email)

    rate_limiter.reset(_login_keys(request, payload.email)[0])
    if account.email_verification_pending:
        # Erst nach richtigem Passwort verraten; den Bestätigungslink gibt es dabei erneut.
        tenant = await db.get(Tenant, account.tenant_id)
        await send_verification_mail(db, tenant, account)
        raise AppError(
            403,
            "EMAIL_NOT_VERIFIED",
            "Bitte bestätige zuerst deine E-Mail-Adresse – wir haben dir den Link (erneut) geschickt.",
        )
    if account.totp_enabled_at is not None:
        return LoginResponse(two_factor="required", challenge_token=two_factor_service.create_challenge(account, "verify"))
    if await two_factor_service.two_factor_required(db, account):
        return LoginResponse(two_factor="setup", challenge_token=two_factor_service.create_challenge(account, "setup"))
    return LoginResponse(**(await complete_login(db, account)).model_dump())


@router.post("/login/2fa", response_model=TokenResponse)
async def login_two_factor(
    request: Request, payload: TwoFactorLoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Zweiter Schritt: Code aus der Authenticator-App oder ein Wiederherstellungscode."""
    account = await two_factor_service.read_challenge(db, request, payload.challenge_token, "verify")
    used_recovery = two_factor_service.verify_code(account, payload.code)
    detail = "Anmeldung mit Wiederherstellungscode" if used_recovery else "Anmeldung (Zwei-Faktor)"
    return await complete_login(db, account, detail)


async def complete_login(db: AsyncSession, account: Account, detail: str = "Anmeldung") -> TokenResponse:
    """Anmeldung im Audit-Protokoll festhalten (nicht beim Super-Admin) und Tokens ausgeben. Committet."""
    if account.tenant_id is not None:
        log_action(
            db, tenant_id=account.tenant_id, actor_account_id=account.id,
            action=AuditAction.LOGIN, entity_type="account", entity_id=account.id, detail=detail,
        )
    await db.commit()
    return _issue_token_pair(account)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    claims = decode_token(payload.refresh_token)
    if claims.get("type") != "account_refresh":
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Refresh-Token.")

    account = await db.get(Account, int(claims["sub"]))
    if (
        account is None
        or not account_can_sign_in(account)
        or not _matches_request_tenant(request, account.tenant_id, account.role == HrRole.SUPER_ADMIN)
        or claims.get("pwv") != session_fingerprint(account)
    ):
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Refresh-Token.")

    return _issue_token_pair(account)


def _matches_request_tenant(request: Request, row_tenant_id: int | None, is_super_admin: bool) -> bool:
    if is_super_admin:
        return getattr(request.state, "is_super_admin_host", False)
    tenant = getattr(request.state, "tenant", None)
    return tenant is not None and row_tenant_id == tenant.id


def _issue_token_pair(account: Account) -> TokenResponse:
    """Claims für die Anzeige in der Webapp (role, emp, payroll, perms) – geprüft wird immer im Backend."""
    access = create_token(
        subject=str(account.id),
        token_type="account_access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        extra_claims={
            "role": account.role.value if account.role else None,
            "emp": account.employee_id,
            "payroll": Actor(account=account).has_payroll_access,
            # Eigene Rolle: {Bereich: Stufe} für Navigation und Seitenschutz der Webapp; null = keine
            "perms": (
                {area.value: level.value for area, level in permissions.items()}
                if (permissions := account_custom_permissions(account)) is not None
                else None
            ),
            "tenant_id": account.tenant_id,
            "pwv": session_fingerprint(account),
        },
    )
    refresh_token = create_token(
        subject=str(account.id),
        token_type="account_refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        extra_claims={"pwv": session_fingerprint(account)},
    )
    return TokenResponse(access_token=access, refresh_token=refresh_token)


# --- Passwort selbst ändern / vergessen ----------------------------------------------------

_PW_CHANGE_LIMIT = 5
_PW_RESET_MAIL_LIMIT = 3  # Links je E-Mail-Adresse und Stunde
_PW_RESET_IP_LIMIT = 10  # Anfragen je IP und Stunde
_HOUR = 3600


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Eigenes Passwort ändern (jedes Konto inkl. Super-Admin). Alle anderen Sitzungen enden
    (Passwort-Fingerabdruck im Token); diese bekommt ein neues Token-Paar."""
    principal = actor.account
    if principal is None:
        raise AppError(403, "ACCOUNT_REQUIRED", "Nur für angemeldete Personen.")
    key = f"pwchange:{principal.id}"
    rate_limiter.check_rate_limit(key, _PW_CHANGE_LIMIT, _LOGIN_WINDOW)
    if principal.password_hash is None or not verify_password(payload.current_password, principal.password_hash):
        rate_limiter.record_failure(key)
        raise AppError(400, "PASSWORD_WRONG", "Das aktuelle Passwort stimmt nicht.")
    if verify_password(payload.new_password, principal.password_hash):
        raise AppError(400, "PASSWORD_UNCHANGED", "Das neue Passwort muss sich vom bisherigen unterscheiden.")
    principal.password_hash = hash_password(payload.new_password)
    await db.commit()
    rate_limiter.reset(key)
    return _issue_token_pair(principal)


_RESET_ANSWER = {"detail": "Wenn es ein Konto mit dieser E-Mail-Adresse gibt, haben wir dir einen Link geschickt."}


@router.post("/password-reset/request", status_code=202)
async def request_password_reset(
    request: Request, payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """"Passwort vergessen": Link (1 Stunde gültig) an die Login-E-Mail – nur mit Mailversand
    (eigener SMTP der Firma oder Plattform). Antwortet immer gleich, damit sich nicht
    herausfinden lässt, welche Adressen ein Konto haben."""
    tenant_id = _require_tenant_id(request)
    ip_key = f"pwreset-ip:{_client_ip(request)}"
    rate_limiter.check_rate_limit(ip_key, _PW_RESET_IP_LIMIT, _HOUR)
    rate_limiter.record_failure(ip_key)
    email = payload.email.lower()
    mail_key = f"pwreset:{tenant_id}:{email}"
    try:
        rate_limiter.check_rate_limit(mail_key, _PW_RESET_MAIL_LIMIT, _HOUR)
    except AppError:
        return _RESET_ANSWER
    config = await resolve_smtp_config(db, tenant_id)
    if config is None:
        return _RESET_ANSWER

    account = await db.scalar(select(Account).where(Account.tenant_id == tenant_id, func.lower(Account.email) == email))
    if account is None or not account_can_sign_in(account):
        return _RESET_ANSWER

    raw = await issue_token(
        db, tenant_id=tenant_id, purpose=AccountTokenPurpose.PASSWORD_RESET, ttl=PASSWORD_RESET_TTL, account=account
    )
    await db.commit()
    rate_limiter.record_failure(mail_key)
    host = request.headers.get("host") or request.url.netloc
    link = f"{request.url.scheme}://{host}/passwort-zuruecksetzen#token={raw}"
    await send_email(
        account.email,
        "HR3000 – Passwort zurücksetzen",
        (
            "Hallo,\n\nfür dein HR3000-Konto wurde ein neues Passwort angefordert.\n"
            "Mit diesem Link legst du es fest (1 Stunde gültig, nur einmal verwendbar):\n\n"
            f"{link}\n\n"
            "Wenn du das nicht warst, ignoriere diese E-Mail – dein Passwort bleibt unverändert.\n"
        ),
        config=config,
    )
    return _RESET_ANSWER


@router.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    request: Request, payload: PasswordResetConfirm, db: AsyncSession = Depends(get_db)
) -> None:
    """Neues Passwort mit dem Link aus der E-Mail setzen. Alle bisherigen Sitzungen enden."""
    tenant_id = _require_tenant_id(request)
    ip_key = f"pwreset-confirm:{_client_ip(request)}"
    rate_limiter.check_rate_limit(ip_key, 20, _HOUR)
    token = await consume_token(db, payload.token, AccountTokenPurpose.PASSWORD_RESET)
    account = await db.get(Account, token.account_id) if token else None
    if token is None or token.tenant_id != tenant_id or account is None or not account_can_sign_in(account):
        await db.rollback()
        rate_limiter.record_failure(ip_key)
        raise AppError(400, "TOKEN_INVALID", "Der Link ist ungültig oder abgelaufen. Bitte fordere einen neuen an.")
    account.password_hash = hash_password(payload.new_password)
    # Wer den Link aus seinem Postfach nutzt, hat die Adresse damit auch bestätigt.
    account.email_verification_pending = False
    await db.commit()
