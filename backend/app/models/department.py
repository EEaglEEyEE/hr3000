from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Department(Base):
    """Abteilung, hierarchisch über parent_id (z. B. Vertrieb → Innendienst). Grundlage für das
    Attribut „Abteilung“ am Mitarbeiter und das Organigramm. Teams bleiben daneben bestehen
    (Schichtplanung, Teamleitungen, Sichtbarkeit für Führungskräfte)."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_departments_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(150))
    # Übergeordnete Abteilung; beim Löschen der übergeordneten wird sie zur obersten Ebene
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
