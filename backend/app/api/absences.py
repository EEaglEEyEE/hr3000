from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_hr_or_self, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, AuditAction, Employee
from app.schemas.absence import (
    AbsenceCreateRequest,
    AbsenceDecideRequest,
    AbsenceResponse,
    AbsenceUpdateRequest,
)
from app.services.absence_type_service import resolve_absence_type
from app.services.audit_service import log_action
from app.services.notification_service import notify_absence_decided, notify_absence_requested
from app.services.settings_service import get_or_create_settings
from app.services.team_scope_service import ensure_employee_visible, supervisor_team_ids
from app.services.period_service import ensure_range_open
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["absences"])


async def _get_absence_in_tenant(db: AsyncSession, absence_id: int, tenant_id: int) -> Absence:
    """Absence hat kein eigenes tenant_id (leitet sich über employee_id ab),
    daher Prüfung über einen Join statt einem einfachen Attribut-Vergleich."""
    result = await db.execute(
        select(Absence)
        .join(Employee, Employee.id == Absence.employee_id)
        .where(Absence.id == absence_id, Employee.tenant_id == tenant_id)
    )
    absence = result.scalar_one_or_none()
    if absence is None:
        raise AppError(404, "ABSENCE_NOT_FOUND", "Abwesenheit nicht gefunden.")
    return absence


async def _has_authority_over_employee(db: AsyncSession, actor: Actor, employee: Employee) -> bool:
    """Ob der Actor diesen Mitarbeiter final entscheiden/direkt-genehmigen
    darf: Admin/HR (unbeschränkt) oder Supervisor des Teams des Mitarbeiters
    (siehe app/services/team_scope_service.py)."""
    if actor.is_full_hr_level:
        return True
    if not actor.is_supervisor_level:
        return False
    try:
        await ensure_employee_visible(db, actor, employee)
    except AppError:
        return False
    return True


def _is_full_day(absence: Absence) -> bool:
    return not absence.half_day and absence.duration_minutes is None


async def _ensure_day_parts_fit(
    db: AsyncSession,
    employee_id: int,
    date_from: date,
    date_to: date,
    half_day: bool,
    duration_minutes: int | None,
    exclude_id: int | None = None,
) -> None:
    """Teil-Abwesenheiten eines Tages: höchstens zwei halbe Tage (z.B. ½ Sonderurlaub + ½ Urlaub)
    und beliebig viele Stundenangaben (z.B. 3 Std. Homeoffice) – aber nie zusammen mit einer
    ganztägigen Abwesenheit, sonst wäre unklar, was gutgeschrieben bzw. verbraucht wird."""
    stmt = select(Absence).where(
        Absence.employee_id == employee_id,
        Absence.date_from <= date_to,
        Absence.date_to >= date_from,
        Absence.approval_status != AbsenceApprovalStatus.REJECTED,
    )
    if exclude_id is not None:
        stmt = stmt.where(Absence.id != exclude_id)
    others = (await db.execute(stmt)).scalars().all()
    if half_day or duration_minutes is not None:
        if any(_is_full_day(other) for other in others):
            raise AppError(409, "ABSENCE_OVERLAP", "An diesem Tag ist bereits eine ganztägige Abwesenheit eingetragen.")
        if half_day and sum(1 for other in others if other.half_day) >= 2:
            raise AppError(409, "ABSENCE_OVERLAP", "An diesem Tag sind bereits zwei halbe Tage eingetragen.")
    elif any(not _is_full_day(other) for other in others):
        raise AppError(
            409,
            "ABSENCE_OVERLAP",
            "In diesem Zeitraum ist bereits ein halber Tag oder eine Stundenangabe eingetragen – bitte zuerst anpassen.",
        )


def _ensure_duration_allowed(category: AbsenceType, duration_minutes: int | None) -> None:
    # Urlaub zählt in Tagen (Urlaubskonto) – dafür gibt es ganze und halbe Tage.
    if duration_minutes is not None and category == AbsenceType.VACATION:
        raise AppError(400, "DURATION_NOT_FOR_VACATION", "Urlaub bitte als ganzen oder halben Tag eintragen, nicht in Stunden.")


