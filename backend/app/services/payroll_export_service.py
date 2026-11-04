from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AbsenceType, Employee, SummaryStatus
from app.services.timesheet_service import absence_day_counts, calculate_day, employee_timezone, today_in


@dataclass
class PayrollSummary:
    """Aggregat über einen Zeitraum für einen Mitarbeiter – dieselbe
    Tages-Auflösung (calculate_day) wie Kalender/Timesheet/PDF-Export, damit
    alle Darstellungen immer übereinstimmen. open_or_error_days ist bewusst
    ein eigenes Feld: HR muss diese Tage vor dem Lohnlauf klären, ein
    Lohn-Export mit unklaren Tagen sollte nicht kommentarlos verbucht werden."""

    employee: Employee
    target_minutes: int
    actual_minutes: int
    # Halbe Abwesenheitstage zählen 0,5
    vacation_days: float
    sick_days: float
    special_leave_days: float
    unpaid_days: float
    time_off_days: float
    child_sick_days: float
    # Feiertage laut Kalender + Abwesenheiten der Kategorie "Feiertag" (z.B. Feiertag GfB)
    holiday_days: float
    open_or_error_days: int


async def summarize_payroll(
    db: AsyncSession, employee: Employee, date_from: date, date_to: date
) -> PayrollSummary:
    tz = await employee_timezone(db, employee)
    target_minutes = 0
    actual_minutes = 0
    days: dict[AbsenceType, float] = {category: 0.0 for category in AbsenceType}
    holiday_days = 0
    open_or_error_days = 0

    # Nur bis heute: künftige Tage haben noch kein Ist und dürfen das Soll nicht belasten.
    date_to = min(date_to, today_in(tz))
    current = date_from
    while current <= date_to:
        calculation = await calculate_day(db, employee, current, tz)
        target_minutes += calculation.target_minutes or 0
        actual_minutes += calculation.actual_minutes or 0

        for category, count in absence_day_counts(calculation).items():
            days[category] += count
        if calculation.status == SummaryStatus.HOLIDAY:
            holiday_days += 1
        elif calculation.status in (SummaryStatus.OPEN_MISSING_PUNCH, SummaryStatus.ERROR):
            open_or_error_days += 1

        current += timedelta(days=1)

    return PayrollSummary(
        employee=employee,
        target_minutes=target_minutes,
        actual_minutes=actual_minutes,
        vacation_days=days[AbsenceType.VACATION],
        sick_days=days[AbsenceType.SICK],
        special_leave_days=days[AbsenceType.SPECIAL_LEAVE],
        unpaid_days=days[AbsenceType.UNPAID],
        time_off_days=days[AbsenceType.TIME_OFF_IN_LIEU],
        child_sick_days=days[AbsenceType.CHILD_SICK],
        holiday_days=holiday_days + days[AbsenceType.PUBLIC_HOLIDAY],
        open_or_error_days=open_or_error_days,
    )
