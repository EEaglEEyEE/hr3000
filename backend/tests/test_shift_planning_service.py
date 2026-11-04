from datetime import date, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (
    BreakMode,
    Employee,
    EmployeeDefaultShift,
    Location,
    ShiftPlanEntry,
    ShiftTemplate,
    TargetPeriod,
)
from app.services.shift_planning_service import (
    check_max_daily_working_time,
    check_rest_period_for_default,
    check_rest_period_for_entry,
    resolve_effective_shift,
)

_MO_FR = 0b0011111


async def _create_employee(db_session: AsyncSession) -> Employee:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    employee = Employee(
        location_id=location.id, first_name="Max", last_name="Mustermann", employee_number="EMP-1", active=True
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_template(
    db_session: AsyncSession,
    name: str = "Frühschicht",
    start: time | None = time(6, 0),
    end: time | None = time(14, 0),
    target_minutes: int = 480,
    target_period: TargetPeriod = TargetPeriod.DAILY,
) -> ShiftTemplate:
    template = ShiftTemplate(
        name=name,
        start_time=start,
        end_time=end,
        break_mode=BreakMode.FLEXIBLE,
        target_minutes=target_minutes,
        target_period=target_period,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_resolve_effective_shift_unconfigured_employee(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)

    plan = await resolve_effective_shift(db_session, employee.id, date(2026, 8, 10))

    assert plan.plan_exists is False
    assert plan.is_workday is True
    assert plan.target_minutes is None
    assert plan.from_entry is False


async def test_resolve_effective_shift_uses_default_on_matching_weekday(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session)
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id, shift_template_id=template.id, valid_from=date(2026, 8, 1), weekdays_mask=_MO_FR
        )
    )
    await db_session.commit()

    monday = date(2026, 8, 10)
    plan = await resolve_effective_shift(db_session, employee.id, monday)
    assert plan.plan_exists is True
    assert plan.is_workday is True
    assert plan.target_minutes == 480
    assert plan.start_time == time(6, 0)
    assert plan.from_entry is False

    saturday = date(2026, 8, 15)
    weekend_plan = await resolve_effective_shift(db_session, employee.id, saturday)
    assert weekend_plan.plan_exists is True
    assert weekend_plan.is_workday is False
    assert weekend_plan.from_entry is False


async def test_resolve_effective_shift_entry_overrides_default(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session)
    other_template = await _create_template(db_session, name="Spätschicht", start=time(14, 0), end=time(22, 0))
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id, shift_template_id=template.id, valid_from=date(2026, 8, 1), weekdays_mask=_MO_FR
        )
    )
    db_session.add(
        ShiftPlanEntry(
            employee_id=employee.id,
            date=date(2026, 8, 10),
            shift_template_id=other_template.id,
            is_workday=True,
            target_minutes=480,
        )
    )
    await db_session.commit()

    plan = await resolve_effective_shift(db_session, employee.id, date(2026, 8, 10))
    assert plan.shift_template_id == other_template.id
    assert plan.start_time == time(14, 0)
    assert plan.from_entry is True


