import enum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WageTypeItem(str, enum.Enum):
    """Zeitarten mit eigener Lohnart (Seite „Lohnarten“, DATEV-Export)."""

    WORKED = "WORKED"  # gearbeitete (gestempelte) Stunden, nur bei Stundenlohn
    VACATION = "VACATION"
    SICK = "SICK"
    CHILD_SICK = "CHILD_SICK"
    SPECIAL_LEAVE = "SPECIAL_LEAVE"
    PUBLIC_HOLIDAY = "PUBLIC_HOLIDAY"  # Feiertage laut Kalender und Abwesenheiten "Feiertag"
    WORK_TIME = "WORK_TIME"  # Arbeitszeit-Angaben (z.B. Homeoffice); leer = wie gearbeitete Stunden
    OVERTIME_PAYOUT = "OVERTIME_PAYOUT"  # ausgezahlte Überstunden (Korrekturbuchung "Auszahlung")


class WageTypeMapping(Base):
    """Lohnart einer Zeitart je Mandant; ohne Zeile wird die Zeitart nicht übertragen (Hinweis)."""

    __tablename__ = "wage_type_mappings"
    __table_args__ = (UniqueConstraint("tenant_id", "item", name="uq_wage_type_mappings_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    item: Mapped[str] = mapped_column(String(20))
    wage_type: Mapped[str] = mapped_column(String(6))
