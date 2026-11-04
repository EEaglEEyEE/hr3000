from datetime import date

from pydantic import BaseModel

from app.models.absence import AbsenceType
from app.models.daily_summary import SummaryStatus


class TeamCalendarDay(BaseModel):
    date: date
    # Nur HOLIDAY oder ABSENCE werden hier je gesetzt (siehe
    # app/api/team_calendar.py) – None bedeutet "kein Feiertag, keine
    # genehmigte Absenz", unabhängig davon ob überhaupt gearbeitet wurde.
    status: SummaryStatus | None
    absence_type: AbsenceType | None
    absence_type_id: int | None = None
    # Nur ein halber Tag abwesend (die andere Hälfte wird gearbeitet)
    half_day: bool = False
    # Bei halben Tagen, z.B. "½ Urlaub" oder "½ Sonderurlaub + ½ Urlaub"
    absence_label: str | None = None
    # Geburtstag (nur wenn in den Einstellungen und am Mitarbeiter freigegeben)
    is_birthday: bool = False


class TeamCalendarEmployee(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    team_id: int | None
    days: list[TeamCalendarDay]
