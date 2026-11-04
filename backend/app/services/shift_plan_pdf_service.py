from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, ShiftTemplate
from app.services.shift_planning_service import resolve_effective_shift

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=select_autoescape())

# Bit 0=Montag ... Bit 6=Sonntag, siehe app/models/employee_default_shift.py –
# hier nur zur Anzeige, keine Bitmaske-Logik.
_WEEKDAY_LABELS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _format_day_header(day: date) -> str:
    return f"{_WEEKDAY_LABELS_DE[day.weekday()]} {day.strftime('%d.%m.%Y')}"


async def render_shift_plan_pdf(
    db: AsyncSession, employees: list[Employee], date_from: date, date_to: date
) -> bytes:
    """Rendert den Schichtplan für die übergebenen Mitarbeiter über den
    angegebenen Zeitraum als PDF (Jinja2-Template + WeasyPrint) – dieselbe
    Auflösung (resolve_effective_shift) wie Kalenderansicht und
    Druckansicht, damit alle drei Darstellungen immer übereinstimmen."""
    dates: list[date] = []
    current = date_from
    while current <= date_to:
        dates.append(current)
        current += timedelta(days=1)

    rows = []
    for employee in sorted(employees, key=lambda e: (e.last_name, e.first_name)):
        cells = []
        for day in dates:
            plan = await resolve_effective_shift(db, employee.id, day)
            template = (
                await db.get(ShiftTemplate, plan.shift_template_id)
                if plan.shift_template_id is not None
                else None
            )
            cells.append(
                {
                    "is_workday": plan.is_workday,
                    "plan_exists": plan.plan_exists,
                    "template_name": template.name if template else None,
                    "start_time": (
                        template.start_time.strftime("%H:%M")
                        if template and template.start_time
                        else None
                    ),
                    "end_time": (
                        template.end_time.strftime("%H:%M") if template and template.end_time else None
                    ),
                }
            )
        rows.append({"name": f"{employee.last_name}, {employee.first_name}", "cells": cells})

    template = _env.get_template("shift_plan.html")
    html = template.render(
        dates=[_format_day_header(day) for day in dates],
        rows=rows,
        range_label=f"{date_from.strftime('%d.%m.%Y')} – {date_to.strftime('%d.%m.%Y')}",
    )
    # Import erst hier (statt auf Modulebene): WeasyPrint dlopen't Pango/GObject
    # als native Libs, die auf frischen Entwicklungsmaschinen (v.a. macOS) fehlen
    # können – ein modulweiter Import würde dann schon app.main-Import und damit
    # die komplette Testsuite zum Absturz bringen, obwohl nur dieser eine Endpoint
    # PDF-Erzeugung braucht.
    from weasyprint import HTML

    return HTML(string=html).write_pdf()
