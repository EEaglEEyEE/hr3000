from datetime import date, time

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.shift_template import BreakMode, TargetPeriod

# Erste Fassung eines Modells gilt "von Anfang an", damit es auch rückwirkend (z.B. ab Eintritt)
# zugewiesen werden kann.
PROFILE_START = date(2000, 1, 1)


class WorkTimeProfile(Base):
    """Arbeitszeitmodell eines Mandanten (z.B. "Vollzeit Büro"), das Mitarbeitern zugewiesen wird.
    Die Angaben stehen in effektiv-datierten Fassungen (WorkTimeProfileVersion). Eine Zuweisung ist
    eine Fassung der Arbeitszeit (EmployeeDefaultShift) mit profile_id – deren Angaben werden aus
    der Modell-Fassung übernommen und bei jeder Modelländerung nachgezogen (siehe
    app/services/work_time_profile_service.py)."""

    __tablename__ = "work_time_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_work_time_profiles_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    # Archiviert: nicht mehr neu zuweisbar; bestehende Zuweisungen gelten weiter.
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkTimeProfileVersion(Base):
    """Fassung eines Arbeitszeitmodells für einen Zeitraum – dieselben Angaben wie eine Fassung der
    Arbeitszeit eines Mitarbeiters (Arbeitstage, Art, Soll, Pause, Kernzeit, Schichtvorlage für die
    Uhrzeiten), dazu Gleitzeit-Rahmen und Pünktlichkeits-Toleranz."""

    __tablename__ = "work_time_profile_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("work_time_profiles.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    shift_template_id: Mapped[int | None] = mapped_column(ForeignKey("shift_templates.id"), nullable=True)
    weekdays_mask: Mapped[int] = mapped_column(Integer)
    day_minutes: Mapped[str | None] = mapped_column(String(60), nullable=True)
    flexible: Mapped[bool] = mapped_column(Boolean, default=False)
    on_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_period: Mapped[TargetPeriod | None] = mapped_column(Enum(TargetPeriod), nullable=True)
    break_mode: Mapped[BreakMode | None] = mapped_column(Enum(BreakMode), nullable=True)
    fixed_break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    fixed_break_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    min_break_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_break_after_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Mehrere feste Pausenzeiten ("09:00-09:15,12:00-12:30"); NULL = höchstens eine (fixed_break_start/-end)
    fixed_break_windows: Mapped[str | None] = mapped_column(String(100), nullable=True)
    core_time_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    core_time_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    core_time_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    core_time_days: Mapped[str | None] = mapped_column(String(100), nullable=True)
    flex_frame_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    flex_frame_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    flex_frame_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    flex_frame_days: Mapped[str | None] = mapped_column(String(100), nullable=True)
    late_tolerance_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def day_minutes_list(self) -> list[int] | None:
        return [int(v) for v in self.day_minutes.split(",")] if self.day_minutes else None

    def copy(self, **changes) -> "WorkTimeProfileVersion":
        """Neue Fassung mit allen Angaben dieser (z.B. beim Teilen ab Stichtag)."""
        values = {c.key: getattr(self, c.key) for c in self.__table__.columns if c.key != "id"}
        return WorkTimeProfileVersion(**{**values, **changes})
