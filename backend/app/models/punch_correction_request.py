import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CorrectionRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CorrectionRequestKind(str, enum.Enum):
    # Korrektur fehlender/falscher Stempelungen ("Gehen vergessen") – übernommen als HR-Buchung
    CORRECTION = "CORRECTION"
    # Selbst eingetragene Zeiten (Stundenzettel) mit Genehmigung – übernommen als "selbst eingetragen"
    TIME_ENTRY = "TIME_ENTRY"


class PunchCorrectionRequest(Base):
    """Korrekturantrag eines Mitarbeiters ("Gehen vergessen") – HR bestätigt, erst dann werden
    die gewünschten Stempelungen als manuelle HR-Buchung angelegt, siehe
    app/api/punch_correction_requests.py. Bis dahin bleibt der Tag unverändert offen."""

    __tablename__ = "punch_correction_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[CorrectionRequestKind] = mapped_column(
        Enum(CorrectionRequestKind), default=CorrectionRequestKind.CORRECTION,
        server_default=CorrectionRequestKind.CORRECTION.value,
    )
    # JSON-Liste [{"punch_type": "GO", "time": "17:00", "next_day": false}, ...] (Ortszeit des Standorts).
    # Bei TIME_ENTRY sind es die Kommen/Gehen- (und Pausen-)Stempelungen der eingetragenen Spannen.
    items: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[CorrectionRequestStatus] = mapped_column(
        Enum(CorrectionRequestStatus), default=CorrectionRequestStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
