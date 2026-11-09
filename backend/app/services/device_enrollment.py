"""Tablets per MDM verteilen: Selbstregistrierung mit dem Registrierungsschlüssel eines Standorts.

Das MDM (Intune, Endpoint Central, …) setzt für eine Gerätegruppe die Start-URL der Kiosk-App auf
``…/#enroll=<schlüssel>&name=<gerätename>``. Beim ersten Start meldet sich das Gerät hier:

1. Ist diese Installation am Standort schon an einen Eintrag gebunden (Token am Gerät verloren, z. B.
   „Tablet zurücksetzen“), bekommt sie für diesen Eintrag ein neues Token.
2. Gibt es am Standort einen *noch nie benutzten* Eintrag mit diesem Gerätenamen im MDM, wird das
   Gerät ohne Freigabe daran gebunden (Admin/HR werden benachrichtigt).
3. Sonst entsteht eine offene Registrierung: Das Gerät bekommt ein Token, kann sich damit aber erst
   anmelden, wenn Admin/HR die Anfrage in der Webapp freigeben (Abgleich über den Prüfcode).

Der Schlüssel allein übernimmt also nie einen benutzten Eintrag – auch nicht nach „Kopplung aufheben“.
"""
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import AuditAction, Device, DeviceEnrollment, DeviceEnrollmentKey, Location
from app.schemas.device import DeviceEnrollResponse
from app.services.audit_service import log_action
from app.services.notification_service import notify_device_enrolled, notify_enrollment_requested
from app.services.pairing_service import new_device_token, new_verify_code, token_hash

# Offene Registrierungen je Standort – bremst Fluten mit einem abgeflossenen Schlüssel
PENDING_LIMIT_PER_LOCATION = 20


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_enrollment_key() -> str:
    """256 Bit, URL-tauglich (steht in der Start-URL hinter #enroll=)."""
    return secrets.token_urlsafe(32)


def device_name_matches(column, name: str):
    return func.lower(column) == name.lower()


