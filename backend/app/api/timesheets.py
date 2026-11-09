from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal, get_current_hr_or_self, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import DailySummary, DayReview, Employee, EmployeeDefaultShift, SummaryStatus
from app.schemas.timesheet import (
    BalanceLimitRow,
    DayReviewRequest,
    MonthlyCapRow,
    OpenDayResponse,
    OvertimeBalanceResponse,
    TimesheetDay,
    WeeklyBalanceWeek,
)
from app.services.monthly_cap_service import WARN_SHARE, monthly_cap_status
from app.services.notification_service import notify_open_days_digest
from app.services.settings_service import get_or_create_settings
from app.services.team_scope_service import ensure_employee_visible, supervisor_team_ids
from app.services.timesheet_service import (
    balance_as_of,
    balance_start,
    calculate_day,
    day_fingerprint,
    day_reviews,
    employee_timezone,
    is_birthday,
    needs_review,
    punch_blocks,
    punches_for_day,
    rebuild_balance,
    review_valid,
    today_in,
    utc_today,
    week_start,
)

router = APIRouter(tags=["timesheets"])

# Jeder Tag kostet mehrere Abfragen – ohne Obergrenze könnte ein einzelner Request
# (auch aus dem Self-Service) den Server mit Jahrhunderten an Tagen lahmlegen.
_MAX_RANGE_DAYS = 366


async def _refresh_stale_day_cache(db: AsyncSession, tenant_id: int) -> None:
    """Korrekturen über Abwesenheiten, Feiertage, Arbeitszeitmodelle, Schichtplan usw. markieren das
    Konto nur als veraltet (invalidate_balance) – der Tages-Cache, aus dem "Zu klären" liest, wäre
    sonst bis zum nächsten Öffnen des Mitarbeiters veraltet. Daher die betroffenen Mitarbeiter vorher
    nachrechnen (nur ab dem veralteten Tag)."""
    yesterday = utc_today() - timedelta(days=1)
    stale = (
        await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                or_(
                    Employee.balance_through.is_(None),
                    Employee.balance_through < yesterday,
                    # Frühere Tage, die noch als "anwesend" zwischengespeichert sind, können inzwischen
                    # über die maximale Schichtlänge hinaus offen sein (vergessenes "Gehen").
                    Employee.id.in_(
                        select(DailySummary.employee_id).where(
                            DailySummary.status.in_([SummaryStatus.PRESENT, SummaryStatus.ON_BREAK, SummaryStatus.ON_ERRAND]),
                            DailySummary.work_date < utc_today(),
                        )
                    ),
                ),
                # Ausgeschiedene sind nur bis zum Austritt zu rechnen (danach bleibt der Marker dort stehen).
                or_(
                    Employee.termination_date.is_(None),
                    Employee.balance_through.is_(None),
                    Employee.balance_through < Employee.termination_date,
                ),
            )
        )
    ).scalars().all()
    for employee in stale:
        await rebuild_balance(db, employee)


