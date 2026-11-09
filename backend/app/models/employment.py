import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ContractType(str, enum.Enum):
    PERMANENT = "PERMANENT"
    FIXED_TERM = "FIXED_TERM"
    APPRENTICESHIP = "APPRENTICESHIP"
    MINI_JOB = "MINI_JOB"
    WORKING_STUDENT = "WORKING_STUDENT"
    INTERNSHIP = "INTERNSHIP"
    FREELANCE = "FREELANCE"


class EmploymentContract(Base):
    """Vertragsdaten eines Mitarbeiters, effektiv-datiert (z.B. befristet →
    unbefristet): zu jedem Zeitpunkt höchstens ein gültiger Vertrag, siehe
    app/services/effective_dating.py. Speist u.a. die Warnung "Befristung /
    Probezeit läuft aus" (siehe Analysen). Sichtbar für Admin/HR."""

    __tablename__ = "employment_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_type: Mapped[ContractType] = mapped_column(Enum(ContractType))
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    probation_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    fixed_term_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Jahresurlaub laut Vertrag (Tage, bezogen auf die 5-Tage-Woche); leer = Standard der Firma
    annual_vacation_days: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PayType(str, enum.Enum):
    HOURLY = "HOURLY"
    MONTHLY = "MONTHLY"


class Compensation(Base):
    """Vergütung (Stundenlohn oder Monatsgehalt), effektiv-datiert und
    unveränderlich (Korrektur = Löschen + neu anlegen). Besonders schützens-
    wert: nur Admins dürfen sie lesen/ändern, jeder Zugriff wird im Audit-Protokoll
    vermerkt – dort bewusst OHNE Beträge, da der Audit-Protokoll auch HR sieht."""

    __tablename__ = "compensations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    pay_type: Mapped[PayType] = mapped_column(Enum(PayType))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
