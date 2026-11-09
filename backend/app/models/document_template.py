from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.document import DocumentCategory


class DocumentTemplate(Base):
    """Dokumentvorlage mit Platzhaltern ({{vorname}} …), wird je Mitarbeiter als PDF in die Akte
    gelegt (app/services/document_template_service.py)."""

    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[DocumentCategory] = mapped_column(Enum(DocumentCategory), default=DocumentCategory.OTHER)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("document_categories.id"), nullable=True)
    employee_visible: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
