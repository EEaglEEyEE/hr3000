import enum
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SummaryStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    OPEN_MISSING_PUNCH = "OPEN_MISSING_PUNCH"
    ABSENCE = "ABSENCE"
    PRESENT = "PRESENT"
    ON_BREAK = "ON_BREAK"
    # Gerade auf Dienstgang (zählt als Arbeitszeit)
    ON_ERRAND = "ON_ERRAND"
    ERROR = "ERROR"
    HOLIDAY = "HOLIDAY"
    # Laut Schichtplan kein Arbeitstag – siehe app/services/shift_planning_service.py
    # resolve_effective_shift. Verhindert, dass solche Tage fälschlich als
    # OPEN_MISSING_PUNCH markiert werden.
    PLANNED_OFF = "PLANNED_OFF"


class DailySummary(Base):
    """Optionaler Cache der Ist-Zeit-Berechnung pro Tag, siehe Konzept Abschnitt 3."""

    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("employee_id", "work_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    work_date: Mapped[date] = mapped_column(Date)
    actual_minutes: Mapped[int | None] = mapped_column(nullable=True)
    target_minutes: Mapped[int] = mapped_column()
    status: Mapped[SummaryStatus] = mapped_column(Enum(SummaryStatus))
    # Kommagetrennte Sonderfälle (siehe timesheet_service.DayFlag), z.B. "UNPLANNED_WORK".
    flags: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Tag eines flexiblen Modells, dessen Tage der Mandant nicht melden lässt (AppSettings.
    # report_flexible_days aus): Status und Zeiten bleiben, "offen" ist der Tag nur noch mit einem Hinweis
    # in flags ("Wochensoll nicht erreicht") – siehe timesheet_service.needs_review.
    review_exempt: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
