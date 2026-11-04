from sqlalchemy import ForeignKey, String
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

    employees: Mapped[list["Employee"]] = relationship(back_populates="location")
    devices: Mapped[list["Device"]] = relationship(back_populates="location")
