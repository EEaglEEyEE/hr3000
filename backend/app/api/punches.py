import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Employee, Punch, PunchSource, PunchType
from app.schemas.common import normalize_card_uid
from app.schemas.punch import OwnPunchRequest, PunchCorrectionRequest, PunchCreateRequest, PunchResponse
from app.services.audit_service import log_action
from app.services import rate_limiter
from app.services.auth_service import verify_password
from app.services.settings_service import get_or_create_settings
from app.services.timesheet_service import (
    DayCalculation,
    balance_as_of,
    employee_timezone,
    local_date,
    maybe_auto_insert_break,
    recalculate_day,
    shift_day_of,
)
from app.services.team_scope_service import ensure_employee_visible
from app.services.ws_manager import manager
from app.services.period_service import ensure_period_open

router = APIRouter(tags=["punches"])


async def _broadcast_balance_update(
    db: AsyncSession, employee: Employee, calculation: DayCalculation
) -> None:
    """Sendet den aktuellen Gleitzeitsaldo nach jeder abgeschlossenen Stempelung an
    alle verbundenen Kiosks des Standorts, siehe docs/konzept.md Abschnitt 5."""
    message: dict = {
        "type": "OVERTIME_BALANCE_UPDATED",
        "employee_id": employee.id,
        "work_date": calculation.work_date.isoformat(),
        "status": calculation.status.value,
        "actual_minutes": calculation.actual_minutes,
    }

    # Saldo nur mitsenden, wenn der Mandant ihn am Tablet zeigt (Datenschutz am Gemeinschaftsgerät).
    if (await get_or_create_settings(db, employee.tenant_id)).kiosk_show_balance:
        # recalculate_day hat das Konto gerade aktualisiert – kein erneutes Nachrechnen nötig.
        info = await balance_as_of(db, employee, refresh=False)
        row = info.last_row
        if row is not None and row.balance_date == calculation.work_date:
            message["daily_target_minutes"] = row.daily_target_minutes
            message["daily_delta_minutes"] = row.daily_delta_minutes
        message["running_balance_minutes"] = info.total_minutes

    await manager.broadcast(employee.location_id, message)


