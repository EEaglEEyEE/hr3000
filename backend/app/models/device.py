from datetime import datetime, time

from sqlalchemy import DateTime, ForeignKey, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Device(Base):
    """Registriertes Kiosk-Tablet, authentifiziert über Device-Token."""

    __tablename__ = "devices"
    # device_token ist nur innerhalb eines Tenants eindeutig, nicht global.
    __table_args__ = (UniqueConstraint("tenant_id", "token_hash", name="uq_devices_tenant_token_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    # SHA-256 des Geräte-Tokens (das Token selbst kennt nur das Tablet; neu nur durch Koppeln).
    token_hash: Mapped[str] = mapped_column(String(64))
    # Bindung an genau ein Tablet: SHA-256 der Installations-ID des Tablets, das sich zuerst bzw.
    # beim Koppeln angemeldet hat. Andere Geräte mit demselben Token werden abgewiesen.
    installation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Letzter abgewiesener Anmeldeversuch eines anderen Geräts (für Warnung und Anzeige)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    # Gerätename im MDM (z. B. NB-FRA-01): Meldet sich ein noch nie benutzter Eintrag per
    # Registrierungsschlüssel mit diesem Namen, wird er ohne Freigabe gebunden (siehe DeviceEnrollment).
    mdm_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    location: Mapped["Location"] = relationship(back_populates="devices")


class DeviceEnrollmentKey(Base):
    """Registrierungsschlüssel eines Standorts: Das MDM verteilt ihn in der Start-URL der Kiosk-App
    (``#enroll=…``), Tablets richten sich damit selbst ein. Gespeichert nur als SHA-256, angezeigt
    einmal beim Erzeugen. Ein Schlüssel je Standort; Erneuern ersetzt, Löschen sperrt."""

    __tablename__ = "device_enrollment_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    # None = unbefristet
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceEnrollment(Base):
    """Offene Registrierung: ein Gerät mit gültigem Schlüssel, das keinem vorbereiteten Tablet-Eintrag
    zugeordnet werden konnte. Es hat schon ein Token (nur als Hash hier), die Anmeldung damit ist aber
    gesperrt (DEVICE_PENDING), bis Admin/HR es in der Webapp freigibt."""

    __tablename__ = "device_enrollments"
    __table_args__ = (UniqueConstraint("tenant_id", "installation_hash", name="uq_device_enrollments_installation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    # Vom Gerät gemeldeter Name (MDM-Platzhalter oder Skript) – ungeprüft, nur Anzeige und Zuordnung
    reported_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Prüfcode, den das Gerät auf dem Bildschirm zeigt (Abgleich vor der Freigabe)
    verify_code: Mapped[str] = mapped_column(String(7))
    installation_hash: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
