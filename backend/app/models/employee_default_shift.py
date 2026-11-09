from datetime import date, time

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.shift_template import BreakMode, TargetPeriod


class EmployeeDefaultShift(Base):
    """Fassung der Arbeitszeit eines Mitarbeiters für einen effektiv-datierten Zeitraum (Oberfläche:
    "Arbeitszeitmodell", mit Schichtvorlage auch "Standard-Schicht"). Genau eine aktive Fassung pro
    Mitarbeiter zu jedem Zeitpunkt – keine überlappenden valid_from/valid_to. Wochentage stehen in
    weekdays_mask (Bit 0=Montag … Bit 6=Sonntag); einzelne Ausnahmetage überschreibt ShiftPlanEntry.

    Die Fassung trägt den Vertrag selbst: Soll (target_minutes + target_period), eigene Pause und
    Kernzeit. Eine Schichtvorlage (shift_template_id) liefert nur Uhrzeiten – und, solange die
    Fassung kein eigenes Soll bzw. keine eigene Pause hat, auch diese (bisherige Standard-Schicht)."""

    __tablename__ = "employee_default_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    shift_template_id: Mapped[int | None] = mapped_column(ForeignKey("shift_templates.id"), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekdays_mask: Mapped[int] = mapped_column(Integer)
    # Optional: Soll-Minuten je Wochentag (Mo..So, kommagetrennt, z.B. "480,480,240,0,0,0,0") für
    # Teilzeit mit ungleich verteilten Stunden. Überschreibt dann das Soll der Vorlage.
    day_minutes: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Flexibel (z.B. Aushilfe): nur ein Wochensoll (Vorlagen-Soll), keine festen Arbeitstage.
    flexible: Mapped[bool] = mapped_column(Boolean, default=False)
    # Nach Aufwand (Aushilfe ohne feste Stunden): kein Soll, kein Überstundenkonto – abgerechnet werden
    # die Ist-Stunden je Monat. Optional eine Monatsgrenze (z.B. Minijob) als Warnung.
    on_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Soll der Fassung: Minuten je Tag/Woche/Monat (None = Soll der Schichtvorlage)
    target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_period: Mapped[TargetPeriod | None] = mapped_column(Enum(TargetPeriod), nullable=True)
    # Eigene Pause (break_mode None = Pause der Schichtvorlage bzw. Pausenregeln)
    break_mode: Mapped[BreakMode | None] = mapped_column(Enum(BreakMode), nullable=True)
    fixed_break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    fixed_break_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    min_break_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_break_after_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Mehrere feste Pausenzeiten ("09:00-09:15,12:00-12:30"); NULL = höchstens eine (fixed_break_start/-end)
    fixed_break_windows: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Kernzeit/Pünktlichkeit dieser Fassung: TENANT (oder leer) = wie in den Einstellungen,
    # CUSTOM = eigene Kernzeit (Beginn/Ende oder je Wochentag), NONE = keine Prüfung.
    core_time_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    core_time_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    core_time_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    core_time_days: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Gleitzeit-Rahmen: TENANT (oder leer) = wie in den Einstellungen, CUSTOM = eigener, NONE = keiner.
    flex_frame_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    flex_frame_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    flex_frame_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Eigener Rahmen je Wochentag (Format wie core_time_days, schemas/core_time.py); NULL = jeden Tag
    # flex_frame_start/-end.
    flex_frame_days: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Toleranz der Pünktlichkeitsprüfung in Minuten (leer = wie in den Einstellungen).
    late_tolerance_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Zugewiesenes Arbeitszeitmodell: Die Angaben oben kommen dann aus dessen Fassung und werden bei
    # Modelländerungen nachgezogen (leer = individuell eingetragen).
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("work_time_profiles.id"), nullable=True)

    @property
    def day_minutes_list(self) -> list[int] | None:
        return [int(v) for v in self.day_minutes.split(",")] if self.day_minutes else None

    def copy(self, **changes) -> "EmployeeDefaultShift":
        """Neue Fassung mit allen Angaben dieser (z.B. beim Teilen ab Stichtag), geänderte Felder per kwargs."""
        values = {c.key: getattr(self, c.key) for c in self.__table__.columns if c.key != "id"}
        return EmployeeDefaultShift(**{**values, **changes})