@router.post("/punches", response_model=PunchResponse, status_code=201)
async def create_punch(
    payload: PunchCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> PunchResponse:
    # idempotency_key ist eine client-generierte UUID, absichtlich nicht
    # mandantenscoped geprüft (Kollision über Mandanten hinweg ist praktisch
    # ausgeschlossen und eine globale Prüfung ist hier die sicherere Variante).
    existing = await db.execute(
        select(Punch).where(Punch.idempotency_key == payload.idempotency_key)
    )
    if existing.scalar_one_or_none() is not None:
        raise AppError(409, "PUNCH_DUPLICATE", "Diese Stempelung wurde bereits erfasst.")

    employee = await db.get(Employee, payload.employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")

    if actor.device is not None:
        settings_row = await get_or_create_settings(db, actor.tenant_id)
        card_uid = normalize_card_uid(payload.nfc_uid)
        card_ok = (
            settings_row.kiosk_rfid_enabled
            and card_uid is not None
            and employee.nfc_uid is not None
            and card_uid == normalize_card_uid(employee.nfc_uid)
        )
        _ensure_punch_type_enabled(settings_row, payload.punch_type)
        if settings_row.rfid_required and not card_ok:
            raise AppError(400, "RFID_REQUIRED", "Stempeln ist nur mit dem eigenen Chip möglich.")
        if settings_row.require_pin_for_punch and not card_ok:
            # Eine passende Karte ersetzt den PIN – sie ist die stärkere Authentifizierung.
            if not employee.has_pin:
                raise AppError(400, "PIN_NOT_CONFIGURED", "Für diesen Mitarbeiter ist kein PIN hinterlegt.")
            pin_key = f"pin:{actor.tenant_id}:{employee.id}"
            # 4-stellige PINs sind schnell durchprobiert: nach 5 Fehlversuchen
            # in 5 Minuten wird der Mitarbeiter am Tablet kurz gesperrt.
            rate_limiter.check_rate_limit(pin_key, 5, 300, code="PIN_LOCKED")
            if payload.pin is None or not verify_password(payload.pin, employee.pin_hash):
                rate_limiter.record_failure(pin_key)
                raise AppError(401, "PIN_INVALID", "PIN falsch.")
            rate_limiter.reset(pin_key)
        source = PunchSource.KIOSK
        device_id = actor.device.id
        created_by = None
        created_by_employee_id = None
    elif actor.is_full_hr_level:
        # Supervisor dürfen Zeiten nur ansehen; manuelle Buchungen/Korrekturen sind Admin/HR vorbehalten.
        await ensure_employee_visible(db, actor, employee)
        source = PunchSource.MANUAL_HR
        device_id = None
        created_by = actor.audit_hr_user_id
        created_by_employee_id = actor.audit_employee_id
    else:
        raise AppError(403, "FORBIDDEN", "Mitarbeiter-Login erlaubt keine eigene Stempelung.")

    await ensure_period_open(
        db, employee.id, local_date(payload.timestamp_utc, await employee_timezone(db, employee))
    )

    punch = Punch(
        tenant_id=actor.tenant_id,
        employee_id=employee.id,
        location_id=employee.location_id,
        punch_type=payload.punch_type,
        timestamp_utc=payload.timestamp_utc,
        source=source,
        device_id=device_id,
        created_by=created_by,
        created_by_employee_id=created_by_employee_id,
        idempotency_key=payload.idempotency_key,
    )
    db.add(punch)
    try:
        await db.flush()
        # Ende einer Nachtschicht gehört zum Vortag – dessen Monat darf ebenfalls nicht gesperrt sein.
        await ensure_period_open(db, employee.id, await shift_day_of(db, employee, punch, await employee_timezone(db, employee)))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "PUNCH_DUPLICATE", "Diese Stempelung wurde bereits erfasst.") from exc

    await db.refresh(punch)
    await _after_punch(db, employee, punch)
    return PunchResponse.model_validate(punch)


_BREAK_TYPES = (PunchType.BREAK_START, PunchType.BREAK_END)
_ERRAND_TYPES = (PunchType.ERRAND_START, PunchType.ERRAND_END)


def _ensure_punch_type_enabled(settings_row, punch_type: PunchType) -> None:
    """Pausen-/Dienstgang-Buttons sind je Mandant abschaltbar (Einstellungen → Kiosk)."""
    if punch_type in _BREAK_TYPES and not settings_row.kiosk_break_buttons:
        raise AppError(400, "PUNCH_TYPE_DISABLED", "Pausen werden nicht gestempelt.")
    if punch_type in _ERRAND_TYPES and not settings_row.kiosk_errand_buttons:
        raise AppError(400, "PUNCH_TYPE_DISABLED", "Dienstgänge werden nicht gestempelt.")


async def _after_punch(db: AsyncSession, employee: Employee, punch: Punch) -> None:
    """Automatische Pause beim Gehen, Tag/Konto neu rechnen, Kiosks informieren."""
    tz = await employee_timezone(db, employee)
    if punch.punch_type == PunchType.GO:
        await maybe_auto_insert_break(db, employee, punch, tz)
    calculation = await recalculate_day(db, employee, await shift_day_of(db, employee, punch, tz))
    await _broadcast_balance_update(db, employee, calculation)


@router.post("/me/punches", response_model=PunchResponse, status_code=201)
async def create_own_punch(
    payload: OwnPunchRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> PunchResponse:
    """Stempeln über den Web-Login (Startseite): nur für sich selbst, nur wenn der Mandant es
    erlaubt (Standard aus), immer mit der Serverzeit – ein Zurückdatieren ist nicht möglich."""
    if actor.employee is None or actor.device is not None:
        raise AppError(403, "FORBIDDEN", "Nur Mitarbeiter können im Portal stempeln.")
    employee = actor.employee
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not settings_row.portal_punching_enabled:
        raise AppError(403, "PORTAL_PUNCHING_DISABLED", "Stempeln über den Web-Login ist nicht freigeschaltet.")
    _ensure_punch_type_enabled(settings_row, payload.punch_type)

    now = datetime.now(UTC).replace(tzinfo=None)
    # Doppelklick-Schutz: dieselbe Aktion innerhalb einer Minute nur einmal.
    recent = (
        await db.execute(
            select(Punch.id).where(
                Punch.employee_id == employee.id,
                Punch.punch_type == payload.punch_type,
                Punch.timestamp_utc >= now - timedelta(minutes=1),
            )
        )
    ).first()
    if recent is not None:
        raise AppError(409, "PUNCH_DUPLICATE", "Diese Stempelung wurde gerade erst erfasst.")
    tz = await employee_timezone(db, employee)
    await ensure_period_open(db, employee.id, local_date(now.replace(tzinfo=UTC), tz))

    punch = Punch(
        tenant_id=actor.tenant_id,
        employee_id=employee.id,
        location_id=employee.location_id,
        punch_type=payload.punch_type,
        timestamp_utc=now,
        source=PunchSource.PORTAL,
        created_by_employee_id=employee.id,
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(punch)
    await db.flush()
    await ensure_period_open(db, employee.id, await shift_day_of(db, employee, punch, tz))
    await db.commit()
    await db.refresh(punch)
    await _after_punch(db, employee, punch)
    return PunchResponse.model_validate(punch)


@router.get("/employees/{employee_id}/punches", response_model=list[PunchResponse])
async def list_employee_punches(
    employee_id: int,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[PunchResponse]:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    stmt = select(Punch).where(Punch.employee_id == employee_id)
    if date_from is not None:
        stmt = stmt.where(Punch.timestamp_utc >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(Punch.timestamp_utc <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(Punch.timestamp_utc.asc())

    result = await db.execute(stmt)
    return [PunchResponse.model_validate(p) for p in result.scalars().all()]


@router.patch("/punches/{punch_id}", response_model=PunchResponse)
async def correct_punch(
    punch_id: int,
    payload: PunchCorrectionRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PunchResponse:
    punch = await db.get(Punch, punch_id)
    if punch is None or punch.tenant_id != actor.tenant_id:
        raise AppError(404, "PUNCH_NOT_FOUND", "Stempelung nicht gefunden.")

    employee = await db.get(Employee, punch.employee_id)
    await ensure_employee_visible(db, actor, employee)
    tz = await employee_timezone(db, employee)
    old_date = await shift_day_of(db, employee, punch, tz)
    await ensure_period_open(db, employee.id, old_date)
    if payload.timestamp_utc is not None:
        await ensure_period_open(db, employee.id, local_date(payload.timestamp_utc, tz))

    if payload.punch_type is not None:
        punch.punch_type = payload.punch_type
    if payload.timestamp_utc is not None:
        punch.timestamp_utc = payload.timestamp_utc
    punch.corrected = True
    punch.correction_reason = payload.correction_reason
    punch.created_by = actor.audit_hr_user_id
    punch.created_by_employee_id = actor.audit_employee_id

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.PUNCH_CORRECTED,
        entity_type="punch",
        entity_id=punch.id,
        detail=payload.correction_reason,
    )

    await db.commit()
    await db.refresh(punch)

    new_date = await shift_day_of(db, employee, punch, tz)
    calculation = await recalculate_day(db, employee, old_date)
    if new_date != old_date:
        calculation = await recalculate_day(db, employee, new_date)
    await _broadcast_balance_update(db, employee, calculation)

    return PunchResponse.model_validate(punch)


@router.delete("/punches/{punch_id}", status_code=204)
async def delete_punch(
    punch_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löscht eine fehlerhafte Stempelung (z.B. Doppel-Buchung) endgültig, statt
    sie nur zu korrigieren. Danach wird der betroffene Tag/Woche neu berechnet."""
    punch = await db.get(Punch, punch_id)
    if punch is None or punch.tenant_id != actor.tenant_id:
        raise AppError(404, "PUNCH_NOT_FOUND", "Stempelung nicht gefunden.")

    employee = await db.get(Employee, punch.employee_id)
    await ensure_employee_visible(db, actor, employee)
    tz = await employee_timezone(db, employee)
    work_date = await shift_day_of(db, employee, punch, tz)
    await ensure_period_open(db, employee.id, work_date)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.PUNCH_DELETED,
        entity_type="punch",
        entity_id=punch.id,
        detail=f"{punch.punch_type.value} um {punch.timestamp_utc.isoformat()}",
    )

    await db.delete(punch)
    await db.commit()

    calculation = await recalculate_day(db, employee, work_date)
    await _broadcast_balance_update(db, employee, calculation)
