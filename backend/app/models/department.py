from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Rollen in der Leitung einer Abteilung
LEADER_HEAD = "HEAD"
LEADER_DEPUTY = "DEPUTY"
LEADER_ROLES = (LEADER_HEAD, LEADER_DEPUTY)

# Rechte einer Stellvertretung (je Stellvertretung einstellbar, Entscheidung 09.11.2026):
# STANDBY  – sieht die Abteilung immer, entscheidet und wird benachrichtigt, wenn keine Leitung da ist
# FULL     – gleiche Rechte wie die Leitung (sieht, entscheidet, wird benachrichtigt)
# ABSENCE  – sieht und entscheidet nur, solange keine Leitung da ist
DEPUTY_STANDBY = "STANDBY"
DEPUTY_FULL = "FULL"
DEPUTY_ABSENCE = "ABSENCE"
DEPUTY_RIGHTS = (DEPUTY_STANDBY, DEPUTY_FULL, DEPUTY_ABSENCE)


class Department(Base):
    """Abteilung, hierarchisch über parent_id (z. B. Vertrieb → Innendienst) – die einzige
    Organisationsstruktur (Teams wurden mit Migration 0134 zu Abteilungen). Leitungen und
    Stellvertretungen stehen in department_leaders; die Leitungen sind die Führungskräfte der
    Mitarbeiter darin. Zuständigkeiten siehe app/services/org_service.py."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_departments_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(150))
    # Übergeordnete Abteilung; beim Löschen der übergeordneten wird sie zur obersten Ebene
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DepartmentLeader(Base):
    """Leitung (HEAD, beliebig viele, gleichberechtigt) oder Stellvertretung (DEPUTY, mit Rechten
    deputy_rights) einer Abteilung. Eine Person steht je Abteilung höchstens einmal darin; sie muss
    nicht selbst Mitglied der Abteilung sein (Migration 0135)."""

    __tablename__ = "department_leaders"
    __table_args__ = (UniqueConstraint("department_id", "employee_id", name="uq_department_leaders"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10), default=LEADER_HEAD)
    # Nur für Stellvertretungen von Bedeutung (bei Leitungen immer STANDBY gespeichert)
    deputy_rights: Mapped[str] = mapped_column(String(10), default=DEPUTY_STANDBY, server_default=DEPUTY_STANDBY)
    # Reihenfolge der Anzeige (wie eingegeben)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
