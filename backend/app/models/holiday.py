from datetime import date

from sqlalchemy import Boolean, Column, Date, ForeignKey, Index, String, Table, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Zuordnung Feiertag <-> Standort. Keine Zeile = der Feiertag gilt für ALLE
# Standorte des Mandanten (standortübergreifend), sonst nur für die
# aufgeführten Standorte.
holiday_locations = Table(
    "holiday_locations",
    Base.metadata,
    Column("holiday_id", ForeignKey("holidays.id", ondelete="CASCADE"), primary_key=True),
    Column("location_id", ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True),
)


class Holiday(Base):
    """Feiertag im Werkskalender – wirkt wie eine Absenz (kein Soll, kein
    "zu klären"), ist aber nicht an einen einzelnen Mitarbeiter gebunden.

    Ein Feiertag steht genau einmal da und wird beliebig vielen Standorten
    zugeordnet (holiday_locations), z.B. Fronleichnam für die Standorte in
    Bayern und Baden-Württemberg. Ohne Zuordnung gilt er für alle Standorte
    (z.B. bundeseinheitliche Feiertage), siehe
    app/services/holiday_service.py. Eindeutigkeit (pro Datum überlappen sich
    die abgedeckten Standorte nicht) wird anwendungsseitig geprüft, siehe
    app/api/holidays.py und app/services/holiday_import_service.py."""

    __tablename__ = "holidays"
    __table_args__ = (Index("ix_holidays_tenant_date", "tenant_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(200))
    # Halber Feiertag (z. B. Heiligabend, Silvester): kein Feiertag im Sinne der übrigen Logik,
    # sondern ein Arbeitstag mit halbem Soll; Abwesenheiten zählen an dem Tag halb
    # (timesheet_service._half_holiday, leave_service.leave_day_weight).
    half_day: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    locations: Mapped[list["Location"]] = relationship(  # noqa: F821
        secondary=holiday_locations, lazy="selectin", order_by="Location.name"
    )

    @property
    def location_ids(self) -> list[int]:
        return sorted(location.id for location in self.locations)
