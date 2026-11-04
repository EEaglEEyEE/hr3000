from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.db import get_db
from app.errors import AppError
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    CorrectionRequestStatus,
    DailySummary,
    Employee,
    Holiday,
    PunchCorrectionRequest,
    SummaryStatus,
)
from app.schemas.dashboard import DashboardEvent, DashboardMe, DashboardPerson, DashboardResponse, DashboardTeam
from app.services.absence_type_service import CATEGORY_LABELS, list_absence_types
from app.services.holiday_service import location_scope
from app.services.leave_service import leave_balance
from app.services.monthly_cap_service import monthly_cap_status
from app.services.settings_service import get_or_create_settings
from app.services.team_scope_service import supervisor_team_ids
from app.services.timesheet_service import (
    balance_as_of,
    calculate_day,
    employee_timezone,
    format_hours,
    is_birthday,
    punch_blocks,
    punches_for_day,
    today_in,
    week_start,
)

router = APIRouter(tags=["dashboard"])

_MAX_EVENTS = 100


def _name(employee: Employee) -> str:
    return f"{employee.first_name} {employee.last_name}"


async def _me(db: AsyncSession, employee: Employee) -> DashboardMe:
    tz = await employee_timezone(db, employee)
    today = today_in(tz)
    info = await balance_as_of(db, employee)
    leave = await leave_balance(db, employee.id, today.year)
    calc = await calculate_day(db, employee, today, tz)
    week_target = week_actual = 0
    day = week_start(today)
    while day <= today:
        week_calc = calc if day == today else await calculate_day(db, employee, day, tz)
        week_target += week_calc.target_minutes or 0
        week_actual += week_calc.actual_minutes or 0
        day += timedelta(days=1)
    pending_absences = (
        await db.execute(
            select(func.count(Absence.id)).where(
                Absence.employee_id == employee.id, Absence.approval_status == AbsenceApprovalStatus.PENDING
            )
        )
    ).scalar_one()
    pending_corrections = (
        await db.execute(
            select(func.count(PunchCorrectionRequest.id)).where(
                PunchCorrectionRequest.employee_id == employee.id,
                PunchCorrectionRequest.status == CorrectionRequestStatus.PENDING,
            )
        )
    ).scalar_one()
    cap = await monthly_cap_status(db, employee)
    settings_row = await get_or_create_settings(db, employee.tenant_id)
    return DashboardMe(
        portal_punching=settings_row.portal_punching_enabled,
        break_buttons=settings_row.kiosk_break_buttons,
        errand_buttons=settings_row.kiosk_errand_buttons,
        on_demand=cap.on_demand,
        month_actual_minutes=cap.actual_minutes if cap.on_demand else None,
        monthly_cap_minutes=cap.cap_minutes,
        employee_id=employee.id,
        first_name=employee.first_name,
        balance_minutes=info.total_minutes,
        balance_date=info.last_row.balance_date if info.last_row else None,
        vacation_year=today.year,
        vacation_remaining_days=leave.remaining_days,
        vacation_expiring_days=leave.expiring_days,
        vacation_expiry_date=leave.expiry_date if leave.expiring_days else None,
        today_status=calc.status if calc.has_punches or calc.status == SummaryStatus.ABSENCE else None,
        today_times=punch_blocks(await punches_for_day(db, employee, today, tz), tz),
        today_actual_minutes=calc.actual_minutes,
        week_target_minutes=week_target,
        week_actual_minutes=week_actual,
        pending_absences=pending_absences,
        pending_corrections=pending_corrections,
    )


async def _visible_employees(db: AsyncSession, actor: Actor) -> list[Employee]:
    stmt = select(Employee).where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True))
    if actor.is_supervisor_level:
        stmt = stmt.where(Employee.team_id.in_(await supervisor_team_ids(db, actor) or set()))
    return list((await db.execute(stmt.order_by(Employee.last_name, Employee.first_name))).scalars().all())


