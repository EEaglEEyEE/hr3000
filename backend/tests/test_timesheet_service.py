from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceType,
    BreakRule,
    DailySummary,
    Employee,
    EmployeeDefaultShift,
    Location,
    OvertimeBalance,
    Punch,
    PunchSource,
    PunchType,
    ShiftTemplate,
    SummaryStatus,
)
from app.services.timesheet_service import calculate_day, employee_timezone, local_date, recalculate_day

MONDAY = date(2026, 8, 10)
TUESDAY = date(2026, 8, 11)
WEDNESDAY = date(2026, 8, 12)
_WEEKDAYS_MO_FR = 0b0011111


def test_local_date_uses_location_timezone() -> None:
    tz = ZoneInfo("Europe/Berlin")
    dt = datetime(2026, 8, 10, 22, 30)  # UTC, CEST = UTC+2 -> nächster Tag lokal
    assert local_date(dt, tz) == date(2026, 8, 11)


async def _seed_break_rules(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            BreakRule(min_work_minutes=360, deduct_minutes=30),
            BreakRule(min_work_minutes=540, deduct_minutes=45),
        ]
    )
    await db_session.commit()


async def _create_employee(db_session: AsyncSession, timezone: str = "UTC") -> Employee:
    location = Location(name="Standort A", timezone=timezone)
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number="EMP-1",
        active=True,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _assign_default_shift(
    db_session: AsyncSession, employee: Employee, target_minutes: int, weekdays_mask: int = _WEEKDAYS_MO_FR
) -> None:
    template = ShiftTemplate(name="Normalschicht", target_minutes=target_minutes)
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id,
            shift_template_id=template.id,
            valid_from=date(2026, 1, 1),
            weekdays_mask=weekdays_mask,
        )
    )
    await db_session.commit()


def _punch(employee: Employee, punch_type: PunchType, when: datetime) -> Punch:
    return Punch(
        employee_id=employee.id,
        location_id=employee.location_id,
        punch_type=punch_type,
        timestamp_utc=when,
        source=PunchSource.KIOSK,
    )


async def test_calculate_day_open_come_without_later_punch_is_present(
    db_session: AsyncSession,
    at_time,
) -> None:
    at_time(datetime(2026, 8, 10, 12, 0))  # Schicht läuft noch (innerhalb der maximalen Schichtlänge)
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes is None
    assert calculation.status == SummaryStatus.PRESENT


async def test_calculate_day_open_come_with_later_punch_is_missing_punch(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    # Am Folgetag wird schon wieder gestempelt -> Montag wurde offensichtlich
    # vergessen abzuschließen, kein "gerade anwesend" mehr.
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 11, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 11, 14, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes is None
    assert calculation.status == SummaryStatus.OPEN_MISSING_PUNCH


async def test_calculate_day_open_break_without_later_punch_is_on_break(
    db_session: AsyncSession,
    at_time,
) -> None:
    at_time(datetime(2026, 8, 10, 12, 0))  # Schicht läuft noch (innerhalb der maximalen Schichtlänge)
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_START, datetime(2026, 8, 10, 10, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes is None
    assert calculation.status == SummaryStatus.ON_BREAK


async def test_calculate_day_open_break_with_later_punch_is_missing_punch(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_START, datetime(2026, 8, 10, 10, 0)))
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 11, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 11, 14, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.OPEN_MISSING_PUNCH


async def test_calculate_day_double_come_is_error(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 7, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes is None
    assert calculation.status == SummaryStatus.ERROR


async def test_calculate_day_go_without_come_is_error(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 6, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.ERROR


async def test_calculate_day_break_end_without_break_start_is_error(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_END, datetime(2026, 8, 10, 10, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.ERROR


async def test_calculate_day_without_break_applies_30min_deduction(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 0)))  # 480 min gross
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.COMPLETE
    assert calculation.actual_minutes == 480 - 30


async def test_calculate_day_short_punched_break_tops_up_to_legal_minimum(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_START, datetime(2026, 8, 10, 10, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_END, datetime(2026, 8, 10, 10, 10)))  # 10 min
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 0)))  # 480 min gross
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes == 480 - 30  # gesetzliches Minimum statt gestempelter 10 Min.


