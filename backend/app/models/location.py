from sqlalchemy import Double, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64))
    # Bundesland-Kürzel (siehe app/services/holiday_calendar.py) – überschreibt
    # AppSettings.default_bundesland beim Feiertags-Import für diesen Standort.
    bundesland: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Kreis für die Standortprüfung beim Stempeln im Web-Login (A18): Mittelpunkt und Radius in Metern,
    # alle drei gesetzt oder alle leer (= kein Kreis). Firmendaten, keine Mitarbeiterpositionen.
    geo_latitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    geo_longitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    geo_radius_m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def has_geofence(self) -> bool:
        return self.geo_latitude is not None and self.geo_longitude is not None and self.geo_radius_m is not None

    employees: Mapped[list["Employee"]] = relationship(back_populates="location")
    devices: Mapped[list["Device"]] = relationship(back_populates="location")
