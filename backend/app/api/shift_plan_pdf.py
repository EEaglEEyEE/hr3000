from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Employee
from app.services.shift_plan_pdf_service import render_shift_plan_pdf
from app.services.team_scope_service import ensure_employee_visible

router = APIRouter(tags=["shift_plan_pdf"])

# Deckt sich mit dem Limit von GET /employees/{id}/effective-shifts, siehe
# app/api/shift_plan_entries.py – dieselbe Missbrauchsbremse, kein
# fachlicher Wert.
_MAX_RANGE_DAYS = 62


@router.get("/shift-plan/pdf")
async def export_shift_plan_pdf(
    employee_ids: list[int] = Query(default_factory=list),
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """PDF-Export des Schichtplans für exakt die Mitarbeiter, die der
    Aufrufer im Kalender sieht (siehe ShiftPlanCalendarPage.tsx) – die
    Sichtbarkeitsprüfung pro Mitarbeiter (ensure_employee_visible) verhindert,
    dass ein Supervisor sich Mitarbeiter außerhalb der eigenen Teams
    exportieren kann, selbst wenn die ID direkt in der URL übergeben wird."""
    if not employee_ids:
        raise AppError(400, "NO_EMPLOYEES", "Mindestens ein Mitarbeiter muss ausgewählt werden.")
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

    pdf_bytes = await render_shift_plan_pdf(db, employees, date_from, date_to)
    filename = f"schichtplan_{date_from.isoformat()}_{date_to.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
