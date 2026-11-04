import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
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


class Notification(Base):
    """In-App-Benachrichtigung (kein E-Mail-Versand – dafür wäre ein
    SMTP-Server samt Zugangsdaten nötig, die es in dieser Umgebung nicht
    gibt; die Glocke im HR-Webapp-Header, siehe hr-webapp, deckt den
    eigentlichen Bedarf "wer muss worauf reagieren" bereits ab).

    Dual-Recipient wie überall sonst im Projekt (HrUser ODER Employee mit
    hr_role/Self-Service-Login, genau einer von beiden), siehe
    app/services/notification_service.py."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    recipient_hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    recipient_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    message: Mapped[str] = mapped_column(String(500))
    related_absence_id: Mapped[int | None] = mapped_column(ForeignKey("absences.id"), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
