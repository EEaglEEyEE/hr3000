"""Migration aus einem Altsystem: Werte bestehender Mitarbeiter per CSV übernehmen (Semikolon,
UTF-8), zugeordnet über die Personalnummer, alles zu einem Stichtag:

- saldo_stunden: Überstunden-Übertrag (Buchung "Übertrag" zum Stichtag, auch negativ),
- urlaubsanspruch_tage / uebertrag_vorjahr_tage: Urlaubskonto des Stichtag-Jahres,
- Arbeitszeitmodell ab Stichtag: wochenstunden + arbeitstage, tagesstunden, monatsstunden +
  arbeitstage, nur wochenstunden (flexibel) oder arbeitstage "nach Aufwand" (+ monatsgrenze);
  optional pause_minuten (feste Pause des Modells).

Spaltennamen wie beim Mitarbeiter-Import (Groß-/Kleinschreibung egal). Leere Zellen = nichts
ändern. Geparst und geprüft wird ohne Datenbankzugriff; Sperren (abgeschlossene Monate) und
doppelte Übernahmen prüft der Aufrufer (app/api/migration.py)."""
import csv
import io
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.models import Employee
from app.schemas.employee import BulkImportRowError
from app.schemas.work_time_model import WorkTimeModelInput
from app.services.employee_import_service import _parse_daily_hours, _parse_weekdays

COLUMNS = (
    "personalnummer",
    "saldo_stunden",
    "urlaubsanspruch_tage",
    "uebertrag_vorjahr_tage",
    "wochenstunden",
    "arbeitstage",
    "tagesstunden",
    "monatsstunden",
    "monatsgrenze",
    "pause_minuten",
)


@dataclass
class MigrationRow:
    line: int
    employee: Employee
    balance_minutes: int | None = None
    entitled_days: float | None = None
    carried_over_days: float | None = None
    model: WorkTimeModelInput | None = None
    changes: list[str] = field(default_factory=list)


def _de(value: float) -> str:
    """Zahl mit Dezimalkomma für die Vorschau, z.B. 12,5."""
    return f"{value:g}".replace(".", ",")


def _number(raw: str, label: str, low: float, high: float) -> float:
    try:
        value = float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Ungültige Zahl '{raw}' für {label}.") from exc
    if not low <= value <= high:
        raise ValueError(f"{label} muss zwischen {_de(low)} und {_de(high)} liegen.")
    return value


def _days(value: float) -> float:
    if abs(value * 2 - round(value * 2)) > 1e-9:
        raise ValueError("Urlaubstage nur in halben Tagen (z. B. 12,5).")
    return value


def _model(row: dict[str, str]) -> WorkTimeModelInput | None:
    hours_raw, days_raw, daily_raw = row.get("wochenstunden", ""), row.get("arbeitstage", ""), row.get("tagesstunden", "")
    monthly_raw, cap_raw, pause_raw = row.get("monatsstunden", ""), row.get("monatsgrenze", ""), row.get("pause_minuten", "")
    if not any((hours_raw, days_raw, daily_raw, monthly_raw, cap_raw)):
        if pause_raw:
            raise ValueError("pause_minuten nur zusammen mit einem Arbeitszeitmodell.")
        return None
    data: dict = {}
    if pause_raw:
        data["break_minutes"] = int(_number(pause_raw, "pause_minuten", 1, 240))
    if days_raw.strip().lower() in ("nach aufwand", "aufwand"):
        data.update(on_demand=True, monthly_cap_hours=_number(cap_raw, "monatsgrenze", 0.01, 400) if cap_raw else None)
    elif daily_raw:
        data["daily_hours"] = _parse_daily_hours(daily_raw)
    elif monthly_raw:
        if not days_raw:
            raise ValueError("Monatsstunden ohne Arbeitstage – bitte arbeitstage ergänzen (z. B. Mo-Fr).")
        data.update(monthly_hours=_number(monthly_raw, "monatsstunden", 0.01, 260), weekdays=_parse_weekdays(days_raw))
    elif hours_raw and not days_raw:
        data.update(weekly_hours=_number(hours_raw, "wochenstunden", 0.01, 60), flexible=True)
    else:
        if not hours_raw:
            raise ValueError("Arbeitstage ohne Wochenstunden – bitte wochenstunden ergänzen.")
        data.update(weekly_hours=_number(hours_raw, "wochenstunden", 0.01, 60), weekdays=_parse_weekdays(days_raw))
    try:
        model = WorkTimeModelInput(**data)
    except ValidationError as exc:
        raise ValueError(f"Arbeitszeitmodell ungültig: {exc.errors()[0]['msg']}") from exc
    if model.exceeds_daily_maximum:
        raise ValueError("Arbeitszeitmodell ergibt mehr als 10 Std. pro Arbeitstag (§3 ArbZG).")
    return model


