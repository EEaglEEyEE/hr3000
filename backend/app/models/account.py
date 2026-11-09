"""Ein Konto je Person und Firma (docs/konzept-konten.md): Zugang zur Webapp mit E-Mail und Passwort,
optional mit Verwaltungsrolle und optional verknüpft mit einem Mitarbeiter.

- Mitarbeiter mit Zugang: Konto mit employee_id (Rolle leer = nur „Mein Bereich“).
- Reine Verwaltungskonten (z. B. erster Admin einer Firma, externes Lohnbüro): ohne employee_id.
- Super-Admin: tenant_id NULL, Rolle SUPER_ADMIN.
- Konto ohne E-Mail/Passwort: kein Zugang (mehr), bleibt aber für den Verlauf bestehen
  („erstellt von“, Audit-Protokoll), z. B. nach „Zugang entfernen“.

Alle „wer war das“-Spalten zeigen auf accounts.id (*_account_id).
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, event, false, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


class HrRole(str, enum.Enum):
    ADMIN = "ADMIN"
    HR = "HR"
    # Führungskraft: Zugriff auf den eigenen Bereich (Unterstellte), siehe app/services/scope_service.py –
    # im Gegensatz zu ADMIN/HR nicht "voller HR-Zugriff", siehe Actor.is_full_hr_level.
    SUPERVISOR = "SUPERVISOR"
    # Plattformweit, nicht einem Tenant zugeordnet – siehe Account.tenant_id.
    SUPER_ADMIN = "SUPER_ADMIN"


class Account(Base):
    __tablename__ = "accounts"
    # E-Mail eindeutig je Firma (NULL = kein Zugang, mehrfach erlaubt). Super-Admin: tenant_id NULL.
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_accounts_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = plattformweiter Super-Admin (siehe HrRole.SUPER_ADMIN)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    # Verknüpfter Mitarbeiter („Mein Bereich“); NULL = reines Verwaltungskonto
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # NULL = nur „Mein Bereich“, sonst Verwaltungsrolle
    role: Mapped[HrRole | None] = mapped_column(Enum(HrRole), nullable=True)
    # Berechtigung „Vergütung & Lohn-Export“ für Rolle HR (Admins haben sie immer)
    payroll_access: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Nur bei Selbstregistrierung mit Mailversand: Anmeldung erst nach Klick auf den
    # Bestätigungslink (api/public.verify_email). Alle übrigen Konten: False.
    email_verification_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Benachrichtigungen zusätzlich per E-Mail (die Glocke bleibt immer); selbst einstellbar.
    notification_emails: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # iCal-Abo: SHA-256 des geheimen Tokens im Abo-Link (nur der Hash wird gespeichert)
    calendar_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Zwei-Faktor-Anmeldung (app/services/totp_service.py): Geheimnis verschlüsselt (secret_box);
    # gesetzt, aber totp_enabled_at leer = Einrichtung begonnen, noch nicht bestätigt.
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Zuletzt benutzter Zeitschritt – derselbe Code gilt nur einmal
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # JSON-Liste der SHA-256 noch nicht benutzter Wiederherstellungscodes
    totp_recovery_hashes: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee | None"] = relationship(back_populates="account", lazy="selectin")

    def __init__(self, **kwargs) -> None:
        # Ohne Mitarbeiter gilt employee=None als geladen (kein Nachladen im async-Kontext).
        if "employee" not in kwargs and kwargs.get("employee_id") is None:
            kwargs["employee"] = None
        super().__init__(**kwargs)

    @property
    def has_login(self) -> bool:
        return self.email is not None and self.password_hash is not None

    @property
    def two_factor_enabled(self) -> bool:
        return self.totp_enabled_at is not None

    @property
    def display_name(self) -> str:
        """Für „erstellt von“ und das Audit-Protokoll: Name des Mitarbeiters, sonst die E-Mail."""
        if self.employee is not None:
            return f"{self.employee.first_name} {self.employee.last_name}"
        return self.email or f"Konto {self.id}"


@event.listens_for(Account, "before_insert")
def _tenant_from_employee(mapper, connection, target: Account) -> None:
    # Über Employee.login_email & Co. angelegte Konten erben die Firma des Mitarbeiters.
    if target.tenant_id is None and target.employee is not None:
        target.tenant_id = target.employee.tenant_id