async def test_calculate_day_longer_punched_break_is_used_as_is(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_START, datetime(2026, 8, 10, 10, 0)))
    db_session.add(_punch(employee, PunchType.BREAK_END, datetime(2026, 8, 10, 10, 50)))  # 50 min
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 0)))  # 480 min gross
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes == 480 - 50  # tatsächliche längere Pause zählt


async def test_calculate_day_long_shift_uses_45min_tier(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 16, 0)))  # 600 min gross
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.actual_minutes == 600 - 45


async def test_calculate_day_without_shift_plan_has_no_target(db_session: AsyncSession) -> None:
    """Kein EmployeeDefaultShift/ShiftPlanEntry -> unkonfiguriert, kein Soll
    (Rückwärtskompatibilität für Mandanten ohne Schichtplanung), siehe
    app/services/shift_planning_service.py resolve_effective_shift."""
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 0)))
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.COMPLETE
    assert calculation.actual_minutes == 480 - 30
    assert calculation.target_minutes is None


async def test_calculate_day_outside_default_shift_mask_is_planned_off(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)  # nur Mo-Fr

    tz = await employee_timezone(db_session, employee)
    saturday = date(2026, 8, 15)
    calculation = await calculate_day(db_session, employee, saturday, tz)

    assert calculation.status == SummaryStatus.PLANNED_OFF
    assert calculation.actual_minutes is None
    assert calculation.target_minutes is None


async def test_recalculate_day_writes_daily_summary_with_target(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 0)))  # 480 -30 = 450
    await db_session.commit()

    calculation = await recalculate_day(db_session, employee, MONDAY)
    assert calculation.actual_minutes == 450
    assert calculation.target_minutes == 480

    summary = (
        await db_session.execute(
            select(DailySummary).where(
                DailySummary.employee_id == employee.id, DailySummary.work_date == MONDAY
            )
        )
    ).scalar_one()
    assert summary.status == SummaryStatus.COMPLETE
    assert summary.actual_minutes == 450
    assert summary.target_minutes == 480

    balance = (
        await db_session.execute(
            select(OvertimeBalance).where(
                OvertimeBalance.employee_id == employee.id, OvertimeBalance.balance_date == MONDAY
            )
        )
    ).scalar_one()
    assert balance.daily_target_minutes == 480
    assert balance.daily_actual_minutes == 450
    assert balance.daily_delta_minutes == 450 - 480
    assert balance.running_balance_minutes == 450 - 480


async def test_recalculate_day_without_target_skips_overtime_balance(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 0)))
    await db_session.commit()

    await recalculate_day(db_session, employee, MONDAY)

    balance = (
        await db_session.execute(
            select(OvertimeBalance).where(OvertimeBalance.employee_id == employee.id)
        )
    ).scalar_one_or_none()
    assert balance is None


