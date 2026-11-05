"""DATEV-LODAS-Export: Bewegungsdaten eines Abrechnungsmonats als ASCII-Importdatei, die das
Lohnbüro in LODAS einliest (Mandant → Daten übernehmen → ASCII-Import).

Aufbau nach dem LODAS-Schnittstellenhandbuch: Abschnitte [Allgemein] (Ziel, Berater-/
Mandantennummer, Formate), [Satzbeschreibung] (Tabelle u_lod_bwd_buchung_standard mit
Abrechnungszeitraum, Personalnummer, Lohnart, Bearbeitungsschlüssel, Wert) und [Bewegungsdaten].
Bearbeitungsschlüssel 01 = Stunden, 02 = Betrag (brutto). Übertragen werden:

- Ist-Stunden von Mitarbeitern mit Stundenlohn (Vergütung "Stundenlohn" im Monat), Lohnart aus
  den Einstellungen,
- Zuschlagsstunden je Zuschlagsregel mit hinterlegter Lohnart,
- Zulagen und Einmalzahlungen mit hinterlegter Lohnart als Betrag.

Fehlzeiten (Urlaub, Krankheit) überträgt der Export nicht – die erfasst das Lohnbüro wie bisher
(z.B. aus dem CSV-Lohn-Export). Was nicht übertragen werden kann, steht in den Hinweisen.
Der Aufbau muss mit dem Lohnbüro einmal per Testimport abgestimmt werden.
"""
import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings, Compensation, Employee, PayType
from app.services.pay_component_service import pay_component_amounts
from app.services.payroll_export_service import summarize_payroll
from app.services.surcharge_service import active_rules, compute_surcharges

HOURS = "01"
AMOUNT = "02"
_CENT = Decimal("0.01")
_PNR = re.compile(r"^\d{1,10}$")


@dataclass
class DatevLine:
    personnel_number: str
    name: str
    wage_type: str
    key: str  # Bearbeitungsschlüssel
    value: Decimal
    label: str  # wofür (nur Vorschau)


@dataclass
class DatevExport:
    month_start: date
    lines: list[DatevLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self, consultant: str, client: str) -> str:
        """Importdatei; Zeilenende CRLF wie unter Windows (LODAS)."""
        out = [
            "[Allgemein]",
            "Ziel=LODAS",
            "Version_SST=1.0",
            f"BeraterNr={consultant}",
            f"MandantenNr={client}",
            "Datumsformat=TT.MM.JJJJ",
            "Feldtrennzeichen=;",
            "Zahlenkomma=,",
            "",
            "[Satzbeschreibung]",
            "1;u_lod_bwd_buchung_standard;abrechnung_zeitraum#bwd;pnr#bwd;la_eigene#bwd;bs_nr#bwd;bs_wert_butab#bwd;",
            "",
            "[Bewegungsdaten]",
        ]
        period = self.month_start.strftime("%d.%m.%Y")
        for line in self.lines:
            value = f"{line.value:.2f}".replace(".", ",")
            out.append(f"1;{period};{line.personnel_number};{line.wage_type};{line.key};{value};")
        return "\r\n".join(out) + "\r\n"


async def _hourly_ranges(db: AsyncSession, employee: Employee, first: date, last: date) -> list[tuple[date, date]]:
    """Teile des Monats, in denen der Mitarbeiter laut Vergütung Stundenlohn bekommt."""
    rows = (
        await db.execute(
            select(Compensation).where(
                Compensation.employee_id == employee.id,
                Compensation.pay_type == PayType.HOURLY,
                Compensation.valid_from <= last,
                or_(Compensation.valid_to.is_(None), Compensation.valid_to >= first),
            )
        )
    ).scalars().all()
    return [(max(first, c.valid_from), min(last, c.valid_to or last)) for c in rows]


async def build_datev_export(db: AsyncSession, tenant_id: int, employees: list[Employee], year: int, month: int) -> DatevExport:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    settings_row = (await db.execute(select(AppSettings).where(AppSettings.tenant_id == tenant_id))).scalar_one_or_none()
    hours_wage_type = settings_row.datev_hours_wage_type if settings_row else None
    rules = await active_rules(db, tenant_id)
    export = DatevExport(first)
    missing_rule_types: set[str] = set()
    hours_without_type: list[str] = []

    for employee in sorted(employees, key=lambda e: (e.last_name, e.first_name)):
        name = f"{employee.last_name}, {employee.first_name}"
        pnr = (employee.employee_number or "").strip()
        if not _PNR.match(pnr):
            export.warnings.append(f"{name}: Personalnummer „{pnr}“ ist nicht rein numerisch – nicht übertragen.")
            continue
        lines: dict[tuple[str, str], DatevLine] = {}

        def add(wage_type: str, key: str, value: Decimal, label: str) -> None:
            if value == 0:
                return
            existing = lines.get((wage_type, key))
            if existing is None:
                lines[(wage_type, key)] = DatevLine(pnr, name, wage_type, key, value, label)
            else:
                existing.value += value
                existing.label += f", {label}"

        summary = await summarize_payroll(db, employee, first, last)
        if summary.open_or_error_days:
            export.warnings.append(
                f"{name}: {summary.open_or_error_days} offene oder fehlerhafte Tage – vor dem Export unter „Zu klären“ prüfen."
            )

        hourly_minutes = 0
        for start, end in await _hourly_ranges(db, employee, first, last):
            hourly_minutes += (await summarize_payroll(db, employee, start, end)).actual_minutes
        if hourly_minutes:
            if hours_wage_type:
                add(hours_wage_type, HOURS, (Decimal(hourly_minutes) / 60).quantize(_CENT, ROUND_HALF_UP), "Ist-Stunden")
            else:
                hours_without_type.append(name)

        for total in await compute_surcharges(db, employee, first, last, rules):
            if not total.minutes:
                continue
            if total.rule.wage_type:
                add(total.rule.wage_type, HOURS, (Decimal(total.minutes) / 60).quantize(_CENT, ROUND_HALF_UP), f"Zuschlag {total.rule.name}")
            else:
                missing_rule_types.add(total.rule.name)

        for item in await pay_component_amounts(db, employee, first, last):
            if not item.amount:
                continue
            if item.component.wage_type:
                add(item.component.wage_type, AMOUNT, item.amount, item.column)
            else:
                export.warnings.append(f"{name}: {item.column} ohne Lohnart – nicht übertragen.")

        export.lines.extend(sorted(lines.values(), key=lambda line: (line.wage_type, line.key)))

    if hours_without_type:
        export.warnings.append(
            "Keine Lohnart für Ist-Stunden hinterlegt – Stunden nicht übertragen für: " + "; ".join(hours_without_type)
        )
    for rule_name in sorted(missing_rule_types):
        export.warnings.append(f"Zuschlag „{rule_name}“ ohne Lohnart – Zuschlagsstunden nicht übertragen.")
    return export

