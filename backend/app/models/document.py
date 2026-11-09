import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentCategory(str, enum.Enum):
    CONTRACT = "CONTRACT"
    CERTIFICATE = "CERTIFICATE"
    SICK_NOTE = "SICK_NOTE"
    QUALIFICATION = "QUALIFICATION"
    WARNING = "WARNING"
    PAYROLL = "PAYROLL"
    TIME_REPORT = "TIME_REPORT"
    OTHER = "OTHER"


class DocumentCategoryDefinition(Base):
    """Eigene Dokumentkategorie der Firma mit Rechten: Mitarbeiter dürfen hochladen, für Mitarbeiter
    sichtbar (Vorgabe beim Ablegen), vertraulich (nur Admins). Die festen Kategorien bleiben daneben."""

    __tablename__ = "document_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(60))
    employee_upload: Mapped[bool] = mapped_column(Boolean, default=False)
    employee_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class EmployeeDocument(Base):
    """Dokument in der Personalakte. Der Inhalt liegt verschlüsselt im
    Dateisystem (storage_key, siehe app/services/document_service.py), hier
    nur Metadaten. confidential = nur Admins; employee_visible = der Mitarbeiter
    sieht es in "Mein Bereich"; retention_until = bis dahin nicht löschbar
    (gesetzliche Aufbewahrungsfrist)."""

    __tablename__ = "employee_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    category: Mapped[DocumentCategory] = mapped_column(Enum(DocumentCategory))
    title: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    employee_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    # Eigene Kategorie (dann category = OTHER)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("document_categories.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
