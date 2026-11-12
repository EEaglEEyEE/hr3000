"""DATEV-LODAS-Export: Bewegungsdaten eines Abrechnungsmonats als ASCII-Importdatei, die das
Lohnbüro in LODAS einliest (Mandant → Daten übernehmen → ASCII-Import).

Aufbau nach dem LODAS-Schnittstellenhandbuch: Abschnitte [Allgemein] (Ziel, Berater-/
Mandantennummer, Formate), [Satzbeschreibung] (Tabelle u_lod_bwd_buchung_standard mit
Abrechnungszeitraum, Personalnummer, Lohnart, Bearbeitungsschlüssel, Wert) und [Bewegungsdaten].
Bearbeitungsschlüssel 01 = Stunden, 02 = Betrag (brutto). Übertragen werden (Lohnarten von der
Seite „Lohnarten“):

- Stunden je Zeitart von Mitarbeitern mit Stundenlohn (Vergütung "Stundenlohn" im Monat):
  gearbeitete Stunden (Stempelzeit) und – wenn dafür eine Lohnart hinterlegt ist – Gutschriften
  für Urlaub, Krankheit, Kind krank, Sonderurlaub, Feiertag; Arbeitszeit-Angaben (z.B. Homeoffice)
  ohne eigene Lohnart zählen als gearbeitete Stunden,
- ausgezahlte Überstunden (Korrekturbuchung "Auszahlung") mit Lohnart, unabhängig von der
  Vergütungsart,
- Zuschlagsstunden je Zuschlagsregel mit hinterlegter Lohnart,
- Zulagen und Einmalzahlungen mit der Lohnart ihrer Art als Betrag.

Mit dem Gehalt abgegoltene Überstunden (Grenze im Arbeitszeitmodell) lösen keine Zahlung aus und
werden deshalb nicht gebucht; die Vorschau nennt sie je Mitarbeiter als Hinweis.

Gutschriften ohne Lohnart erfasst das Lohnbüro wie bisher als Fehlzeiten (z.B. aus dem
CSV-Lohn-Export); die Vorschau nennt sie je Mitarbeiter. Was nicht übertragen werden kann, steht in
den Hinweisen. Der Aufbau muss mit dem Lohnbüro einmal per Testimport abgestimmt werden.
"""
import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AbsenceType, Compensation, Employee, PayType, WageTypeItem
from app.schemas.wage_type import WAGE_TYPE_LABELS
from app.services.pay_component_service import pay_component_amounts
from app.services.payroll_export_service import payroll_period
from app.services.surcharge_service import active_rules, compute_surcharges
from app.services.timesheet_service import has_settled_limit, settled_between
from app.services.wage_type_service import wage_type_map

HOURS = "01"
AMOUNT = "02"
_CENT = Decimal("0.01")
_PNR = re.compile(r"^\d{1,10}$")
# Gutschriften je Kategorie -> Zeitart mit eigener Lohnart
_CREDIT_ITEMS = {
    AbsenceType.VACATION: WageTypeItem.VACATION,
    AbsenceType.SICK: WageTypeItem.SICK,
    AbsenceType.CHILD_SICK: WageTypeItem.CHILD_SICK,
    AbsenceType.SPECIAL_LEAVE: WageTypeItem.SPECIAL_LEAVE,
    AbsenceType.PUBLIC_HOLIDAY: WageTypeItem.PUBLIC_HOLIDAY,
    AbsenceType.WORK_TIME: WageTypeItem.WORK_TIME,
}


def _hours(minutes: int) -> Decimal:
    return (Decimal(minutes) / 60).quantize(_CENT, ROUND_HALF_UP)


def _hours_text(minutes: int) -> str:
    return f"{minutes / 60:.2f}".replace(".", ",")


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


