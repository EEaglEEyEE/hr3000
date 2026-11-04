from datetime import date

from sqlalchemy import Date, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmployeeLocationPeriod(Base):
    """Standort-Historie eines Mitarbeiters: ab valid_from gilt location_id (bis zur nächsten Zeile).
    Entsteht erst beim ersten Standortwechsel; ohne Zeilen gilt Employee.location_id für alle Tage.
    Wird für die Feiertagsermittlung je Tag verwendet."""

    __tablename__ = "employee_location_periods"
    __table_args__ = (Index("ix_employee_location_periods_employee", "employee_id", "valid_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    valid_from: Mapped[date] = mapped_column(Date)
