"""Eigene Rollen: Bereiche, Stufen und die zentrale Zuordnung Route → Bereich.

Eine eigene Rolle SCHRÄNKT ein HR-Konto ein, sie erweitert nie: Das Konto bleibt Rolle HR, die
bestehenden Prüfungen der Endpoints (Admin, volle HR, Vergütung …) gelten weiter. Zusätzlich prüft
app/api/deps.get_current_actor für Konten mit eigener Rolle jede Anfrage gegen ROUTE_RULES.

Grundsatz: Was hier nicht steht, ist für Konten mit eigener Rolle verboten (deny by default).
tests/test_role_route_coverage.py geht alle registrierten Routen der App durch und scheitert, wenn
eine fehlt – eine neue Route muss also bewusst einem Bereich zugeordnet werden.

Stufe je Bereich: NONE < VIEW < EDIT. GET/HEAD verlangen VIEW, alle anderen Methoden EDIT; Ausnahmen
stehen ausdrücklich an der Regel (z. B. der Lohn-Export: ein GET, das Live-Lohndaten liefert und
deshalb EDIT verlangt). Eine Stufe „Vorschlagen“ gibt es bewusst nicht – dafür gibt es die Funktion
„Vorschläge“ (Änderungsanträge der Mitarbeiter), die ohne eigene Rolle auskommt.
"""
import enum
import json
from dataclasses import dataclass


class Area(str, enum.Enum):
    EMPLOYEES = "EMPLOYEES"
    DOCUMENTS = "DOCUMENTS"
    PAYROLL = "PAYROLL"
    TIME = "TIME"
    ABSENCES = "ABSENCES"
    SHIFT_PLANNING = "SHIFT_PLANNING"
    PERIOD_CLOSURE = "PERIOD_CLOSURE"
    REPORTS = "REPORTS"
    ORGANIZATION = "ORGANIZATION"
    CHECKLISTS = "CHECKLISTS"
    MASTER_DATA = "MASTER_DATA"
    RECRUITING = "RECRUITING"


class Level(str, enum.Enum):
    NONE = "NONE"
    VIEW = "VIEW"
    EDIT = "EDIT"


_RANK = {Level.NONE: 0, Level.VIEW: 1, Level.EDIT: 2}

# Reihenfolge = Reihenfolge in der Oberfläche (Matrix Bereich × Stufe)
AREA_INFO: dict[Area, tuple[str, str]] = {
    Area.EMPLOYEES: (
        "Mitarbeiter & Stammdaten",
        "Mitarbeiterliste, Profil, persönliche Daten, eigene Felder, Verträge, Verlauf, Vorschläge.",
    ),
    Area.DOCUMENTS: ("Personalakte: Dokumente", "Dokumente der Personalakte und Dokumente aus Vorlagen."),
    Area.PAYROLL: (
        "Vergütung & Lohn",
        "Ansehen: freigegebene Lohnbuchhaltung, Lohnarten; mit „Mitarbeiter“ auch Gehalt und Zulagen im Profil. "
        "Bearbeiten: zusätzlich Lohn-Export, Freigabe der Lohnbuchhaltung, Gehalt und Zulagen pflegen.",
    ),
    Area.TIME: ("Zeiterfassung & „Zu klären“", "Zeiten, Buchungen, Korrekturanträge, Zeitkonto, Arbeitszeitmodell."),
    Area.ABSENCES: ("Abwesenheiten", "Abwesenheiten, Anträge, Urlaubskonto, Teamkalender."),
    Area.SHIFT_PLANNING: ("Schichtplanung", "Schichtplan, Standard-Schichten, Schichtvorlagen."),
    Area.PERIOD_CLOSURE: ("Monatsabschluss", "Monate einreichen, abschließen, wieder öffnen; Monatsberichte."),
    Area.REPORTS: ("Auswertungen", "Auswertungen zu Abwesenheiten, Urlaub, Überstunden und Auffälligkeiten."),
    Area.ORGANIZATION: ("Organisation", "Abteilungen, Leitungen und Organigramm."),
    Area.CHECKLISTS: ("Checklisten", "Checklisten für Ein- und Austritt samt Vorlagen."),
    Area.MASTER_DATA: (
        "Stammdaten der Firma",
        "Standorte, Tablets, Feiertage, Kostenstellen, Arbeitszeitprofile.",
    ),
    Area.RECRUITING: (
        "Recruiting",
        "Stellen und Bewerbungen. Ohne diesen Bereich nur die Stellen, in deren Hiring Team das Konto steht.",
    ),
}

Permissions = dict[Area, Level]

# Vorlagen, die die Oberfläche per Klick anbietet
TEMPLATES: dict[str, tuple[str, str, Permissions]] = {
    "PAYROLL_OFFICE_READONLY": (
        "Lohnbüro (nur lesen)",
        "Für die Steuerberatung bzw. ein externes Lohnbüro: sieht nur die freigegebene Lohnbuchhaltung.",
        {Area.PAYROLL: Level.VIEW},
    ),
}


