from dataclasses import dataclass, field

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.db import get_db
from app.errors import AppError
from app.models import Account, Device, Employee, HrRole
from app.services import role_permissions
from app.services.auth_service import account_can_sign_in, decode_token, session_fingerprint
from app.services.role_permissions import Area, Level

bearer_scheme = HTTPBearer()


@dataclass
class Actor:
    """Wer die Anfrage stellt: ein Tablet (device) oder eine Person mit Konto (account). Das Konto hat
    ggf. eine Verwaltungsrolle und ggf. einen verknüpften Mitarbeiter („Mein Bereich“)."""

    device: Device | None = None
    account: Account | None = None
    # Konto mit eigener Rolle auf einer Route, die auch „Mein Bereich“ bedient, ohne das Recht für den
    # Bereich: gilt für diese Anfrage als reiner Mitarbeiter (role_permissions.Decision.SELF).
    self_only: bool = field(default=False, compare=False)

    @property
    def employee(self) -> Employee | None:
        return self.account.employee if self.account is not None else None

    @property
    def role(self) -> HrRole | None:
        if self.account is None or self.self_only:
            return None
        return self.account.role

    @property
    def custom_permissions(self) -> role_permissions.Permissions | None:
        """Rechte der eigenen Rolle; None = Konto ohne eigene Rolle (keine zusätzliche Einschränkung)."""
        return account_custom_permissions(self.account)

    def has_area(self, area: Area, level: Level = Level.VIEW) -> bool:
        """Darf das Konto den Bereich nutzen? Ohne eigene Rolle entscheidet die Rolle wie bisher (True)."""
        if self.self_only:
            return False
        permissions = self.custom_permissions
        return permissions is None or role_permissions.has_level(permissions, area, level)

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
        den eigenen Bereich (Unterstellte) beschränkt, siehe app/services/scope_service.py."""
        return self.role is not None and self.role != HrRole.SUPERVISOR

    @property
    def is_supervisor_level(self) -> bool:
        return self.role == HrRole.SUPERVISOR

    @property
    def is_admin_level(self) -> bool:
        return self.role == HrRole.ADMIN

    @property
    def has_payroll_access(self) -> bool:
        """Berechtigung „Vergütung & Lohn-Export“: Admins immer, volle HR nur mit Freigabe. Mit eigener
        Rolle entscheidet stattdessen deren Bereich „Vergütung & Lohn“ (ab Ansehen)."""
        return self._payroll(Level.VIEW)

    @property
    def can_edit_payroll(self) -> bool:
        """Lohndaten ändern bzw. Live-Lohndaten exportieren: wie has_payroll_access, mit eigener Rolle
        aber erst ab Stufe Bearbeiten."""
        return self._payroll(Level.EDIT)

    def _payroll(self, level: Level) -> bool:
        if self.is_admin_level:
            return True
        if not self.is_full_hr_level:
            return False
        permissions = self.custom_permissions
        if permissions is not None:
            return role_permissions.has_level(permissions, Area.PAYROLL, level)
        return bool(self.account.payroll_access)


def account_custom_permissions(account: Account | None) -> role_permissions.Permissions | None:
    """Eigene Rollen gelten nur für Rolle HR (Admins und Führungskräfte bekommen keine)."""
    if account is None or account.role != HrRole.HR or account.custom_role_id is None:
        return None
    role = account.custom_role
    # Verweis ohne Rolle darf es nicht geben (FK); falls doch: kein Zugriff statt voller Zugriff.
    return role_permissions.parse_permissions(role.permissions if role is not None else None)


def _enforce_custom_role(request: Request, actor: Actor) -> None:
    """Zentrale Prüfung für Konten mit eigener Rolle: Route → Bereich, Methode → Stufe
    (role_permissions.ROUTE_RULES). Nicht zugeordnete Routen sind verboten."""
    permissions = actor.custom_permissions
    if permissions is None:
        return
    route = request.scope.get("route")
    decision = role_permissions.decide(
        request.method, getattr(route, "path", None), permissions, has_employee=actor.employee is not None
    )
    if decision == role_permissions.Decision.SELF:
        actor.self_only = True
    elif decision == role_permissions.Decision.DENY:
        raise AppError(403, "ROLE_PERMISSION_REQUIRED", "Die zugewiesene Rolle erlaubt das nicht.")


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
        if account.employee is not None:
            # Rückverweis setzen: über Account.employee geladen, wäre employee.account sonst nicht geladen und
            # würde später im async-Kontext nachgeladen (MissingGreenlet), z. B. wenn die angemeldete Person
            # selbst als Führungskraft entscheidet oder den eigenen Datensatz abruft.
            set_committed_value(account.employee, "account", account)
        actor = Actor(account=account)
    else:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")

    _check_tenant_match(request, actor)
    _enforce_custom_role(request, actor)
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
    """Für Aktionen, die einem Supervisor bewusst NICHT erlaubt sind (Abteilungen/
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
