from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Customer(Base):
    """Kunde der Projektzeiterfassung (Einstellung „Projektzeiten“). Mit Projekten nur deaktivierbar."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_customers_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Project(Base):
    """Projekt, dem selbst eingetragene Zeiten zugeordnet werden (Punch.project_id am „Kommen“).
    Mit zugeordneten Zeiten nur deaktivierbar, nicht löschbar."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_projects_tenant_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Projektnummer (optional, je Firma eindeutig)
    number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    cost_center_id: Mapped[int | None] = mapped_column(ForeignKey("cost_centers.id"), nullable=True)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Optionaler Zeitraum, in dem Zeiten auf das Projekt gebucht werden können
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
