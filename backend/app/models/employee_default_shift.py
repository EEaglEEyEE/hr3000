from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmployeeDefaultShift(Base):
    """Standard-Zuordnung Schicht-Vorlage -> Mitarbeiter für einen
    effektiv-datierten Zeitraum. Genau eine aktive Zuordnung pro Mitarbeiter
    zu jedem Zeitpunkt – keine überlappenden valid_from/valid_to (App-Ebene,
    siehe app/api/employee_default_shifts.py, exakt das bestehende Muster aus
    app/api/work_time_models.py). Wochentage, an denen diese Vorlage greift,
    stehen in weekdays_mask (Bit 0=Montag … Bit 6=Sonntag); einzelne
    Ausnahmetage überschreibt ShiftPlanEntry."""

    __tablename__ = "employee_default_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    shift_template_id: Mapped[int] = mapped_column(ForeignKey("shift_templates.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekdays_mask: Mapped[int] = mapped_column(Integer)
    # Optional: Soll-Minuten je Wochentag (Mo..So, kommagetrennt, z.B. "480,480,240,0,0,0,0") für
    # Teilzeit mit ungleich verteilten Stunden. Überschreibt dann das Soll der Vorlage.
    day_minutes: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Flexibel (z.B. Aushilfe): nur ein Wochensoll (Vorlagen-Soll), keine festen Arbeitstage.
    flexible: Mapped[bool] = mapped_column(Boolean, default=False)
    # Nach Aufwand (Aushilfe ohne feste Stunden): kein Soll, kein Gleitzeitkonto – abgerechnet werden
    # die Ist-Stunden je Monat. Optional eine Monatsgrenze (z.B. Minijob) als Warnung.
    on_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def day_minutes_list(self) -> list[int] | None:
        return [int(v) for v in self.day_minutes.split(",")] if self.day_minutes else None
