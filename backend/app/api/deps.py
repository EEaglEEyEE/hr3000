from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError
from app.models import Device, Employee, HrRole, HrUser
from app.services.auth_service import decode_token, password_fingerprint

bearer_scheme = HTTPBearer()


@dataclass
class Actor:
    """Wer die Anfrage stellt: Kiosk-Gerät, HR-User (eigener Account) oder
    Mitarbeiter (Self-Service, ggf. mit hr_role für vollen HR-Zugriff über
    dieselben Zugangsdaten)."""

    device: Device | None = None
    hr_user: HrUser | None = None
    employee: Employee | None = None

    @property
    def tenant_id(self) -> int | None:
        """None nur für den plattformweiten Super-Admin (HrUser.tenant_id
        ist dann ebenfalls None), siehe app/middleware/tenant.py."""
        if self.device is not None:
            return self.device.tenant_id
        if self.hr_user is not None:
            return self.hr_user.tenant_id
        if self.employee is not None:
            return self.employee.tenant_id
        return None

    @property
    def is_super_admin(self) -> bool:
        return self.hr_user is not None and self.hr_user.role == HrRole.SUPER_ADMIN

    @property
    def is_hr_level(self) -> bool:
        return self.hr_user is not None or (self.employee is not None and self.employee.hr_role is not None)

    @property
    def is_full_hr_level(self) -> bool:
        """ADMIN/HR/SUPER_ADMIN – im Gegensatz zu SUPERVISOR nicht auf
        eigene Teams beschränkt, siehe app/services/team_scope_service.py."""
        role = self.hr_user.role if self.hr_user is not None else None
        if self.employee is not None:
            role = self.employee.hr_role
        return role is not None and role != HrRole.SUPERVISOR

    @property
    def is_supervisor_level(self) -> bool:
        role = self.hr_user.role if self.hr_user is not None else None
        if self.employee is not None:
            role = self.employee.hr_role
        return role == HrRole.SUPERVISOR

    @property
    def is_admin_level(self) -> bool:
        if self.hr_user is not None:
            return self.hr_user.role == HrRole.ADMIN
        if self.employee is not None:
            return self.employee.hr_role == HrRole.ADMIN
        return False

    @property
    def has_payroll_access(self) -> bool:
        """Berechtigung „Vergütung & Lohn-Export“: Admins immer, volle HR nur mit Freigabe."""
        if self.is_admin_level:
            return True
        if not self.is_full_hr_level:
            return False
        if self.hr_user is not None:
            return bool(self.hr_user.payroll_access)
        return self.employee is not None and bool(self.employee.hr_payroll_access)

    @property
    def audit_hr_user_id(self) -> int | None:
        """Für created_by-Spalten: nur gesetzt, wenn ein klassischer HrUser-Account
        agiert hat."""
        return self.hr_user.id if self.hr_user is not None else None

    @property
    def audit_employee_id(self) -> int | None:
        """Für created_by_employee_id-Spalten: nur gesetzt, wenn ein Mitarbeiter
        mit hr_role (statt eines separaten HrUser-Accounts) agiert hat."""
        if self.employee is not None and self.employee.hr_role is not None:
            return self.employee.id
        return None


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
    """Akzeptiert Device-, HR-Access- und Mitarbeiter-Token (Self-Service oder
    mit hr_role) – z.B. für POST /punches, GET /overtime-balance."""
    payload = decode_token(credentials.credentials)
    token_type = payload.get("type")

    if token_type == "device":
        device = await db.get(Device, int(payload["sub"]))
        if device is None:
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        actor = Actor(device=device)
    elif token_type == "access":
        user = await db.get(HrUser, int(payload["sub"]))
        if user is None or payload.get("pwv") != password_fingerprint(user.password_hash):
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        actor = Actor(hr_user=user)
    elif token_type == "employee_access":
        employee = await db.get(Employee, int(payload["sub"]))
        if (
            employee is None
            or not employee.active
            or payload.get("pwv") != password_fingerprint(employee.password_hash)
        ):
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        actor = Actor(employee=employee)
    else:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")

    _check_tenant_match(request, actor)
    return actor


async def get_current_hr_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Für schreibende/verwaltende HR-Aktionen: HrUser-Account ODER Mitarbeiter
    mit hr_role. Ersetzt die frühere reine HrUser-Prüfung, damit ein Mitarbeiter
    mit erteilter HR-Berechtigung dieselben Endpoints mit seinem einen Login
    nutzen kann."""
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
    """Für Admin-only Aktionen (z.B. HR-Berechtigungen vergeben): HrUser mit
    role=ADMIN ODER Mitarbeiter mit hr_role=ADMIN. Bewusst getrennt vom
    plattformweiten Super-Admin, siehe get_current_super_admin_principal."""
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
    als auch ein Mitarbeiter per Self-Service-Login (nur eigene Daten) sehen
    dürfen."""
    actor = await get_current_actor(request, credentials, db)

    if actor.device is not None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
    if actor.is_hr_level:
        return actor
    if actor.employee is not None and actor.employee.id == employee_id:
        return actor

    raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