def normalize(permissions: dict) -> Permissions:
    """Vollständige Zuordnung aller Bereiche; Unbekanntes und Fehlendes zählt als kein Zugriff."""
    result: Permissions = {area: Level.NONE for area in Area}
    for key, value in permissions.items():
        try:
            result[Area(key)] = Level(value)
        except ValueError:
            continue
    return result


def parse_permissions(raw: str | None) -> Permissions:
    """Liest die gespeicherte JSON-Spalte; Unlesbares ergibt bewusst „kein Zugriff“."""
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return normalize(data if isinstance(data, dict) else {})


def dump_permissions(permissions: Permissions) -> str:
    return json.dumps({area.value: normalize(permissions)[area].value for area in Area})


def has_level(permissions: Permissions, area: Area, level: Level) -> bool:
    return _RANK[permissions.get(area, Level.NONE)] >= _RANK[level]


def has_lookup_access(permissions: Permissions) -> bool:
    """Nachschlagelisten (Mitarbeiter, Standorte, Abteilungen …) braucht jeder Bereich, der mit
    Mitarbeitern arbeitet. „Vergütung & Lohn“ zählt erst ab Bearbeiten: Wer dort nur ansehen darf
    (Lohnbüro), bekommt freigegebene Monate, aber keine Live-Mitarbeiterliste."""
    return any(
        has_level(permissions, area, Level.EDIT if area == Area.PAYROLL else Level.VIEW) for area in Area
    )


class RuleKind(str, enum.Enum):
    # Ohne Konto-Anmeldung über get_current_actor (öffentlich, Tablet-Anmeldung, API-Clients)
    PUBLIC = "PUBLIC"
    # Für jedes angemeldete Konto: Anmeldung, „Mein Bereich“, Benachrichtigungen, allgemeine Listen
    ALWAYS = "ALWAYS"
    # Nur Admin bzw. Super-Admin – für eigene Rollen immer verboten
    ADMIN = "ADMIN"
    # Sonst für HR erlaubt, für eigene Rollen bewusst nie (Protokoll, Datenexport, Tablet-Endpunkte)
    NEVER = "NEVER"
    # Verwaltungsfunktion eines Bereichs
    AREA = "AREA"
    # Auch vom Mitarbeiter selbst nutzbar („Mein Bereich“): Fehlt das Recht, gilt das Konto für diese
    # Anfrage als reiner Mitarbeiter und kommt nur an die eigenen Daten.
    MIXED = "MIXED"


Requirement = tuple[tuple[Area, Level | None], ...]


@dataclass(frozen=True)
class Rule:
    kind: RuleKind
    # Mindestens eine Alternative muss erfüllt sein; in einer Alternative alle Bereiche.
    # Stufe None = aus der Methode (GET/HEAD → VIEW, sonst EDIT).
    alternatives: tuple[Requirement, ...] = ()
    # Zusätzlich erfüllt, wenn irgendein Bereich Zugriff gibt (has_lookup_access)
    lookup: bool = False
    # MIXED: auch ohne verknüpften Mitarbeiter als „nur ich“ weiterreichen (Startseite)
    without_employee: bool = False


def _alternatives(parts: tuple) -> tuple[Requirement, ...]:
    result = []
    for part in parts:
        if isinstance(part, Area):
            result.append(((part, None),))
        elif isinstance(part[0], Area) and (len(part) == 2 and (part[1] is None or isinstance(part[1], Level))):
            result.append((part,))
        else:
            result.append(tuple((p, None) if isinstance(p, Area) else p for p in part))
    return tuple(result)


def area(*parts) -> Rule:
    """area(Area.TIME) | area((Area.PAYROLL, Level.EDIT)) | area((Area.PAYROLL, Area.EMPLOYEES)) = beide nötig."""
    return Rule(RuleKind.AREA, _alternatives(parts))


def mixed(*parts, lookup: bool = False, without_employee: bool = False) -> Rule:
    return Rule(RuleKind.MIXED, _alternatives(parts), lookup=lookup, without_employee=without_employee)


PUBLIC = Rule(RuleKind.PUBLIC)
ALWAYS = Rule(RuleKind.ALWAYS)
ADMIN = Rule(RuleKind.ADMIN)
NEVER = Rule(RuleKind.NEVER)
LOOKUP = Rule(RuleKind.AREA, lookup=True)

A = Area
V, E = Level.VIEW, Level.EDIT
# Gehalt und Zulagen am Mitarbeiter: Vergütung UND Zugriff auf Mitarbeiter (Profil)
_PAY_AT_EMPLOYEE = ((A.PAYROLL, None), (A.EMPLOYEES, V))
_TIME_OR_EMPLOYEES = (A.TIME, A.EMPLOYEES)
_RECRUITING = mixed(A.RECRUITING, without_employee=True)

