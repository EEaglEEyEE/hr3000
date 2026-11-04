import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Employee
from app.services.absence_type_service import format_days
from app.services.payroll_export_service import summarize_payroll
from app.services.surcharge_service import active_rules, compute_surcharges
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
    if not employee_ids:
        raise AppError(400, "NO_EMPLOYEES", "Mindestens ein Mitarbeiter muss ausgewählt werden.")
    if len(employee_ids) > _MAX_EMPLOYEES:
        raise AppError(400, "TOO_MANY_EMPLOYEES", f"Es können höchstens {_MAX_EMPLOYEES} Mitarbeiter pro Export gewählt werden.")
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(
            400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_RANGE_DAYS} Tage umfassen."
        )

    employees: list[Employee] = []
    for employee_id in employee_ids:
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.tenant_id != actor.tenant_id:
            raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
        if actor.is_hr_level:
            await ensure_employee_visible(db, actor, employee)
        employees.append(employee)

    rules = await active_rules(db, actor.tenant_id)
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
            *[_csv_text(f"Zuschlag {rule.name} (Std.)") for rule in rules],
        ]
    )

    for employee in sorted(employees, key=lambda e: (e.last_name, e.first_name)):
        summary = await summarize_payroll(db, employee, date_from, date_to)
        surcharge_hours = [
            _minutes_to_hours_str(total.minutes) for total in await compute_surcharges(db, employee, date_from, date_to, rules)
        ]
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
                *surcharge_hours,
            ]
        )

    filename = f"lohn-export_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    # UTF-8-BOM voranstellen, damit Excel Umlaute (Müller, Straße, ...) beim
    # Öffnen korrekt als UTF-8 statt als Systemcodepage interpretiert.
    content = "﻿" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
