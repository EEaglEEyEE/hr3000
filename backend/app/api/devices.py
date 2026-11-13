from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, Field

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Device, DeviceEnrollment, DeviceEnrollmentKey, Employee, Location
from app.schemas.device import (
    CardRegistrationRequest,
    DeviceCreateRequest,
    DeviceEnrollmentResponse,
    DeviceResponse,
    DeviceUpdateRequest,
    EnrollmentApproveRequest,
    EnrollmentCleanupResponse,
    EnrollmentKeyCreatedResponse,
    EnrollmentKeyCreateRequest,
    EnrollmentKeyResponse,
    PairingCodeRequest,
    PairingCodeResponse,
    PinSetupRequest,
)
from app.services import rate_limiter
from app.services.audit_service import log_action
from app.services.device_enrollment import (
    bind_device,
    describe_client,
    device_name_matches,
    enrollment_active,
    new_enrollment_key,
    purge_stale_enrollments,
    remove_inactive_enrollments,
)
from app.services.auth_service import hash_password, verify_password
from app.services.pairing_service import PAIRING_CODE_TTL, new_device_token, new_pairing_code, pairing_code_hash, token_hash
from app.services.platform_domain import kiosk_url_for_host
from app.schemas.auth import KioskConfigResponse
from app.services.settings_service import device_kiosk_config, get_or_create_settings

router = APIRouter(tags=["devices"])


def _generate_device_token() -> str:
    """Neues Token – nur als Hash gespeichert; das Tablet bekommt ein Token erst beim Koppeln."""
    return new_device_token()


