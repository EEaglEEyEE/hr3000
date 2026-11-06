import calendar
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_payroll_principal
from app.db import get_db
from app.errors import AppError
from app.models import AppSettings, AuditAction, Employee, HrUser, PayrollExportLog, PeriodClosure, PeriodStatus
from app.services.audit_service import log_action
from app.services.settings_service import get_or_create_settings
from app.services.absence_type_service import format_days
from app.services.datev_export_service import build_datev_export
from app.services.pay_component_service import PayComponentAmount, pay_component_amounts
from app.services.payroll_export_service import PayrollPeriod, payroll_period
from app.services.surcharge_service import active_rules, compute_surcharges, merge_by_family
from app.services.team_scope_service import ensure_employee_visible

router = APIRouter(tags=["payroll_export"])

# Lohn-Export deckt typischerweise einen Monat oder ein Jahr ab – deutlich
# großzügiger als das 62-Tage-Limit von Kalender/PDF-Export (siehe
# app/api/shift_plan_pdf.py), aber immer noch eine Missbrauchsbremse.
_MAX_RANGE_DAYS = 366
_MAX_EMPLOYEES = 200


def _csv_text(value: str) -> str:
    """Schutz vor CSV-/Formel-Injektion: Text, der in Excel als Formel gelesen würde
    (=, +, -, @, Tab, CR am Anfang), wird mit einem Apostroph entschärft."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _minutes_to_hours_str(minutes: int) -> str:
    """Deutsches Dezimalkomma statt Punkt (Excel-DE-Locale) – Semikolon als
    CSV-Trenner (siehe unten) macht das Komma dabei nicht mehrdeutig."""
    return f"{minutes / 60:.2f}".replace(".", ",")


def _euro(amounts: list[PayComponentAmount], column: str) -> str:
    """Summe der Zulagen/Einmalzahlungen dieser Spalte mit Dezimalkomma; leer, wenn keine."""
    matching = [a.amount for a in amounts if a.column == column]
    return f"{sum(matching):.2f}".replace(".", ",") if matching else ""


def _log_export(db: AsyncSession, actor: Actor, kind: str, date_from: date, date_to: date, count: int) -> None:
    """Protokoll für den Hinweis "schon exportiert" (ohne Inhalte)."""
    db.add(
        PayrollExportLog(
            tenant_id=actor.tenant_id, kind=kind, date_from=date_from, date_to=date_to, employee_count=count,
            created_by_hr_user_id=actor.audit_hr_user_id,
        )
    )


async def _load_employees(db: AsyncSession, actor: Actor, employee_ids: list[int]) -> list[Employee]:
    if not employee_ids:
        raise AppError(400, "NO_EMPLOYEES", "Mindestens ein Mitarbeiter muss ausgewählt werden.")
    if len(employee_ids) > _MAX_EMPLOYEES:
        raise AppError(400, "TOO_MANY_EMPLOYEES", f"Es können höchstens {_MAX_EMPLOYEES} Mitarbeiter pro Export gewählt werden.")
    employees: list[Employee] = []
    for employee_id in employee_ids:
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.tenant_id != actor.tenant_id:
            raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
        if actor.is_hr_level:
            await ensure_employee_visible(db, actor, employee)
        employees.append(employee)
    return employees


@router.get("/payroll-export")
async def export_payroll(
    employee_ids: list[int] = Query(default_factory=list),
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """CSV-Export für die Lohnbuchhaltung: pro Mitarbeiter aggregiertes
    Soll/Ist/Saldo sowie Abwesenheitstage über den gewählten Zeitraum (siehe
    app/services/payroll_export_service.py). Dieselbe Sichtbarkeitsprüfung
    wie beim PDF-Export (app/api/shift_plan_pdf.py) – ein Supervisor kann
    nur für die eigenen Teams exportieren."""
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(
            400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_RANGE_DAYS} Tage umfassen."
        )

    employees = await _load_employees(db, actor, employee_ids)

    rules = await active_rules(db, actor.tenant_id)
    # Eine Spalte je Regel über alle Fassungen (Name der neuesten Fassung)
    families: dict[int, str] = {}
    for rule in sorted(rules, key=lambda r: (r.family, r.valid_from or date.min)):
        families[rule.family] = rule.name
    # Einmal je Mitarbeiter rechnen (Rechenkern), daraus alle Spalten.
    periods: dict[int, PayrollPeriod] = {e.id: await payroll_period(db, e, date_from, date_to) for e in employees}
    # Zulagen/Einmalzahlungen sind Vergütung: nur mit Berechtigung „Vergütung & Lohn-Export“.
    pay: dict[int, list[PayComponentAmount]] = {}
    if actor.has_payroll_access:
        for employee in employees:
            pay[employee.id] = await pay_component_amounts(db, employee, date_from, date_to, periods[employee.id])
    pay_columns = sorted(
        {amount.column for amounts in pay.values() for amount in amounts},
        key=lambda column: (not column.startswith("Zulage "), column.lower()),
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Personalnummer",
            "Nachname",
            "Vorname",
            "Zeitraum von",
            "Zeitraum bis",
            "Soll (Std.)",
            "Ist (Std.)",
            "Saldo (Std.)",
            "Urlaubstage",
            "Krankheitstage",
            "Sonderurlaubstage",
            "Unbezahlte Tage",
            "Freizeitausgleich-Tage",
            "Feiertage",
            "Offene/fehlerhafte Tage",
            "Kind-krank-Tage",
            "Ausgezahlte Überstunden (Std.)",
            *[_csv_text(f"Zuschlag {name} (Std.)") for name in families.values()],
            *[_csv_text(f"{column} (€)") for column in pay_columns],
        ]
    )

    for employee in sorted(employees, key=lambda e: (e.last_name, e.first_name)):
        summary = periods[employee.id].summary()
        by_family = {rule.family: minutes for rule, minutes in merge_by_family(await compute_surcharges(db, employee, date_from, date_to, rules))}
        surcharge_hours = [_minutes_to_hours_str(by_family.get(family, 0)) for family in families]
        writer.writerow(
            [
                _csv_text(employee.employee_number),
                _csv_text(employee.last_name),
                _csv_text(employee.first_name),
                date_from.isoformat(),
                date_to.isoformat(),
                _minutes_to_hours_str(summary.target_minutes),
                _minutes_to_hours_str(summary.actual_minutes),
                _minutes_to_hours_str(summary.actual_minutes - summary.target_minutes),
                format_days(summary.vacation_days),
                format_days(summary.sick_days),
                format_days(summary.special_leave_days),
                format_days(summary.unpaid_days),
                format_days(summary.time_off_days),
                format_days(summary.holiday_days),
                summary.open_or_error_days,
                format_days(summary.child_sick_days),
                _minutes_to_hours_str(summary.payout_minutes),
                *surcharge_hours,
                *[_euro(pay.get(employee.id, []), column) for column in pay_columns],
            ]
        )

    _log_export(db, actor, "CSV", date_from, date_to, len(employees))
    await db.commit()
    filename = f"lohn-export_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    # UTF-8-BOM voranstellen, damit Excel Umlaute (Müller, Straße, ...) beim
    # Öffnen korrekt als UTF-8 statt als Systemcodepage interpretiert.
    content = "﻿" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- DATEV LODAS (Berechtigung „Vergütung & Lohn-Export“: enthält Beträge) ----------------------------


class DatevSettings(BaseModel):
    # "" = entfernen
    consultant_number: str = Field(default="", pattern=r"^(\d{4,7})?$")
    client_number: str = Field(default="", pattern=r"^(\d{1,5})?$")


@router.get("/payroll-export/datev/settings", response_model=DatevSettings)
async def get_datev_settings(
    actor: Actor = Depends(get_current_payroll_principal), db: AsyncSession = Depends(get_db)
) -> DatevSettings:
    row = await get_or_create_settings(db, actor.tenant_id)
    await db.commit()
    return DatevSettings(consultant_number=row.datev_consultant_number or "", client_number=row.datev_client_number or "")


@router.put("/payroll-export/datev/settings", response_model=DatevSettings)
async def update_datev_settings(
    payload: DatevSettings,
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> DatevSettings:
    """Berater- und Mandantennummer für die DATEV-Datei (auch ohne Zugriff auf die Einstellungen)."""
    row = await get_or_create_settings(db, actor.tenant_id)
    row.datev_consultant_number = payload.consultant_number or None
    row.datev_client_number = payload.client_number or None
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.SETTINGS_CHANGED,
        entity_type="settings",
        entity_id=actor.tenant_id,
        detail=f"DATEV: Beraternummer {payload.consultant_number or 'leer'}, Mandantennummer {payload.client_number or 'leer'}",
    )
    await db.commit()
    return payload

_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class DatevLineResponse(BaseModel):
    personnel_number: str
    name: str
    wage_type: str
    key: str
    value: float
    label: str


class DatevPreviewResponse(BaseModel):
    lines: list[DatevLineResponse]
    warnings: list[str]


async def _datev(db: AsyncSession, actor: Actor, employee_ids: list[int], month: str):
    settings_row = (await db.execute(select(AppSettings).where(AppSettings.tenant_id == actor.tenant_id))).scalar_one_or_none()
    if settings_row is None or not settings_row.datev_consultant_number or not settings_row.datev_client_number:
        raise AppError(400, "DATEV_NOT_CONFIGURED", "Bitte zuerst Berater- und Mandantennummer für DATEV hinterlegen.")
    employees = await _load_employees(db, actor, employee_ids)
    year, number = (int(part) for part in month.split("-"))
    export = await build_datev_export(db, actor.tenant_id, employees, year, number)
    return export, settings_row


@router.get("/payroll-export/datev/preview", response_model=DatevPreviewResponse)
async def preview_datev_export(
    employee_ids: list[int] = Query(default_factory=list),
    month: str = Query(pattern=_MONTH),
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> DatevPreviewResponse:
    """Vorschau der Buchungen und Hinweise (was nicht übertragen werden kann) vor dem Download."""
    export, _ = await _datev(db, actor, employee_ids, month)
    return DatevPreviewResponse(
        lines=[
            DatevLineResponse(
                personnel_number=line.personnel_number,
                name=line.name,
                wage_type=line.wage_type,
                key=line.key,
                value=float(line.value),
                label=line.label,
            )
            for line in export.lines
        ],
        warnings=export.warnings,
    )


@router.get("/payroll-export/datev")
async def download_datev_export(
    employee_ids: list[int] = Query(default_factory=list),
    month: str = Query(pattern=_MONTH),
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """ASCII-Importdatei für DATEV LODAS (Bewegungsdaten des Monats), siehe
    app/services/datev_export_service.py."""
    export, settings_row = await _datev(db, actor, employee_ids, month)
    content = export.render(settings_row.datev_consultant_number, settings_row.datev_client_number)
    first = export.month_start
    _log_export(db, actor, "DATEV", first, first.replace(day=calendar.monthrange(first.year, first.month)[1]), len(employee_ids))
    await db.commit()
    return Response(
        content=content.encode("cp1252", errors="replace"),
        media_type="text/plain; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="datev-lodas_{month}.txt"'},
    )


# --- Status eines Monats: Abschluss und bisherige Exporte ------------------------------------------


class ExportLogEntry(BaseModel):
    kind: str
    date_from: date
    date_to: date
    employee_count: int
    created_at: datetime
    created_by: str | None


class PayrollMonthStatus(BaseModel):
    month: str
    employee_count: int
    # Monatsabschluss der gewählten Mitarbeiter: abgeschlossen / vorgelegt (gesperrt) / offen
    closed: int
    submitted: int
    open: int
    # Exporte, die diesen Monat berühren (neueste zuerst); DATEV nur mit „Vergütung & Lohn-Export“
    exports: list[ExportLogEntry]


@router.get("/payroll-export/status", response_model=PayrollMonthStatus)
async def payroll_month_status(
    month: str = Query(pattern=_MONTH),
    employee_ids: list[int] = Query(default_factory=list),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PayrollMonthStatus:
    """Vor dem Export: Ist der Monat für die Gewählten abgeschlossen, und wurde er schon exportiert?"""
    year, number = (int(part) for part in month.split("-"))
    first = date(year, number, 1)
    last = first.replace(day=calendar.monthrange(year, number)[1])
    employees = await _load_employees(db, actor, employee_ids) if employee_ids else []
    statuses = {
        employee_id: status
        for employee_id, status in (
            await db.execute(
                select(PeriodClosure.employee_id, PeriodClosure.status).where(
                    PeriodClosure.tenant_id == actor.tenant_id,
                    PeriodClosure.year == year,
                    PeriodClosure.month == number,
                    PeriodClosure.employee_id.in_([e.id for e in employees] or [0]),
                )
            )
        ).all()
    }
    closed = sum(1 for e in employees if statuses.get(e.id) == PeriodStatus.CLOSED)
    submitted = sum(1 for e in employees if statuses.get(e.id) == PeriodStatus.SUBMITTED)
    query = (
        select(PayrollExportLog, HrUser.email)
        .outerjoin(HrUser, HrUser.id == PayrollExportLog.created_by_hr_user_id)
        .where(PayrollExportLog.tenant_id == actor.tenant_id, PayrollExportLog.date_from <= last, PayrollExportLog.date_to >= first)
        .order_by(PayrollExportLog.created_at.desc(), PayrollExportLog.id.desc())
        .limit(10)
    )
    if not actor.has_payroll_access:
        query = query.where(PayrollExportLog.kind == "CSV")
    exports = [
        ExportLogEntry(
            kind=log.kind, date_from=log.date_from, date_to=log.date_to, employee_count=log.employee_count,
            created_at=log.created_at, created_by=email,
        )
        for log, email in (await db.execute(query)).all()
    ]
    return PayrollMonthStatus(
        month=month, employee_count=len(employees), closed=closed, submitted=submitted,
        open=len(employees) - closed - submitted, exports=exports,
    )
