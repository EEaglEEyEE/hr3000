import enum
from datetime import time

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BreakMode(str, enum.Enum):
    FIXED = "FIXED"
    FLEXIBLE = "FLEXIBLE"


class TargetPeriod(str, enum.Enum):
    """Bezugszeitraum von ShiftTemplate.target_minutes. DAILY (Standard):
    Minuten für genau diesen einen Arbeitstag, unverändertes Altverhalten.
    WEEKLY/MONTHLY: Minuten für die ganze Woche/den ganzen Kalendermonat,
    gleichmäßig auf die durch EmployeeDefaultShift.weekdays_mask
    abgedeckten Wochentage verteilt (Rest zuerst auf die frühesten Tage),
    siehe app/services/shift_planning_service.py resolve_effective_shift.
    Nur für EmployeeDefaultShift sinnvoll – ein einzelner ShiftPlanEntry-Tag
    kann kein Wochen-/Monatssoll repräsentieren, siehe
    app/api/shift_plan_entries.py upsert_shift_plan_entry."""

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class ShiftTemplate(Base):
    """Wiederverwendbare Schicht-Vorlage (z.B. "Frühschicht"), zugewiesen über
    EmployeeDefaultShift/ShiftPlanEntry. Ersetzt WorkTimeModelTemplate.

    start_time/end_time sind bewusst NULLABLE: aus der Migration bestehender
    WorkTimeModel-Daten (siehe scripts/migrate_work_time_models.py) lassen
    sich keine echten Schichtzeiten ableiten – ein erfundener Platzhalter
    wäre gefährlicher als ein sichtbares NULL, siehe
    app/services/shift_planning_service.py check_rest_period_*."""

    __tablename__ = "shift_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_shift_templates_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_mode: Mapped[BreakMode] = mapped_column(Enum(BreakMode), default=BreakMode.FLEXIBLE)
    # Nur bei break_mode=FIXED relevant: festes Pausenfenster wird automatisch
    # abgezogen, ohne dass gestempelt werden muss.
    fixed_break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    fixed_break_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Nur bei break_mode=FLEXIBLE relevant: Mindestpause, falls der
    # Mitarbeiter selbst keine/zu wenig Pause stempelt (wie break_rules,
    # aber pro Vorlage statt gesetzlicher Staffel).
    min_break_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_minutes: Mapped[int] = mapped_column(Integer, default=0)
    target_period: Mapped[TargetPeriod] = mapped_column(Enum(TargetPeriod), default=TargetPeriod.DAILY)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    # Automatisch erzeugte Vorlage hinter einem Arbeitszeitmodell (Wochenstunden
    # ohne Zeiten), siehe app/api/work_time_model.py – wird in der Schichtvorlagen-
    # Verwaltung ausgeblendet.
    is_work_time_model: Mapped[bool] = mapped_column(Boolean, default=False)
    # Alte Fassung nach einer Soll-Änderung ab Stichtag (siehe app/api/shift_templates.py):
    # bleibt für die Vergangenheit zugeordnet, wird in der Verwaltung ausgeblendet.
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
