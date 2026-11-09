import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, func, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PayComponentKind(str, enum.Enum):
    ALLOWANCE = "ALLOWANCE"  # wiederkehrende Zulage (gültig von–bis)
    ONE_TIME = "ONE_TIME"  # Einmalzahlung (z.B. Weihnachtsgeld) zu einem Datum


class AllowanceUnit(str, enum.Enum):
    PER_MONTH = "PER_MONTH"  # fester Betrag je Monat, in Rumpfmonaten anteilig nach Kalendertagen
    PER_HOUR = "PER_HOUR"  # Betrag je Ist-Stunde (z.B. Zulage auf den Stundenlohn)


class PayComponentType(Base):
    """Zulagen- bzw. Einmalzahlungsart des Mandanten (Katalog auf der Seite „Lohnarten“): Name und
    Lohnart für den DATEV-Export werden einmal gepflegt statt je Mitarbeiter – derselbe Name ergibt
    so immer dieselbe Spalte im Lohn-Export."""

    __tablename__ = "pay_component_types"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "name", name="uq_pay_component_types_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    kind: Mapped[PayComponentKind] = mapped_column(Enum(PayComponentKind))
    name: Mapped[str] = mapped_column(String(100))
    # Lohnart für den DATEV-Export (optional)
    wage_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Inaktive Arten stehen bei neuen Zulagen nicht mehr zur Auswahl; bestehende behalten sie.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PayComponent(Base):
    """Zulage oder Einmalzahlung eines Mitarbeiters – Teil der Vergütung, daher wie Compensation nur
    für Admins sichtbar; Audit-Protokoll ohne Beträge. Erscheint im Lohn-Export (nur wenn ein Admin ihn
    zieht) bzw. im DATEV-Export mit der Lohnart seiner Art. Berechnung siehe
    app/services/pay_component_service.py."""

    __tablename__ = "pay_components"
    __table_args__ = (Index("ix_pay_components_employee", "employee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    kind: Mapped[PayComponentKind] = mapped_column(Enum(PayComponentKind))
    # Art aus dem Katalog (Name und Lohnart stehen dort)
    type_id: Mapped[int] = mapped_column(ForeignKey("pay_component_types.id"))
    type: Mapped[PayComponentType] = relationship(lazy="joined")
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    # Nur Zulage: Einheit und Gültigkeit (valid_to NULL = unbefristet)
    unit: Mapped[AllowanceUnit | None] = mapped_column(Enum(AllowanceUnit), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Nur Einmalzahlung: Datum (zählt im Lohn-Export des Zeitraums, in dem es liegt)
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Nur Einmalzahlung: Betrag als Prozent des Monatsgehalts am Zahltag (z. B. 50 = Urlaubsgeld,
    # 100 = 13. Monatsgehalt); amount ist dann 0. recurs_yearly: jedes Jahr am selben Tag ab pay_date,
    # bis valid_to (leer = unbefristet).
    percent_of_salary: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    recurs_yearly: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def name(self) -> str:
        return self.type.name

    @property
    def wage_type(self) -> str | None:
        return self.type.wage_type