async def _find_key(db: AsyncSession, tenant_id: int, key: str) -> DeviceEnrollmentKey:
    row = (
        await db.execute(
            select(DeviceEnrollmentKey).where(
                DeviceEnrollmentKey.tenant_id == tenant_id, DeviceEnrollmentKey.key_hash == token_hash(key)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError(
            401,
            "ENROLLMENT_KEY_INVALID",
            "Registrierungsschlüssel ungültig oder gesperrt – bitte in der HR-Webapp unter „Tablets“ prüfen.",
        )
    if row.expires_at is not None and row.expires_at < _now():
        raise AppError(
            401,
            "ENROLLMENT_KEY_EXPIRED",
            "Registrierungsschlüssel abgelaufen – in der HR-Webapp unter „Tablets“ einen neuen erzeugen und im MDM "
            "eintragen.",
        )
    return row


def bind_device(device: Device, installation_hash: str, new_token_hash: str) -> None:
    """Eintrag an genau diese Installation binden; altes Token und alte Sitzungen werden ungültig."""
    device.token_hash = new_token_hash
    device.installation_hash = installation_hash
    device.bound_at = _now()
    device.rejected_at = None
    device.pairing_code_hash = None
    device.pairing_code_expires_at = None


async def enroll_device(
    db: AsyncSession, tenant_id: int, key: str, installation_id: str, name: str | None
) -> DeviceEnrollResponse:
    key_row = await _find_key(db, tenant_id, key)
    now = _now()
    key_row.last_used_at = now
    location = await db.get(Location, key_row.location_id)
    installation = token_hash(installation_id)
    label = f"„{name}“" if name else "ohne Namen"

    # 1. Diese Installation ist am Standort schon gebunden (Token am Gerät verloren)
    device = (
        await db.execute(
            select(Device).where(
                Device.tenant_id == tenant_id,
                Device.location_id == key_row.location_id,
                Device.installation_hash == installation,
            )
        )
    ).scalar_one_or_none()
    prepared = False
    namesake: Device | None = None
    if device is None and name:
        namesake = (
            await db.execute(
                select(Device).where(
                    Device.tenant_id == tenant_id,
                    Device.location_id == key_row.location_id,
                    device_name_matches(Device.mdm_name, name),
                )
            )
        ).scalar_one_or_none()
        # 2. Vorbereiteter, noch nie benutzter Eintrag mit diesem Gerätenamen
        if namesake is not None and namesake.installation_hash is None and namesake.last_seen is None:
            device, prepared, namesake = namesake, True, None

    if device is not None:
        token = new_device_token()
        bind_device(device, installation, token_hash(token))
        stale = (
            await db.execute(
                select(DeviceEnrollment).where(
                    DeviceEnrollment.tenant_id == tenant_id, DeviceEnrollment.installation_hash == installation
                )
            )
        ).scalar_one_or_none()
        if stale is not None:
            await db.delete(stale)
        log_action(
            db, tenant_id=tenant_id, actor_account_id=None, action=AuditAction.DEVICE_ENROLLMENT,
            entity_type="device", entity_id=device.id,
            detail=(
                f"Gerät {label} hat sich per Registrierungsschlüssel als Tablet „{device.name}“ eingerichtet"
                if prepared
                else f"Tablet „{device.name}“ hat sich per Registrierungsschlüssel neu angemeldet (gleiches Gerät)"
            ),
        )
        if prepared:
            await notify_device_enrolled(db, device, name)
        await db.commit()
        return DeviceEnrollResponse(status="BOUND", device_token=token)

    # 3. Offene Registrierung (gleiche Installation: dieselbe Anfrage, gleicher Prüfcode)
    enrollment = (
        await db.execute(
            select(DeviceEnrollment).where(
                DeviceEnrollment.tenant_id == tenant_id, DeviceEnrollment.installation_hash == installation
            )
        )
    ).scalar_one_or_none()
    token = new_device_token()
    if enrollment is None:
        pending = (
            await db.execute(
                select(func.count(DeviceEnrollment.id)).where(
                    DeviceEnrollment.tenant_id == tenant_id, DeviceEnrollment.location_id == key_row.location_id
                )
            )
        ).scalar_one()
        if pending >= PENDING_LIMIT_PER_LOCATION:
            raise AppError(
                429,
                "TOO_MANY_PENDING_ENROLLMENTS",
                "Zu viele offene Registrierungen an diesem Standort – bitte in der HR-Webapp unter „Tablets“ "
                "freigeben oder ablehnen.",
            )
        enrollment = DeviceEnrollment(
            tenant_id=tenant_id,
            location_id=key_row.location_id,
            verify_code=new_verify_code(),
            installation_hash=installation,
            token_hash=token_hash(token),
            reported_name=name,
            last_seen_at=now,
        )
        db.add(enrollment)
        log_action(
            db, tenant_id=tenant_id, actor_account_id=None, action=AuditAction.DEVICE_ENROLLMENT,
            entity_type="location", entity_id=key_row.location_id,
            detail=f"Gerät {label} (Prüfcode {enrollment.verify_code}) möchte sich am Standort "
            f"„{location.name if location else '?'}“ einrichten – wartet auf Freigabe",
        )
        await notify_enrollment_requested(
            db, tenant_id, location.name if location else "?", name, enrollment.verify_code,
            namesake.name if namesake is not None else None,
        )
    else:
        enrollment.token_hash = token_hash(token)
        enrollment.location_id = key_row.location_id
        enrollment.reported_name = name
        enrollment.last_seen_at = now
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "ENROLLMENT_CONFLICT", "Bitte erneut versuchen.") from exc
    return DeviceEnrollResponse(status="PENDING", device_token=token, verify_code=enrollment.verify_code)


async def pending_enrollment_for_token(db: AsyncSession, tenant_id: int, device_token: str) -> DeviceEnrollment | None:
    return (
        await db.execute(
            select(DeviceEnrollment).where(
                DeviceEnrollment.tenant_id == tenant_id, DeviceEnrollment.token_hash == token_hash(device_token)
            )
        )
    ).scalar_one_or_none()
