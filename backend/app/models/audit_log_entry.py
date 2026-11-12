import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditAction(str, enum.Enum):
    PUNCH_CORRECTED = "PUNCH_CORRECTED"
    PUNCH_DELETED = "PUNCH_DELETED"
    EMPLOYEE_HR_ROLE_CHANGED = "EMPLOYEE_HR_ROLE_CHANGED"
    ABSENCE_DECIDED = "ABSENCE_DECIDED"
    EMPLOYEE_CREATED = "EMPLOYEE_CREATED"
    SETTINGS_CHANGED = "SETTINGS_CHANGED"
    HR_USER_CREATED = "HR_USER_CREATED"
    HR_USER_DELETED = "HR_USER_DELETED"
    TEAM_CREATED = "TEAM_CREATED"
    TEAM_UPDATED = "TEAM_UPDATED"
    TEAM_DELETED = "TEAM_DELETED"
    TENANT_ADMIN_EMAIL_CHANGED = "TENANT_ADMIN_EMAIL_CHANGED"
    EMPLOYEES_BULK_IMPORTED = "EMPLOYEES_BULK_IMPORTED"
    EMPLOYEE_DATA_EXPORTED = "EMPLOYEE_DATA_EXPORTED"
    EMPLOYEE_ANONYMIZED = "EMPLOYEE_ANONYMIZED"
    EMPLOYEE_WORK_TIME_MODEL_SET = "EMPLOYEE_WORK_TIME_MODEL_SET"
    EMPLOYEE_PASSWORD_RESET = "EMPLOYEE_PASSWORD_RESET"
    CONTRACT_CHANGED = "CONTRACT_CHANGED"
    COMPENSATION_CHANGED = "COMPENSATION_CHANGED"
    COMPENSATION_VIEWED = "COMPENSATION_VIEWED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_UPDATED = "DOCUMENT_UPDATED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    DOCUMENT_ACCESSED = "DOCUMENT_ACCESSED"
    PERIOD_SUBMITTED = "PERIOD_SUBMITTED"
    PERIOD_CONFIRMED = "PERIOD_CONFIRMED"
    PERIOD_DISPUTED = "PERIOD_DISPUTED"
    PERIOD_CLOSED = "PERIOD_CLOSED"
    PERIOD_REOPENED = "PERIOD_REOPENED"
    CHECKLIST_STARTED = "CHECKLIST_STARTED"
    SURCHARGE_RULES_CHANGED = "SURCHARGE_RULES_CHANGED"
    BALANCE_ADJUSTED = "BALANCE_ADJUSTED"
    PUNCH_CORRECTION_DECIDED = "PUNCH_CORRECTION_DECIDED"
    EMPLOYEE_CARD_REGISTERED = "EMPLOYEE_CARD_REGISTERED"
    EMPLOYEE_PIN_SET_AT_KIOSK = "EMPLOYEE_PIN_SET_AT_KIOSK"
    # Erfolgreiche Anmeldung in der Webapp (ohne IP-Adresse; Super-Admin ohne Mandant nicht).
    LOGIN = "LOGIN"
    # Korrektur am Urlaubskonto (± Tage, ggf. mit Verfall)
    LEAVE_ADJUSTED = "LEAVE_ADJUSTED"
    # Anmeldung eines weiteren Geräts mit dem Zugang eines gebundenen Tablets abgewiesen
    DEVICE_LOGIN_REJECTED = "DEVICE_LOGIN_REJECTED"
    TWO_FACTOR_CHANGED = "TWO_FACTOR_CHANGED"
    DEPARTMENT_CHANGED = "DEPARTMENT_CHANGED"
    PERSONAL_DATA_CHANGED = "PERSONAL_DATA_CHANGED"
    COST_CENTERS_CHANGED = "COST_CENTERS_CHANGED"
    ATTRIBUTE_CHANGED = "ATTRIBUTE_CHANGED"
    # Registrierungsschlüssel erzeugt/gesperrt, Tablet per MDM eingerichtet, Anfrage freigegeben/abgelehnt
    DEVICE_ENROLLMENT = "DEVICE_ENROLLMENT"
    # Hinweisgebersystem: Beauftragte benannt/abberufen; Meldung angesehen, bearbeitet, gelöscht –
    # nie mit Inhalten (app/services/whistle_service.py)
    WHISTLE_OFFICER_CHANGED = "WHISTLE_OFFICER_CHANGED"
    WHISTLE_CASE_VIEWED = "WHISTLE_CASE_VIEWED"
    WHISTLE_CASE_CHANGED = "WHISTLE_CASE_CHANGED"
    WHISTLE_CASE_DELETED = "WHISTLE_CASE_DELETED"
    # Eigene Berichte (Berichts-Builder): Definition angelegt/geändert/gelöscht, ausgeführt (Vorschau),
    # als CSV exportiert – jeweils ohne Inhalte
    REPORT_CHANGED = "REPORT_CHANGED"
    REPORT_RUN = "REPORT_RUN"
    REPORT_EXPORTED = "REPORT_EXPORTED"
    # Recruiting: Stelle angelegt/geändert/gelöscht, Bewerbung angelegt/geändert (Phase, Notiz,
    # Bewertung, Übernahme), Anhang angesehen/heruntergeladen, Bewerbung gelöscht (ohne Inhalte)
    RECRUITING_JOB_CHANGED = "RECRUITING_JOB_CHANGED"
    RECRUITING_APPLICATION_CHANGED = "RECRUITING_APPLICATION_CHANGED"
    RECRUITING_ATTACHMENT_ACCESSED = "RECRUITING_ATTACHMENT_ACCESSED"
    RECRUITING_DELETED = "RECRUITING_DELETED"
    # Eigene Rolle angelegt/geändert/gelöscht bzw. einem Konto zugewiesen oder entzogen
    ROLE_CHANGED = "ROLE_CHANGED"
    # Lohnbuchhaltung: Monat freigegeben / Freigabe zurückgenommen / Monat oder Datei abgerufen
    PAYROLL_RELEASED = "PAYROLL_RELEASED"
    PAYROLL_RELEASE_REVOKED = "PAYROLL_RELEASE_REVOKED"
    # Zeiten selbst eintragen (Stundenzettel): ohne Genehmigung eingetragen bzw. selbst wieder gelöscht
    TIME_ENTRY_CREATED = "TIME_ENTRY_CREATED"
    TIME_ENTRY_DELETED = "TIME_ENTRY_DELETED"
    # Projektzeiten: Kunde oder Projekt angelegt/geändert/gelöscht, Projekt einer Stempelung geändert
    PROJECT_CHANGED = "PROJECT_CHANGED"
    PAYROLL_ACCOUNTING_ACCESSED = "PAYROLL_ACCOUNTING_ACCESSED"


class AuditLogEntry(Base):
    """Protokolliert sicherheits-/compliancerelevante Änderungen (wer, wann,
    was) – siehe app/services/audit_service.py. Bewusst schlank: ein
    Freitext-Detail statt strukturiertem Before/After-Diff, kein generisches
    Event-Sourcing, nur die explizit gehookten Aktionen (siehe AuditAction).

    entity_id ist bewusst ein einfacher Integer statt eines ForeignKey – ein
    gelöschter Punch (siehe PUNCH_DELETED) muss als historischer Verweis
    bestehen bleiben, auch nachdem die referenzierte Zeile nicht mehr
    existiert."""

    __tablename__ = "audit_log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    # Wer gehandelt hat (Konto); NULL = System bzw. Tablet ohne Konto.
    actor_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
