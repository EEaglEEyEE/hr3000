import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CorrectionRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PunchCorrectionRequest(Base):
    """Korrekturantrag eines Mitarbeiters ("Gehen vergessen") – HR bestätigt, erst dann werden
    die gewünschten Stempelungen als manuelle HR-Buchung angelegt, siehe
    app/api/punch_correction_requests.py. Bis dahin bleibt der Tag unverändert offen."""

    __tablename__ = "punch_correction_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    # JSON-Liste [{"punch_type": "GO", "time": "17:00", "next_day": false}, ...] (Ortszeit des Standorts)
    items: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[CorrectionRequestStatus] = mapped_column(
        Enum(CorrectionRequestStatus), default=CorrectionRequestStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
