from datetime import date

from pydantic import BaseModel, Field

from app.models.absence import AbsenceType
from app.models.daily_summary import SummaryStatus


class TimesheetDay(BaseModel):
    work_date: date
    target_minutes: int | None
    actual_minutes: int | None
    status: SummaryStatus
    absence_type: AbsenceType | None = None
    absence_type_id: int | None = None
    # Bei halben Abwesenheitstagen, z.B. "½ Urlaub" oder "½ Sonderurlaub + ½ Urlaub"
    absence_label: str | None = None
    is_birthday: bool = False
    exceeds_max_daily_minutes: bool = False
    # Sonderfälle (UNPLANNED_WORK, WORK_DURING_ABSENCE, ...) und ob HR sie als geklärt markiert hat.
    flags: list[str] = []
    reviewed: bool = False


class OpenDayResponse(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    location_id: int
    work_date: date
    status: SummaryStatus
    flags: list[str] = []
    # Gestempelte Zeiten des Tages, z.B. "08:00–12:00, 13:00–17:00"
    times: str = ""
    actual_minutes: int | None = None


class MonthlyCapRow(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    cap_minutes: int
    actual_minutes: int
    exceeded: bool


class BalanceLimitRow(BaseModel):
    """Überstundenkonto nahe an der Obergrenze (ab 90 %) oder unter der Untergrenze."""

    employee_id: int
    first_name: str
    last_name: str
    balance_minutes: int
    limit_minutes: int
    # MAX = Obergrenze, MIN = Untergrenze
    kind: str
    exceeded: bool


class DayReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class OvertimeBalanceResponse(BaseModel):
    employee_id: int
    balance_date: date | None
    daily_target_minutes: int | None
    daily_actual_minutes: int | None
    daily_delta_minutes: int | None
    # Kontostand inkl. Korrekturbuchungen (Übertrag, Auszahlung, Korrektur).
    running_balance_minutes: int
    adjustment_minutes: int = 0
    # Erster Kontotag (None = noch kein Konto: beginnt mit der ersten Stempelung)
    balance_start: date | None = None


class WeeklyBalanceWeek(BaseModel):
    week_start: date
    week_end: date
    target_minutes: int | None
    actual_minutes: int
    delta_minutes: int | None
    absence_days: int
    holiday_days: int
