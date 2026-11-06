import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_payroll_principal
from app.db import get_db
from app.errors import AppError
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    AuditAction,
    Compensation,
    Employee,
    EmployeeDefaultShift,
    EmploymentContract,
    Holiday,
    LeaveEntitlement,
    PayType,
)
from app.schemas.reports import (
    AbsenceStatsEmployee,
    AbsenceStatsMonth,
    AbsenceStatsResponse,
    AttentionItem,
    AttentionKind,
    LaborCostResponse,
    LaborCostRow,
    OvertimeRow,
    VacationRow,
)
from app.services.absence_type_service import format_days
from app.services.audit_service import log_action
from app.services.holiday_service import location_scope
from app.services.leave_service import is_leave_day, leave_balance
from app.services.pay_component_service import pay_component_amounts
from app.services.payroll_export_service import payroll_period
from app.services.surcharge_service import active_rules, compute_surcharges
from app.services.timesheet_service import balance_as_of

router = APIRouter(prefix="/reports", tags=["reports"])

_BEM_THRESHOLD_DAYS = 42  # 6 Wochen (§167 Abs. 2 SGB IX), gezählt in Kalendertagen der letzten 12 Monate
_MAX_COST_RANGE_DAYS = 93
_MAX_COST_EMPLOYEES = 300


async def _employees(db: AsyncSession, tenant_id: int, *, active_only: bool = True) -> list[Employee]:
    stmt = select(Employee).where(Employee.tenant_id == tenant_id, Employee.anonymized_at.is_(None))
    if active_only:
        stmt = stmt.where(Employee.active.is_(True))
    return list((await db.execute(stmt.order_by(Employee.last_name, Employee.first_name))).scalars().all())


def _ref(employee: Employee) -> dict:
    return dict(
        employee_id=employee.id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        employee_number=employee.employee_number,
    )


async def _holiday_scopes(db: AsyncSession, tenant_id: int, date_from: date, date_to: date) -> dict[date, list[set[int] | None]]:
    rows = await db.execute(select(Holiday).where(Holiday.tenant_id == tenant_id, Holiday.date >= date_from, Holiday.date <= date_to))
    scopes: dict[date, list[set[int] | None]] = {}
    for holiday in rows.scalars().all():
        scopes.setdefault(holiday.date, []).append(location_scope(holiday))
    return scopes


def _is_holiday(scopes: dict[date, list[set[int] | None]], day: date, location_id: int) -> bool:
    return any(scope is None or location_id in scope for scope in scopes.get(day, []))


async def _planned_workdays(
    db: AsyncSession, employee: Employee, first: date, last: date, scopes: dict[date, list[set[int] | None]]
) -> int:
    """Soll-Arbeitstage laut Arbeitszeitmodell (Teilzeit!) ohne Feiertage; ohne Modell und bei
    flexiblem Modell Mo–Fr, nach Aufwand keine (ohne feste Tage gibt es keine Krankheitsquote).
    Schnelle Näherung ohne Tagesausnahmen des Schichtplans."""
    defaults = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.employee_id == employee.id, EmployeeDefaultShift.valid_from <= last
            )
        )
    ).scalars().all()
    count = 0
    day = first
    while day <= last:
        if not _is_holiday(scopes, day, employee.location_id):
            active = next((d for d in defaults if d.valid_from <= day and (d.valid_to is None or d.valid_to >= day)), None)
            if active is None:
                count += day.weekday() < 5
            elif not active.on_demand:
                per_day = active.day_minutes_list
                if active.flexible:
                    count += day.weekday() < 5
                elif per_day is not None:
                    count += per_day[day.weekday()] > 0
                else:
                    count += bool(active.weekdays_mask & (1 << day.weekday()))
        day += timedelta(days=1)
    return count