async def _ensure_mdm_name_free(
    db: AsyncSession, tenant_id: int, name: str, exclude_device_id: int | None = None
) -> None:
    """Ein Gerätename im MDM gehört zu höchstens einem Tablet-Eintrag der Firma."""
    stmt = select(Device.id).where(Device.tenant_id == tenant_id, device_name_matches(Device.mdm_name, name))
    if exclude_device_id is not None:
        stmt = stmt.where(Device.id != exclude_device_id)
    if (await db.execute(stmt)).first() is not None:
        raise AppError(409, "MDM_NAME_TAKEN", "Dieser Gerätename im MDM ist schon einem anderen Tablet zugeordnet.")


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

    if payload.mdm_name:
        await _ensure_mdm_name_free(db, actor.tenant_id, payload.mdm_name)
    device = Device(
        tenant_id=actor.tenant_id,
        location_id=payload.location_id,
        name=payload.name,
        token_hash=token_hash(_generate_device_token()),
        mdm_name=payload.mdm_name,
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
    if "mdm_name" in payload.model_fields_set:
        if payload.mdm_name:
            await _ensure_mdm_name_free(db, actor.tenant_id, payload.mdm_name, exclude_device_id=device.id)
        device.mdm_name = payload.mdm_name
    if payload.regenerate_token:
        # „Kopplung aufheben“: altes Token und Gerätebindung ungültig, laufende Sitzungen enden
        device.token_hash = token_hash(_generate_device_token())
        device.installation_hash = None
        device.bound_at = None
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


# --- Verteilung per MDM: Registrierungsschlüssel je Standort und offene Registrierungen -----------------


@router.get("/devices/enrollment-keys", response_model=list[EnrollmentKeyResponse])
async def list_enrollment_keys(
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentKeyResponse]:
    rows = (
        await db.execute(select(DeviceEnrollmentKey).where(DeviceEnrollmentKey.tenant_id == actor.tenant_id))
    ).scalars().all()
    return [EnrollmentKeyResponse.model_validate(row) for row in rows]


@router.post("/devices/enrollment-keys", response_model=EnrollmentKeyCreatedResponse, status_code=201)
async def create_enrollment_key(
    payload: EnrollmentKeyCreateRequest,
    request: Request,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> EnrollmentKeyCreatedResponse:
    """Neuer Schlüssel für einen Standort – ersetzt einen vorhandenen sofort (der alte gilt nicht mehr).
    Der Schlüssel wird nur in dieser Antwort gezeigt; gespeichert ist nur sein Hash."""
    location = await db.get(Location, payload.location_id)
    if location is None or location.tenant_id != actor.tenant_id:
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
    existing = (
        await db.execute(select(DeviceEnrollmentKey).where(DeviceEnrollmentKey.location_id == location.id))
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()
    key = new_enrollment_key()
    now = datetime.now(UTC).replace(tzinfo=None)
    row = DeviceEnrollmentKey(
        tenant_id=actor.tenant_id,
        location_id=location.id,
        key_hash=token_hash(key),
        created_at=now,
        created_by_account_id=actor.account_id,
        expires_at=now + timedelta(days=payload.valid_days) if payload.valid_days else None,
    )
    db.add(row)
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.DEVICE_ENROLLMENT,
        entity_type="location", entity_id=location.id,
        detail=f"Registrierungsschlüssel für Standort „{location.name}“ {'erneuert' if existing else 'erzeugt'} "
        f"({f'{payload.valid_days} Tage gültig' if payload.valid_days else 'unbefristet'})",
    )
    await db.commit()
    await db.refresh(row)
    host = request.headers.get("host") or request.url.netloc
    kiosk_url = kiosk_url_for_host(host, request.url.scheme)
    return EnrollmentKeyCreatedResponse(
        location_id=row.location_id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=None,
        key=key,
        enroll_url=f"{kiosk_url}#enroll={key}" if kiosk_url else None,
    )


@router.delete("/devices/enrollment-keys/{location_id}", status_code=204)
async def delete_enrollment_key(
    location_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Schlüssel sperren: Neue Geräte können sich damit nicht mehr registrieren. Eingerichtete Tablets
    bleiben angemeldet."""
    row = (
        await db.execute(
            select(DeviceEnrollmentKey).where(
                DeviceEnrollmentKey.tenant_id == actor.tenant_id, DeviceEnrollmentKey.location_id == location_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError(404, "ENROLLMENT_KEY_NOT_FOUND", "Für diesen Standort gibt es keinen Registrierungsschlüssel.")
    location = await db.get(Location, location_id)
    await db.delete(row)
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.DEVICE_ENROLLMENT,
        entity_type="location", entity_id=location_id,
        detail=f"Registrierungsschlüssel für Standort „{location.name if location else location_id}“ gesperrt",
    )
    await db.commit()


@router.get("/devices/enrollments", response_model=list[DeviceEnrollmentResponse])
async def list_enrollments(
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceEnrollmentResponse]:
    """Geräte, die sich mit einem Registrierungsschlüssel gemeldet haben und auf Freigabe warten –
    wartende zuerst. Anfragen, deren Gerät sich seit 24 Stunden nicht gemeldet hat, verfallen hier."""
    if await purge_stale_enrollments(db, actor.tenant_id):
        await db.commit()
    rows = (
        await db.execute(
            select(DeviceEnrollment)
            .where(DeviceEnrollment.tenant_id == actor.tenant_id)
            .order_by(DeviceEnrollment.created_at.asc(), DeviceEnrollment.id.asc())
        )
    ).scalars().all()
    result = []
    for row in rows:
        conflict = None
        if row.reported_name:
            namesake = (
                await db.execute(
                    select(Device).where(
                        Device.tenant_id == actor.tenant_id, device_name_matches(Device.mdm_name, row.reported_name)
                    )
                )
            ).scalar_one_or_none()
            if namesake is not None and (namesake.installation_hash is not None or namesake.last_seen is not None):
                conflict = namesake.name
        result.append(
            DeviceEnrollmentResponse(
                id=row.id,
                location_id=row.location_id,
                reported_name=row.reported_name,
                verify_code=row.verify_code,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                conflict_device_name=conflict,
                active=enrollment_active(row),
                client=describe_client(row.user_agent),
                client_ip=row.client_ip,
            )
        )
    return sorted(result, key=lambda item: not item.active)  # stabil: je Gruppe nach Eingang


@router.post("/devices/enrollments/remove-inactive", response_model=EnrollmentCleanupResponse)
async def remove_inactive(
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> EnrollmentCleanupResponse:
    """Alle Anfragen entfernen, deren Gerät sich nicht mehr meldet. Wartende Geräte bleiben stehen."""
    removed = await remove_inactive_enrollments(db, actor.tenant_id, actor.account_id)
    await db.commit()
    return EnrollmentCleanupResponse(removed=removed)


async def _get_enrollment(db: AsyncSession, actor: Actor, enrollment_id: int) -> DeviceEnrollment:
    row = await db.get(DeviceEnrollment, enrollment_id)
    if row is None or row.tenant_id != actor.tenant_id:
        raise AppError(404, "ENROLLMENT_NOT_FOUND", "Registrierung nicht gefunden.")
    return row


@router.post("/devices/enrollments/{enrollment_id}/approve", response_model=DeviceResponse)
async def approve_enrollment(
    enrollment_id: int,
    payload: EnrollmentApproveRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Freigeben: als neues Tablet anlegen oder einen vorhandenen Eintrag desselben Standorts übernehmen
    (Tablet-Tausch – das bisherige Gerät ist danach abgemeldet). Das Gerät meldet sich innerhalb einer
    Minute von selbst an."""
    enrollment = await _get_enrollment(db, actor, enrollment_id)
    reported = enrollment.reported_name
    if payload.device_id is not None:
        device = await db.get(Device, payload.device_id)
        if device is None or device.tenant_id != actor.tenant_id:
            raise AppError(404, "DEVICE_NOT_FOUND", "Gerät nicht gefunden.")
        if device.location_id != enrollment.location_id:
            raise AppError(400, "LOCATION_MISMATCH", "Das Tablet gehört zu einem anderen Standort als der Schlüssel.")
        replaced = device.installation_hash is not None
    else:
        device = Device(
            tenant_id=actor.tenant_id,
            location_id=enrollment.location_id,
            name=payload.name or reported or f"Tablet {enrollment.verify_code}",
            token_hash=enrollment.token_hash,
        )
        db.add(device)
        await db.flush()
        replaced = False
    # Gerätename übernehmen, damit eine spätere Neuinstallation desselben Geräts zugeordnet werden kann
    if reported and not device.mdm_name:
        taken = (
            await db.execute(
                select(Device.id).where(
                    Device.tenant_id == actor.tenant_id,
                    device_name_matches(Device.mdm_name, reported),
                    Device.id != device.id,
                )
            )
        ).first()
        if taken is None:
            device.mdm_name = reported
    bind_device(device, enrollment.installation_hash, enrollment.token_hash)
    await db.delete(enrollment)
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.DEVICE_ENROLLMENT,
        entity_type="device", entity_id=device.id,
        detail=f"Registrierung von Gerät „{reported or 'ohne Namen'}“ (Prüfcode {enrollment.verify_code}) freigegeben "
        f"als Tablet „{device.name}“{' (ersetzt das bisherige Gerät)' if replaced else ''}",
    )
    await db.commit()
    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.delete("/devices/enrollments/{enrollment_id}", status_code=204)
async def reject_enrollment(
    enrollment_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Ablehnen: Das Token des Geräts wird ungültig. Startet es neu, meldet es sich erneut (neue Anfrage) –
    dauerhaft stoppt das nur der Entzug im MDM oder ein neuer Schlüssel."""
    enrollment = await _get_enrollment(db, actor, enrollment_id)
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.DEVICE_ENROLLMENT,
        entity_type="location", entity_id=enrollment.location_id,
        detail=f"Registrierung von Gerät „{enrollment.reported_name or 'ohne Namen'}“ (Prüfcode "
        f"{enrollment.verify_code}) abgelehnt",
    )
    await db.delete(enrollment)
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
    payload: PairingCodeRequest | None = None,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PairingCodeResponse:
    """Kurzer Code (15 Min., einmalig) zum Einrichten eines Tablets ohne das lange Token abzutippen.
    Ist das Tablet schon mit einem Gerät verbunden, nur mit replace_bound (Tablet-Tausch): sonst würde
    ein zweites Gerät den Eintrag übernehmen und das verbundene unbemerkt abmelden."""
    device = await db.get(Device, device_id)
    if device is None or device.tenant_id != actor.tenant_id:
        raise AppError(404, "DEVICE_NOT_FOUND", "Gerät nicht gefunden.")
    if device.installation_hash is not None and not (payload is not None and payload.replace_bound):
        raise AppError(
            409,
            "DEVICE_BOUND",
            f"Das Tablet „{device.name}“ ist schon mit einem Gerät verbunden. Ein QR-Code koppelt ein anderes Gerät "
            "und meldet das bisherige ab. Für ein zusätzliches Tablet bitte „Neues Tablet“ anlegen.",
        )
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
        actor_account_id=employee.account.id if employee.account is not None else None,
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
        actor_account_id=employee.account.id if employee.account is not None else None,
        action=AuditAction.EMPLOYEE_PIN_SET_AT_KIOSK,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"PIN am Tablet „{actor.device.name}“ selbst festgelegt",
    )
    await db.commit()
