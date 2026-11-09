from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CostCenter(Base):
    """Kostenstelle der Firma (Nummer und Name); benutzte werden archiviert statt gelöscht."""

    __tablename__ = "cost_centers"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_cost_centers_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class EmployeeCostCenter(Base):
    """Aufteilung eines Mitarbeiters auf Kostenstellen in Prozent (zusammen 100)."""

    __tablename__ = "employee_cost_centers"
    __table_args__ = (UniqueConstraint("employee_id", "cost_center_id", name="uq_employee_cost_centers"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    cost_center_id: Mapped[int] = mapped_column(ForeignKey("cost_centers.id"))
    percent: Mapped[int] = mapped_column(Integer)


class EmployeePersonalData(Base):
    """Persönliche Angaben für Personalakte und Lohnvorbereitung (Adresse, Familie, Bank, Steuer,
    Sozialversicherung) – als JSON verschlüsselt (secret_box), siehe app/services/personal_data_service.py."""

    __tablename__ = "employee_personal_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    data: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
