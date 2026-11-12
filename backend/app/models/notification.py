import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationType(str, enum.Enum):
    ABSENCE_REQUESTED = "ABSENCE_REQUESTED"
    ABSENCE_DECIDED = "ABSENCE_DECIDED"
    OPEN_DAYS_DIGEST = "OPEN_DAYS_DIGEST"
    PERIOD_SUBMITTED = "PERIOD_SUBMITTED"
    PERIOD_DISPUTED = "PERIOD_DISPUTED"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"
    CORRECTION_DECIDED = "CORRECTION_DECIDED"
    # Jemand ist als Vertretung einer (genehmigten) Abwesenheit eingetragen.
    SUBSTITUTE_ASSIGNED = "SUBSTITUTE_ASSIGNED"
    # Erinnerung (Probezeit, Befristung, Austritt, verfallender Urlaub)
    REMINDER = "REMINDER"
    # Ein weiteres Gerät wollte sich mit dem Zugang eines Tablets anmelden (abgewiesen)
    DEVICE_ALERT = "DEVICE_ALERT"
    # Mitarbeiter schlägt eine Änderung eigener Daten vor bzw. die Entscheidung dazu
    DATA_CHANGE_REQUESTED = "DATA_CHANGE_REQUESTED"
    DATA_CHANGE_DECIDED = "DATA_CHANGE_DECIDED"
    # Mitarbeiter hat selbst ein Dokument hochgeladen
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    # Hinweisgebersystem: neue Meldung/Nachricht oder Frist – nur an Meldestellen-Beauftragte
    WHISTLEBLOWING = "WHISTLEBLOWING"
    # Neue Bewerbung über die Karriereseite (an das Hiring Team der Stelle)
    RECRUITING_APPLICATION = "RECRUITING_APPLICATION"


class Notification(Base):
    """In-App-Benachrichtigung (Glocke in der Webapp) an ein Konto; zusätzlich per E-Mail, wenn ein
    Mailversand eingerichtet ist und das Konto Mails will, siehe app/services/notification_service.py."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_account", "tenant_id", "recipient_account_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    recipient_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    message: Mapped[str] = mapped_column(String(500))
    related_absence_id: Mapped[int | None] = mapped_column(ForeignKey("absences.id"), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