async def _has_compensation(db: AsyncSession, employee: Employee, first: date, last: date) -> bool:
    return (
        await db.execute(
            select(Compensation.id).where(
                Compensation.employee_id == employee.id,
                Compensation.valid_from <= last,
                or_(Compensation.valid_to.is_(None), Compensation.valid_to >= first),
            ).limit(1)
        )
    ).first() is not None


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
    mapping = await wage_type_map(db, tenant_id)
    hours_wage_type = mapping.get(WageTypeItem.WORKED)
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

        period = await payroll_period(db, employee, first, last)
        summary = period.summary()
        if summary.open_or_error_days:
            export.warnings.append(
                f"{name}: {summary.open_or_error_days} offene oder fehlerhafte Tage – vor dem Export unter „Zu klären“ prüfen."
            )

        hourly_minutes = 0
        credits: dict[AbsenceType, int] = {}
        for start, end in await _hourly_ranges(db, employee, first, last):
            part = period.summary(start, end)
            hourly_minutes += part.worked_minutes
            for category, minutes in part.credit_minutes.items():
                credits[category] = credits.get(category, 0) + minutes
        # Arbeitszeit-Angaben (z.B. Homeoffice) ohne eigene Lohnart sind gearbeitete Stunden.
        if WageTypeItem.WORK_TIME not in mapping:
            hourly_minutes += credits.pop(AbsenceType.WORK_TIME, 0)
        if hourly_minutes:
            if hours_wage_type:
                add(hours_wage_type, HOURS, _hours(hourly_minutes), WAGE_TYPE_LABELS[WageTypeItem.WORKED])
            else:
                hours_without_type.append(name)
        if not hourly_minutes and summary.worked_minutes and not await _has_compensation(db, employee, first, last):
            export.warnings.append(
                f"{name}: keine Vergütung hinterlegt („Vertrag & Vergütung“) – Stunden nicht übertragen."
            )
        unmapped: list[str] = []
        for category, minutes in sorted(credits.items(), key=lambda pair: pair[0].value):
            item = _CREDIT_ITEMS.get(category)
            if not minutes or item is None:
                continue
            if item in mapping:
                add(mapping[item], HOURS, _hours(minutes), WAGE_TYPE_LABELS[item])
            else:
                unmapped.append(f"{_hours_text(minutes)} Std. {WAGE_TYPE_LABELS[item]}")
        if unmapped:
            export.warnings.append(
                f"{name}: {', '.join(unmapped)} ohne Lohnart nicht übertragen – Lohnart unter „Lohnarten“ hinterlegen "
                "oder im Lohnprogramm als Fehlzeiten erfassen."
            )
        if summary.payout_has_factor:
            export.warnings.append(
                f"{name}: Auszahlung mit Faktor – übertragen werden die Stunden ({_hours_text(summary.payout_minutes)}), "
                f"gewichtet {_hours_text(summary.weighted_payout_minutes)} Std.; den Zuschlag im Lohnprogramm erfassen."
            )
        if summary.payout_minutes:
            if WageTypeItem.OVERTIME_PAYOUT in mapping:
                add(mapping[WageTypeItem.OVERTIME_PAYOUT], HOURS, _hours(summary.payout_minutes), WAGE_TYPE_LABELS[WageTypeItem.OVERTIME_PAYOUT])
            else:
                export.warnings.append(
                    f"{name}: {_hours_text(summary.payout_minutes)} Std. ausgezahlte Überstunden ohne Lohnart – nicht übertragen."
                )

        if await has_settled_limit(db, employee, first, last):
            settled = await settled_between(db, employee, first, last)
            if settled:
                export.warnings.append(
                    f"{name}: {_hours_text(settled)} Std. Überstunden mit dem Gehalt abgegolten – keine Buchung, nur zur Information."
                )

        for total in await compute_surcharges(db, employee, first, last, rules):
            if not total.minutes:
                continue
            if total.rule.wage_type:
                add(total.rule.wage_type, HOURS, _hours(total.minutes), f"Zuschlag {total.rule.name}")
            else:
                missing_rule_types.add(total.rule.name)

        for item in await pay_component_amounts(db, employee, first, last, period):
            if not item.amount:
                continue
            if item.component.wage_type:
                add(item.component.wage_type, AMOUNT, item.amount, item.column)
            else:
                export.warnings.append(f"{name}: {item.column} ohne Lohnart – nicht übertragen.")

        export.lines.extend(sorted(lines.values(), key=lambda line: (line.wage_type, line.key)))

    if hours_without_type:
        export.warnings.append(
            "Keine Lohnart für gearbeitete Stunden hinterlegt („Lohnarten“) – Stunden nicht übertragen für: "
            + "; ".join(hours_without_type)
        )
    for rule_name in sorted(missing_rule_types):
        export.warnings.append(f"Zuschlag „{rule_name}“ ohne Lohnart – Zuschlagsstunden nicht übertragen.")
    return export

