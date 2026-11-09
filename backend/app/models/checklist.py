import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChecklistKind(str, enum.Enum):
    ONBOARDING = "ONBOARDING"
    OFFBOARDING = "OFFBOARDING"


class ChecklistRole(str, enum.Enum):
    """Wer die Aufgabe erledigt – rein informativ (Zuständigkeit), kein Rechtekonzept."""

    HR = "HR"
    IT = "IT"
    SUPERVISOR = "SUPERVISOR"
    EMPLOYEE = "EMPLOYEE"
    OTHER = "OTHER"


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    kind: Mapped[ChecklistKind] = mapped_column(Enum(ChecklistKind))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChecklistTemplateItem(Base):
    __tablename__ = "checklist_template_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    responsible: Mapped[ChecklistRole] = mapped_column(Enum(ChecklistRole), default=ChecklistRole.HR)
    # Fälligkeit relativ zum Stichtag (Eintritts-/Austrittsdatum): negativ = davor.
    due_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    # Aktion (app/api/checklists.py): TASK abhaken, UPLOAD_DOCUMENT (Person lädt in action_category_id
    # hoch), FILL_DATA (Person schlägt ihre Daten vor), SEND_EMAIL (beim Start an die Zuständigen)
    action: Mapped[str] = mapped_column(String(20), default="TASK", server_default="TASK")
    action_category_id: Mapped[int | None] = mapped_column(ForeignKey("document_categories.id"), nullable=True)


class EmployeeChecklist(Base):
    """Instanz einer Vorlage für einen Mitarbeiter (Schnappschuss – spätere Änderungen an der
    Vorlage wirken nicht zurück)."""

    __tablename__ = "employee_checklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    kind: Mapped[ChecklistKind] = mapped_column(Enum(ChecklistKind))
    name: Mapped[str] = mapped_column(String(100))
    anchor_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EmployeeChecklistItem(Base):
    __tablename__ = "employee_checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("employee_checklists.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    responsible: Mapped[ChecklistRole] = mapped_column(Enum(ChecklistRole))
    due_date: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    done_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    action: Mapped[str] = mapped_column(String(20), default="TASK", server_default="TASK")
    action_category_id: Mapped[int | None] = mapped_column(ForeignKey("document_categories.id"), nullable=True)
