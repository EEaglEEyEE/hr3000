import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    TRIAL = "TRIAL"
    SUSPENDED = "SUSPENDED"


class TenantPlan(str, enum.Enum):
    # Kostenlos bis config.free_employee_limit aktive Mitarbeiter
    FREE = "FREE"
    # Bezahltes Abo: keine Grenze, abgerechnet je aktivem Mitarbeiter
    PAID = "PAID"
    # Ohne Grenze und ohne Abrechnung (Bestandskunden, interne Nutzung) – nur Plattform-Admin
    UNLIMITED = "UNLIMITED"


class Tenant(Base):
    """Ein Mandant (Firma) im Mehrmandantensystem – über die Subdomain
    (siehe app/middleware/tenant.py) wird jeder Request genau einem Tenant
    zugeordnet. Der Super-Admin (HrUser.role=SUPER_ADMIN, tenant_id=NULL) ist
    keinem Tenant zugeordnet und verwaltet diese Tabelle."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    subdomain: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    # SUSPENDED sperrt den Zugriff (siehe app/middleware/tenant.py), TRIAL ist
    # weiterhin voll nutzbar – nur ein Signal für Vertrieb/Abrechnung, keine
    # technische Einschränkung.
    status: Mapped[TenantStatus] = mapped_column(Enum(TenantStatus), default=TenantStatus.ACTIVE)
    plan: Mapped[TenantPlan] = mapped_column(Enum(TenantPlan), default=TenantPlan.FREE)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Selbst registriert über hr3000.de/registrieren (api/public.py) statt vom Super-Admin angelegt.
    self_signup: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Nachweis der Zustimmung zu Nutzungsbedingungen + AV-Vertrag (UTC, Fassung wie
    # services/tenant_provisioning.TERMS_VERSION) – nur bei Selbstregistrierung gesetzt.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Kündigung (services/tenant_lifecycle.py): Vertragsende = Monatsende, danach 30 Tage Export,
    # am Löschtermin löscht app/tools/purge_tenants.py alle Daten der Firma.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    deletion_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
