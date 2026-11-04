from sqlalchemy import Boolean, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LeaveEntitlement(Base):
    """Urlaubsanspruch eines Mitarbeiters für ein Kalenderjahr, inkl. manuell
    erfasstem Resturlaub aus dem Vorjahr. Der tatsächliche Verbrauch wird nicht
    hier gespeichert, sondern aus den Absence-Einträgen (VACATION) des Jahres
    berechnet, siehe app/services/leave_service.py."""

    __tablename__ = "leave_entitlements"
    __table_args__ = (UniqueConstraint("employee_id", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    year: Mapped[int] = mapped_column()
    entitled_days: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    carried_over_days: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    # True = Übertrag von HR fest eingetragen. False = bei aktivem automatischem Übertrag
    # (AppSettings.vacation_carry_over_auto) aus dem Resturlaub des Vorjahres berechnet.
    carried_over_manual: Mapped[bool] = mapped_column(Boolean, default=False)
