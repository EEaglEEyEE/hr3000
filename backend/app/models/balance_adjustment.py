import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdjustmentKind(str, enum.Enum):
    OPENING_BALANCE = "OPENING_BALANCE"  # Übertrag aus Altsystem/Vorjahr
    PAYOUT = "PAYOUT"  # Überstunden ausgezahlt (negativ)
    CORRECTION = "CORRECTION"  # sonstige Korrektur, Begründung Pflicht


class BalanceAdjustment(Base):
    """Manuelle Buchung auf dem Gleitzeitkonto. Unveränderlich (Korrektur = löschen + neu),
    jede Buchung landet im Audit-Log."""

    __tablename__ = "balance_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    effective_date: Mapped[date] = mapped_column(Date)
    minutes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[AdjustmentKind] = mapped_column(Enum(AdjustmentKind))
    note: Mapped[str] = mapped_column(String(300))
    created_by_hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    created_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