async def test_resolve_effective_shift_explicit_day_off_entry(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    db_session.add(
        ShiftPlanEntry(employee_id=employee.id, date=date(2026, 8, 10), is_workday=False)
    )
    await db_session.commit()

    plan = await resolve_effective_shift(db_session, employee.id, date(2026, 8, 10))
    assert plan.plan_exists is True
    assert plan.is_workday is False
    assert plan.from_entry is True


async def test_check_rest_period_for_entry_rejects_short_gap(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    late_template = await _create_template(db_session, name="Spät", start=time(14, 0), end=time(23, 0))
    db_session.add(
        ShiftPlanEntry(
            employee_id=employee.id,
            date=date(2026, 8, 10),
            shift_template_id=late_template.id,
            is_workday=True,
            target_minutes=480,
        )
    )
    await db_session.commit()

    early_template = await _create_template(db_session, name="Früh", start=time(6, 0), end=time(14, 0))
    try:
        await check_rest_period_for_entry(
            db_session, employee.id, date(2026, 8, 11), early_template.start_time, early_template.end_time
        )
        assert False, "Erwartete REST_PERIOD_VIOLATION"
    except AppError as exc:
        assert exc.code == "REST_PERIOD_VIOLATION"


async def test_check_rest_period_for_entry_skips_without_times(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    # Sollte nicht werfen, da keine Zeiten vorhanden sind (z.B. migrierte Vorlage).
    await check_rest_period_for_entry(db_session, employee.id, date(2026, 8, 10), None, None)


async def test_check_rest_period_for_default_rejects_self_overlapping_mask(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    # 06:00-22:00 (16h-Schicht) an aufeinanderfolgenden Tagen: nur 8h Ruhezeit
    # bis zum nächsten Schichtbeginn -> Verstoß (< 11h).
    template = await _create_template(db_session, name="Lang", start=time(6, 0), end=time(22, 0))
    try:
        await check_rest_period_for_default(
            db_session, employee.id, template, _MO_FR, date(2026, 8, 3), None
        )
        assert False, "Erwartete REST_PERIOD_VIOLATION"
    except AppError as exc:
        assert exc.code == "REST_PERIOD_VIOLATION"


async def test_check_rest_period_for_default_allows_sufficient_gap(db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session, name="Frueh", start=time(6, 0), end=time(14, 0))
    await check_rest_period_for_default(db_session, employee.id, template, _MO_FR, date(2026, 8, 3), None)


async def test_resolve_effective_shift_distributes_weekly_target_with_remainder(
    db_session: AsyncSession,
) -> None:
    # 2003 Minuten auf 5 Werktage (Mo-Fr): 400 Basis + Rest 3 -> Mo/Di/Mi
    # bekommen 401, Do/Fr bekommen 400 (Summe bleibt exakt 2003).
    employee = await _create_employee(db_session)
    template = await _create_template(
        db_session, target_minutes=2003, target_period=TargetPeriod.WEEKLY
    )
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id, shift_template_id=template.id, valid_from=date(2026, 8, 1), weekdays_mask=_MO_FR
        )
    )
    await db_session.commit()

    week = [date(2026, 8, 10 + i) for i in range(5)]  # Mo..Fr
    plans = [await resolve_effective_shift(db_session, employee.id, day) for day in week]

    assert [p.target_minutes for p in plans] == [401, 401, 401, 400, 400]
    assert sum(p.target_minutes for p in plans) == 2003


async def test_resolve_effective_shift_distributes_monthly_target_per_calendar_month(
    db_session: AsyncSession,
) -> None:
    # August 2026, Mo-Fr-Maske: 21 zutreffende Tage (5x Mo, je 4x Di-Fr).
    # 2110 Minuten / 21 -> Basis 100, Rest 10: die ersten 10 Tage (Datum-
    # Reihenfolge) bekommen 101, der Rest 100.
    employee = await _create_employee(db_session)
    template = await _create_template(
        db_session, target_minutes=2110, target_period=TargetPeriod.MONTHLY
    )
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id, shift_template_id=template.id, valid_from=date(2026, 8, 1), weekdays_mask=_MO_FR
        )
    )
    await db_session.commit()

    matching_days_in_august = [
        date(2026, 8, d)
        for d in range(1, 32)
        if date(2026, 8, d).weekday() < 5
    ]
    assert len(matching_days_in_august) == 21

    plans = [
        await resolve_effective_shift(db_session, employee.id, day) for day in matching_days_in_august
    ]
    assert [p.target_minutes for p in plans[:10]] == [101] * 10
    assert [p.target_minutes for p in plans[10:]] == [100] * 11
    assert sum(p.target_minutes for p in plans) == 2110


def test_check_max_daily_working_time_allows_exactly_ten_hours() -> None:
    # Grenzfall: 10:00 Stunden exakt ist noch zulässig (>, nicht >=).
    check_max_daily_working_time(time(6, 0), time(16, 0))


def test_check_max_daily_working_time_rejects_over_ten_hours() -> None:
    try:
        check_max_daily_working_time(time(6, 0), time(16, 1))
        assert False, "Erwartete MAX_DAILY_WORKING_TIME_EXCEEDED"
    except AppError as exc:
        assert exc.code == "MAX_DAILY_WORKING_TIME_EXCEEDED"


def test_check_max_daily_working_time_handles_overnight_shift() -> None:
    # 22:00-06:00 überspannt Mitternacht -> 8 Stunden, zulässig.
    check_max_daily_working_time(time(22, 0), time(6, 0))
    # 20:00-07:00 überspannt Mitternacht -> 11 Stunden, unzulässig.
    try:
        check_max_daily_working_time(time(20, 0), time(7, 0))
        assert False, "Erwartete MAX_DAILY_WORKING_TIME_EXCEEDED"
    except AppError as exc:
        assert exc.code == "MAX_DAILY_WORKING_TIME_EXCEEDED"


def test_check_max_daily_working_time_skips_without_times() -> None:
    # Sollte nicht werfen, da keine Zeiten vorhanden sind (z.B. migrierte Vorlage).
    check_max_daily_working_time(None, None)
