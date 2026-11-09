from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Employee, Holiday, SummaryStatus
from app.schemas.team_calendar import TeamCalendarDay, TeamCalendarEmployee
from app.services.absence_type_service import list_absence_types
from app.services.holiday_service import location_scope
from app.services.settings_service import get_or_create_settings
from app.services.team_scope_service import supervisor_team_ids
from app.services.timesheet_service import describe_absence_parts, is_birthday

router = APIRouter(tags=["team_calendar"])

# Ein Kalendermonat plus etwas Puffer – deutlich enger als der 366-Tage-Rahmen
# des Lohn-Exports, da diese Ansicht für die monatliche Übersicht gedacht ist.
_MAX_RANGE_DAYS = 62


@router.get("/team-calendar", response_model=list[TeamCalendarEmployee])
async def get_team_calendar(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    location_id: int | None = Query(default=None),
    # Filter auf ein oder mehrere Teams (leer = alle sichtbaren); 0 = Mitarbeiter ohne Team.
    team_ids: list[int] = Query(default_factory=list, alias="team_id"),
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[TeamCalendarEmployee]:
    """Monatsübersicht über Urlaub/Krankheit/Feiertage für alle für den Actor
    sichtbaren Mitarbeiter (Supervisor: nur eigene Teams, siehe
    app/services/team_scope_service.py). Bewusst ohne Ist-Zeit-Berechnung –
    reine Absenz-/Feiertagsübersicht, daher zwei Bulk-Queries (Holiday,
    Absence) statt einer Punch-Historie-Abfrage pro Tag und Mitarbeiter wie
    bei calculate_day."""
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(
            400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_RANGE_DAYS} Tage umfassen."
        )

    stmt = select(Employee).where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True))
    if location_id is not None:
        stmt = stmt.where(Employee.location_id == location_id)
    if team_ids:
        wanted = [t for t in team_ids if t > 0]
        condition = Employee.team_id.in_(wanted) if wanted else None
        if 0 in team_ids:
            condition = Employee.team_id.is_(None) if condition is None else or_(condition, Employee.team_id.is_(None))
        stmt = stmt.where(condition)
    if actor.is_supervisor_level:
        team_ids = await supervisor_team_ids(db, actor)
        stmt = stmt.where(Employee.team_id.in_(team_ids or set()))
    stmt = stmt.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    employees = (await db.execute(stmt)).scalars().all()
    if not employees:
        return []

    return await _calendar(db, actor.tenant_id, employees, date_from, date_to)


@dataclass(frozen=True)
class _Mask:
    """Sicht eines Mitarbeiters: eigene Einträge voll, bei Kollegen die Art nur bei „farbig“."""

    self_id: int
    colored_type_ids: frozenset[int]


