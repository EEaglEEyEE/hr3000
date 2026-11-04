from datetime import datetime, time

from sqlalchemy import DateTime, ForeignKey, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Device(Base):
    """Registriertes Kiosk-Tablet, authentifiziert über Device-Token."""

    __tablename__ = "devices"
    # device_token ist nur innerhalb eines Tenants eindeutig, nicht global.
    __table_args__ = (UniqueConstraint("tenant_id", "device_token", name="uq_devices_tenant_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    device_token: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Darstellung dieses Tablets: DARK | LIGHT, NULL = Standard des Mandanten (Einstellungen → Kiosk)
    theme: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Bildschirmzeiten dieses Tablets: NULL = wie Mandant, ALWAYS = immer an, CUSTOM = eigene Zeiten
    screen_hours_mode: Mapped[str | None] = mapped_column(String(7), nullable=True)
    screen_on_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    screen_on_until: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Kurzer Kopplungscode zum Einrichten statt des langen Tokens (SHA-256, einmalig, läuft ab)
    pairing_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pairing_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    location: Mapped["Location"] = relationship(back_populates="devices")
