from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Role(Base):
    """Eigene Rolle einer Firma: schränkt ein HR-Konto auf einzelne Bereiche ein (Stufe je Bereich),
    siehe app/services/role_permissions.py. Das Konto bleibt Rolle HR und verweist über
    accounts.custom_role_id hierher; ohne Verweis gilt der volle HR-Zugriff wie bisher."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # JSON {Bereich: Stufe}; fehlende Bereiche = kein Zugriff (role_permissions.parse_permissions)
    permissions: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