@router.get("/timesheet/open-days", response_model=list[OpenDayResponse])
async def list_open_days(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    location_id: int | None = Query(default=None),
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[OpenDayResponse]:
    """Tage mit einer offenen (unvollständigen) oder widersprüchlichen Buchung über
    alle Mitarbeiter, aus dem daily_summaries-Cache. Erfasst nur Tage, an denen
    tatsächlich gestempelt wurde – ein Tag ganz ohne Punches erzeugt keinen
    Cache-Eintrag, siehe docs/konzept.md Abschnitt 3.

    Was HR mit "Erledigt" abgehakt hat (DayReview), erscheint nicht mehr – solange sich der Tag
    nicht ändert. Dieselbe Regel (timesheet_service.needs_review) gilt für Monatsabschluss,
    Monatsbericht und Lohn-Export."""
    await _refresh_stale_day_cache(db, actor.tenant_id)
    today = utc_today()
    stmt = (
        select(DailySummary, Employee)
        .join(Employee, Employee.id == DailySummary.employee_id)
        .where(
            or_(
                DailySummary.status.in_(
                    [SummaryStatus.OPEN_MISSING_PUNCH, SummaryStatus.ERROR, SummaryStatus.PRESENT, SummaryStatus.ON_BREAK, SummaryStatus.ON_ERRAND]
                ),
                DailySummary.flags.is_not(None),
            ),
            Employee.tenant_id == actor.tenant_id,
            DailySummary.work_date <= today,
        )
    )
    if date_from is not None:
        stmt = stmt.where(DailySummary.work_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DailySummary.work_date <= date_to)
    if location_id is not None:
        stmt = stmt.where(Employee.location_id == location_id)
    if actor.is_supervisor_level:
        team_ids = await supervisor_team_ids(db, actor)
        stmt = stmt.where(Employee.team_id.in_(team_ids or set()))
    stmt = stmt.order_by(DailySummary.work_date.asc())

    candidates = (await db.execute(stmt)).all()
    reviews = await day_reviews(
        db,
        sorted({employee.id for _, employee in candidates}),
        min((s.work_date for s, _ in candidates), default=today),
        today,
    )
    rows = []
    for summary, employee in candidates:
        flags = summary.flags.split(",") if summary.flags else []
        if not needs_review(summary.status, flags, summary.work_date, today):
            continue
        fingerprint = day_fingerprint(summary.status, summary.target_minutes, summary.actual_minutes, flags)
        if review_valid(reviews, employee.id, summary.work_date, fingerprint):
            continue
        rows.append((summary, employee))

    # Digest-Benachrichtigung nur bei ungefiltertem Vollüberblick auslösen
    # (kein location_id-Filter, kein Supervisor mit team-beschränkter Sicht)
    # – sonst würde die Anzahl fälschlich einen Ausschnitt statt des
    # tenant-weiten Bestands widerspiegeln, siehe notify_open_days_digest.
    if location_id is None and actor.is_full_hr_level:
        await notify_open_days_digest(db, actor.tenant_id, len(rows))
        await db.commit()

    response = []
    for summary, employee in rows:
        # Zeiten mitliefern, damit HR den Sonderfall (z.B. außerplanmäßig gestempelt) direkt beurteilen kann.
        tz = await employee_timezone(db, employee)
        punches = await punches_for_day(db, employee, summary.work_date, tz)
        response.append(
            OpenDayResponse(
                employee_id=employee.id,
                first_name=employee.first_name,
                last_name=employee.last_name,
                location_id=employee.location_id,
                work_date=summary.work_date,
                status=summary.status,
                flags=summary.flags.split(",") if summary.flags else [],
                times=punch_blocks(punches, tz),
                actual_minutes=summary.actual_minutes,
            )
        )
    return response


@router.get("/timesheet/monthly-caps", response_model=list[MonthlyCapRow])
async def list_monthly_caps(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[MonthlyCapRow]:
    """Aushilfen "nach Aufwand" mit Monatsgrenze, die im laufenden Monat mindestens 90 % davon
    erreicht haben (für "Zu klären" und die Startseite)."""
    stmt = (
        select(Employee)
        .join(EmployeeDefaultShift, EmployeeDefaultShift.employee_id == Employee.id)
        .where(
            Employee.tenant_id == actor.tenant_id,
            Employee.active.is_(True),
            EmployeeDefaultShift.on_demand.is_(True),
            EmployeeDefaultShift.monthly_cap_minutes.is_not(None),
        )
        .distinct()
    )
    if actor.is_supervisor_level:
        stmt = stmt.where(Employee.team_id.in_(await supervisor_team_ids(db, actor) or set()))
    rows = []
    for employee in (await db.execute(stmt)).scalars().all():
        status = await monthly_cap_status(db, employee)
        if status.cap_minutes and status.actual_minutes >= status.cap_minutes * WARN_SHARE:
            rows.append(
                MonthlyCapRow(
                    employee_id=employee.id,
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                    cap_minutes=status.cap_minutes,
                    actual_minutes=status.actual_minutes,
                    exceeded=status.actual_minutes > status.cap_minutes,
                )
            )
    return sorted(rows, key=lambda r: (not r.exceeded, r.last_name, r.first_name))


@router.get("/timesheet/balance-limits", response_model=list[BalanceLimitRow])
async def list_balance_limits(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[BalanceLimitRow]:
    """Überstundenkonten an den Grenzen aus den Einstellungen („Zu klären“ → „Grenzen“): ab 90 % der
    Obergrenze oder unter der Untergrenze. Ohne eingestellte Grenzen leer."""
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    max_hours, min_hours = settings_row.overtime_limit_max_hours, settings_row.overtime_limit_min_hours
    if max_hours is None and min_hours is None:
        return []
    stmt = select(Employee).where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True))
    if actor.is_supervisor_level:
        stmt = stmt.where(Employee.team_id.in_(await supervisor_team_ids(db, actor) or set()))
    rows = []
    for employee in (await db.execute(stmt)).scalars().all():
        balance = (await balance_as_of(db, employee)).total_minutes
        if max_hours is not None and balance >= max_hours * 60 * WARN_SHARE:
            limit, kind, exceeded = max_hours * 60, "MAX", balance > max_hours * 60
        elif min_hours is not None and balance < min_hours * 60:
            limit, kind, exceeded = min_hours * 60, "MIN", True
        else:
            continue
        rows.append(
            BalanceLimitRow(
                employee_id=employee.id, first_name=employee.first_name, last_name=employee.last_name,
                balance_minutes=balance, limit_minutes=limit, kind=kind, exceeded=exceeded,
            )
        )
    return sorted(rows, key=lambda r: (not r.exceeded, r.last_name, r.first_name))


@router.get("/employees/{employee_id}/timesheet", response_model=list[TimesheetDay])
async def get_timesheet(
    employee_id: int,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[TimesheetDay]:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_RANGE_DAYS} Tage umfassen.")

    settings_row = await get_or_create_settings(db, employee.tenant_id)
    show_birthday = (
        settings_row.show_birthdays_in_calendar
        and employee.show_birthday_in_calendar
        and employee.birth_date is not None
    )

    tz = await employee_timezone(db, employee)
    reviews = await day_reviews(db, [employee.id], date_from, date_to)
    days: list[TimesheetDay] = []
    current = date_from
    while current <= date_to:
        calculation = await calculate_day(db, employee, current, tz)
        birthday = show_birthday and is_birthday(employee.birth_date, current)
        days.append(
            TimesheetDay(
                work_date=current,
                target_minutes=calculation.target_minutes,
                actual_minutes=calculation.actual_minutes,
                status=calculation.status,
                absence_type=calculation.absence_type,
                absence_type_id=calculation.absence_type_id,
                absence_label=calculation.absence_label,
                is_birthday=birthday,
                exceeds_max_daily_minutes=calculation.exceeds_max_daily_minutes,
                flags=calculation.flags,
                reviewed=review_valid(
                    reviews, employee.id, current,
                    day_fingerprint(calculation.status, calculation.target_minutes, calculation.actual_minutes, calculation.flags),
                ),
            )
        )
        current += timedelta(days=1)
    return days


@router.put("/employees/{employee_id}/day-reviews/{work_date}", status_code=204)
async def mark_day_reviewed(
    employee_id: int,
    work_date: date,
    payload: DayReviewRequest | None = None,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Tag aus "Zu klären" als erledigt markieren: Sonderfälle (z.B. außerplanmäßige Arbeit
    genehmigt), aber auch fehlende/widersprüchliche Stempelungen, die HR bewusst so stehen lässt –
    der Tag zählt dann mit der Zeit, die er hat (keine automatische Ergänzung)."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    calc = await calculate_day(db, employee, work_date, await employee_timezone(db, employee))
    fingerprint = day_fingerprint(calc.status, calc.target_minutes, calc.actual_minutes, calc.flags)
    existing = (
        await db.execute(select(DayReview).where(DayReview.employee_id == employee_id, DayReview.work_date == work_date))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            DayReview(
                tenant_id=actor.tenant_id,
                employee_id=employee_id,
                work_date=work_date,
                note=(payload.note.strip() or None) if payload and payload.note else None,
                reviewed_by_account_id=actor.account_id,
                fingerprint=fingerprint,
            )
        )
    else:
        # erneut abgehakt (der Tag hatte sich geändert): neuer Stand
        existing.fingerprint = fingerprint
        existing.reviewed_by_account_id = actor.account_id
    await db.commit()


@router.delete("/employees/{employee_id}/day-reviews/{work_date}", status_code=204)
async def unmark_day_reviewed(
    employee_id: int,
    work_date: date,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    review = (
        await db.execute(
            select(DayReview).where(
                DayReview.employee_id == employee_id, DayReview.work_date == work_date, DayReview.tenant_id == actor.tenant_id
            )
        )
    ).scalar_one_or_none()
    if review is not None:
        await db.delete(review)
        await db.commit()


@router.get("/employees/{employee_id}/weekly-balance", response_model=list[WeeklyBalanceWeek])
async def get_weekly_balance(
    employee_id: int,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[WeeklyBalanceWeek]:
    """Soll/Ist/Saldo pro Kalenderwoche (Mo-So) für den angeforderten Zeitraum.
    Soll kommt jetzt direkt aus der Schichtplanung (siehe
    app/services/shift_planning_service.py) und wird pro Tag aufgelöst –
    hier nur noch über die 7 Tage der Woche aufsummiert, kein separates
    Wochen-Soll-Modell mehr."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_RANGE_DAYS} Tage umfassen.")

    tz = await employee_timezone(db, employee)
    today = today_in(tz)
    weeks: list[WeeklyBalanceWeek] = []
    current = week_start(date_from)
    last_week_start = week_start(date_to)
    while current <= last_week_start:
        actual_total = 0
        target_total: int | None = None
        absence_days = 0
        holiday_days = 0
        for offset in range(7):
            if current + timedelta(days=offset) > today:
                break  # nur bis heute – künftige Tage zählen nicht ins Soll
            day_calc = await calculate_day(db, employee, current + timedelta(days=offset), tz)
            if day_calc.status == SummaryStatus.ABSENCE:
                absence_days += 1
            elif day_calc.status == SummaryStatus.HOLIDAY:
                holiday_days += 1
            if day_calc.actual_minutes is not None:
                actual_total += day_calc.actual_minutes
            if day_calc.target_minutes is not None:
                target_total = (target_total or 0) + day_calc.target_minutes
            if day_calc.flexible_share:
                target_total = (target_total or 0) + day_calc.flexible_share

        if target_total is not None:
            target_total = round(target_total)
        delta = actual_total - target_total if target_total is not None else None
        weeks.append(
            WeeklyBalanceWeek(
                week_start=current,
                week_end=current + timedelta(days=6),
                target_minutes=target_total,
                actual_minutes=actual_total,
                delta_minutes=delta,
                absence_days=absence_days,
                holiday_days=holiday_days,
            )
        )
        current += timedelta(days=7)
    return weeks


@router.get("/employees/{employee_id}/overtime-balance", response_model=OvertimeBalanceResponse)
async def get_overtime_balance(
    employee_id: int,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> OvertimeBalanceResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.device is not None and employee.location_id != actor.device.location_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.device is not None and not (await get_or_create_settings(db, actor.tenant_id)).kiosk_show_balance:
        raise AppError(403, "KIOSK_BALANCE_HIDDEN", "Der Saldo wird am Tablet nicht angezeigt.")
    if actor.employee is not None and not actor.is_hr_level and actor.employee.id != employee_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    info = await balance_as_of(db, employee)
    row = info.last_row
    return OvertimeBalanceResponse(
        employee_id=employee_id,
        balance_date=row.balance_date if row else None,
        daily_target_minutes=row.daily_target_minutes if row else None,
        daily_actual_minutes=row.daily_actual_minutes if row else None,
        daily_delta_minutes=row.daily_delta_minutes if row else None,
        running_balance_minutes=info.total_minutes,
        adjustment_minutes=info.adjustment_minutes,
        balance_start=await balance_start(db, employee),
    )
