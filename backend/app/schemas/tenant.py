from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.tenant import TenantPlan, TenantStatus


# Namen, die als Mandanten-Subdomain nicht vergeben werden dürfen (kollidieren mit
# Infrastruktur-/Plattform-Hosts oder erleichtern Phishing).
RESERVED_SUBDOMAINS = frozenset(
    {"admin", "www", "api", "mail", "smtp", "imap", "ftp", "kiosk", "hr", "static", "assets", "app",
     "login", "status", "support", "test", "dev", "staging", "docs", "help", "billing", "root"}
)

# Ein DNS-Label: Kleinbuchstaben, Ziffern, Bindestriche (nicht am Rand), max. 63 Zeichen.
SUBDOMAIN_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"


class TenantLookupResponse(BaseModel):
    """Antwort der Website-Login-Seite: Adresse, unter der sich die Firma anmeldet."""

    login_url: str


class SubdomainAvailabilityResponse(BaseModel):
    """Live-Prüfung im Registrierungsformular: ist die Wunsch-Adresse noch frei?"""

    available: bool
    reason: Literal["TAKEN", "RESERVED"] | None = None


class SignupRequest(BaseModel):
    """Selbstregistrierung einer Firma auf hr3000.de/registrieren (api/public.py)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=2, max_length=255)
    subdomain: str = Field(pattern=SUBDOMAIN_PATTERN, max_length=63)
    contact_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    # Min. 10 Zeichen; bcrypt verarbeitet höchstens 72 Byte (siehe auth_service) – längere
    # Passwörter würden sonst stillschweigend abgeschnitten bzw. scheitern.
    password: str = Field(min_length=10, max_length=128)
    # Pflicht-Häkchen: nur für Unternehmen (kein Verbrauchervertrag) und Zustimmung zu
    # Nutzungsbedingungen + AV-Vertrag.
    is_business: Literal[True]
    accept_terms: Literal[True]
    # Honeypot: im Formular unsichtbar – Menschen lassen es leer, einfache Bots nicht.
    website: str = Field(default="", max_length=0)

    @field_validator("subdomain")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value in RESERVED_SUBDOMAINS:
            raise ValueError("Diese Adresse ist reserviert.")
        return value

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Das Passwort ist zu lang (höchstens 72 Byte).")
        return value


class SignupResponse(BaseModel):
    subdomain: str
    login_url: str
    # True = erst den Link in der E-Mail bestätigen, dann anmelden (nur mit Mailversand).
    verification_required: bool = False


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class VerifyEmailResponse(BaseModel):
    login_url: str


class TenantCreateRequest(BaseModel):
    subdomain: str = Field(pattern=SUBDOMAIN_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    # Jeder Mandant braucht sofort einen funktionierenden Login – sonst gibt es
    # nach dem Anlegen keinen Weg mehr hinein (siehe create_tenant).
    admin_email: EmailStr
    contact_email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=255)
    plan: TenantPlan = TenantPlan.FREE
    # Zugangsdaten zusätzlich per E-Mail (Plattform-SMTP) an admin_email senden.
    send_credentials_email: bool = False

    @field_validator("subdomain")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value in RESERVED_SUBDOMAINS:
            raise ValueError("Diese Subdomain ist reserviert.")
        return value


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: TenantStatus | None = None
    plan: TenantPlan | None = None
    contact_email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=255)


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subdomain: str
    name: str
    status: TenantStatus
    plan: TenantPlan = TenantPlan.FREE
    contact_email: str | None
    contact_name: str | None
    # Auslastung für die Plattform-Übersicht (nur in der Liste gefüllt)
    active_employees: int | None = None
    # Selbst registriert (Website) statt vom Super-Admin angelegt, mit Anlagedatum.
    self_signup: bool = False
    created_at: datetime | None = None
    # Kündigung: None = nicht gekündigt (services/tenant_lifecycle.py)
    cancelled_at: datetime | None = None
    contract_end: date | None = None
    deletion_due_on: date | None = None


class TenantCreateResponse(TenantResponse):
    """Einmalige Antwort auf POST /tenants – enthält das generierte
    Erst-Admin-Passwort im Klartext. Wird nirgends gespeichert und danach
    nie wieder ausgegeben."""

    admin_email: str
    initial_admin_password: str
    # False, wenn nicht angefordert, kein SMTP konfiguriert oder der Versand scheiterte.
    credentials_emailed: bool = False


class TenantAdminPasswordResetRequest(BaseModel):
    send_email: bool = False


class TenantAdminPasswordResetResponse(BaseModel):
    admin_email: str
    new_password: str
    emailed: bool = False


class TenantAdminEmailUpdateRequest(BaseModel):
    new_email: EmailStr


class TenantAdminEmailUpdateResponse(BaseModel):
    admin_email: str


class TenantPurgeRequest(BaseModel):
    """Sofort löschen nur mit eingetippter Subdomain als Bestätigung."""

    model_config = ConfigDict(str_strip_whitespace=True)

    confirm_subdomain: str = Field(min_length=1, max_length=63)


class TenantPurgeResponse(BaseModel):
    subdomain: str
    deleted_rows: int