ROUTE_RULES: dict[str, Rule] = {
    # --- Plattform (Super-Admin) ---------------------------------------------------------------
    "GET /tenants": ADMIN,
    "POST /tenants": ADMIN,
    "PATCH /tenants/{tenant_id}": ADMIN,
    "POST /tenants/{tenant_id}/reset-admin-password": ADMIN,
    "PATCH /tenants/{tenant_id}/admin-email": ADMIN,
    "POST /tenants/{tenant_id}/cancel": ADMIN,
    "POST /tenants/{tenant_id}/cancel/revoke": ADMIN,
    "POST /tenants/{tenant_id}/purge": ADMIN,
    "GET /platform/server-metrics": ADMIN,
    # --- Ohne Konto-Anmeldung --------------------------------------------------------------------
    "POST /auth/device/login": PUBLIC,
    "POST /auth/device/enroll": PUBLIC,
    "POST /auth/device/pair": PUBLIC,
    "POST /auth/login": PUBLIC,
    "POST /auth/login/2fa": PUBLIC,
    "POST /auth/refresh": PUBLIC,
    "POST /auth/password-reset/request": PUBLIC,
    "POST /auth/password-reset/confirm": PUBLIC,
    "POST /auth/2fa/setup": PUBLIC,
    "POST /auth/2fa/enable": PUBLIC,
    "GET /calendar/{token}.ics": PUBLIC,
    "POST /v1/auth/token": PUBLIC,
    "GET /v1/employees": PUBLIC,
    "GET /v1/absence-types": PUBLIC,
    "GET /v1/absences": PUBLIC,
    "GET /v1/punches": PUBLIC,
    "GET /branding": PUBLIC,
    "GET /internal/tls-allowed": PUBLIC,
    "GET /public/tenant-lookup": PUBLIC,
    "GET /public/subdomain-available": PUBLIC,
    "POST /public/signup": PUBLIC,
    "POST /public/verify-email": PUBLIC,
    "GET /health": PUBLIC,
    # --- Jedes angemeldete Konto: Anmeldung, „Mein Bereich“, Benachrichtigungen, allgemeine Listen
    "POST /auth/change-password": ALWAYS,
    "GET /auth/2fa": ALWAYS,
    "POST /auth/2fa/disable": ALWAYS,
    "POST /me/calendar-token": ALWAYS,
    "DELETE /me/calendar-token": ALWAYS,
    "POST /me/punches": ALWAYS,
    # Zeiten selbst eintragen (Stundenzettel): nur eigene Zeiten; Entscheidung über die Korrekturanträge
    "GET /me/time-entries": ALWAYS,
    "POST /me/time-entries": ALWAYS,
    "DELETE /me/time-entries/requests/{request_id}": ALWAYS,
    "DELETE /me/time-entries/{punch_id}": ALWAYS,
    "GET /me/personal-data": ALWAYS,
    "GET /me/attributes": ALWAYS,
    "GET /me/attribute-values": ALWAYS,
    "POST /me/change-requests": ALWAYS,
    "GET /me/change-requests": ALWAYS,
    "GET /me/team-calendar": ALWAYS,
    "POST /me/documents": ALWAYS,
    "GET /me/checklist-items": ALWAYS,
    "POST /me/checklist-items/{item_id}/done": ALWAYS,
    "GET /notifications": ALWAYS,
    "PATCH /notifications/read-all": ALWAYS,
    "PATCH /notifications/{notification_id}/read": ALWAYS,
    "GET /notifications/settings": ALWAYS,
    "PUT /notifications/settings": ALWAYS,
    "GET /features": ALWAYS,
    "GET /plan": ALWAYS,
    "GET /absence-types": ALWAYS,
    "GET /holidays": ALWAYS,
    "GET /document-categories": ALWAYS,
    # --- Nur Admin ------------------------------------------------------------------------------
    "PATCH /employees/{employee_id}/hr-role": ADMIN,
    "POST /employees/{employee_id}/reset-password": ADMIN,
    "POST /employees/{employee_id}/anonymize": ADMIN,
    "POST /employees/{employee_id}/2fa-reset": ADMIN,
    "POST /absence-types": ADMIN,
    "PATCH /absence-types/{type_id}": ADMIN,
    "GET /hr-users": ADMIN,
    "POST /hr-users": ADMIN,
    "PATCH /hr-users/{hr_user_id}": ADMIN,
    "DELETE /hr-users/{hr_user_id}": ADMIN,
    "POST /hr-users/{account_id}/2fa-reset": ADMIN,
    "GET /roles": ADMIN,
    "GET /roles/meta": ADMIN,
    "POST /roles": ADMIN,
    "PATCH /roles/{role_id}": ADMIN,
    "DELETE /roles/{role_id}": ADMIN,
    "POST /attribute-sections": ADMIN,
    "PATCH /attribute-sections/{section_id}": ADMIN,
    "POST /attributes": ADMIN,
    "PATCH /attributes/{attribute_id}": ADMIN,
    "POST /document-templates": ADMIN,
    "PATCH /document-templates/{template_id}": ADMIN,
    "GET /api-clients": ADMIN,
    "POST /api-clients": ADMIN,
    "DELETE /api-clients/{client_id}": ADMIN,
    "GET /webhooks": ADMIN,
    "POST /webhooks": ADMIN,
    "PATCH /webhooks/{webhook_id}": ADMIN,
    "DELETE /webhooks/{webhook_id}": ADMIN,
    "POST /webhooks/{webhook_id}/test": ADMIN,
    "GET /webhooks/{webhook_id}/deliveries": ADMIN,
    "GET /break-rules": ADMIN,
    "POST /break-rules": ADMIN,
    "PATCH /break-rules/{rule_id}": ADMIN,
    "DELETE /break-rules/{rule_id}": ADMIN,
    "GET /settings": ADMIN,
    "PATCH /settings": ADMIN,
    "POST /settings/smtp-test": ADMIN,
    "PUT /settings/logo": ADMIN,
    "DELETE /settings/logo": ADMIN,
    "POST /account/cancel": ADMIN,
    "POST /account/cancel/revoke": ADMIN,
    "GET /migration/settings-export": ADMIN,
    "POST /migration/settings-import": ADMIN,
    "POST /document-categories": ADMIN,
    "PATCH /document-categories/{category_id}": ADMIN,
    "POST /surcharge-rules": ADMIN,
    "POST /surcharge-rules/defaults": ADMIN,
    "PATCH /surcharge-rules/{rule_id}": ADMIN,
    "DELETE /surcharge-rules/{rule_id}": ADMIN,
    # --- Für eigene Rollen nie ----------------------------------------------------------------
    "GET /audit-log": NEVER,  # enthält Vorgänge aller Bereiche
    "POST /migration/employee-values": NEVER,  # schreibt quer über alle Bereiche
    "GET /employees/{employee_id}/data-export": NEVER,  # Auskunft mit allen Daten einer Person
    "POST /devices/verify-admin-pin": NEVER,  # nur Tablets
    "GET /device/config": NEVER,
    "POST /device/register-card": NEVER,
    "POST /device/setup-pin": NEVER,
    # --- Nachschlagelisten: jeder Bereich, der mit Mitarbeitern arbeitet ------------------------
    "GET /employees": LOOKUP,
    "GET /locations/{location_id}/employees": LOOKUP,
    "GET /employees/{employee_id}": mixed(lookup=True),
    "GET /locations": LOOKUP,
    "GET /departments": LOOKUP,
    "GET /cost-centers": LOOKUP,
    "GET /work-time-profiles": LOOKUP,
    "GET /work-time-profiles/{profile_id}/history": LOOKUP,
    "GET /shift-templates": LOOKUP,
    # Startseite: wer ist da/abwesend – sonst nur die eigenen Kennzahlen bzw. Feiertage
    "GET /dashboard": mixed(A.ABSENCES, A.TIME, A.EMPLOYEES, without_employee=True),
    # --- Mitarbeiter & Stammdaten -----------------------------------------------------------------
    "POST /employees": area(A.EMPLOYEES),
    "POST /employees/bulk-import": area(A.EMPLOYEES),
    "PATCH /employees/{employee_id}": area(A.EMPLOYEES),
    "GET /employees/{employee_id}/personal-data": area(A.EMPLOYEES),
    "PATCH /employees/{employee_id}/personal-data": area(A.EMPLOYEES),
    "PUT /employees/{employee_id}/cost-centers": area(A.EMPLOYEES),
    "GET /attribute-sections": area(A.EMPLOYEES),
    "GET /employees/{employee_id}/attributes": area(A.EMPLOYEES),
    "PUT /employees/{employee_id}/attributes/{attribute_id}": area(A.EMPLOYEES),
    "DELETE /employees/{employee_id}/attributes/values/{value_id}": area(A.EMPLOYEES),
    "GET /employees/{employee_id}/history": area(A.EMPLOYEES),
    "GET /change-requests": area(A.EMPLOYEES),
    "POST /change-requests/{request_id}/decide": area(A.EMPLOYEES),
    "GET /employees/{employee_id}/contracts": area(A.EMPLOYEES),
    "POST /employees/{employee_id}/contracts": area(A.EMPLOYEES),
    "PATCH /employees/{employee_id}/contracts/{contract_id}": area(A.EMPLOYEES),
    "DELETE /employees/{employee_id}/contracts/{contract_id}": area(A.EMPLOYEES),
    # --- Personalakte: Dokumente --------------------------------------------------------------
    "GET /employees/{employee_id}/documents": mixed(A.DOCUMENTS),
    "GET /employees/{employee_id}/documents/{document_id}/download": mixed(A.DOCUMENTS),
    "POST /employees/{employee_id}/documents": area(A.DOCUMENTS),
    "PATCH /employees/{employee_id}/documents/{document_id}": area(A.DOCUMENTS),
    "DELETE /employees/{employee_id}/documents/{document_id}": area(A.DOCUMENTS),
    "GET /document-templates/placeholders": area(A.DOCUMENTS),
    "GET /document-templates": area(A.DOCUMENTS),
    "GET /employees/{employee_id}/document-templates/{template_id}/preview": area(A.DOCUMENTS),
    "POST /employees/{employee_id}/documents/from-template": area(A.DOCUMENTS),
    # --- Vergütung & Lohn -----------------------------------------------------------------------
    "GET /employees/{employee_id}/compensation": area(_PAY_AT_EMPLOYEE),
    "POST /employees/{employee_id}/compensation": area(_PAY_AT_EMPLOYEE),
    "DELETE /employees/{employee_id}/compensation/{compensation_id}": area(_PAY_AT_EMPLOYEE),
    "GET /employees/{employee_id}/pay-components": area(_PAY_AT_EMPLOYEE),
    "POST /employees/{employee_id}/pay-components": area(_PAY_AT_EMPLOYEE),
    "PATCH /employees/{employee_id}/pay-components/{component_id}": area(_PAY_AT_EMPLOYEE),
    "DELETE /employees/{employee_id}/pay-components/{component_id}": area(_PAY_AT_EMPLOYEE),
    # Lohn-Export liefert Live-Daten aller Mitarbeiter: Ausnahme, GET verlangt Bearbeiten
    "GET /payroll-export": area((A.PAYROLL, E)),
    "GET /payroll-export/datev/preview": area((A.PAYROLL, E)),
    "GET /payroll-export/datev": area((A.PAYROLL, E)),
    "GET /payroll-export/status": area((A.PAYROLL, E)),
    "GET /payroll-export/datev/settings": area(A.PAYROLL),
    "PUT /payroll-export/datev/settings": area(A.PAYROLL),
    "GET /wage-types": area(A.PAYROLL),
    "PUT /wage-types": area(A.PAYROLL),
    "GET /pay-component-types": area(A.PAYROLL),
    "POST /pay-component-types": area(A.PAYROLL),
    "PATCH /pay-component-types/{type_id}": area(A.PAYROLL),
    "DELETE /pay-component-types/{type_id}": area(A.PAYROLL),
    "PUT /surcharge-rules/{rule_id}/wage-type": area(A.PAYROLL),
    "GET /reports/labor-costs": area(((A.PAYROLL, None), (A.REPORTS, V))),
    # Lohnbuchhaltung: Ansehen = freigegebene Monate samt Dateien; aktueller Stand und Freigeben prüft
    # der Endpoint zusätzlich (Actor.can_edit_payroll). Zurücknehmen nur Admin.
    "GET /payroll-accounting/releases": area(A.PAYROLL),
    "GET /payroll-accounting/{month}": area(A.PAYROLL),
    "POST /payroll-accounting/{month}/release": area(A.PAYROLL),
    "DELETE /payroll-accounting/{month}/release": ADMIN,
    "GET /payroll-accounting/{month}/files/{kind}": area(A.PAYROLL),
    # --- Zeiterfassung & „Zu klären“ ------------------------------------------------------------
    "POST /punches": area(A.TIME),  # manuelle Buchung durch die Verwaltung (Tablets sind nicht betroffen)
    "GET /employees/{employee_id}/punches": mixed(A.TIME),
    "PATCH /punches/{punch_id}": area(A.TIME),
    "DELETE /punches/{punch_id}": area(A.TIME),
    "GET /timesheet/open-days": area(A.TIME),
    "GET /timesheet/monthly-caps": area(A.TIME),
    "GET /timesheet/balance-limits": area(A.TIME),
    "GET /employees/{employee_id}/timesheet": mixed(A.TIME),
    "PUT /employees/{employee_id}/day-reviews/{work_date}": area(A.TIME),
    "DELETE /employees/{employee_id}/day-reviews/{work_date}": area(A.TIME),
    "GET /employees/{employee_id}/weekly-balance": mixed(A.TIME),
    "GET /employees/{employee_id}/overtime-balance": mixed(A.TIME),
    "POST /punch-correction-requests": mixed(A.TIME),
    "GET /punch-correction-requests": mixed(A.TIME),
    "PATCH /punch-correction-requests/{request_id}/decide": area(A.TIME),
    "GET /employees/{employee_id}/balance-adjustments": mixed(A.TIME),
    "POST /employees/{employee_id}/balance-adjustments": area(A.TIME),
    "POST /employees/{employee_id}/balance-adjustments/set-balance": area(A.TIME),
    "DELETE /employees/{employee_id}/balance-adjustments/{adjustment_id}": area(A.TIME),
    "GET /employees/{employee_id}/surcharges": mixed(A.TIME),
    "GET /surcharge-rules": area(A.TIME, A.PAYROLL, A.MASTER_DATA),
    "GET /employees/{employee_id}/work-time-model": mixed(*_TIME_OR_EMPLOYEES),
    "GET /employees/{employee_id}/work-time-model/history": mixed(*_TIME_OR_EMPLOYEES),
    "PUT /employees/{employee_id}/work-time-model": area(*_TIME_OR_EMPLOYEES),
    "PUT /employees/{employee_id}/work-time-profile": area(*_TIME_OR_EMPLOYEES),
    "PUT /employees/{employee_id}/work-time-model/versions/{version_id}": area(*_TIME_OR_EMPLOYEES),
    "DELETE /employees/{employee_id}/work-time-model/versions/{version_id}": area(*_TIME_OR_EMPLOYEES),
    # --- Abwesenheiten ----------------------------------------------------------------------------
    "GET /employees/{employee_id}/absences": mixed(A.ABSENCES),
    "GET /absences/pending": area(A.ABSENCES),
    "GET /employees/{employee_id}/team-overlaps": mixed(A.ABSENCES),
    "GET /employees/{employee_id}/substitute-candidates": mixed(A.ABSENCES),
    "POST /absences": mixed(A.ABSENCES),
    "PATCH /absences/{absence_id}/decide": area(A.ABSENCES),
    "PATCH /absences/{absence_id}": area(A.ABSENCES),
    "POST /absences/{absence_id}/certificate": mixed(A.ABSENCES),
    "DELETE /absences/{absence_id}": area(A.ABSENCES),
    "GET /employees/{employee_id}/leave-entitlement": mixed(A.ABSENCES),
    "PATCH /employees/{employee_id}/leave-entitlement": area(A.ABSENCES),
    "GET /employees/{employee_id}/leave-adjustments": mixed(A.ABSENCES),
    "POST /employees/{employee_id}/leave-adjustments": area(A.ABSENCES),
    "DELETE /employees/{employee_id}/leave-adjustments/{adjustment_id}": area(A.ABSENCES),
    "GET /team-calendar": area(A.ABSENCES, A.SHIFT_PLANNING),
    # --- Schichtplanung ---------------------------------------------------------------------------
    "POST /shift-templates": area(A.SHIFT_PLANNING),
    "PATCH /shift-templates/{template_id}": area(A.SHIFT_PLANNING),
    "DELETE /shift-templates/{template_id}": area(A.SHIFT_PLANNING),
    "GET /employees/{employee_id}/default-shifts": mixed(A.SHIFT_PLANNING, A.TIME),
    "POST /employees/{employee_id}/default-shifts": area(A.SHIFT_PLANNING),
    "PATCH /employees/{employee_id}/default-shifts/{default_id}": area(A.SHIFT_PLANNING),
    "DELETE /employees/{employee_id}/default-shifts/{default_id}": area(A.SHIFT_PLANNING),
    "GET /employees/{employee_id}/shift-plan-entries": mixed(A.SHIFT_PLANNING, A.TIME),
    "GET /employees/{employee_id}/effective-shifts": mixed(A.SHIFT_PLANNING, A.TIME),
    "PUT /employees/{employee_id}/shift-plan-entries/{entry_date}": area(A.SHIFT_PLANNING),
    "DELETE /employees/{employee_id}/shift-plan-entries/{entry_date}": area(A.SHIFT_PLANNING),
    "GET /shift-plan/pdf": area(A.SHIFT_PLANNING),
    # --- Monatsabschluss ------------------------------------------------------------------------
    "GET /employees/{employee_id}/period-closures": mixed(A.PERIOD_CLOSURE, A.TIME),
    "POST /employees/{employee_id}/period-closures/{year}/{month}/submit": area(A.PERIOD_CLOSURE),
    "POST /employees/{employee_id}/period-closures/{year}/{month}/confirm": mixed(A.PERIOD_CLOSURE),
    "POST /employees/{employee_id}/period-closures/{year}/{month}/dispute": mixed(A.PERIOD_CLOSURE),
    "POST /employees/{employee_id}/period-closures/{year}/{month}/close": area(A.PERIOD_CLOSURE),
    "POST /employees/{employee_id}/period-closures/{year}/{month}/reopen": area(A.PERIOD_CLOSURE),
    "GET /employees/{employee_id}/month-report": mixed(A.PERIOD_CLOSURE, A.TIME),
    "GET /month-reports": area(A.PERIOD_CLOSURE),
    "GET /period-closures": area(A.PERIOD_CLOSURE),
    "POST /period-closures/submit-all": area(A.PERIOD_CLOSURE),
    # --- Auswertungen -----------------------------------------------------------------------------
    "GET /reports/absence-stats": area(A.REPORTS),
    "GET /reports/vacation": area(A.REPORTS),
    "GET /reports/overtime": area(A.REPORTS),
    "GET /reports/attention": area(A.REPORTS),
    # --- Organisation -----------------------------------------------------------------------------
    "POST /departments": area(A.ORGANIZATION),
    "PATCH /departments/{department_id}": area(A.ORGANIZATION),
    "POST /departments/{department_id}/members": area(A.ORGANIZATION),
    "DELETE /departments/{department_id}": area(A.ORGANIZATION),
    "GET /org-chart": mixed(A.ORGANIZATION, A.EMPLOYEES),
    # --- Checklisten ------------------------------------------------------------------------------
    "GET /checklist-templates": area(A.CHECKLISTS),
    "POST /checklist-templates": area(A.CHECKLISTS),
    "POST /checklist-templates/defaults": area(A.CHECKLISTS),
    "PATCH /checklist-templates/{template_id}": area(A.CHECKLISTS),
    "DELETE /checklist-templates/{template_id}": area(A.CHECKLISTS),
    "GET /employees/{employee_id}/checklists": area(A.CHECKLISTS),
    "POST /employees/{employee_id}/checklists": area(A.CHECKLISTS),
    "PATCH /checklists/{checklist_id}/items/{item_id}": area(A.CHECKLISTS),
    "DELETE /checklists/{checklist_id}": area(A.CHECKLISTS),
    "GET /checklists/open-items": area(A.CHECKLISTS),
    # --- Stammdaten der Firma -----------------------------------------------------------------------
    "POST /locations": area(A.MASTER_DATA),
    "PATCH /locations/{location_id}": area(A.MASTER_DATA),
    "GET /devices": area(A.MASTER_DATA),
    "POST /devices": area(A.MASTER_DATA),
    "PATCH /devices/{device_id}": area(A.MASTER_DATA),
    "DELETE /devices/{device_id}": area(A.MASTER_DATA),
    "GET /devices/enrollment-keys": area(A.MASTER_DATA),
    "POST /devices/enrollment-keys": area(A.MASTER_DATA),
    "DELETE /devices/enrollment-keys/{location_id}": area(A.MASTER_DATA),
    "GET /devices/enrollments": area(A.MASTER_DATA),
    "POST /devices/enrollments/{enrollment_id}/approve": area(A.MASTER_DATA),
    "DELETE /devices/enrollments/{enrollment_id}": area(A.MASTER_DATA),
    "POST /devices/enrollments/remove-inactive": area(A.MASTER_DATA),
    "POST /devices/{device_id}/pairing-code": area(A.MASTER_DATA),
    "POST /holidays": area(A.MASTER_DATA),
    "POST /holidays/import": area(A.MASTER_DATA),
    "PATCH /holidays/{holiday_id}": area(A.MASTER_DATA),
    "DELETE /holidays/{holiday_id}": area(A.MASTER_DATA),
    "POST /cost-centers": area(A.MASTER_DATA),
    "PATCH /cost-centers/{cost_center_id}": area(A.MASTER_DATA),
    "DELETE /cost-centers/{cost_center_id}": area(A.MASTER_DATA),
    "POST /work-time-profiles": area(A.MASTER_DATA),
    "PUT /work-time-profiles/{profile_id}/model": area(A.MASTER_DATA),
    "PATCH /work-time-profiles/{profile_id}": area(A.MASTER_DATA),
    "DELETE /work-time-profiles/{profile_id}": area(A.MASTER_DATA),
    # Projektzeiten: Kunden und Projekte pflegen; die Listen braucht auch, wer Zeiten korrigiert (Projekt
    # einer Stempelung ändern) oder Projektzeiten auswertet
    "GET /customers": area(A.MASTER_DATA, A.TIME, A.REPORTS),
    "POST /customers": area(A.MASTER_DATA),
    "PATCH /customers/{customer_id}": area(A.MASTER_DATA),
    "DELETE /customers/{customer_id}": area(A.MASTER_DATA),
    "GET /projects": area(A.MASTER_DATA, A.TIME, A.REPORTS),
    "POST /projects": area(A.MASTER_DATA),
    "PATCH /projects/{project_id}": area(A.MASTER_DATA),
    "DELETE /projects/{project_id}": area(A.MASTER_DATA),
    # --- Auswertungen: feste Analysen und eigene Berichte (Berichts-Builder) ----------------------
    "GET /reports/absence-rate": area(A.REPORTS),
    "GET /reports/project-times": area(A.REPORTS),
    "GET /reports/headcount": area(A.REPORTS),
    "GET /report-builder/catalog": area(A.REPORTS),
    "GET /report-builder/reports": area(A.REPORTS),
    "GET /report-builder/reports/{report_id}": area(A.REPORTS),
    # Vorschau, Ausführen und Export sind POSTs, die nur lesen
    "POST /report-builder/preview": area((A.REPORTS, V)),
    "POST /report-builder/export": area((A.REPORTS, V)),
    "POST /report-builder/reports/{report_id}/run": area((A.REPORTS, V)),
    "POST /report-builder/reports/{report_id}/export": area((A.REPORTS, V)),
    "POST /report-builder/reports": area(A.REPORTS),
    "PUT /report-builder/reports/{report_id}": area(A.REPORTS),
    "DELETE /report-builder/reports/{report_id}": area(A.REPORTS),
    # --- Hinweisgebersystem: Meldeseite öffentlich; Meldestelle prüft die Benennung selbst (nicht
    # über Rollen – Vertraulichkeit), Benennen nur Admin -----------------------------------------
    "GET /public/whistle/info": PUBLIC,
    "POST /public/whistle/reports": PUBLIC,
    "POST /public/whistle/status": PUBLIC,
    "POST /public/whistle/messages": PUBLIC,
    "POST /public/whistle/attachments": PUBLIC,
    "GET /whistle/status": ALWAYS,
    "GET /whistle/cases": ALWAYS,
    "GET /whistle/cases/{case_id}": ALWAYS,
    "PATCH /whistle/cases/{case_id}": ALWAYS,
    "DELETE /whistle/cases/{case_id}": ALWAYS,
    "POST /whistle/cases/{case_id}/messages": ALWAYS,
    "GET /whistle/cases/{case_id}/attachments/{attachment_id}": ALWAYS,
    "GET /whistle/officers": ADMIN,
    "POST /whistle/officers": ADMIN,
    "DELETE /whistle/officers/{account_id}": ADMIN,
    # --- Recruiting: Karriereseite öffentlich. Intern MIXED: Ohne Bereich „Recruiting“ gilt das Konto
    # als Mitarbeiter und sieht nur Stellen, in deren Hiring Team es steht (prüft recruiting_service).
    "GET /public/careers": PUBLIC,
    "GET /public/careers/jobs/{job_id}": PUBLIC,
    "POST /public/careers/jobs/{job_id}/applications": PUBLIC,
    "GET /recruiting/access": _RECRUITING,
    "GET /recruiting/jobs": _RECRUITING,
    "POST /recruiting/jobs": _RECRUITING,
    "GET /recruiting/jobs/{job_id}": _RECRUITING,
    "PUT /recruiting/jobs/{job_id}": _RECRUITING,
    "DELETE /recruiting/jobs/{job_id}": _RECRUITING,
    "GET /recruiting/team-candidates": _RECRUITING,
    "GET /recruiting/applications": _RECRUITING,
    "POST /recruiting/applications": _RECRUITING,
    "GET /recruiting/applications/due-for-deletion": _RECRUITING,
    "GET /recruiting/applications/{application_id}": _RECRUITING,
    "PATCH /recruiting/applications/{application_id}": _RECRUITING,
    "DELETE /recruiting/applications/{application_id}": _RECRUITING,
    "POST /recruiting/applications/{application_id}/stage": _RECRUITING,
    "POST /recruiting/applications/{application_id}/notes": _RECRUITING,
    "DELETE /recruiting/applications/{application_id}/notes/{note_id}": _RECRUITING,
    "PUT /recruiting/applications/{application_id}/rating": _RECRUITING,
    "DELETE /recruiting/applications/{application_id}/rating": _RECRUITING,
    "POST /recruiting/applications/{application_id}/attachments": _RECRUITING,
    "GET /recruiting/applications/{application_id}/attachments/{attachment_id}/download": _RECRUITING,
    "DELETE /recruiting/applications/{application_id}/attachments/{attachment_id}": _RECRUITING,
    "POST /recruiting/applications/{application_id}/hire": _RECRUITING,
}


