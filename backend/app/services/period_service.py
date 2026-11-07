import base64
import calendar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (
    LOCKING_STATUSES,
    AbsenceType,
    Employee,
    PeriodClosure,
    Punch,
    PunchType,
    SummaryStatus,
    Tenant,
)
from app.services.absence_type_service import format_days, list_absence_types
from app.services.settings_service import get_or_create_settings, tenant_logo_data_url
from app.services.surcharge_service import compute_surcharges
from app.services.timesheet_service import (
    absence_day_counts,
    balance_as_of,
    calculate_day,
    day_fingerprint,
    day_reviews,
    employee_timezone,
    missing_punch_reported,
    needs_review,
    pair_punches_detail,
    punch_blocks,
    punches_by_day,
    review_valid,
    today_in,
)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=select_autoescape())
# Tage: ganze Zahlen ohne Nachkommastelle, halbe Tage mit Komma ("2,5")
_env.filters["days"] = format_days

_WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
_FLAG_LABELS = {
    "UNPLANNED_WORK": "außerplanmäßig gearbeitet",
    "WORK_DURING_ABSENCE": "gestempelt trotz Abwesenheit",
    "HOLIDAY_WORK": "Feiertagsarbeit",
    "OUTSIDE_EMPLOYMENT": "außerhalb Beschäftigung",
    "OVER_MAX_DAILY": "über 10 Std.",
    "LATE_ARRIVAL": "zu spät gekommen",
    "EARLY_LEAVE": "zu früh gegangen",
    "OUTSIDE_FLEX_FRAME": "außerhalb Gleitzeit-Rahmen",
}
_ABSENCE_LABELS = {
    AbsenceType.VACATION: "Urlaub",
    AbsenceType.SICK: "Krank",
    AbsenceType.SPECIAL_LEAVE: "Sonderurlaub",
    AbsenceType.UNPAID: "Unbezahlt",
    AbsenceType.TIME_OFF_IN_LIEU: "Freizeitausgleich",
    AbsenceType.WORK_TIME: "Arbeitszeit",
    AbsenceType.PUBLIC_HOLIDAY: "Feiertag",
    AbsenceType.CHILD_SICK: "Kind krank",
}


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def month_label(year: int, month: int) -> str:
    return f"{_MONTHS[month - 1]} {year}"


def validate_month(year: int, month: int) -> None:
    if not (2000 <= year <= 2100) or not (1 <= month <= 12):
        raise AppError(400, "INVALID_PERIOD", "Ungültiger Monat.")


# --- Sperre -------------------------------------------------------------------------------------


async def locked_months(db: AsyncSession, employee_id: int) -> set[tuple[int, int]]:
    result = await db.execute(
        select(PeriodClosure.year, PeriodClosure.month).where(
            PeriodClosure.employee_id == employee_id, PeriodClosure.status.in_(LOCKING_STATUSES)
        )
    )
    return {(year, month) for year, month in result.all()}


def _locked_error(year: int, month: int) -> AppError:
    return AppError(
        409,
        "PERIOD_LOCKED",
        f"Der Monat {month_label(year, month)} ist abgeschlossen bzw. zur Bestätigung vorgelegt und kann nicht mehr geändert werden. "
        "Er muss zuerst wieder geöffnet werden.",
    )


async def ensure_range_open(db: AsyncSession, employee_id: int, date_from: date, date_to: date) -> None:
    """Wirft PERIOD_LOCKED, wenn ein Tag im Bereich in einem gesperrten Monat liegt."""
    locked = await locked_months(db, employee_id)
    if not locked:
        return
    year, month = date_from.year, date_from.month
    while (year, month) <= (date_to.year, date_to.month):
        if (year, month) in locked:
            raise _locked_error(year, month)
        month += 1
        if month == 13:
            year, month = year + 1, 1


async def ensure_period_open(db: AsyncSession, employee_id: int, day: date) -> None:
    await ensure_range_open(db, employee_id, day, day)


async def ensure_open_from(db: AsyncSession, employee_id: int, from_date: date) -> None:
    """Für Änderungen mit offenem Ende (z.B. neues Arbeitszeitmodell ab Datum X): kein
    gesperrter Monat ab X darf betroffen sein."""
    for year, month in sorted(await locked_months(db, employee_id)):
        if (year, month) >= (from_date.year, from_date.month):
            raise _locked_error(year, month)


async def ensure_tenant_open_from(db: AsyncSession, tenant_id: int, from_date: date) -> None:
    """Mandantenweite Änderung ab Stichtag (z.B. Pausenregeln): kein vorgelegter/abgeschlossener
    Monat irgendeines Mitarbeiters ab diesem Monat darf betroffen sein."""
    row = (
        await db.execute(
            select(PeriodClosure.year, PeriodClosure.month)
            .where(
                PeriodClosure.tenant_id == tenant_id,
                PeriodClosure.status.in_(LOCKING_STATUSES),
                or_(
                    PeriodClosure.year > from_date.year,
                    and_(PeriodClosure.year == from_date.year, PeriodClosure.month >= from_date.month),
                ),
            )
            .order_by(PeriodClosure.year, PeriodClosure.month)
            .limit(1)
        )
    ).first()
    if row is not None:
        raise AppError(
            409,
            "PERIOD_LOCKED",
            f"Ab {month_label(row[0], row[1])} sind bereits Monate vorgelegt bzw. abgeschlossen – "
            "bitte einen späteren Gültig-ab-Stichtag wählen oder die Monate zuerst wieder öffnen.",
        )


