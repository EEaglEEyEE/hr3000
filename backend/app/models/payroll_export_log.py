from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PayrollExportLog(Base):
    """Ein Lohn-Export (CSV oder DATEV-Datei): Zeitraum, Anzahl Mitarbeiter, wer und wann – für den
    Hinweis "schon exportiert" auf der Seite „Lohn-Export“. Inhalte werden nicht gespeichert."""

    __tablename__ = "payroll_export_logs"
    __table_args__ = (Index("ix_payroll_export_logs_tenant", "tenant_id", "date_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    kind: Mapped[str] = mapped_column(String(10))  # CSV | DATEV
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    employee_count: Mapped[int] = mapped_column(Integer)
    created_by_hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
