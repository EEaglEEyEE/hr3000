from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DataChangeRequest(Base):
    """Vorschlag eines Mitarbeiters zu eigenen Daten (persönliche Daten, freigegebene eigene Felder).
    Die Änderungen liegen verschlüsselt als JSON {"personal": {...}, "attributes": {"<id>": "Wert"}}."""

    __tablename__ = "data_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    changes: Mapped[str] = mapped_column(Text)
    # Enthält Bank, Steuer oder SV – entscheiden nur Konten mit „Vergütung & Lohn-Export“
    contains_payroll: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # PENDING, APPROVED, REJECTED
    status: Mapped[str] = mapped_column(String(10), default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
