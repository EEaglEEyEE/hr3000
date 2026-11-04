from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.models import Device, Employee, HrRole, HrUser
from app.schemas.device import DevicePairRequest, DevicePairResponse
from app.schemas.auth import (
    DeviceLoginRequest,
    DeviceLoginResponse,
    EmployeeLoginRequest,
    HrLoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth_service import create_token, decode_token, password_fingerprint, verify_password
from app.services import rate_limiter
from app.services.pairing_service import pairing_code_hash
from app.services.settings_service import device_kiosk_config

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


@router.post("/device/login", response_model=DeviceLoginResponse)
async def device_login(
    request: Request, payload: DeviceLoginRequest, db: AsyncSession = Depends(get_db)
) -> DeviceLoginResponse:
    tenant_id = _require_tenant_id(request)
    result = await db.execute(
        select(Device).where(Device.tenant_id == tenant_id, Device.device_token == payload.device_token)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise AppError(401, "INVALID_DEVICE_TOKEN", "Unbekanntes Gerät.")

    device.last_seen = datetime.now(UTC)
    await db.commit()

    token = create_token(
        subject=str(device.id),
        token_type="device",
        expires_delta=timedelta(hours=settings.jwt_device_token_expire_hours),
        extra_claims={"location_id": device.location_id, "tenant_id": device.tenant_id},
    )
    return DeviceLoginResponse(
        access_token=token,
        location_id=device.location_id,
        device_name=device.name,
        **(await device_kiosk_config(db, device)).model_dump(),
    )


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
    device.pairing_code_hash = None
    device.pairing_code_expires_at = None
    await db.commit()
    return DevicePairResponse(device_token=device.device_token)


@router.post("/hr/login", response_model=TokenResponse)
async def hr_login(
    request: Request, payload: HrLoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    if getattr(request.state, "is_super_admin_host", False):
        stmt = select(HrUser).where(HrUser.role == HrRole.SUPER_ADMIN, HrUser.email == payload.email)
    else:
        tenant_id = _require_tenant_id(request)
        stmt = select(HrUser).where(HrUser.tenant_id == tenant_id, HrUser.email == payload.email)

    _check_login_allowed(request, payload.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _login_failed(request, payload.email)

    rate_limiter.reset(_login_keys(request, payload.email)[0])
    return _issue_token_pair(user)


@router.post("/hr/refresh", response_model=TokenResponse)
async def hr_refresh(
    request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    claims = decode_token(payload.refresh_token)
    if claims.get("type") != "refresh":
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Refresh-Token.")

    user = await db.get(HrUser, int(claims["sub"]))
    if (
        user is None
        or not _matches_request_tenant(request, user.tenant_id, user.role == HrRole.SUPER_ADMIN)
        or claims.get("pwv") != password_fingerprint(user.password_hash)
    ):
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Refresh-Token.")

    return _issue_token_pair(user)


@router.post("/employee/login", response_model=TokenResponse)
async def employee_login(
    request: Request, payload: EmployeeLoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    tenant_id = _require_tenant_id(request)
    _check_login_allowed(request, payload.email)
    result = await db.execute(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.login_email == payload.email)
    )
    employee = result.scalar_one_or_none()
    if (
        employee is None
        or not employee.active  # deaktivierte/ausgeschiedene/anonymisierte Mitarbeiter dürfen sich nicht mehr anmelden
        or employee.password_hash is None
        or not verify_password(payload.password, employee.password_hash)
    ):
        raise _login_failed(request, payload.email)

    rate_limiter.reset(_login_keys(request, payload.email)[0])
    return _issue_employee_token_pair(employee)


@router.post("/employee/refresh", response_model=TokenResponse)
async def employee_refresh(
    request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    claims = decode_token(payload.refresh_token)
    if claims.get("type") != "employee_refresh":
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Refresh-Token.")

    employee = await db.get(Employee, int(claims["sub"]))
    if (
        employee is None
        or not employee.active
        or not _matches_request_tenant(request, employee.tenant_id, False)
        or claims.get("pwv") != password_fingerprint(employee.password_hash)
    ):
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Refresh-Token.")

    return _issue_employee_token_pair(employee)


def _matches_request_tenant(request: Request, row_tenant_id: int | None, is_super_admin: bool) -> bool:
    if is_super_admin:
        return getattr(request.state, "is_super_admin_host", False)
    tenant = getattr(request.state, "tenant", None)
    return tenant is not None and row_tenant_id == tenant.id


def _issue_employee_token_pair(employee: Employee) -> TokenResponse:
    access = create_token(
        subject=str(employee.id),
        token_type="employee_access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        extra_claims={
            "hr_role": employee.hr_role.value if employee.hr_role else None,
            "pwv": password_fingerprint(employee.password_hash),
        },
    )
    refresh = create_token(
        subject=str(employee.id),
        token_type="employee_refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        extra_claims={"pwv": password_fingerprint(employee.password_hash)},
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


def _issue_token_pair(user: HrUser) -> TokenResponse:
    access = create_token(
        subject=str(user.id),
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        extra_claims={
            "role": user.role.value,
            "tenant_id": user.tenant_id,
            "pwv": password_fingerprint(user.password_hash),
        },
    )
    refresh = create_token(
        subject=str(user.id),
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        extra_claims={"pwv": password_fingerprint(user.password_hash)},
    )
    return TokenResponse(access_token=access, refresh_token=refresh)
