import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditAction(str, enum.Enum):
    PUNCH_CORRECTED = "PUNCH_CORRECTED"
    PUNCH_DELETED = "PUNCH_DELETED"
    EMPLOYEE_HR_ROLE_CHANGED = "EMPLOYEE_HR_ROLE_CHANGED"
    ABSENCE_DECIDED = "ABSENCE_DECIDED"
    EMPLOYEE_CREATED = "EMPLOYEE_CREATED"
    SETTINGS_CHANGED = "SETTINGS_CHANGED"
    HR_USER_CREATED = "HR_USER_CREATED"
    HR_USER_DELETED = "HR_USER_DELETED"
    TEAM_CREATED = "TEAM_CREATED"
    TEAM_UPDATED = "TEAM_UPDATED"
    TEAM_DELETED = "TEAM_DELETED"
    TENANT_ADMIN_EMAIL_CHANGED = "TENANT_ADMIN_EMAIL_CHANGED"
    EMPLOYEES_BULK_IMPORTED = "EMPLOYEES_BULK_IMPORTED"
    EMPLOYEE_DATA_EXPORTED = "EMPLOYEE_DATA_EXPORTED"
    EMPLOYEE_ANONYMIZED = "EMPLOYEE_ANONYMIZED"
    EMPLOYEE_WORK_TIME_MODEL_SET = "EMPLOYEE_WORK_TIME_MODEL_SET"
    EMPLOYEE_PASSWORD_RESET = "EMPLOYEE_PASSWORD_RESET"
    CONTRACT_CHANGED = "CONTRACT_CHANGED"
    COMPENSATION_CHANGED = "COMPENSATION_CHANGED"
    COMPENSATION_VIEWED = "COMPENSATION_VIEWED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    DOCUMENT_ACCESSED = "DOCUMENT_ACCESSED"
    PERIOD_SUBMITTED = "PERIOD_SUBMITTED"
    PERIOD_CONFIRMED = "PERIOD_CONFIRMED"
    PERIOD_DISPUTED = "PERIOD_DISPUTED"
    PERIOD_CLOSED = "PERIOD_CLOSED"
    PERIOD_REOPENED = "PERIOD_REOPENED"
    CHECKLIST_STARTED = "CHECKLIST_STARTED"
    SURCHARGE_RULES_CHANGED = "SURCHARGE_RULES_CHANGED"
    BALANCE_ADJUSTED = "BALANCE_ADJUSTED"
    PUNCH_CORRECTION_DECIDED = "PUNCH_CORRECTION_DECIDED"
    EMPLOYEE_CARD_REGISTERED = "EMPLOYEE_CARD_REGISTERED"
    EMPLOYEE_PIN_SET_AT_KIOSK = "EMPLOYEE_PIN_SET_AT_KIOSK"


class AuditLogEntry(Base):
    """Protokolliert sicherheits-/compliancerelevante Änderungen (wer, wann,
    was) – siehe app/services/audit_service.py. Bewusst schlank: ein
    Freitext-Detail statt strukturiertem Before/After-Diff, kein generisches
    Event-Sourcing, nur die explizit gehookten Aktionen (siehe AuditAction).

    entity_id ist bewusst ein einfacher Integer statt eines ForeignKey – ein
    gelöschter Punch (siehe PUNCH_DELETED) muss als historischer Verweis
    bestehen bleiben, auch nachdem die referenzierte Zeile nicht mehr
    existiert."""

    __tablename__ = "audit_log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    # Dual-Actor-Muster wie überall sonst im Projekt (siehe z.B. Punch.created_by).
    actor_hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    actor_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