async def test_recalculate_day_creates_one_row_per_day_with_cascading_running_balance(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    # Montag: 510 -30 = 480 (genau Soll erfüllt)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 30)))
    # Dienstag: 530 -30 = 500 (20 Min. über Soll)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 11, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 11, 14, 50)))
    # Konto endet mit dem Austritt – macht den Test unabhängig vom heutigen Datum.
    employee.termination_date = TUESDAY
    await db_session.commit()

    await recalculate_day(db_session, employee, MONDAY)
    await recalculate_day(db_session, employee, TUESDAY)

    # Tagesgenaue Saldierung -> zwei getrennte Zeilen, nicht mehr eine
    # gemeinsame Wochen-Zeile.
    balances = (
        await db_session.execute(
            select(OvertimeBalance)
            .where(OvertimeBalance.employee_id == employee.id)
            .order_by(OvertimeBalance.balance_date.asc())
        )
    ).scalars().all()
    assert len(balances) == 2
    monday_balance, tuesday_balance = balances
    assert monday_balance.balance_date == MONDAY
    assert monday_balance.daily_delta_minutes == 0
    assert monday_balance.running_balance_minutes == 0
    assert tuesday_balance.balance_date == TUESDAY
    assert tuesday_balance.daily_delta_minutes == 20
    assert tuesday_balance.running_balance_minutes == 20  # kumuliert auf Montags-Saldo


async def test_recalculate_day_cascades_running_balance_to_later_days(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    await _seed_break_rules(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 10, 14, 30)))  # Montag: 480
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 12, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 12, 14, 30)))  # Mittwoch: 480
    employee.termination_date = WEDNESDAY
    await db_session.commit()

    await recalculate_day(db_session, employee, MONDAY)
    await recalculate_day(db_session, employee, WEDNESDAY)

    monday = (
        await db_session.execute(
            select(OvertimeBalance).where(
                OvertimeBalance.employee_id == employee.id, OvertimeBalance.balance_date == MONDAY
            )
        )
    ).scalar_one()
    wednesday = (
        await db_session.execute(
            select(OvertimeBalance).where(
                OvertimeBalance.employee_id == employee.id, OvertimeBalance.balance_date == WEDNESDAY
            )
        )
    ).scalar_one()
    assert monday.running_balance_minutes == 0
    # Dienstag ist ein Soll-Tag ohne Stempelung und ohne Abwesenheit -> zählt mit -480.
    assert wednesday.running_balance_minutes == -480

    # Korrektur: Montags-Ausstempelung 20 Min. später -> Montag +20, muss bis
    # zum Mittwoch durchkaskadieren (bulk UPDATE, siehe timesheet_service.py
    # _cascade_running_balance_from), obwohl Dienstag dazwischen keine eigene
    # Zeile hat.
    monday_go = (
        await db_session.execute(
            select(Punch)
            .where(Punch.employee_id == employee.id, Punch.punch_type == PunchType.GO)
            .order_by(Punch.timestamp_utc.asc())
        )
    ).scalars().first()
    monday_go.timestamp_utc = datetime(2026, 8, 10, 14, 50)
    await db_session.commit()

    await recalculate_day(db_session, employee, MONDAY)

    monday_after = (
        await db_session.execute(
            select(OvertimeBalance).where(
                OvertimeBalance.employee_id == employee.id, OvertimeBalance.balance_date == MONDAY
            )
        )
    ).scalar_one()
    wednesday_after = (
        await db_session.execute(
            select(OvertimeBalance).where(
                OvertimeBalance.employee_id == employee.id, OvertimeBalance.balance_date == WEDNESDAY
            )
        )
    ).scalar_one()
    assert monday_after.running_balance_minutes == 20
    assert wednesday_after.running_balance_minutes == -460  # Korrektur wirkt bis zum Mittwoch durch


async def test_recalculate_day_flips_stale_present_to_missing_punch(
    db_session: AsyncSession,
    at_time,
) -> None:
    """Der daily_summaries-Cache wird nur reaktiv für den gestempelten Tag
    aktualisiert – ein zuvor als PRESENT zwischengespeicherter Tag muss beim
    nächsten recalculate_day (für einen späteren Tag) rückwirkend auf
    OPEN_MISSING_PUNCH umspringen, siehe _recalculate_stale_present_days."""
    at_time(datetime(2026, 8, 10, 12, 0))  # Schicht läuft noch (innerhalb der maximalen Schichtlänge)
    employee = await _create_employee(db_session)
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 10, 6, 0)))
    await db_session.commit()

    await recalculate_day(db_session, employee, MONDAY)
    monday_summary = (
        await db_session.execute(
            select(DailySummary).where(
                DailySummary.employee_id == employee.id, DailySummary.work_date == MONDAY
            )
        )
    ).scalar_one()
    assert monday_summary.status == SummaryStatus.PRESENT

    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 11, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 11, 14, 0)))
    await db_session.commit()

    await recalculate_day(db_session, employee, TUESDAY)

    monday_summary_after = (
        await db_session.execute(
            select(DailySummary).where(
                DailySummary.employee_id == employee.id, DailySummary.work_date == MONDAY
            )
        )
    ).scalar_one()
    assert monday_summary_after.status == SummaryStatus.OPEN_MISSING_PUNCH


