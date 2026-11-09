import json
import uuid
from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import (
    AuditAction,
    CorrectionRequestStatus,
    Employee,
    Punch,
    PunchCorrectionRequest,
    PunchSource,
    PunchType,
)
from app.schemas.punch_correction_request import (
    CorrectionRequestCreate,
    CorrectionRequestDecide,
    CorrectionRequestResponse,
)
from app.services.audit_service import log_action
from app.services.notification_service import notify_correction_decided, notify_correction_requested
from app.services.period_service import ensure_period_open
from app.services.scope_service import ensure_employee_visible
from app.services.timesheet_service import employee_timezone, recalculate_day, refresh_auto_breaks, today_in

router = APIRouter(tags=["punch_correction_requests"])


def _response(row: PunchCorrectionRequest, employee: Employee | None = None) -> CorrectionRequestResponse:
    response = CorrectionRequestResponse.model_validate(row)
    if employee is not None:
        response.employee_name = f"{employee.last_name}, {employee.first_name}"
    return response


@router.post("/punch-correction-requests", response_model=CorrectionRequestResponse, status_code=201)
async def create_correction_request(
    payload: CorrectionRequestCreate,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> CorrectionRequestResponse:
    """Nur der Mitarbeiter selbst (Mein Bereich) – HR bucht Korrekturen direkt."""
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Korrekturanträge stellt der Mitarbeiter selbst.")
    employee = actor.employee
    tz = await employee_timezone(db, employee)
    if payload.work_date > today_in(tz):
        raise AppError(400, "DATE_IN_FUTURE", "Korrekturen sind nur für vergangene Tage oder heute möglich.")
    await ensure_period_open(db, employee.id, payload.work_date)

    pending = (
        await db.execute(
            select(PunchCorrectionRequest.id).where(
                PunchCorrectionRequest.employee_id == employee.id,
                PunchCorrectionRequest.work_date == payload.work_date,
                PunchCorrectionRequest.status == CorrectionRequestStatus.PENDING,
            )
        )
    ).first()
    if pending is not None:
        raise AppError(409, "CORRECTION_PENDING", "Für diesen Tag liegt schon ein offener Antrag vor.")

    row = PunchCorrectionRequest(
        tenant_id=actor.tenant_id,
        employee_id=employee.id,
        work_date=payload.work_date,
        items=json.dumps([item.model_dump(mode="json") for item in payload.items]),
        reason=payload.reason,
        status=CorrectionRequestStatus.PENDING,
    )
    db.add(row)
    await notify_correction_requested(db, actor.tenant_id, employee, payload.work_date)
    await db.commit()
    await db.refresh(row)
    return _response(row)


@router.get("/punch-correction-requests", response_model=list[CorrectionRequestResponse])
async def list_correction_requests(
    status: CorrectionRequestStatus | None = Query(default=None),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[CorrectionRequestResponse]:
    """Admin/HR: alle Anträge des Mandanten. Mitarbeiter: nur die eigenen."""
    if actor.device is not None:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    stmt = (
        select(PunchCorrectionRequest, Employee)
        .join(Employee, Employee.id == PunchCorrectionRequest.employee_id)
        .where(PunchCorrectionRequest.tenant_id == actor.tenant_id)
    )
    if not actor.is_full_hr_level:
        if actor.employee is None:
            raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
        stmt = stmt.where(PunchCorrectionRequest.employee_id == actor.employee.id)
    if status is not None:
        stmt = stmt.where(PunchCorrectionRequest.status == status)
    stmt = stmt.order_by(PunchCorrectionRequest.work_date.desc(), PunchCorrectionRequest.id.desc()).limit(200)
    return [_response(row, employee) for row, employee in (await db.execute(stmt)).all()]


@router.patch("/punch-correction-requests/{request_id}/decide", response_model=CorrectionRequestResponse)
async def decide_correction_request(
    request_id: int,
    payload: CorrectionRequestDecide,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> CorrectionRequestResponse:
    """Übernehmen legt die beantragten Stempelungen als manuelle HR-Buchung an (mit Antrag als
    Begründung), Ablehnen ändert nichts an den Zeiten."""
    row = await db.get(PunchCorrectionRequest, request_id)
    if row is None or row.tenant_id != actor.tenant_id:
        raise AppError(404, "CORRECTION_NOT_FOUND", "Antrag nicht gefunden.")
    if row.status != CorrectionRequestStatus.PENDING:
        raise AppError(400, "NOT_PENDING", "Dieser Antrag wurde bereits entschieden.")
    employee = await db.get(Employee, row.employee_id)
    await ensure_employee_visible(db, actor, employee)
    await ensure_period_open(db, employee.id, row.work_date)

    tz = await employee_timezone(db, employee)
    created: list[Punch] = []
    if payload.approve:
        for item in CorrectionRequestResponse.model_validate(row).items:
            hour, minute = (int(v) for v in item.time.split(":"))
            local = datetime.combine(row.work_date + timedelta(days=1 if item.next_day else 0), time(hour, minute), tz)
            punch = Punch(
                tenant_id=actor.tenant_id,
                employee_id=employee.id,
                location_id=employee.location_id,
                punch_type=item.punch_type,
                timestamp_utc=local.astimezone(UTC).replace(tzinfo=None),
                source=PunchSource.MANUAL_HR,
                created_by_account_id=actor.account_id,
                correction_reason=f"Korrekturantrag: {row.reason}"[:500],
                idempotency_key=str(uuid.uuid4()),
            )
            db.add(punch)
            created.append(punch)

    row.status = CorrectionRequestStatus.APPROVED if payload.approve else CorrectionRequestStatus.REJECTED
    row.decided_by_account_id = actor.account_id
    row.decided_at = datetime.now(UTC).replace(tzinfo=None)
    row.decision_note = payload.note
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.PUNCH_CORRECTION_DECIDED,
        entity_type="punch_correction_request",
        entity_id=row.id,
        detail=(
            f"{'Übernommen' if payload.approve else 'Abgelehnt'}: {employee.first_name} {employee.last_name}, "
            f"{row.work_date.isoformat()}"
        ),
    )
    await notify_correction_decided(db, actor.tenant_id, employee, row.work_date, payload.approve)
    await db.commit()

    if created:
        await refresh_auto_breaks(db, employee, row.work_date, tz)
    if created:
        await recalculate_day(db, employee, row.work_date)
    await db.refresh(row)
    return _response(row, employee)