async def _calendar(
    db: AsyncSession, tenant_id: int, employees, date_from: date, date_to: date, mask: _Mask | None = None
) -> list[TeamCalendarEmployee]:
    employee_ids = [employee.id for employee in employees]

    holidays_result = await db.execute(
        select(Holiday).where(
            Holiday.tenant_id == tenant_id,
            Holiday.date >= date_from,
            Holiday.date <= date_to,
        )
    )
    tenant_wide_holidays: set[date] = set()
    holidays_by_location: dict[int, set[date]] = {}
    for holiday in holidays_result.scalars().all():
        scope = location_scope(holiday)
        if scope is None:
            tenant_wide_holidays.add(holiday.date)
        else:
            for holiday_location_id in scope:
                holidays_by_location.setdefault(holiday_location_id, set()).add(holiday.date)

    absences_result = await db.execute(
        select(Absence).where(
            Absence.employee_id.in_(employee_ids),
            Absence.approval_status == AbsenceApprovalStatus.APPROVED,
            Absence.date_from <= date_to,
            Absence.date_to >= date_from,
        ).order_by(Absence.id)
    )
    absences_by_employee: dict[int, list[Absence]] = {}
    for absence in absences_result.scalars().all():
        hidden_work_time = mask is not None and absence.employee_id != mask.self_id and absence.type == AbsenceType.WORK_TIME
        if not hidden_work_time:  # Homeoffice o. ä. ist für Kollegen keine Abwesenheit
            absences_by_employee.setdefault(absence.employee_id, []).append(absence)

    show_birthdays = (await get_or_create_settings(db, tenant_id)).show_birthdays_in_calendar
    type_names = {t.id: t.name for t in await list_absence_types(db, tenant_id)}

    responses: list[TeamCalendarEmployee] = []
    for employee in employees:
        birth_date = employee.birth_date if show_birthdays and employee.show_birthday_in_calendar else None
        employee_holidays = tenant_wide_holidays | holidays_by_location.get(employee.location_id, set())
        employee_absences = absences_by_employee.get(employee.id, [])

        days: list[TeamCalendarDay] = []
        current = date_from
        while current <= date_to:
            if current in employee_holidays:
                days.append(TeamCalendarDay(date=current, status=SummaryStatus.HOLIDAY, absence_type=None, is_birthday=is_birthday(birth_date, current)))
            else:
                covering = [a for a in employee_absences if a.date_from <= current <= a.date_to]
                full = [a for a in covering if not a.half_day and a.duration_minutes is None]
                # Wie in der Tagesberechnung: ganztägig hat Vorrang, sonst bis zu zwei halbe Tage
                # und Stundenangaben (z.B. 3 Std. Homeoffice).
                halves = [a for a in covering if a.half_day][:2]
                durations = [a for a in covering if a.duration_minutes is not None]
                parts = full[:1] or halves + durations
                if parts and mask is not None and employee.id != mask.self_id and not any(
                    a.absence_type_id in mask.colored_type_ids for a in parts
                ):
                    # „ausgegraut“: nur, dass jemand fehlt – ohne Art
                    days.append(
                        TeamCalendarDay(
                            date=current, status=SummaryStatus.ABSENCE, absence_type=None,
                            half_day=not full and len(halves) == 1 and not durations,
                            is_birthday=is_birthday(birth_date, current),
                        )
                    )
                elif parts:
                    partial = not full
                    days.append(
                        TeamCalendarDay(
                            date=current,
                            status=SummaryStatus.ABSENCE,
                            absence_type=parts[0].type,
                            absence_type_id=parts[0].absence_type_id,
                            half_day=partial and len(halves) == 1 and not durations,
                            absence_label=describe_absence_parts(halves, durations, type_names) if partial else None,
                            is_birthday=is_birthday(birth_date, current),
                        )
                    )
                else:
                    days.append(
                        TeamCalendarDay(date=current, status=None, absence_type=None, is_birthday=is_birthday(birth_date, current))
                    )
            current += timedelta(days=1)

        responses.append(
            TeamCalendarEmployee(
                employee_id=employee.id,
                first_name=employee.first_name,
                last_name=employee.last_name,
                team_id=employee.team_id,
                days=days,
            )
        )

    return responses


@router.get("/me/team-calendar", response_model=list[TeamCalendarEmployee])
async def get_my_team_calendar(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[TeamCalendarEmployee]:
    """Teamkalender für Mitarbeiter („Mein Bereich“): das eigene Team (ohne Team nur man selbst).
    Bei Kollegen erscheint die Art nur bei Abwesenheitsarten mit „im Teamkalender farbig“, sonst
    „ausgegraut“; Arbeitszeit-Angaben (Homeoffice) gar nicht. Nur mit Einstellung
    team_calendar_for_employees."""
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    if date_to < date_from or (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(400, "INVALID_RANGE", f"Bitte einen Zeitraum von höchstens {_MAX_RANGE_DAYS} Tagen angeben.")
    if not (await get_or_create_settings(db, actor.tenant_id)).team_calendar_for_employees:
        raise AppError(403, "TEAM_CALENDAR_DISABLED", "Der Teamkalender ist für Mitarbeiter nicht freigeschaltet.")
    me = actor.employee
    stmt = select(Employee).where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True))
    stmt = stmt.where(Employee.team_id == me.team_id) if me.team_id is not None else stmt.where(Employee.id == me.id)
    employees = (await db.execute(stmt.order_by(Employee.last_name, Employee.first_name))).scalars().all()
    colored = frozenset(t.id for t in await list_absence_types(db, actor.tenant_id) if t.calendar_visibility == "COLOR")
    return await _calendar(db, actor.tenant_id, employees, date_from, date_to, _Mask(me.id, colored))
