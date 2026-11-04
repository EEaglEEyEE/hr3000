from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, EmployeeDefaultShift
from app.services.timesheet_service import calculate_day, employee_timezone, today_in

# Ab diesem Anteil der Monatsgrenze wird gewarnt (Vorwarnung), darüber gilt sie als überschritten.
WARN_SHARE = 0.9


@dataclass
class MonthlyCapStatus:
    on_demand: bool
    cap_minutes: int | None
    actual_minutes: int  # Ist-Stunden im laufenden Monat bis heute


async def active_model(db: AsyncSession, employee_id: int, on: date) -> EmployeeDefaultShift | None:
    rows = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.employee_id == employee_id, EmployeeDefaultShift.valid_from <= on
            )
        )
    ).scalars().all()
    return next((d for d in rows if d.valid_to is None or d.valid_to >= on), None)


async def monthly_cap_status(db: AsyncSession, employee: Employee) -> MonthlyCapStatus:
    """Für Aushilfen "nach Aufwand": gearbeitete Stunden im laufenden Monat und ggf. die Grenze."""
    tz = await employee_timezone(db, employee)
    today = today_in(tz)
    model = await active_model(db, employee.id, today)
    if model is None or not model.on_demand:
        return MonthlyCapStatus(False, None, 0)
    actual = 0
    day = today.replace(day=1)
    while day <= today:
        actual += (await calculate_day(db, employee, day, tz)).actual_minutes or 0
        day += timedelta(days=1)
    return MonthlyCapStatus(True, model.monthly_cap_minutes, actual)