async def ensure_holiday_change_allowed(db: AsyncSession, tenant_id: int, day: date, location_ids: set[int] | None) -> None:
    """Ein Feiertag ändert Soll/Ist aller betroffenen Mitarbeiter – in einem bereits vorgelegten
    oder abgeschlossenen Monat (irgendeines betroffenen Mitarbeiters) ist das gesperrt."""
    stmt = (
        select(PeriodClosure.id)
        .join(Employee, Employee.id == PeriodClosure.employee_id)
        .where(
            PeriodClosure.tenant_id == tenant_id,
            PeriodClosure.year == day.year,
            PeriodClosure.month == day.month,
            PeriodClosure.status.in_(LOCKING_STATUSES),
        )
        .limit(1)
    )
    if location_ids:
        stmt = stmt.where(Employee.location_id.in_(location_ids))
    if (await db.execute(stmt)).first() is not None:
        raise AppError(
            409,
            "PERIOD_LOCKED",
            f"Für {month_label(day.year, day.month)} sind bereits Monatsnachweise vorgelegt bzw. abgeschlossen – "
            "Feiertage in diesem Monat können erst nach dem Wiederöffnen geändert werden.",
        )


# --- Monatsbericht --------------------------------------------------------------------------------


@dataclass
class ReportDay:
    day: date
    weekday: str
    label: str
    come: str | None
    go: str | None
    actual_minutes: int | None
    target_minutes: int | None
    delta_minutes: int | None
    non_working: bool
    open: bool
    blocks: str = ""
    # Pausen des Tages (gestempelt, Unterbrechungen, gesetzlicher Abzug) – nur bei vollständigen Tagen
    break_minutes: int | None = None


@dataclass
class MonthReport:
    employee: Employee
    tenant_name: str
    year: int
    month: int
    days: list[ReportDay]
    target_minutes: int = 0
    actual_minutes: int = 0
    delta_minutes: int = 0
    balance_end_minutes: int = 0
    # Halbe Abwesenheitstage zählen 0,5
    vacation_days: float = 0
    sick_days: float = 0
    special_leave_days: float = 0
    unpaid_days: float = 0
    time_off_days: float = 0
    child_sick_days: float = 0
    open_days: list[date] = field(default_factory=list)
    break_minutes: int = 0
    tenant_logo: str | None = None
    # (Name, Prozentsatz, Minuten) je aktiver Zuschlagsregel mit Zeiten > 0
    surcharges: list[tuple[str, float, int]] = field(default_factory=list)


