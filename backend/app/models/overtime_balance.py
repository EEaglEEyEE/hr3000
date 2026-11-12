from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OvertimeBalance(Base):
    """Überstundenkonto, pro Mitarbeiter und Stichtag fortgeschrieben."""

    __tablename__ = "overtime_balances"
    __table_args__ = (UniqueConstraint("employee_id", "balance_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    balance_date: Mapped[date] = mapped_column(Date)
    daily_target_minutes: Mapped[int] = mapped_column()
    daily_actual_minutes: Mapped[int] = mapped_column()
    daily_delta_minutes: Mapped[int] = mapped_column()
    running_balance_minutes: Mapped[int] = mapped_column()
    # Mit dem Gehalt abgegoltene Minuten des Kalendermonats bis einschließlich dieses Tages (laufend,
    # siehe timesheet_service.rebuild_balance); running_balance_minutes enthält sie schon nicht mehr.
    settled_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
