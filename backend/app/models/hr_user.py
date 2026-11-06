import enum

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HrRole(str, enum.Enum):
    ADMIN = "ADMIN"
    HR = "HR"
    # Team-beschränkter Zugriff, siehe app/services/team_scope_service.py –
    # im Gegensatz zu ADMIN/HR nicht "voller HR-Zugriff", siehe Actor.is_full_hr_level.
    SUPERVISOR = "SUPERVISOR"
    # Plattformweit, nicht einem Tenant zugeordnet – siehe HrUser.tenant_id.
    SUPER_ADMIN = "SUPER_ADMIN"


class HrUser(Base):
    __tablename__ = "hr_users"
    # email ist nur innerhalb eines Tenants eindeutig, nicht global – siehe
    # app/middleware/tenant.py und app/api/auth.py. NULL ist von dieser
    # Eindeutigkeitsprüfung ausgenommen (Super-Admin, siehe tenant_id).
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_hr_users_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = plattformweiter Super-Admin (siehe HrRole.SUPER_ADMIN), sonst
    # Mandanten-Admin/HR dieses Tenants.
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[HrRole] = mapped_column(Enum(HrRole))
    # Berechtigung „Vergütung & Lohn-Export“ für Rolle HR (Admins haben sie immer)
    payroll_access: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Nur bei Selbstregistrierung mit Mailversand: Anmeldung erst nach Klick auf den
    # Bestätigungslink (api/public.verify_email). Alle übrigen Konten: False.
    email_verification_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
