from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError
from app.models import Account, Device, Employee, HrRole
from app.services.auth_service import account_can_sign_in, decode_token, session_fingerprint

bearer_scheme = HTTPBearer()


@dataclass
class Actor:
    """Wer die Anfrage stellt: ein Tablet (device) oder eine Person mit Konto (account). Das Konto hat
    ggf. eine Verwaltungsrolle und ggf. einen verknüpften Mitarbeiter („Mein Bereich“)."""

    device: Device | None = None
    account: Account | None = None

    @property
    def employee(self) -> Employee | None:
        return self.account.employee if self.account is not None else None

    @property
    def role(self) -> HrRole | None:
        return self.account.role if self.account is not None else None

    @property
    def tenant_id(self) -> int | None:
        """None nur für den plattformweiten Super-Admin, siehe app/middleware/tenant.py."""
        if self.device is not None:
            return self.device.tenant_id
        if self.account is not None:
            return self.account.tenant_id
        return None

    @property
    def account_id(self) -> int | None:
        """Für alle „wer war das“-Spalten (*_account_id)."""
        return self.account.id if self.account is not None else None

    @property
    def is_super_admin(self) -> bool:
        return self.role == HrRole.SUPER_ADMIN

    @property
    def is_hr_level(self) -> bool:
        return self.role is not None

    @property
    def is_full_hr_level(self) -> bool:
        """ADMIN/HR/SUPER_ADMIN – im Gegensatz zu SUPERVISOR nicht auf
        eigene Teams beschränkt, siehe app/services/team_scope_service.py."""
        return self.role is not None and self.role != HrRole.SUPERVISOR

    @property
    def is_supervisor_level(self) -> bool:
        return self.role == HrRole.SUPERVISOR

    @property
    def is_admin_level(self) -> bool:
        return self.role == HrRole.ADMIN

    @property
    def has_payroll_access(self) -> bool:
        """Berechtigung „Vergütung & Lohn-Export“: Admins immer, volle HR nur mit Freigabe."""
        if self.is_admin_level:
            return True
        return self.is_full_hr_level and bool(self.account.payroll_access)


def _require_tenant_context(actor: Actor) -> None:
    """Mandantendaten gibt es nur im Kontext eines Mandanten. Der plattformweite
    Super-Admin (ohne tenant_id) verwaltet ausschließlich Mandanten (app/api/tenants.py)
    und darf diese Endpoints nicht nutzen – sie würden sonst mit tenant_id=None arbeiten."""
    if actor.tenant_id is None:
        raise AppError(403, "TENANT_CONTEXT_REQUIRED", "Dieser Zugang gehört keinem Mandanten.")


def _check_tenant_match(request: Request, actor: Actor) -> None:
    """Stellt sicher, dass der authentifizierte Actor zu der Subdomain passt,
    über die der Request kam (request.state.tenant, siehe
    app/middleware/tenant.py). Ein Mismatch liefert bewusst denselben 401 wie
    ein ungültiges Token – ein 403 würde verraten, dass der Account real ist,
    nur einem anderen Mandanten gehört (Existenz-Leak über Mandantengrenzen)."""
    if actor.is_super_admin:
        if not getattr(request.state, "is_super_admin_host", False):
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        return

    tenant = getattr(request.state, "tenant", None)
    if tenant is None or actor.tenant_id != tenant.id:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")


async def get_current_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Akzeptiert Tablet- und Konto-Token – z.B. für POST /punches, GET /overtime-balance."""
    payload = decode_token(credentials.credentials)
    token_type = payload.get("type")

    if token_type == "device":
        device = await db.get(Device, int(payload["sub"]))
        # tv: nach neuem Koppeln bzw. „Kopplung aufheben“ sind ältere Tablet-Sitzungen ungültig
        if device is None or payload.get("tv") != device.token_hash[:16]:
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        actor = Actor(device=device)
    elif token_type == "account_access":
        account = await db.get(Account, int(payload["sub"]))
        if account is None or not account_can_sign_in(account) or payload.get("pwv") != session_fingerprint(account):
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        actor = Actor(account=account)
    else:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")

    _check_tenant_match(request, actor)
    return actor


async def get_current_hr_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Für schreibende/verwaltende HR-Aktionen: Konto mit Verwaltungsrolle."""
    actor = await get_current_actor(request, credentials, db)
    if not actor.is_hr_level:
        raise AppError(403, "HR_PERMISSION_REQUIRED", "Keine HR-Berechtigung.")
    _require_tenant_context(actor)
    return actor


async def get_current_admin_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Für Admin-only Aktionen (z.B. HR-Berechtigungen vergeben): Konto mit Rolle ADMIN. Bewusst
    getrennt vom plattformweiten Super-Admin, siehe get_current_super_admin_principal."""
    actor = await get_current_actor(request, credentials, db)
    if not actor.is_admin_level:
        raise AppError(403, "ADMIN_PERMISSION_REQUIRED", "Nur für Administratoren.")
    return actor


async def get_current_payroll_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Vergütung, Zulagen, Lohnkosten, DATEV, Lohnarten und Beträge im Lohn-Export: Admins und HR
    mit Berechtigung „Vergütung & Lohn-Export“ (Actor.has_payroll_access)."""
    actor = await get_current_actor(request, credentials, db)
    if not actor.has_payroll_access:
        raise AppError(403, "PAYROLL_PERMISSION_REQUIRED", "Nur mit Berechtigung „Vergütung & Lohn-Export“.")
    return actor


async def get_current_full_hr_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Für Aktionen, die einem Supervisor bewusst NICHT erlaubt sind (Teams/
    Schichtvorlagen/Standard-Schichten verwalten) – ADMIN/HR/SUPER_ADMIN,
    siehe Actor.is_full_hr_level."""
    actor = await get_current_actor(request, credentials, db)
    if not actor.is_full_hr_level:
        raise AppError(403, "HR_PERMISSION_REQUIRED", "Keine HR-Berechtigung.")
    _require_tenant_context(actor)
    return actor


async def get_current_super_admin_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Für die Mandantenverwaltung (app/api/tenants.py) – ausschließlich der
    eine plattformweite Super-Admin, nicht Mandanten-Admins."""
    actor = await get_current_actor(request, credentials, db)
    if not actor.is_super_admin:
        raise AppError(403, "SUPER_ADMIN_PERMISSION_REQUIRED", "Nur für den Super-Admin.")
    return actor


async def get_current_device(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Device:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "device":
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
    device = await db.get(Device, int(payload["sub"]))
    if device is None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
    _check_tenant_match(request, Actor(device=device))
    return device


async def get_current_hr_or_self(
    employee_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Für read-only Ansichten, die sowohl HR-Level-Akteure (jeder Mitarbeiter)
    als auch der Mitarbeiter selbst (nur eigene Daten) sehen dürfen."""
    actor = await get_current_actor(request, credentials, db)

    if actor.device is not None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
    if actor.is_hr_level:
        return actor
    if actor.employee is not None and actor.employee.id == employee_id:
        return actor

    raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