class Decision(str, enum.Enum):
    ALLOW = "ALLOW"
    # Als reiner Mitarbeiter weiterreichen (nur eigene Daten)
    SELF = "SELF"
    DENY = "DENY"


def route_key(method: str, path: str) -> str:
    return f"{'GET' if method.upper() == 'HEAD' else method.upper()} {path}"


def _method_level(method: str) -> Level:
    return Level.VIEW if method.upper() in ("GET", "HEAD") else Level.EDIT


def rule_allows(rule: Rule, method: str, permissions: Permissions) -> bool:
    if rule.lookup and has_lookup_access(permissions):
        return True
    default = _method_level(method)
    return any(
        all(has_level(permissions, area_, level or default) for area_, level in requirement)
        for requirement in rule.alternatives
    )


def decide(method: str, path: str | None, permissions: Permissions, *, has_employee: bool) -> Decision:
    """Entscheidung für ein Konto mit eigener Rolle. Unbekannte Route = verboten."""
    rule = ROUTE_RULES.get(route_key(method, path)) if path else None
    if rule is None or rule.kind in (RuleKind.ADMIN, RuleKind.NEVER):
        return Decision.DENY
    if rule.kind in (RuleKind.PUBLIC, RuleKind.ALWAYS):
        return Decision.ALLOW
    if rule_allows(rule, method, permissions):
        return Decision.ALLOW
    if rule.kind == RuleKind.MIXED and (has_employee or rule.without_employee):
        return Decision.SELF
    return Decision.DENY
