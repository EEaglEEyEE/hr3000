"""Positivliste des Berichts-Builders: Datenquellen, Spalten, Operatoren – reine Daten, ohne Datenbank.

Ein eigener Bericht kann nur enthalten, was hier steht (plus die eigenen Felder der Firma aus dem
Attribut-Katalog, die der Dienst als ``attr_<id>`` ergänzt). Es gibt weder freies SQL noch frei
wählbare Tabellen-/Spaltennamen: Schlüssel werden nie in eine Abfrage eingesetzt, sondern nur gegen
diese Liste geprüft und in Python ausgewertet (app/services/report_builder_service.py).

Zugriff je Spalte:
- ``all``     – jedes Verwaltungskonto (Führungskräfte nur für ihren Bereich),
- ``hr``      – Admin/HR, wie die persönlichen Daten und eigenen Felder der Personalakte,
- ``payroll`` – nur mit Berechtigung „Vergütung & Lohn-Export“ (Vergütung, Bank, Steuer, SV), exakt
  die Felder aus ``app/schemas/personal_data.PAYROLL_FIELDS``.
"""
import math
import re
from dataclasses import dataclass
from datetime import date

from app.schemas.personal_data import PAYROLL_FIELDS

SOURCE_EMPLOYEES = "employees"
SOURCE_ABSENCES = "absences"
SOURCE_TIME_MONTHS = "time_months"
# Projektzeiten je Mitarbeiter und Projekt – nur mit eingeschalteten Projektzeiten
SOURCE_PROJECT_TIMES = "project_times"
SOURCES: dict[str, str] = {
    SOURCE_EMPLOYEES: "Mitarbeitende",
    SOURCE_ABSENCES: "Abwesenheiten",
    SOURCE_TIME_MONTHS: "Zeit je Monat",
    SOURCE_PROJECT_TIMES: "Projektzeiten",
}
# Quellen, die einen Zeitraum verlangen
TIME_BASED_SOURCES = frozenset({SOURCE_ABSENCES, SOURCE_TIME_MONTHS, SOURCE_PROJECT_TIMES})

TEXT, NUMBER, DATE, BOOL, ENUM = "text", "number", "date", "bool", "enum"
ACCESS_ALL, ACCESS_HR, ACCESS_PAYROLL = "all", "hr", "payroll"

