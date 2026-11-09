import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import (
    Absence,
    Account,
    EmployeeDocument,
    AuditAction,
    Employee,
    EmployeeDefaultShift,
    LeaveEntitlement,
    Notification,
    Punch,
    ShiftPlanEntry,
)
from app.schemas.absence import AbsenceResponse
from app.schemas.document import DocumentResponse
from app.schemas.employee import EmployeeResponse
from app.schemas.employee_default_shift import EmployeeDefaultShiftResponse
from app.schemas.employee_export import EmployeeDataExportResponse
from app.schemas.leave_entitlement import LeaveEntitlementResponse
from app.schemas.notification import NotificationResponse
from app.schemas.punch import PunchResponse
from app.schemas.shift_plan_entry import ShiftPlanEntryResponse
from app.schemas.personal_data import PersonalData
from app.services import personal_data_service
from app.services.audit_service import log_action
from app.services.leave_service import leave_balance
from app.services.scope_service import ensure_employee_visible

router = APIRouter(tags=["employee_data_export"])


@router.get("/employees/{employee_id}/data-export")
async def export_employee_data(
    employee_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Nur Admin/HR (nicht Supervisor): enthält auch die Personalakte. Vertrauliche Dokumente
    (z.B. Abmahnungen) erscheinen nur, wenn ein Administrator exportiert.

    DSGVO Art. 15 Auskunftsrecht: bündelt alle über den Mitarbeiter
    gespeicherten personenbezogenen Daten als JSON-Datei zum Download –
    Stammdaten, Stempelungen, Abwesenheiten, Urlaubsansprüche, Schichtplanung
    und Benachrichtigungen. Dieselbe Sichtbarkeitsprüfung wie bei anderen
    mitarbeiterbezogenen Exporten (siehe app/api/payroll_export.py)."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    await ensure_employee_visible(db, actor, employee)

    punches_result = await db.execute(
        select(Punch).where(Punch.employee_id == employee_id).order_by(Punch.timestamp_utc.asc())
    )
    absences_result = await db.execute(
        select(Absence).where(Absence.employee_id == employee_id).order_by(Absence.date_from.asc())
    )
    entitlements_result = await db.execute(
        select(LeaveEntitlement)
        .where(LeaveEntitlement.employee_id == employee_id)
        .order_by(LeaveEntitlement.year.asc())
    )
    default_shifts_result = await db.execute(
        select(EmployeeDefaultShift)
        .where(EmployeeDefaultShift.employee_id == employee_id)
        .order_by(EmployeeDefaultShift.valid_from.asc())
    )
    shift_plan_entries_result = await db.execute(
        select(ShiftPlanEntry).where(ShiftPlanEntry.employee_id == employee_id).order_by(ShiftPlanEntry.date.asc())
    )
    notifications_result = await db.execute(
        select(Notification)
        .join(Account, Account.id == Notification.recipient_account_id)
        .where(Account.employee_id == employee_id)
        .order_by(Notification.created_at.asc())
    )

    documents_result = await db.execute(
        select(EmployeeDocument).where(EmployeeDocument.employee_id == employee_id).order_by(EmployeeDocument.created_at.asc())
    )
    entitlements = entitlements_result.scalars().all()
    leave_entitlement_responses = []
    for entitlement in entitlements:
        balance = await leave_balance(db, employee_id, entitlement.year, entitlement)
        leave_entitlement_responses.append(
            LeaveEntitlementResponse(
                employee_id=employee_id,
                year=entitlement.year,
                entitled_days=balance.entitled_days,
                carried_over_days=balance.carried_over_days,
                used_days=balance.used_days,
                remaining_days=balance.remaining_days,
                carried_over_auto=balance.carried_over_auto,
                expired_days=balance.expired_days,
                expiring_days=balance.expiring_days,
                expiry_date=balance.expiry_date,
            )
        )

    export = EmployeeDataExportResponse(
        exported_at=datetime.now(UTC),
        employee=EmployeeResponse.model_validate(employee),
        punches=[PunchResponse.model_validate(p) for p in punches_result.scalars().all()],
        absences=[AbsenceResponse.model_validate(a) for a in absences_result.scalars().all()],
        leave_entitlements=leave_entitlement_responses,
        default_shifts=[
            EmployeeDefaultShiftResponse.model_validate(s) for s in default_shifts_result.scalars().all()
        ],
        shift_plan_entries=[
            ShiftPlanEntryResponse.model_validate(e) for e in shift_plan_entries_result.scalars().all()
        ],
        notifications=[NotificationResponse.model_validate(n) for n in notifications_result.scalars().all()],
        documents=[
            DocumentResponse.model_validate(d)
            for d in documents_result.scalars().all()
            if actor.is_admin_level or not d.confidential
        ],
        personal_data=PersonalData(**await personal_data_service.load(db, employee.id)),
    )

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.EMPLOYEE_DATA_EXPORTED,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"{employee.first_name} {employee.last_name} ({employee.employee_number})",
    )
    await db.commit()

    filename = f"datenexport_{employee.employee_number}_{export.exported_at.date().isoformat()}.json"
    content = export.model_dump_json(indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
