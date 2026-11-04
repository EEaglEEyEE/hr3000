import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, Field

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Device, Employee, Location
from app.schemas.device import (
    CardRegistrationRequest,
    DeviceCreateRequest,
    DeviceResponse,
    DeviceUpdateRequest,
    PairingCodeResponse,
    PinSetupRequest,
)
from app.services import rate_limiter
from app.services.audit_service import log_action
from app.services.auth_service import hash_password, verify_password
from app.services.pairing_service import PAIRING_CODE_TTL, new_pairing_code, pairing_code_hash
from app.services.platform_domain import kiosk_url_for_host
from app.schemas.auth import KioskConfigResponse
from app.services.settings_service import device_kiosk_config, get_or_create_settings

router = APIRouter(tags=["devices"])


def _generate_device_token() -> str:
    return secrets.token_urlsafe(24)


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    location_id: int | None = Query(default=None),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceResponse]:
    stmt = select(Device).where(Device.tenant_id == actor.tenant_id)
    if location_id is not None:
        stmt = stmt.where(Device.location_id == location_id)
    stmt = stmt.order_by(Device.name.asc())

    result = await db.execute(stmt)
    return [DeviceResponse.model_validate(d) for d in result.scalars().all()]


@router.post("/devices", response_model=DeviceResponse, status_code=201)
async def create_device(
    payload: DeviceCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    location = await db.get(Location, payload.location_id)
    if location is None or location.tenant_id != actor.tenant_id:
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")

    device = Device(
        tenant_id=actor.tenant_id,
        location_id=payload.location_id,
        name=payload.name,
        device_token=_generate_device_token(),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    payload: DeviceUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    device = await db.get(Device, device_id)
    if device is None or device.tenant_id != actor.tenant_id:
        raise AppError(404, "DEVICE_NOT_FOUND", "Gerät nicht gefunden.")

    if payload.location_id is not None:
        location = await db.get(Location, payload.location_id)
        if location is None or location.tenant_id != actor.tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
        device.location_id = payload.location_id
    if payload.name is not None:
        device.name = payload.name
    if payload.regenerate_token:
        device.device_token = _generate_device_token()
        device.pairing_code_hash = None
        device.pairing_code_expires_at = None
    if payload.theme is not None:
        device.theme = None if payload.theme == "DEFAULT" else payload.theme
    if payload.screen_hours_mode is not None:
        # DEFAULT = Spalte NULL (wie Mandant); Zeiten nur bei CUSTOM.
        custom = payload.screen_hours_mode == "CUSTOM"
        device.screen_hours_mode = None if payload.screen_hours_mode == "DEFAULT" else payload.screen_hours_mode
        device.screen_on_from = payload.screen_on_from if custom else None
        device.screen_on_until = payload.screen_on_until if custom else None

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "DEVICE_TOKEN_COLLISION", "Bitte erneut versuchen.") from exc

    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await db.get(Device, device_id)
    if device is None or device.tenant_id != actor.tenant_id:
        raise AppError(404, "DEVICE_NOT_FOUND", "Gerät nicht gefunden.")

    await db.delete(device)
    await db.commit()


class KioskAdminPinRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


@router.post("/devices/verify-admin-pin", status_code=204)
async def verify_kiosk_admin_pin(
    payload: KioskAdminPinRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Das Tablet fragt vor dem Zurücksetzen die Kiosk-Admin-PIN des Mandanten ab
    (Einstellungen). Ohne hinterlegte PIN ist kein Zurücksetzen am Gerät möglich."""
    if actor.device is None:
        raise AppError(403, "DEVICE_REQUIRED", "Nur für Kiosk-Geräte.")
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not settings_row.kiosk_admin_pin_hash:
        raise AppError(409, "ADMIN_PIN_NOT_SET", "Es ist keine Kiosk-Admin-PIN festgelegt (HR-Webapp → Einstellungen).")
    key = f"kiosk-admin-pin:{actor.device.id}"
    rate_limiter.check_rate_limit(key, 5, 300, code="PIN_LOCKED")
    if not verify_password(payload.pin, settings_row.kiosk_admin_pin_hash):
        rate_limiter.record_failure(key)
        raise AppError(401, "PIN_INVALID", "Admin-PIN falsch.")
    rate_limiter.reset(key)


@router.get("/device/config", response_model=KioskConfigResponse)
async def get_kiosk_config(
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> KioskConfigResponse:
    """Das Tablet lädt seine Einstellungen regelmäßig nach – Änderungen wirken ohne Neuanmeldung."""
    if actor.device is None:
        raise AppError(403, "DEVICE_REQUIRED", "Nur für Kiosk-Geräte.")
    return await device_kiosk_config(db, actor.device)


@router.post("/devices/{device_id}/pairing-code", response_model=PairingCodeResponse)
async def create_pairing_code(
    device_id: int,
    request: Request,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PairingCodeResponse:
    """Kurzer Code (15 Min., einmalig) zum Einrichten eines Tablets ohne das lange Token abzutippen."""
    device = await db.get(Device, device_id)
    if device is None or device.tenant_id != actor.tenant_id:
        raise AppError(404, "DEVICE_NOT_FOUND", "Gerät nicht gefunden.")
    code = new_pairing_code()
    device.pairing_code_hash = pairing_code_hash(code)
    device.pairing_code_expires_at = datetime.now(UTC).replace(tzinfo=None) + PAIRING_CODE_TTL
    await db.commit()
    host = request.headers.get("host") or request.url.netloc
    return PairingCodeResponse(
        code=code,
        expires_at=device.pairing_code_expires_at,
        kiosk_url=kiosk_url_for_host(host, request.url.scheme),
    )


@router.post("/device/register-card", status_code=204)
async def register_own_card(
    payload: CardRegistrationRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mitarbeiter registriert am Kiosk-Tablet seinen eigenen Chip: Bestätigung mit dem eigenen PIN,
    danach ersetzt der Chip den bisherigen. Nur, wenn der Mandant das erlaubt (Einstellungen → Kiosk)."""
    if actor.device is None:
        raise AppError(403, "DEVICE_REQUIRED", "Nur für Kiosk-Geräte.")
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not (settings_row.kiosk_rfid_enabled and settings_row.kiosk_card_self_registration):
        raise AppError(403, "CARD_SELF_REGISTRATION_DISABLED", "Chips können hier nicht selbst registriert werden.")
    employee = await db.get(Employee, payload.employee_id)
    if (
        employee is None
        or employee.tenant_id != actor.tenant_id
        or not employee.active
        or employee.location_id != actor.device.location_id
    ):
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if not employee.has_pin:
        raise AppError(400, "PIN_NOT_CONFIGURED", "Für diesen Mitarbeiter ist kein PIN hinterlegt – bitte bei HR melden.")
    pin_key = f"pin:{actor.tenant_id}:{employee.id}"
    rate_limiter.check_rate_limit(pin_key, 5, 300, code="PIN_LOCKED")
    if not verify_password(payload.pin, employee.pin_hash):
        rate_limiter.record_failure(pin_key)
        raise AppError(401, "PIN_INVALID", "PIN falsch.")
    rate_limiter.reset(pin_key)

    taken = (
        await db.execute(
            select(Employee.id).where(
                Employee.tenant_id == actor.tenant_id, Employee.nfc_uid == payload.nfc_uid, Employee.id != employee.id
            )
        )
    ).first()
    if taken is not None:
        raise AppError(409, "CARD_IN_USE", "Dieser Chip ist schon einem anderen Mitarbeiter zugeordnet.")

    replaced = employee.nfc_uid is not None
    employee.nfc_uid = payload.nfc_uid
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=None,
        actor_employee_id=employee.id,
        action=AuditAction.EMPLOYEE_CARD_REGISTERED,
        entity_type="employee",
        entity_id=employee.id,
        detail=(
            f"Chip …{payload.nfc_uid[-4:]} am Tablet „{actor.device.name}“ selbst registriert"
            f"{' (ersetzt bisherigen Chip)' if replaced else ''}"
        ),
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "CARD_IN_USE", "Dieser Chip ist schon einem anderen Mitarbeiter zugeordnet.") from exc


@router.post("/device/setup-pin", status_code=204)
async def setup_own_pin(
    payload: PinSetupRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Erstes Stempeln ohne PIN: der Mitarbeiter legt seinen PIN am Tablet selbst fest. Nur solange
    noch keiner hinterlegt ist – einen vergessenen PIN setzt HR zurück (dann geht es hier erneut)
    oder vergibt selbst einen. Abschaltbar unter Einstellungen → Kiosk."""
    if actor.device is None:
        raise AppError(403, "DEVICE_REQUIRED", "Nur für Kiosk-Geräte.")
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not settings_row.kiosk_pin_self_setup:
        raise AppError(403, "PIN_SELF_SETUP_DISABLED", "Der PIN wird von HR vergeben – bitte bei HR melden.")
    # Bremst massenhaftes Festlegen fremder PINs an einem Gerät.
    key = f"pin-setup:{actor.device.id}"
    rate_limiter.check_rate_limit(key, 20, 3600, code="TOO_MANY_ATTEMPTS")
    employee = await db.get(Employee, payload.employee_id)
    if (
        employee is None
        or employee.tenant_id != actor.tenant_id
        or not employee.active
        or employee.location_id != actor.device.location_id
    ):
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if employee.has_pin:
        raise AppError(409, "PIN_ALREADY_SET", "Es ist bereits ein PIN hinterlegt – bei Bedarf setzt HR ihn zurück.")
    rate_limiter.record_failure(key)
    employee.pin_hash = hash_password(payload.pin)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=None,
        actor_employee_id=employee.id,
        action=AuditAction.EMPLOYEE_PIN_SET_AT_KIOSK,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"PIN am Tablet „{actor.device.name}“ selbst festgelegt",
    )
    await db.commit()