OPERATOR_LABELS: dict[str, str] = {
    "eq": "ist gleich",
    "ne": "ist nicht gleich",
    "contains": "enthält",
    "starts_with": "beginnt mit",
    "gt": "größer als",
    "gte": "größer oder gleich",
    "lt": "kleiner als",
    "lte": "kleiner oder gleich",
    "in": "ist eines von",
    "is_empty": "ist leer",
    "is_not_empty": "ist nicht leer",
}
OPERATORS_BY_TYPE: dict[str, tuple[str, ...]] = {
    TEXT: ("eq", "ne", "contains", "starts_with", "in", "is_empty", "is_not_empty"),
    NUMBER: ("eq", "ne", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty"),
    DATE: ("eq", "ne", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty"),
    BOOL: ("eq",),
    ENUM: ("eq", "ne", "in", "is_empty", "is_not_empty"),
}
VALUELESS_OPERATORS = frozenset({"is_empty", "is_not_empty"})

MAX_COLUMNS = 30
MAX_FILTERS = 10
MAX_SORTS = 3
MAX_TEXT_VALUE = 200
MAX_IN_VALUES = 50
MAX_NUMBER = 1_000_000_000

ATTRIBUTE_KEY = re.compile(r"^attr_([1-9][0-9]{0,9})$")

ABSENCE_CATEGORY_LABELS: tuple[tuple[str, str], ...] = (
    ("VACATION", "Urlaub"),
    ("SICK", "Krankheit"),
    ("CHILD_SICK", "Kind krank"),
    ("SPECIAL_LEAVE", "Sonderurlaub"),
    ("UNPAID", "Unbezahlt"),
    ("TIME_OFF_IN_LIEU", "Freizeitausgleich"),
    ("WORK_TIME", "Arbeitszeit"),
    ("PUBLIC_HOLIDAY", "Feiertag"),
    ("PARENTAL_LEAVE", "Mutterschutz/Elternzeit"),
    ("SHORT_TIME_WORK", "Kurzarbeit"),
    ("UNEXCUSED", "Unentschuldigt"),
    ("CARE_LEAVE", "Pflege von Angehörigen"),
)
APPROVAL_LABELS = (("APPROVED", "Genehmigt"), ("PENDING", "Offen"), ("REJECTED", "Abgelehnt"))
STATUS_LABELS = (("ONBOARDING", "Onboarding"), ("ACTIVE", "Aktiv"), ("LEAVE", "Auszeit"), ("INACTIVE", "Inaktiv"))
CONTRACT_LABELS = (
    ("PERMANENT", "Unbefristet"),
    ("FIXED_TERM", "Befristet"),
    ("APPRENTICESHIP", "Ausbildung"),
    ("MINI_JOB", "Minijob"),
    ("WORKING_STUDENT", "Werkstudent"),
    ("INTERNSHIP", "Praktikum"),
    ("FREELANCE", "Freie Mitarbeit"),
)
PAY_TYPE_LABELS = (("HOURLY", "Stundenlohn"), ("MONTHLY", "Monatsgehalt"))


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    label: str
    type: str = TEXT
    access: str = ACCESS_ALL
    # nur ENUM: (Wert, Anzeige)
    options: tuple[tuple[str, str], ...] = ()
    # Zahlenspalte, deren Summe je Gruppe und gesamt sinnvoll ist
    summable: bool = False
    # Gruppe in der Auswahl der Oberfläche
    group: str = "Stammdaten"

    @property
    def operators(self) -> tuple[str, ...]:
        return OPERATORS_BY_TYPE[self.type]

    def option_label(self, value: str) -> str:
        return dict(self.options).get(value, value)


_PERSON = (
    ColumnSpec("employee_number", "Personalnummer"),
    ColumnSpec("last_name", "Nachname"),
    ColumnSpec("first_name", "Vorname"),
    ColumnSpec("department", "Abteilung"),
    ColumnSpec("location", "Standort"),
)

_PERSONAL_TEXT = (
    ("private_email", "Private E-Mail"),
    ("phone", "Telefon"),
    ("street", "Straße"),
    ("zip_code", "PLZ"),
    ("city", "Ort"),
    ("country", "Land"),
    ("nationality", "Staatsangehörigkeit"),
    ("birth_place", "Geburtsort"),
    ("birth_name", "Geburtsname"),
)
_PAYROLL_TEXT = (
    ("iban", "IBAN"),
    ("bic", "BIC"),
    ("account_holder", "Kontoinhaber"),
    ("tax_id", "Steuer-ID"),
    ("church_tax", "Kirchensteuer"),
    ("social_security_number", "Sozialversicherungsnummer"),
    ("health_insurance", "Krankenkasse"),
)
# Schlüssel der Spalten, die aus den verschlüsselten persönlichen Daten kommen
PERSONAL_DATA_KEYS = frozenset(
    {key for key, _ in _PERSONAL_TEXT} | {key for key, _ in _PAYROLL_TEXT} | {"children_count", "child_allowance", "tax_class"}
)
COMPENSATION_KEYS = frozenset({"pay_type", "pay_amount"})

_EMPLOYEE_COLUMNS = (
    *_PERSON,
    ColumnSpec("position", "Position"),
    ColumnSpec("supervisor", "Führungskraft"),
    ColumnSpec("hire_date", "Eintritt", DATE),
    ColumnSpec("termination_date", "Austritt", DATE),
    ColumnSpec("status", "Status", ENUM, options=STATUS_LABELS),
    ColumnSpec("work_time_model", "Arbeitszeitmodell", group="Arbeitszeit"),
    ColumnSpec("weekly_hours", "Wochenstunden", NUMBER, summable=True, group="Arbeitszeit"),
    ColumnSpec("fte", "Vollzeitanteil (FTE)", NUMBER, summable=True, group="Arbeitszeit"),
    ColumnSpec("birth_date", "Geburtsdatum", DATE, ACCESS_HR, group="Persönliche Daten"),
    ColumnSpec("contract_type", "Vertragsart", ENUM, ACCESS_HR, options=CONTRACT_LABELS, group="Vertrag"),
    ColumnSpec("probation_end", "Probezeit bis", DATE, ACCESS_HR, group="Vertrag"),
    ColumnSpec("fixed_term_end", "Befristet bis", DATE, ACCESS_HR, group="Vertrag"),
    *(ColumnSpec(key, label, TEXT, ACCESS_HR, group="Persönliche Daten") for key, label in _PERSONAL_TEXT),
    ColumnSpec("children_count", "Kinder", NUMBER, ACCESS_HR, group="Persönliche Daten"),
    ColumnSpec("child_allowance", "Kinderfreibeträge", NUMBER, ACCESS_HR, group="Persönliche Daten"),
    *(ColumnSpec(key, label, TEXT, ACCESS_PAYROLL, group="Bank, Steuer, Sozialversicherung") for key, label in _PAYROLL_TEXT),
    ColumnSpec("tax_class", "Steuerklasse", NUMBER, ACCESS_PAYROLL, group="Bank, Steuer, Sozialversicherung"),
    ColumnSpec("pay_type", "Vergütungsart", ENUM, ACCESS_PAYROLL, options=PAY_TYPE_LABELS, group="Vergütung"),
    ColumnSpec("pay_amount", "Vergütung (Betrag)", NUMBER, ACCESS_PAYROLL, group="Vergütung"),
)

_ABSENCE_COLUMNS = (
    *_PERSON,
    ColumnSpec("date_from", "Von", DATE, group="Abwesenheit"),
    ColumnSpec("date_to", "Bis", DATE, group="Abwesenheit"),
    ColumnSpec("absence_type", "Art", group="Abwesenheit"),
    ColumnSpec("category", "Kategorie", ENUM, options=ABSENCE_CATEGORY_LABELS, group="Abwesenheit"),
    ColumnSpec("days", "Tage (im Zeitraum)", NUMBER, summable=True, group="Abwesenheit"),
    ColumnSpec("hours", "Stunden", NUMBER, summable=True, group="Abwesenheit"),
    ColumnSpec("half_day", "Halber Tag", BOOL, group="Abwesenheit"),
    ColumnSpec("approval_status", "Status", ENUM, options=APPROVAL_LABELS, group="Abwesenheit"),
)

_TIME_COLUMNS = (
    *_PERSON,
    ColumnSpec("month", "Monat", group="Zeit"),
    ColumnSpec("target_hours", "Soll (Std.)", NUMBER, summable=True, group="Zeit"),
    ColumnSpec("actual_hours", "Ist (Std.)", NUMBER, summable=True, group="Zeit"),
    ColumnSpec("delta_hours", "Saldo (Std.)", NUMBER, summable=True, group="Zeit"),
    ColumnSpec("settled_hours", "Davon mit dem Gehalt abgegolten (Std.)", NUMBER, summable=True, group="Zeit"),
    ColumnSpec("balance_hours", "Kontostand zum Monatsende (Std.)", NUMBER, group="Zeit"),
    ColumnSpec("vacation_taken", "Urlaub genommen (Tage)", NUMBER, summable=True, group="Urlaub"),
    ColumnSpec("vacation_remaining", "Resturlaub des Jahres (Tage)", NUMBER, group="Urlaub"),
)

_PROJECT_COLUMNS = (
    *_PERSON,
    ColumnSpec("project", "Projekt", group="Projekt"),
    ColumnSpec("project_number", "Projektnummer", group="Projekt"),
    ColumnSpec("customer", "Kunde", group="Projekt"),
    ColumnSpec("billable", "Abrechenbar", BOOL, group="Projekt"),
    ColumnSpec("cost_center", "Kostenstelle", group="Projekt"),
    ColumnSpec("project_hours", "Stunden", NUMBER, summable=True, group="Projekt"),
)

STATIC_COLUMNS: dict[str, dict[str, ColumnSpec]] = {
    SOURCE_EMPLOYEES: {c.key: c for c in _EMPLOYEE_COLUMNS},
    SOURCE_ABSENCES: {c.key: c for c in _ABSENCE_COLUMNS},
    SOURCE_TIME_MONTHS: {c.key: c for c in _TIME_COLUMNS},
    SOURCE_PROJECT_TIMES: {c.key: c for c in _PROJECT_COLUMNS},
}

# Die Positivliste darf die Berechtigung der Personalakte nie unterlaufen: jedes Lohn-Feld der
# persönlichen Daten ist hier „payroll“, kein anderes Feld der persönlichen Daten.
assert {
    key for key in PERSONAL_DATA_KEYS if STATIC_COLUMNS[SOURCE_EMPLOYEES][key].access == ACCESS_PAYROLL
} == set(PAYROLL_FIELDS)


def is_known_key(source: str, key: str) -> bool:
    """Statische Spalte der Quelle oder (nur Mitarbeitende) ein eigenes Feld ``attr_<id>`` – ob es
    das Feld in der Firma gibt, prüft der Dienst gegen den Attribut-Katalog."""
    return key in STATIC_COLUMNS[source] or (source == SOURCE_EMPLOYEES and ATTRIBUTE_KEY.match(key) is not None)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Bitte eine Zahl angeben.")
    if not math.isfinite(value) or abs(value) > MAX_NUMBER:
        raise ValueError("Die Zahl liegt außerhalb des erlaubten Bereichs.")
    return float(value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Bitte einen Wert angeben.")
    if len(value) > MAX_TEXT_VALUE:
        raise ValueError(f"Der Wert darf höchstens {MAX_TEXT_VALUE} Zeichen lang sein.")
    return value.strip()


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Bitte ein Datum angeben.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Bitte ein Datum im Format JJJJ-MM-TT angeben.") from exc


def _option(spec: ColumnSpec, value: object) -> str:
    if not isinstance(value, str) or value not in dict(spec.options):
        raise ValueError(f"„{spec.label}“: bitte einen der Auswahlwerte nehmen.")
    return value


def normalize_filter_value(spec: ColumnSpec, operator: str, value: object) -> object:
    """Prüft Operator und Wert eines Filters gegen den Typ der Spalte und gibt den Vergleichswert
    zurück (float, date, bool, str oder Liste von str). Wirft ValueError mit deutschem Text."""
    if operator not in spec.operators:
        raise ValueError(f"„{spec.label}“ kann nicht mit „{OPERATOR_LABELS.get(operator, operator)}“ gefiltert werden.")
    if operator in VALUELESS_OPERATORS:
        if value is not None:
            raise ValueError("Dieser Vergleich braucht keinen Wert.")
        return None
    if operator == "in":
        if not isinstance(value, list) or not value or len(value) > MAX_IN_VALUES:
            raise ValueError(f"Bitte 1 bis {MAX_IN_VALUES} Werte angeben.")
        return [_option(spec, item) if spec.type == ENUM else _text(item) for item in value]
    if isinstance(value, list) or value is None:
        raise ValueError("Bitte genau einen Wert angeben.")
    if spec.type == NUMBER:
        return _number(value)
    if spec.type == DATE:
        return _date(value)
    if spec.type == BOOL:
        if not isinstance(value, bool):
            raise ValueError("Bitte Ja oder Nein angeben.")
        return value
    if spec.type == ENUM:
        return _option(spec, value)
    return _text(value)
