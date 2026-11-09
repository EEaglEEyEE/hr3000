from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShiftPlanEntry(Base):
    """Konkrete Tagesplanung, überschreibt/konkretisiert EmployeeDefaultShift
    für einen einzelnen Tag (z.B. "diese Woche Samstag statt Mittwoch").
    is_workday=False ist ein expliziter freier Tag (siehe
    app/services/timesheet_service.py SummaryStatus.PLANNED_OFF).

    Integritätsregel (App-Ebene, siehe app/api/shift_plan_entries.py):
    is_workday=True erzwingt target_minutes IS NOT NULL – sonst würde
    calculate_day einen Arbeitstag mit stillschweigend 0 Minuten Soll
    berechnen."""

    __tablename__ = "shift_plan_entries"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_shift_plan_entries_employee_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    date: Mapped[date] = mapped_column(Date)
    shift_template_id: Mapped[int | None] = mapped_column(ForeignKey("shift_templates.id"), nullable=True)
    is_workday: Mapped[bool] = mapped_column(Boolean)
    target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
