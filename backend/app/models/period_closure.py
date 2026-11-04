import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PeriodStatus(str, enum.Enum):
    # Vorgelegt: Monatsnachweis (PDF) liegt in der Personalakte, Mitarbeiter soll bestätigen.
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    # Mitarbeiter hat widersprochen – Monat ist wieder bearbeitbar, HR korrigiert und legt neu vor.
    DISPUTED = "DISPUTED"
    CLOSED = "CLOSED"


# In diesen Status ist der Monat für Stempelungen, Abwesenheiten und Schichtplan gesperrt
# (der vorgelegte Nachweis darf nicht nachträglich "veralten").
LOCKING_STATUSES = (PeriodStatus.SUBMITTED, PeriodStatus.CONFIRMED, PeriodStatus.CLOSED)


class PeriodClosure(Base):
    """Monatsabschluss je Mitarbeiter: vorlegen -> Mitarbeiter bestätigt/widerspricht -> abschließen.
    Zahlen sind ein Schnappschuss zum Zeitpunkt der Vorlage (passend zum abgelegten PDF)."""

    __tablename__ = "period_closures"
    __table_args__ = (UniqueConstraint("employee_id", "year", "month", name="uq_period_closures_employee_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[PeriodStatus] = mapped_column(Enum(PeriodStatus))
    target_minutes: Mapped[int] = mapped_column(Integer)
    actual_minutes: Mapped[int] = mapped_column(Integer)
    delta_minutes: Mapped[int] = mapped_column(Integer)
    balance_end_minutes: Mapped[int] = mapped_column(Integer)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_documents.id", ondelete="SET NULL"), nullable=True
    )
    report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
    submitted_by_hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    submitted_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_without_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
