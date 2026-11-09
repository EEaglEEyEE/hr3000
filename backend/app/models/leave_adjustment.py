from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LeaveAdjustment(Base):
    """Korrektur am Urlaubskonto eines Jahres (relativ bzw. ablaufend): ± Tage mit
    Begründung, optional mit Verfallsdatum. Verbraucht wird zuerst, was am frühesten verfällt
    (zusammen mit dem Übertrag, siehe leave_service.leave_balance). Unveränderlich: korrigieren =
    löschen und neu anlegen."""

    __tablename__ = "leave_adjustments"
    __table_args__ = (Index("ix_leave_adjustments_employee_year", "employee_id", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    year: Mapped[int] = mapped_column(Integer)
    days: Mapped[float] = mapped_column(Numeric(5, 1))
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(300))
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
