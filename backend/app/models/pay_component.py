import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PayComponentKind(str, enum.Enum):
    ALLOWANCE = "ALLOWANCE"  # wiederkehrende Zulage (gültig von–bis)
    ONE_TIME = "ONE_TIME"  # Einmalzahlung (z.B. Weihnachtsgeld) zu einem Datum


class AllowanceUnit(str, enum.Enum):
    PER_MONTH = "PER_MONTH"  # fester Betrag je Monat, in Rumpfmonaten anteilig nach Kalendertagen
    PER_HOUR = "PER_HOUR"  # Betrag je Ist-Stunde (z.B. Zulage auf den Stundenlohn)


class PayComponent(Base):
    """Zulage oder Einmalzahlung eines Mitarbeiters – Teil der Vergütung, daher wie Compensation nur
    für Admins sichtbar; Audit-Log ohne Beträge. Erscheint im Lohn-Export (nur wenn ein Admin ihn
    zieht) bzw. im DATEV-Export mit der hinterlegten Lohnart. Berechnung siehe
    app/services/pay_component_service.py."""

    __tablename__ = "pay_components"
    __table_args__ = (Index("ix_pay_components_employee", "employee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    kind: Mapped[PayComponentKind] = mapped_column(Enum(PayComponentKind))
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    # Nur Zulage: Einheit und Gültigkeit (valid_to NULL = unbefristet)
    unit: Mapped[AllowanceUnit | None] = mapped_column(Enum(AllowanceUnit), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Nur Einmalzahlung: Datum (zählt im Lohn-Export des Zeitraums, in dem es liegt)
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Lohnart für den DATEV-Export (optional)
    wage_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