async def build_month_report(db: AsyncSession, employee: Employee, year: int, month: int) -> MonthReport:
    first, last = month_bounds(year, month)
    tz = await employee_timezone(db, employee)
    tenant = await db.get(Tenant, employee.tenant_id)

    # Nachtschichten zählen zum Tag ihres Kommens (Gehen ggf. am Folgetag).
    by_day = await punches_by_day(db, employee, first, last, tz)
    reviews = await day_reviews(db, [employee.id], first, last)
    today = today_in(tz)

    settings_row = await get_or_create_settings(db, employee.tenant_id)
    type_names = {t.id: t.name for t in await list_absence_types(db, employee.tenant_id)}
    report = MonthReport(
        employee=employee, tenant_name=tenant.name if tenant else "", year=year, month=month, days=[],
        tenant_logo=await tenant_logo_data_url(db, employee.tenant_id),
    )
    flexible_target = 0.0
    report_no_punch_days = settings_row.report_days_without_punches
    # Laufender Monat: nur bis heute (Zukunft hat noch kein Ist und belastet das Soll nicht).
    last = min(last, today_in(tz))
    current = first
    while current <= last:
        calc = await calculate_day(db, employee, current, tz)
        punches = by_day.get(current, [])
        come = next((p for p in punches if p.punch_type == PunchType.COME), None)
        go = next((p for p in reversed(punches) if p.punch_type == PunchType.GO), None)
        # Alle Zeitblöcke des Tages (mehrere Kommen/Gehen), z.B. "08:00–12:00, 13:00–17:00".
        blocks = punch_blocks(punches, tz)

        if calc.status == SummaryStatus.HOLIDAY:
            label = "Feiertag"
        elif calc.status == SummaryStatus.ABSENCE:
            label = type_names.get(calc.absence_type_id) or _ABSENCE_LABELS.get(calc.absence_type, "Abwesend")
        elif calc.status == SummaryStatus.PLANNED_OFF:
            label = "Frei"
        elif calc.status == SummaryStatus.COMPLETE:
            label = ""
        elif calc.status == SummaryStatus.OPEN_MISSING_PUNCH and not missing_punch_reported(calc, report_no_punch_days):
            label = ""  # ohne Tagessoll bzw. Tage ohne Stempelung abgeschaltet (Einstellungen)
        elif calc.status == SummaryStatus.OPEN_MISSING_PUNCH:
            label = "Stempelung fehlt"
        elif calc.status == SummaryStatus.ERROR:
            label = "Fehlerhafte Buchung"
        else:
            label = "Offen"

        if calc.absence_label:
            # Halbe Abwesenheitstage, z.B. "½ Urlaub" oder "½ Urlaub · Stempelung fehlt"
            label = calc.absence_label if calc.status in (SummaryStatus.ABSENCE, SummaryStatus.COMPLETE) or not label else f"{calc.absence_label} · {label}"

        # Die eine Regel "Tag offen" (wie "Zu klären"); "Erledigt" gilt, solange der Tag gleich bleibt.
        is_open = needs_review(
            calc.status, calc.flags, current, today, missing_reported=missing_punch_reported(calc, report_no_punch_days)
        ) and not review_valid(
            reviews, employee.id, current, day_fingerprint(calc.status, calc.target_minutes, calc.actual_minutes, calc.flags)
        )
        if calc.flags:
            label = (label + " · " if label else "") + ", ".join(_FLAG_LABELS.get(f, f) for f in calc.flags)
        target = calc.target_minutes
        actual = calc.actual_minutes
        delta = None
        if target is not None:
            delta = (actual or 0) - target
            report.target_minutes += target
        flexible_target += calc.flexible_share
        report.actual_minutes += actual or 0
        counters = {
            AbsenceType.VACATION: "vacation_days",
            AbsenceType.SICK: "sick_days",
            AbsenceType.SPECIAL_LEAVE: "special_leave_days",
            AbsenceType.UNPAID: "unpaid_days",
            AbsenceType.TIME_OFF_IN_LIEU: "time_off_days",
            AbsenceType.CHILD_SICK: "child_sick_days",
        }
        for category, count in absence_day_counts(calc).items():
            if category in counters:  # Arbeitszeit/Feiertag sind keine Abwesenheitstage
                setattr(report, counters[category], getattr(report, counters[category]) + count)
        if is_open:
            report.open_days.append(current)

        breaks = None
        if punches:
            _, _, breaks = await pair_punches_detail(db, employee, current, tz, punches)
            report.break_minutes += breaks or 0

        report.days.append(
            ReportDay(
                day=current,
                weekday=_WEEKDAYS[current.weekday()],
                label=label,
                come=come.timestamp_utc.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M") if come else None,
                go=go.timestamp_utc.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M") if go else None,
                actual_minutes=actual,
                target_minutes=target,
                delta_minutes=delta,
                non_working=calc.status in (SummaryStatus.PLANNED_OFF, SummaryStatus.HOLIDAY),
                blocks=blocks,
                break_minutes=breaks,
                open=is_open,
            )
        )
        current += timedelta(days=1)

    # Flexibles Modell: Wochensoll anteilig auf die Kalendertage des Monats.
    report.target_minutes += round(flexible_target)
    report.delta_minutes = report.actual_minutes - report.target_minutes
    report.balance_end_minutes = (await balance_as_of(db, employee, last)).total_minutes
    report.surcharges = [
        (total.rule.name, float(total.rule.percent), total.minutes)
        for total in await compute_surcharges(db, employee, first, last)
        if total.minutes > 0
    ]
    return report


def format_minutes(minutes: int | None, signed: bool = False) -> str:
    if minutes is None:
        return "–"
    sign = "-" if minutes < 0 else ("+" if signed and minutes > 0 else "")
    value = abs(minutes)
    return f"{sign}{value // 60}:{value % 60:02d}"


_BRAND_ICON = "data:image/svg+xml;base64," + base64.b64encode((_TEMPLATE_DIR / "brand-icon.svg").read_bytes()).decode()


def _report_html(report: MonthReport, for_confirmation: bool) -> str:
    return _env.get_template("time_report.html").render(
        brand_icon=_BRAND_ICON,
        tenant_logo=report.tenant_logo,
        r=report,
        title=month_label(report.year, report.month),
        fmt=format_minutes,
        generated=datetime.now(UTC).strftime("%d.%m.%Y %H:%M UTC"),
        for_confirmation=for_confirmation,
    )


def render_time_report_pdf(report: MonthReport, for_confirmation: bool = True) -> bytes:
    # Import erst hier, siehe Hinweis in shift_plan_pdf_service.py (native Libs).
    from weasyprint import HTML

    return HTML(string=_report_html(report, for_confirmation)).write_pdf()


def render_time_reports_pdf(reports: list[MonthReport]) -> bytes:
    """Mehrere Monatsberichte in einem PDF (je Mitarbeiter ab neuer Seite) – Druckansicht."""
    from weasyprint import HTML

    documents = [HTML(string=_report_html(r, for_confirmation=False)).render() for r in reports]
    pages = [page for document in documents for page in document.pages]
    return documents[0].copy(pages).write_pdf()