async def _create_absence_creator(db_session: AsyncSession) -> int:
    from app.models import HrRole, Account
    from app.services.auth_service import hash_password

    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


async def test_calculate_day_absence_without_punches_is_not_open(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    creator_id = await _create_absence_creator(db_session)
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=MONDAY,
            date_to=MONDAY,
            created_by_account_id=creator_id,
        )
    )
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.ABSENCE
    assert calculation.actual_minutes == 0  # kein Plan konfiguriert -> kein Soll zum Gutschreiben
    assert calculation.target_minutes is None
    assert calculation.absence_type == AbsenceType.VACATION


async def test_calculate_day_approved_absence_is_credited_with_full_target(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    creator_id = await _create_absence_creator(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.SICK,
            date_from=MONDAY,
            date_to=MONDAY,
            created_by_account_id=creator_id,
        )
    )
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.ABSENCE
    assert calculation.target_minutes == 480
    assert calculation.actual_minutes == 480  # neutral gutgeschrieben, kein Saldo-Effekt


async def test_calculate_day_pending_absence_does_not_neutralize_day(
    db_session: AsyncSession,
) -> None:
    """Eine PENDING-Absenz (Urlaubsgenehmigung erforderlich, noch nicht
    entschieden) darf den Tag NICHT neutralisieren – normales Stempeln bleibt
    Pflicht, siehe app/api/absences.py create_absence."""
    from app.models import AbsenceApprovalStatus

    employee = await _create_employee(db_session)
    creator_id = await _create_absence_creator(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=MONDAY,
            date_to=MONDAY,
            created_by_account_id=creator_id,
            approval_status=AbsenceApprovalStatus.PENDING,
        )
    )
    await db_session.commit()

    tz = await employee_timezone(db_session, employee)
    calculation = await calculate_day(db_session, employee, MONDAY, tz)

    assert calculation.status == SummaryStatus.OPEN_MISSING_PUNCH
    assert calculation.target_minutes == 480


async def test_recalculate_day_full_week_absence_is_neutral_for_overtime_balance(
    db_session: AsyncSession,
) -> None:
    employee = await _create_employee(db_session)
    creator_id = await _create_absence_creator(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=MONDAY,
            date_to=date(2026, 8, 14),
            created_by_account_id=creator_id,
        )
    )
    # Das Konto beginnt mit der ersten Stempelung (Freitag davor, genau 8 Std., keine Pausenregel).
    db_session.add(_punch(employee, PunchType.COME, datetime(2026, 8, 7, 6, 0)))
    db_session.add(_punch(employee, PunchType.GO, datetime(2026, 8, 7, 14, 0)))
    employee.termination_date = date(2026, 8, 14)
    await db_session.commit()

    await recalculate_day(db_session, employee, MONDAY)

    balance = (
        await db_session.execute(
            select(OvertimeBalance).where(
                OvertimeBalance.employee_id == employee.id, OvertimeBalance.balance_date == MONDAY
            )
        )
    ).scalar_one()
    assert balance.daily_delta_minutes == 0
    assert balance.running_balance_minutes == 0

    summary = (
        await db_session.execute(
            select(DailySummary).where(
                DailySummary.employee_id == employee.id, DailySummary.work_date == MONDAY
            )
        )
    ).scalar_one()
    assert summary.status == SummaryStatus.ABSENCE
