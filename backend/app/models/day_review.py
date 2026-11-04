from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DayReview(Base):
    """HR hat einen Tag aus "Zu klären" geprüft und als erledigt markiert – er verschwindet dann
    aus der Liste und blockiert den Monatsabschluss nicht mehr. Das gilt für Sonderfälle (z.B.
    außerplanmäßig gestempelt) wie für fehlende/widersprüchliche Stempelungen; an der Berechnung
    ändert das nichts (keine automatische Ergänzung fehlender Zeiten, siehe CLAUDE.md)."""

    __tablename__ = "day_reviews"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_day_reviews_employee_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    work_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    reviewed_by_hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    reviewed_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