@router.get("/employees/{employee_id}/absences", response_model=list[AbsenceResponse])
async def list_employee_absences(
    employee_id: int,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[AbsenceResponse]:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    stmt = select(Absence).where(Absence.employee_id == employee_id)
    if date_from is not None:
        stmt = stmt.where(Absence.date_to >= date_from)
    if date_to is not None:
        stmt = stmt.where(Absence.date_from <= date_to)
    stmt = stmt.order_by(Absence.date_from.asc())

    result = await db.execute(stmt)
    return [AbsenceResponse.model_validate(a) for a in result.scalars().all()]


@router.get("/absences/pending", response_model=list[AbsenceResponse])
async def list_pending_absences(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[AbsenceResponse]:
    """Für die "Urlaubsanträge"-Seite: offene PENDING-Anträge, für einen
    Supervisor auf die eigenen Teams eingeschränkt."""
    stmt = (
        select(Absence)
        .join(Employee, Employee.id == Absence.employee_id)
        .where(Employee.tenant_id == actor.tenant_id, Absence.approval_status == AbsenceApprovalStatus.PENDING)
    )
    if actor.is_supervisor_level:
        team_ids = await supervisor_team_ids(db, actor)
        stmt = stmt.where(Employee.team_id.in_(team_ids or set()))
    stmt = stmt.order_by(Absence.date_from.asc())

    result = await db.execute(stmt)
    return [AbsenceResponse.model_validate(a) for a in result.scalars().all()]


@router.post("/absences", response_model=AbsenceResponse, status_code=201)
async def create_absence(
    payload: AbsenceCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    """Erreichbar für HR-Level-Akteure (für jeden Mitarbeiter) UND per
    Self-Service für den eigenen Mitarbeiter (Urlaubsantrag stellen) – siehe
    approval_status-Logik unten, die genau zwischen diesen Fällen
    unterscheidet."""
    if actor.device is not None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")

    employee = await db.get(Employee, payload.employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")

    is_self = actor.employee is not None and actor.employee.id == employee.id
    if not actor.is_hr_level and not is_self:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    if actor.is_hr_level and not is_self:
        await ensure_employee_visible(db, actor, employee)

    if payload.date_to < payload.date_from:
        raise AppError(400, "INVALID_RANGE", "'date_to' darf nicht vor 'date_from' liegen.")

    await ensure_range_open(db, employee.id, payload.date_from, payload.date_to)
    await _ensure_day_parts_fit(db, employee.id, payload.date_from, payload.date_to, payload.half_day, payload.duration_minutes)

    absence_type = await resolve_absence_type(db, actor.tenant_id, payload.absence_type_id, payload.type)
    _ensure_duration_allowed(absence_type.category, payload.duration_minutes)
    has_authority = await _has_authority_over_employee(db, actor, employee)
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not has_authority and not settings_row.absence_requests_enabled:
        raise AppError(403, "ABSENCE_REQUESTS_DISABLED", "Anträge über das Portal sind abgeschaltet – bitte an HR wenden.")
    if not has_authority and not absence_type.employee_can_request:
        raise AppError(403, "ABSENCE_TYPE_NOT_REQUESTABLE", "Diese Abwesenheitsart kann nur HR eintragen.")

    approval_status = AbsenceApprovalStatus.APPROVED
    needs_approval = absence_type.requires_approval or (
        absence_type.category == AbsenceType.VACATION and settings_row.vacation_approval_required
    )
    if needs_approval and not has_authority:
        approval_status = AbsenceApprovalStatus.PENDING

    absence = Absence(
        employee_id=payload.employee_id,
        type=absence_type.category,
        absence_type_id=absence_type.id,
        date_from=payload.date_from,
        date_to=payload.date_to,
        half_day=payload.half_day,
        duration_minutes=payload.duration_minutes,
        created_by=actor.audit_hr_user_id,
        created_by_employee_id=actor.audit_employee_id,
        note=payload.note,
        approval_status=approval_status,
    )
    db.add(absence)
    if approval_status == AbsenceApprovalStatus.PENDING:
        await notify_absence_requested(db, actor.tenant_id, employee, absence_type.name)
    else:
        await invalidate_balance(db, employee.id, payload.date_from)
    await db.commit()
    await db.refresh(absence)
    return AbsenceResponse.model_validate(absence)


@router.patch("/absences/{absence_id}/decide", response_model=AbsenceResponse)
async def decide_absence(
    absence_id: int,
    payload: AbsenceDecideRequest,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    """Genehmigt/lehnt einen PENDING-Urlaubsantrag ab – nur für Supervisor
    (eigenes Team) oder Admin/HR."""
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    if employee is None or not await _has_authority_over_employee(db, actor, employee):
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")

    if absence.approval_status != AbsenceApprovalStatus.PENDING:
        raise AppError(400, "NOT_PENDING", "Dieser Antrag wurde bereits entschieden.")
    await ensure_range_open(db, employee.id, absence.date_from, absence.date_to)

    absence.approval_status = (
        AbsenceApprovalStatus.APPROVED if payload.approve else AbsenceApprovalStatus.REJECTED
    )
    absence.decided_by = actor.audit_hr_user_id
    absence.decided_by_employee_id = actor.audit_employee_id
    absence.decided_at = datetime.now(UTC)
    if payload.note:
        marker = f"[Entscheidung: {payload.note}]"
        absence.note = f"{absence.note} {marker}" if absence.note else marker

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.ABSENCE_DECIDED,
        entity_type="absence",
        entity_id=absence.id,
        detail=f"{'Genehmigt' if payload.approve else 'Abgelehnt'} für {employee.first_name} {employee.last_name}",
    )
    await notify_absence_decided(db, actor.tenant_id, absence, employee)
    await invalidate_balance(db, employee.id, absence.date_from)

    await db.commit()
    await db.refresh(absence)
    return AbsenceResponse.model_validate(absence)


@router.patch("/absences/{absence_id}", response_model=AbsenceResponse)
async def update_absence(
    absence_id: int,
    payload: AbsenceUpdateRequest,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    if employee is not None:
        await ensure_employee_visible(db, actor, employee)
    await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
    old_from = absence.date_from

    if payload.absence_type_id is not None or payload.type is not None:
        absence_type = await resolve_absence_type(db, actor.tenant_id, payload.absence_type_id, payload.type)
        absence.type = absence_type.category
        absence.absence_type_id = absence_type.id
    if payload.date_from is not None:
        absence.date_from = payload.date_from
    if payload.date_to is not None:
        absence.date_to = payload.date_to
    if payload.half_day is not None:
        absence.half_day = payload.half_day
    if payload.duration_minutes is not None:
        absence.duration_minutes = payload.duration_minutes
    elif payload.clear_duration:
        absence.duration_minutes = None
    if payload.note is not None:
        absence.note = payload.note

    if absence.date_to < absence.date_from:
        await db.rollback()
        raise AppError(400, "INVALID_RANGE", "'date_to' darf nicht vor 'date_from' liegen.")
    if (absence.half_day or absence.duration_minutes is not None) and absence.date_from != absence.date_to:
        await db.rollback()
        raise AppError(400, "HALF_DAY_SINGLE_DAY", "Halbe Tage und Stundenangaben sind nur für einen einzelnen Tag möglich.")
    if absence.half_day and absence.duration_minutes is not None:
        await db.rollback()
        raise AppError(400, "HALF_DAY_OR_DURATION", "Bitte entweder halber Tag oder Stunden angeben.")
    _ensure_duration_allowed(absence.type, absence.duration_minutes)
    await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
    await _ensure_day_parts_fit(
        db, absence.employee_id, absence.date_from, absence.date_to, absence.half_day, absence.duration_minutes, absence.id
    )
    await invalidate_balance(db, absence.employee_id, min(old_from, absence.date_from))

    await db.commit()
    await db.refresh(absence)
    return AbsenceResponse.model_validate(absence)


@router.delete("/absences/{absence_id}", status_code=204)
async def delete_absence(
    absence_id: int,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    if employee is not None:
        await ensure_employee_visible(db, actor, employee)
    await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
    await invalidate_balance(db, absence.employee_id, absence.date_from)

    await db.delete(absence)
    await db.commit()
