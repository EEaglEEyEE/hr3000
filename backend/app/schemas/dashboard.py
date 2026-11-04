from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.daily_summary import SummaryStatus


class DashboardEvent(BaseModel):
    date: date
    # Mehrtägige Abwesenheit: letzter Tag
    date_to: date | None = None
    kind: Literal["HOLIDAY", "ABSENCE", "PENDING_ABSENCE", "BIRTHDAY"]
    title: str
    employee_id: int | None = None
    employee_name: str | None = None
    color: str | None = None


class DashboardMe(BaseModel):
    employee_id: int
    first_name: str
    balance_minutes: int
    balance_date: date | None
    vacation_year: int
    vacation_remaining_days: float
    vacation_expiring_days: float = 0
    vacation_expiry_date: date | None = None
    today_status: SummaryStatus | None
    today_times: str = ""
    today_actual_minutes: int | None = None
    week_target_minutes: int = 0
    week_actual_minutes: int = 0
    pending_absences: int = 0
    pending_corrections: int = 0
    # Aushilfe "nach Aufwand": Ist-Stunden im laufenden Monat statt Soll/Saldo, ggf. mit Grenze
    on_demand: bool = False
    # Stempeln über den Web-Login freigeschaltet und welche Aktionen angeboten werden
    portal_punching: bool = False
    break_buttons: bool = True
    errand_buttons: bool = False
    month_actual_minutes: int | None = None
    monthly_cap_minutes: int | None = None


class DashboardPerson(BaseModel):
    employee_id: int
    name: str
    detail: str | None = None
    color: str | None = None


class DashboardTeam(BaseModel):
    present: list[DashboardPerson]
    on_break: list[DashboardPerson]
    on_errand: list[DashboardPerson] = []
    absent: list[DashboardPerson]
    visible_employees: int


class DashboardResponse(BaseModel):
    me: DashboardMe | None
    team: DashboardTeam | None
    events: list[DashboardEvent]
    # Letzter Tag, bis zu dem Termine aufgelistet sind
    horizon_date: date | None = None
    # Mandanten-Schalter, die die Startseite auch ohne verknüpften Mitarbeiter braucht
    portal_punching_enabled: bool = False
    absence_requests_enabled: bool = True
