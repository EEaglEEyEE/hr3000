import csv
import datetime as dt
import io
from dataclasses import dataclass

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.models import Department, Location
from app.schemas.employee import BulkImportRowError
from app.schemas.work_time_model import WorkTimeModelInput

_EMAIL = TypeAdapter(EmailStr)
REQUIRED_COLUMNS = ("vorname", "nachname", "personalnummer", "standort")
_TRUE_VALUES = {"ja", "j", "true", "1", "wahr"}
_FALSE_VALUES = {"nein", "n", "false", "0", "falsch"}


@dataclass
class ParsedEmployeeRow:
    first_name: str
    last_name: str
    employee_number: str
    location_id: int
    department_id: int | None
    active: bool
    login_email: str | None
    hire_date: dt.date | None
    birth_date: dt.date | None
    weekly_hours: float | None = None
    weekdays: list[int] | None = None
    daily_hours: list[float] | None = None
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_hours: float | None = None
    # Mehrwöchiges Modell: Stunden je Wochentag für jede Turnus-Woche (Spalten tagesstunden,
    # tagesstunden_woche2 … _woche4) und der Beginn des Turnus (Spalte turnus_beginn, optional)
    rotation_weeks: list[list[float]] | None = None
    rotation_start: dt.date | None = None
    # Mit dem Gehalt abgegoltene Überstunden je Monat (Spalte abgegoltene_ueberstunden, Stunden)
    settled_overtime_hours: float | None = None
    # Zeile in der CSV-Datei (für Fehlermeldungen nach dem Parsen, z.B. Tarifgrenze)
    line: int = 0


def _parse_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"Ungültiger Wert '{raw}' für Aktiv (erwartet: ja/nein).")


_WEEKDAY_NAMES = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}


def _parse_weekdays(raw: str) -> list[int]:
    """'Mo-Fr', 'Mo,Di,Do' oder 'Mo-Mi,Fr' -> [0, 1, 2, 4]."""
    days: set[int] = set()
    for part in raw.replace(" ", "").lower().split(","):
        if not part:
            continue
        bounds = part.split("-")
        if len(bounds) > 2 or any(b not in _WEEKDAY_NAMES for b in bounds):
            raise ValueError(f"Ungültige Arbeitstage '{raw}' (Beispiele: Mo-Fr, Mo,Mi,Fr).")
        start, end = _WEEKDAY_NAMES[bounds[0]], _WEEKDAY_NAMES[bounds[-1]]
        if end < start:
            raise ValueError(f"Ungültige Arbeitstage '{raw}' (Bereich rückwärts).")
        days.update(range(start, end + 1))
    if not days:
        raise ValueError("Arbeitstage fehlen.")
    return sorted(days)


def _parse_daily_hours(raw: str) -> list[float]:
    """'Mo:8,Di:8,Mi:4.5' bzw. 'Mi:4:30' -> [8, 8, 4.5, 0, 0, 0, 0] (Stunden je Wochentag, Rest frei)."""
    hours = [0.0] * 7
    for part in raw.replace(" ", "").lower().split(","):
        if not part:
            continue
        day, _, value = part.partition(":")
        if day not in _WEEKDAY_NAMES or not value:
            raise ValueError(f"Ungültige Tagesstunden '{raw}' (Beispiel: Mo:8,Di:8,Mi:4).")
        try:
            # "7.5" oder "7:30" (Komma ist bereits Trennzeichen zwischen den Tagen)
            if ":" in value:
                h, m = value.split(":", 1)
                hours[_WEEKDAY_NAMES[day]] = int(h) + int(m) / 60
            else:
                hours[_WEEKDAY_NAMES[day]] = float(value)
        except ValueError as exc:
            raise ValueError(f"Ungültige Stunden '{value}' in Tagesstunden.") from exc
    return hours


ROTATION_COLUMNS = ("tagesstunden_woche2", "tagesstunden_woche3", "tagesstunden_woche4")


def _parse_rotation(first_week: str, row: dict[str, str]) -> list[list[float]] | None:
    """Turnus aus `tagesstunden` (Woche 1) und `tagesstunden_woche2` … `_woche4`; None = kein Turnus.
    Die Wochen müssen lückenlos sein (Woche 3 nur mit Woche 2)."""
    further = [row.get(column, "") for column in ROTATION_COLUMNS]
    if not any(further):
        return None
    if not first_week:
        raise ValueError("Mehrwöchiges Modell: Woche 1 fehlt – bitte die Spalte „tagesstunden“ füllen.")
    weeks = [_parse_daily_hours(first_week)]
    for number, raw in enumerate(further, start=2):
        if not raw:
            if any(further[number - 1:]):
                raise ValueError(f"Mehrwöchiges Modell: Woche {number} fehlt (die Wochen müssen lückenlos sein).")
            break
        weeks.append(_parse_daily_hours(raw))
    return weeks