@router.get("/absence-stats", response_model=AbsenceStatsResponse)
async def absence_stats(
    year: int = Query(ge=2000, le=2100),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceStatsResponse:
    first, last = date(year, 1, 1), date(year, 12, 31)
    employees = await _employees(db, actor.tenant_id, active_only=False)
    by_id = {e.id: e for e in employees}
    scopes = await _holiday_scopes(db, actor.tenant_id, first, last)

    months = {m: dict(vacation_days=0, sick_days=0, special_leave_days=0, unpaid_days=0, time_off_days=0, child_sick_days=0) for m in range(1, 13)}
    per_employee = {e.id: dict(vacation_days=0, sick_days=0, special_leave_days=0, unpaid_days=0, time_off_days=0, child_sick_days=0) for e in employees}
    key = {
        AbsenceType.VACATION: "vacation_days",
        AbsenceType.SICK: "sick_days",
        AbsenceType.SPECIAL_LEAVE: "special_leave_days",
        AbsenceType.UNPAID: "unpaid_days",
        AbsenceType.TIME_OFF_IN_LIEU: "time_off_days",
        AbsenceType.CHILD_SICK: "child_sick_days",
    }

    absences = (
        await db.execute(
            select(Absence).where(
                Absence.employee_id.in_(by_id.keys() or [0]),
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.date_from <= last,
                Absence.date_to >= first,
            )
        )
    ).scalars().all()
    sick_days_total = 0
    for absence in absences:
        employee = by_id[absence.employee_id]
        day = max(absence.date_from, first)
        end = min(absence.date_to, last)
        while day <= end:
            if absence.type not in key:
                break  # Arbeitszeit/Feiertag sind keine Abwesenheitstage
            if await is_leave_day(db, employee, day):
                # Stundenangaben (z.B. 3 Std. Homeoffice) sind keine Abwesenheitstage.
                count = 0 if absence.duration_minutes is not None else 0.5 if absence.half_day else 1
                months[day.month][key[absence.type]] += count
                per_employee[employee.id][key[absence.type]] += count
                if absence.type == AbsenceType.SICK:
                    sick_days_total += count
            day += timedelta(days=1)

    active = [e for e in employees if e.active]
    upto = min(date.today(), last)
    workdays = 0
    if upto >= first:
        for employee in active:
            workdays += await _planned_workdays(db, employee, first, upto, scopes)
    rate = round(sick_days_total / workdays * 100, 2) if workdays else None

    return AbsenceStatsResponse(
        year=year,
        months=[AbsenceStatsMonth(month=m, **values) for m, values in months.items()],
        employees=[
            AbsenceStatsEmployee(**_ref(e), **per_employee[e.id])
            for e in employees
            if any(per_employee[e.id].values())
        ],
        active_employee_count=len(active),
        sick_rate_percent=rate,
    )


@router.get("/vacation", response_model=list[VacationRow])
async def vacation_overview(
    year: int = Query(ge=2000, le=2100),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[VacationRow]:
    employees = await _employees(db, actor.tenant_id)
    entitlements = {
        row.employee_id: row
        for row in (
            await db.execute(select(LeaveEntitlement).where(LeaveEntitlement.employee_id.in_([e.id for e in employees] or [0]), LeaveEntitlement.year == year))
        ).scalars().all()
    }
    rows = []
    for employee in employees:
        balance = await leave_balance(db, employee.id, year, entitlements.get(employee.id))
        rows.append(
            VacationRow(
                **_ref(employee),
                entitled_days=balance.entitled_days,
                carried_over_days=balance.carried_over_days,
                used_days=balance.used_days,
                expired_days=balance.expired_days,
                remaining_days=balance.remaining_days,
            )
        )
    return rows


@router.get("/overtime", response_model=list[OvertimeRow])
async def overtime_overview(
    actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[OvertimeRow]:
    """Aktueller Gleitzeitsaldo je aktivem Mitarbeiter, höchste Überstunden zuerst."""
    rows = []
    for employee in await _employees(db, actor.tenant_id):
        info = await balance_as_of(db, employee)
        rows.append(
            OvertimeRow(
                **_ref(employee),
                balance_minutes=info.total_minutes,
                as_of=info.last_row.balance_date if info.last_row else None,
            )
        )
    return sorted(rows, key=lambda r: r.balance_minutes, reverse=True)


@router.get("/attention", response_model=list[AttentionItem])
async def attention_items(
    actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[AttentionItem]:
    """Handlungsbedarf: BEM-Angebot, auslaufende Probezeit/Befristung, bevorstehende Austritte."""
    today = date.today()
    items: list[AttentionItem] = []
    employees = await _employees(db, actor.tenant_id)

    window_start = today - timedelta(days=365)
    for employee in employees:
        absences = (
            await db.execute(
                select(Absence).where(
                    Absence.employee_id == employee.id,
                    Absence.type == AbsenceType.SICK,
                    Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                    Absence.date_to >= window_start,
                    Absence.date_from <= today,
                )
            )
        ).scalars().all()
        sick_days = sum(
            0 if a.duration_minutes is not None else 0.5 if a.half_day else (min(a.date_to, today) - max(a.date_from, window_start)).days + 1
            for a in absences
        )
        if sick_days >= _BEM_THRESHOLD_DAYS:
            items.append(
                AttentionItem(
                    **_ref(employee), kind=AttentionKind.BEM, due_date=None,
                    detail=f"{format_days(sick_days)} Krankheitstage in den letzten 12 Monaten – betriebliches Eingliederungsmanagement (BEM) anbieten.",
                )
            )
        if employee.termination_date is not None and today <= employee.termination_date <= today + timedelta(days=60):
            items.append(
                AttentionItem(
                    **_ref(employee), kind=AttentionKind.TERMINATION, due_date=employee.termination_date,
                    detail="Austritt steht bevor – Offboarding-Checkliste prüfen.",
                )
            )
        contracts = (
            await db.execute(
                select(EmploymentContract).where(
                    EmploymentContract.employee_id == employee.id,
                    EmploymentContract.valid_from <= today,
                    (EmploymentContract.valid_to.is_(None)) | (EmploymentContract.valid_to >= today),
                )
            )
        ).scalars().all()
        for contract in contracts:
            if contract.probation_end is not None and today <= contract.probation_end <= today + timedelta(days=30):
                items.append(
                    AttentionItem(
                        **_ref(employee), kind=AttentionKind.PROBATION_ENDING, due_date=contract.probation_end,
                        detail="Probezeit endet – Probezeitgespräch/Entscheidung fällig.",
                    )
                )
            if contract.fixed_term_end is not None and today <= contract.fixed_term_end <= today + timedelta(days=90):
                items.append(
                    AttentionItem(
                        **_ref(employee), kind=AttentionKind.FIXED_TERM_ENDING, due_date=contract.fixed_term_end,
                        detail="Befristung läuft aus – Verlängerung/Entfristung klären.",
                    )
                )
    return sorted(items, key=lambda i: (i.due_date is None, i.due_date or today, i.last_name))


def _segments(comps: list[Compensation], date_from: date, date_to: date) -> list[tuple[date, date, Compensation | None]]:
    """Zerlegt den Zeitraum in Abschnitte mit jeweils gleicher gültiger Vergütung (oder keiner)."""
    def valid_on(day: date) -> Compensation | None:
        for comp in reversed(comps):
            if comp.valid_from <= day and (comp.valid_to is None or day <= comp.valid_to):
                return comp
        return None

    segments: list[tuple[date, date, Compensation | None]] = []
    day = date_from
    while day <= date_to:
        comp = valid_on(day)
        if segments and segments[-1][2] is comp and segments[-1][1] == day - timedelta(days=1):
            segments[-1] = (segments[-1][0], day, comp)
        else:
            segments.append((day, day, comp))
        day += timedelta(days=1)
    return segments


@router.get("/labor-costs", response_model=LaborCostResponse)
async def labor_costs(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> LaborCostResponse:
    """Brutto-Lohnkosten (ohne Arbeitgeberanteile) je Mitarbeiter – nur Administratoren, jeder Abruf
    wird protokolliert. Stundenlohn: bezahlte Stunden (inkl. Feiertag/Urlaub/Krank-Gutschrift) x Satz
    plus Zuschläge; Monatsgehalt: anteilig nach Tagen, Zuschläge werden nicht bewertet. Dazu Zulagen
    und Einmalzahlungen im Zeitraum (gleicher Rechenkern wie der Lohn-Export)."""
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_COST_RANGE_DAYS:
        raise AppError(400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_COST_RANGE_DAYS} Tage umfassen.")
    employees = await _employees(db, actor.tenant_id, active_only=False)
    employees = [
        e for e in employees
        if (e.hire_date is None or e.hire_date <= date_to) and (e.termination_date is None or e.termination_date >= date_from)
    ]
    if len(employees) > _MAX_COST_EMPLOYEES:
        raise AppError(400, "TOO_MANY_EMPLOYEES", f"Es werden höchstens {_MAX_COST_EMPLOYEES} Mitarbeiter ausgewertet.")

    rules = await active_rules(db, actor.tenant_id)
    rows: list[LaborCostRow] = []
    total = 0.0
    for employee in employees:
        comps = list(
            (
                await db.execute(
                    select(Compensation)
                    .where(
                        Compensation.employee_id == employee.id,
                        Compensation.valid_from <= date_to,
                        (Compensation.valid_to.is_(None)) | (Compensation.valid_to >= date_from),
                    )
                    .order_by(Compensation.valid_from)
                )
            ).scalars().all()
        )
        period = await payroll_period(db, employee, date_from, date_to)
        actual_minutes = period.summary().actual_minutes
        allowance = float(sum(item.amount for item in await pay_component_amounts(db, employee, date_from, date_to, period)))
        if not comps:
            total += allowance
            rows.append(
                LaborCostRow(
                    **_ref(employee), pay_type=None, rate=None, actual_minutes=actual_minutes, base_cost=None, surcharge_cost=None,
                    allowance_cost=round(allowance, 2), total_cost=round(allowance, 2) if allowance else None,
                    note="Keine Vergütung hinterlegt",
                )
            )
            continue

        base = 0.0
        surcharge = 0.0
        uncovered_days = 0
        has_monthly = False
        # Je Vergütungsabschnitt getrennt bewerten (Satzwechsel mitten im Zeitraum).
        for segment_start, segment_end, comp in _segments(comps, date_from, date_to):
            if comp is None:
                uncovered_days += (segment_end - segment_start).days + 1
                continue
            amount = float(comp.amount)
            if comp.pay_type == PayType.HOURLY:
                minutes = period.summary(segment_start, segment_end).actual_minutes
                base += minutes / 60 * amount
                equivalent = sum(t.equivalent_minutes for t in await compute_surcharges(db, employee, segment_start, segment_end, rules))
                surcharge += equivalent / 60 * amount
            else:
                has_monthly = True
                day = segment_start
                while day <= segment_end:
                    base += amount / calendar.monthrange(day.year, day.month)[1]
                    day += timedelta(days=1)

        notes = []
        if len(comps) > 1:
            notes.append("Satzwechsel im Zeitraum – anteilig bewertet")
        if has_monthly:
            notes.append("Monatsgehalt: Zuschläge nicht bewertet")
        if uncovered_days:
            notes.append(f"{uncovered_days} Tag(e) ohne hinterlegte Vergütung")
        latest = comps[-1]
        row_total = round(base + surcharge + allowance, 2)
        total += row_total
        rows.append(
            LaborCostRow(
                **_ref(employee), pay_type=latest.pay_type, rate=float(latest.amount), actual_minutes=actual_minutes,
                base_cost=round(base, 2), surcharge_cost=round(surcharge, 2), allowance_cost=round(allowance, 2), total_cost=row_total,
                note="; ".join(notes) or None,
            )
        )

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.COMPENSATION_VIEWED,
        entity_type="report",
        entity_id=actor.tenant_id,
        detail=f"Lohnkostenauswertung {date_from.isoformat()} – {date_to.isoformat()}",
    )
    await db.commit()
    return LaborCostResponse(date_from=date_from, date_to=date_to, rows=rows, total_cost=round(total, 2))