def _describe_model(model: WorkTimeModelInput) -> str:
    if model.on_demand:
        return "Arbeitszeitmodell: nach Aufwand" + (f", Monatsgrenze {_de(model.monthly_cap_hours)} h" if model.monthly_cap_hours else "")
    if model.monthly_hours is not None:
        text = f"Arbeitszeitmodell: {_de(model.monthly_hours)} h/Monat"
    elif model.flexible:
        text = f"Arbeitszeitmodell: {_de(model.weekly_hours)} h/Woche flexibel"
    else:
        text = f"Arbeitszeitmodell: {_de(model.weekly_hours)} h/Woche"
    return text + model.break_label


def parse_migration_csv(content: str, employees_by_number: dict[str, Employee]) -> tuple[list[MigrationRow], list[BulkImportRowError]]:
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    if reader.fieldnames is None:
        return [], [BulkImportRowError(row=1, message="Die CSV-Datei ist leer.")]
    header = {name.strip().lower() for name in reader.fieldnames if name}
    if "personalnummer" not in header:
        return [], [BulkImportRowError(row=1, message="Spalte personalnummer fehlt.")]
    unknown = sorted(header - set(COLUMNS))
    if unknown:
        return [], [BulkImportRowError(row=1, message=f"Unbekannte Spalte(n): {', '.join(unknown)}. Erlaubt: {', '.join(COLUMNS)}.")]

    rows: list[MigrationRow] = []
    errors: list[BulkImportRowError] = []
    seen: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        row = {(key or "").strip().lower(): (value or "").strip() for key, value in raw.items()}
        if not any(row.values()):
            continue  # Leerzeile
        try:
            number = row.get("personalnummer", "")
            employee = employees_by_number.get(number)
            if employee is None:
                raise ValueError(f"Personalnummer '{number}' nicht gefunden.")
            if number in seen:
                raise ValueError(f"Personalnummer '{number}' kommt mehrfach vor.")
            result = MigrationRow(line=line, employee=employee)
            if row.get("saldo_stunden"):
                hours = _number(row["saldo_stunden"], "saldo_stunden", -2000, 2000)
                result.balance_minutes = round(hours * 60)
                result.changes.append(f"Überstunden-Übertrag {'+' if hours >= 0 else '−'}{_de(abs(hours))} h")
            if row.get("urlaubsanspruch_tage"):
                result.entitled_days = _days(_number(row["urlaubsanspruch_tage"], "urlaubsanspruch_tage", 0, 365))
                result.changes.append(f"Urlaubsanspruch {_de(result.entitled_days)} Tage")
            if row.get("uebertrag_vorjahr_tage"):
                result.carried_over_days = _days(_number(row["uebertrag_vorjahr_tage"], "uebertrag_vorjahr_tage", -365, 365))
                result.changes.append(f"Übertrag Vorjahr {_de(result.carried_over_days)} Tage")
            result.model = _model(row)
            if result.model is not None:
                result.changes.append(_describe_model(result.model))
            if not result.changes:
                raise ValueError("Keine Werte zum Übernehmen.")
        except ValueError as exc:
            errors.append(BulkImportRowError(row=line, message=str(exc)))
            continue
        seen.add(number)
        rows.append(result)
    return rows, errors