def _parse_settled_overtime(raw: str) -> float | None:
    """'10' oder '7,5' -> Stunden je Monat; leer oder 0 = keine."""
    if not raw:
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Ungültige abgegoltene Überstunden '{raw}' (Stunden je Monat, z. B. 10).") from exc
    if not 0 <= value <= 100:
        raise ValueError(f"Abgegoltene Überstunden '{raw}' müssen zwischen 0 und 100 Stunden je Monat liegen.")
    return value or None


def _parse_date(raw: str, field_label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Ungültiges Datum '{raw}' für {field_label} (erwartet: JJJJ-MM-TT).") from exc


def parse_bulk_import_csv(
    content: str,
    locations: list[Location],
    departments: list[Department],
    existing_employee_numbers: set[str],
    existing_login_emails: set[str],
) -> tuple[list[ParsedEmployeeRow], list[BulkImportRowError]]:
    """Parst und validiert eine hochgeladene Mitarbeiter-CSV, ohne selbst auf
    die Datenbank zuzugreifen (Standorte/Abteilungen/bestehende Kennungen werden
    vom Aufrufer übergeben) – macht die Funktion isoliert testbar und
    vermeidet N+1-Lookups pro Zeile."""
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    if reader.fieldnames is None:
        return [], [BulkImportRowError(row=1, message="Die CSV-Datei ist leer.")]

    header = {name.strip().lower() for name in reader.fieldnames if name}
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        return [], [
            BulkImportRowError(
                row=1,
                message=f"Fehlende Spalte(n): {', '.join(missing)}. Erforderlich: {', '.join(REQUIRED_COLUMNS)}.",
            )
        ]

    locations_by_name = {loc.name.strip().lower(): loc for loc in locations}
    departments_by_name = {department.name.strip().lower(): department for department in departments}

    rows: list[ParsedEmployeeRow] = []
    errors: list[BulkImportRowError] = []
    seen_employee_numbers: set[str] = set()
    seen_login_emails: set[str] = set()

    for line_number, raw_row in enumerate(reader, start=2):
        row = {(key or "").strip().lower(): (value or "").strip() for key, value in raw_row.items()}
        try:
            first_name = row.get("vorname", "")
            last_name = row.get("nachname", "")
            employee_number = row.get("personalnummer", "")
            location_name = row.get("standort", "")
            if not first_name or not last_name or not employee_number or not location_name:
                raise ValueError("Vorname, Nachname, Personalnummer und Standort sind Pflichtfelder.")

            if employee_number in existing_employee_numbers or employee_number in seen_employee_numbers:
                raise ValueError(f"Personalnummer '{employee_number}' ist bereits vergeben.")

            location = locations_by_name.get(location_name.lower())
            if location is None:
                raise ValueError(f"Standort '{location_name}' wurde nicht gefunden.")

            department_id = None
            # Spalte „abteilung“; die frühere Spalte „team“ gilt weiter als Abteilung (Teams wurden
            # mit Migration 0134 zu Abteilungen).
            department_name = row.get("abteilung", "") or row.get("team", "")
            if department_name:
                department = departments_by_name.get(department_name.lower())
                if department is None:
                    raise ValueError(f"Abteilung '{department_name}' wurde nicht gefunden.")
                department_id = department.id

            active_raw = row.get("aktiv", "")
            active = _parse_bool(active_raw) if active_raw else True

            if len(first_name) > 100 or len(last_name) > 100 or len(employee_number) > 50:
                raise ValueError("Vorname/Nachname (max. 100) oder Personalnummer (max. 50 Zeichen) ist zu lang.")

            login_email = (row.get("login_email", "") or "").lower() or None
            if login_email is not None:
                try:
                    login_email = _EMAIL.validate_python(login_email)
                except ValidationError as exc:
                    raise ValueError(f"Login-E-Mail '{login_email}' ist keine gültige Adresse.") from exc
            if login_email is not None:
                if login_email in existing_login_emails or login_email in seen_login_emails:
                    raise ValueError(f"Login-E-Mail '{login_email}' ist bereits vergeben.")
                seen_login_emails.add(login_email)

            hire_date_raw = row.get("eintrittsdatum", "")
            hire_date = _parse_date(hire_date_raw, "Anstelldatum") if hire_date_raw else None

            birth_date_raw = row.get("geburtsdatum", "")
            birth_date = _parse_date(birth_date_raw, "Geburtsdatum") if birth_date_raw else None

            # Optional: Arbeitszeitmodell – Tagesstunden (Teilzeit, ungleich verteilt) ODER
            # Wochenstunden + Arbeitstage (gleichmäßig verteilt).
            hours_raw = row.get("wochenstunden", "")
            days_raw = row.get("arbeitstage", "")
            daily_raw = row.get("tagesstunden", "")
            weekly_hours = weekdays = daily_hours = monthly_cap_hours = None
            flexible = on_demand = False
            settled = _parse_settled_overtime(row.get("abgegoltene_ueberstunden", ""))
            rotation_weeks = _parse_rotation(daily_raw, row)
            rotation_start_raw = row.get("turnus_beginn", "")
            rotation_start = _parse_date(rotation_start_raw, "Turnus-Beginn") if rotation_start_raw else None
            if rotation_start is not None and rotation_weeks is None:
                raise ValueError("„turnus_beginn“ gibt es nur beim mehrwöchigen Modell (tagesstunden_woche2 …).")
            if days_raw.strip().lower() in ("nach aufwand", "aufwand"):
                # Aushilfe ohne feste Stunden: kein Soll, optional Monatsgrenze in Stunden.
                if rotation_weeks is not None:
                    raise ValueError("Ein mehrwöchiges Modell lässt sich nicht mit „nach Aufwand“ verbinden.")
                if settled:
                    raise ValueError("Bei „nach Aufwand“ gibt es keine abgegoltenen Überstunden (kein Überstundenkonto).")
                on_demand = True
                cap_raw = row.get("monatsgrenze", "").strip()
                if cap_raw:
                    try:
                        monthly_cap_hours = float(cap_raw.replace(",", "."))
                        WorkTimeModelInput(on_demand=True, monthly_cap_hours=monthly_cap_hours)
                    except (ValueError, ValidationError) as exc:
                        raise ValueError(f"Ungültige Monatsgrenze '{cap_raw}'.") from exc
            elif rotation_weeks is not None:
                try:
                    model = WorkTimeModelInput(
                        rotation_weeks=rotation_weeks, rotation_start=rotation_start, settled_overtime_hours=settled
                    )
                except ValidationError as exc:
                    raise ValueError(f"Arbeitszeitmodell ungültig: {exc.errors()[0]['msg']}") from exc
                if model.exceeds_daily_maximum:
                    raise ValueError("Tagesstunden über 10 Std. (§3 ArbZG).")
                rotation_start = model.rotation_start  # auf den Montag der Woche gelegt
            elif daily_raw:
                daily_hours = _parse_daily_hours(daily_raw)
                try:
                    model = WorkTimeModelInput(daily_hours=daily_hours, settled_overtime_hours=settled)
                except ValidationError as exc:
                    raise ValueError(f"Arbeitszeitmodell ungültig: {exc.errors()[0]['msg']}") from exc
                if model.exceeds_daily_maximum:
                    raise ValueError("Tagesstunden über 10 Std. (§3 ArbZG).")
            elif hours_raw and not days_raw:
                # Nur Wochenstunden: flexibles Modell ohne feste Tage (z.B. Aushilfe).
                try:
                    weekly_hours = float(hours_raw.replace(",", "."))
                    WorkTimeModelInput(weekly_hours=weekly_hours, flexible=True, settled_overtime_hours=settled)
                except (ValueError, ValidationError) as exc:
                    raise ValueError(f"Ungültige Wochenstunden '{hours_raw}'.") from exc
                flexible = True
            elif hours_raw or days_raw:
                if not hours_raw or not days_raw:
                    raise ValueError("Arbeitstage ohne Wochenstunden – bitte Wochenstunden ergänzen.")
                try:
                    weekly_hours = float(hours_raw.replace(",", "."))
                except ValueError as exc:
                    raise ValueError(f"Ungültige Wochenstunden '{hours_raw}'.") from exc
                weekdays = _parse_weekdays(days_raw)
                try:
                    model = WorkTimeModelInput(weekly_hours=weekly_hours, weekdays=weekdays, settled_overtime_hours=settled)
                except ValidationError as exc:
                    raise ValueError(f"Arbeitszeitmodell ungültig: {exc.errors()[0]['msg']}") from exc
                if model.exceeds_daily_maximum:
                    raise ValueError("Arbeitszeitmodell ergibt mehr als 10 Std. pro Arbeitstag (§3 ArbZG).")
            elif settled:
                raise ValueError(
                    "Abgegoltene Überstunden nur zusammen mit einem Arbeitszeitmodell in derselben Zeile "
                    "(Wochenstunden oder Tagesstunden)."
                )
        except ValueError as exc:
            errors.append(BulkImportRowError(row=line_number, message=str(exc)))
            continue

        seen_employee_numbers.add(employee_number)
        rows.append(
            ParsedEmployeeRow(
                first_name=first_name,
                last_name=last_name,
                employee_number=employee_number,
                location_id=location.id,
                department_id=department_id,
                active=active,
                login_email=login_email,
                hire_date=hire_date,
                weekly_hours=weekly_hours,
                weekdays=weekdays,
                daily_hours=daily_hours,
                flexible=flexible,
                on_demand=on_demand,
                monthly_cap_hours=monthly_cap_hours,
                rotation_weeks=rotation_weeks,
                rotation_start=rotation_start,
                settled_overtime_hours=settled,
                birth_date=birth_date,
                line=line_number,
            )
        )

    return rows, errors