def _next_birthday(birth_date: date, start: date, end: date) -> date | None:
    day = start
    while day <= end:
        if is_birthday(birth_date, day):
            return day
        day += timedelta(days=1)
    return None


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    # Wie weit "Nächste Termine" in die Zukunft schauen (Tage ab heute)
    days: int = Query(default=30, ge=1, le=180),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Startseite: eigene Kennzahlen (Mitarbeiter-Login), für HR/Supervisor wer heute da bzw.
    abwesend ist, und für alle die nächsten Termine (Feiertage, Abwesenheiten, Geburtstage).
    Mitarbeiter ohne HR-Rolle sehen nur eigene Abwesenheiten und den eigenen Geburtstag."""
    if actor.device is not None:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    me_employee = actor.employee
    me = await _me(db, me_employee) if me_employee is not None else None

    today = today_in(await employee_timezone(db, me_employee)) if me_employee is not None else date.today()
    horizon = today + timedelta(days=days)
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    types = {t.id: t for t in await list_absence_types(db, actor.tenant_id)}

    people = await _visible_employees(db, actor) if actor.is_hr_level else ([me_employee] if me_employee else [])
    by_id = {e.id: e for e in people}

    events: list[DashboardEvent] = []
    # Feiertage: für Mitarbeiter nur die des eigenen Standorts, für HR alle.
    holidays = (
        await db.execute(
            select(Holiday).where(Holiday.tenant_id == actor.tenant_id, Holiday.date >= today, Holiday.date <= horizon)
        )
    ).scalars().all()
    for holiday in holidays:
        scope = location_scope(holiday)
        if not actor.is_hr_level and me_employee is not None and scope is not None and me_employee.location_id not in scope:
            continue
        events.append(DashboardEvent(date=holiday.date, kind="HOLIDAY", title=holiday.name))

    absences = (
        await db.execute(
            select(Absence).where(
                Absence.employee_id.in_(by_id.keys() or [0]),
                Absence.approval_status.in_([AbsenceApprovalStatus.APPROVED, AbsenceApprovalStatus.PENDING]),
                Absence.date_to >= today,
                Absence.date_from <= horizon,
            )
        )
    ).scalars().all()
    absent_today: list[DashboardPerson] = []
    for absence in absences:
        employee = by_id[absence.employee_id]
        absence_type = types.get(absence.absence_type_id) if absence.absence_type_id else None
        type_name = absence_type.name if absence_type else CATEGORY_LABELS[absence.type]
        if absence.half_day:
            type_name = f"½ {type_name}"
        elif absence.duration_minutes is not None:
            type_name = f"{type_name} ({format_hours(absence.duration_minutes)})"
        pending = absence.approval_status == AbsenceApprovalStatus.PENDING
        events.append(
            DashboardEvent(
                date=max(absence.date_from, today),
                date_to=absence.date_to if absence.date_to != max(absence.date_from, today) else None,
                kind="PENDING_ABSENCE" if pending else "ABSENCE",
                title=f"{type_name}{' (beantragt)' if pending else ''}",
                employee_id=employee.id,
                employee_name=_name(employee),
                color=absence_type.color if absence_type else None,
            )
        )
        if not pending and absence.date_from <= today <= absence.date_to:
            absent_today.append(
                DashboardPerson(
                    employee_id=employee.id,
                    name=_name(employee),
                    detail=(
                        type_name
                        if absence.half_day or absence.duration_minutes is not None
                        else f"{type_name} bis {absence.date_to.strftime('%d.%m.')}"
                    ),
                    color=absence_type.color if absence_type else None,
                )
            )

    if settings_row.show_birthdays_in_calendar:
        for employee in people:
            if employee.birth_date is None or not employee.show_birthday_in_calendar:
                continue
            day = _next_birthday(employee.birth_date, today, horizon)
            if day is not None:
                events.append(
                    DashboardEvent(
                        date=day,
                        kind="BIRTHDAY",
                        title=f"Geburtstag ({day.year - employee.birth_date.year})"
                        if me_employee is not None and employee.id == me_employee.id
                        else "Geburtstag",
                        employee_id=employee.id,
                        employee_name=_name(employee),
                    )
                )

    team = None
    if actor.is_hr_level:
        summaries = (
            await db.execute(
                select(DailySummary).where(
                    DailySummary.employee_id.in_(by_id.keys() or [0]),
                    DailySummary.work_date == today,
                    DailySummary.status.in_([SummaryStatus.PRESENT, SummaryStatus.ON_BREAK, SummaryStatus.ON_ERRAND]),
                )
            )
        ).scalars().all()
        present = [DashboardPerson(employee_id=s.employee_id, name=_name(by_id[s.employee_id])) for s in summaries if s.status == SummaryStatus.PRESENT]
        on_break = [DashboardPerson(employee_id=s.employee_id, name=_name(by_id[s.employee_id])) for s in summaries if s.status == SummaryStatus.ON_BREAK]
        on_errand = [DashboardPerson(employee_id=s.employee_id, name=_name(by_id[s.employee_id])) for s in summaries if s.status == SummaryStatus.ON_ERRAND]
        team = DashboardTeam(
            on_errand=sorted(on_errand, key=lambda p: p.name),
            present=sorted(present, key=lambda p: p.name),
            on_break=sorted(on_break, key=lambda p: p.name),
            absent=sorted(absent_today, key=lambda p: p.name),
            visible_employees=len(people),
        )

    order = {"HOLIDAY": 0, "BIRTHDAY": 1, "ABSENCE": 2, "PENDING_ABSENCE": 3}
    events.sort(key=lambda e: (e.date, order[e.kind], e.employee_name or ""))
    await db.commit()  # list_absence_types legt beim ersten Aufruf die Standardarten an
    return DashboardResponse(
        me=me,
        team=team,
        events=events[:_MAX_EVENTS],
        horizon_date=horizon,
        portal_punching_enabled=settings_row.portal_punching_enabled,
        absence_requests_enabled=settings_row.absence_requests_enabled,
        shift_planning_enabled=settings_row.shift_planning_enabled,
    )
