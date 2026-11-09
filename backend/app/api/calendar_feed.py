"""Kalender-Abo (iCal): ein privater Link je Person, abonnierbar in Outlook, Google
oder Apple Kalender. Inhalt nach denselben Regeln wie die Kalender in der Webapp:
- Admin/HR/Führungskraft: Abwesenheiten aller für sie sichtbaren Mitarbeiter mit Art.
- Mitarbeiter: eigene Abwesenheiten; mit Teamkalender-Freigabe auch die eigene Abteilung (Art nur bei „farbig“,
  sonst „abwesend“; Arbeitszeit-Angaben nicht).
Dazu die Feiertage. Der Link enthält ein Geheimnis; gespeichert wird nur dessen SHA-256.
"""
import hashlib
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.db import get_db
from app.errors import AppError
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Account, Employee, Holiday
from app.services.absence_type_service import CATEGORY_LABELS, list_absence_types
from app.services.holiday_service import applies_to_location
from app.services.ical_service import CalendarEvent, build_ics
from app.services.settings_service import get_or_create_settings
from app.services.scope_service import visible_employee_ids

router = APIRouter(tags=["calendar_feed"])

_PAST_DAYS = 90
_FUTURE_DAYS = 365


class CalendarTokenResponse(BaseModel):
    # Pfad des Abo-Links (ohne Host) – nur jetzt sichtbar, danach nur neu erzeugbar
    path: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _account(actor: Actor) -> Account:
    if actor.account is None or actor.tenant_id is None:
        raise AppError(403, "FORBIDDEN", "Nur für Konten einer Firma.")
    return actor.account


@router.post("/me/calendar-token", response_model=CalendarTokenResponse)
async def create_calendar_token(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> CalendarTokenResponse:
    """Neuen Abo-Link erzeugen – ein früherer Link gilt danach nicht mehr."""
    account = _account(actor)
    token = secrets.token_urlsafe(32)
    account.calendar_token_hash = _hash(token)
    await db.commit()
    return CalendarTokenResponse(path=f"/api/calendar/{token}.ics")


@router.delete("/me/calendar-token", status_code=204)
async def delete_calendar_token(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> None:
    _account(actor).calendar_token_hash = None
    await db.commit()


@router.get("/calendar/{token}.ics", include_in_schema=False)
async def calendar_feed(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    tenant = getattr(request.state, "tenant", None)
    if tenant is None or len(token) > 100:
        raise AppError(404, "NOT_FOUND", "Nicht gefunden.")
    digest = _hash(token)
    account = (
        await db.execute(select(Account).where(Account.tenant_id == tenant.id, Account.calendar_token_hash == digest))
    ).scalar_one_or_none()
    if account is None or (account.employee is not None and not account.employee.active):
        raise AppError(404, "NOT_FOUND", "Nicht gefunden.")
    if account.role is None and account.employee is None:
        raise AppError(404, "NOT_FOUND", "Nicht gefunden.")

    actor = Actor(account=account)
    employee = account.employee
    today = date.today()
    first, last = today - timedelta(days=_PAST_DAYS), today + timedelta(days=_FUTURE_DAYS)
    type_names = {t.id: t.name for t in await list_absence_types(db, tenant.id)}
    colored = {t.id for t in await list_absence_types(db, tenant.id) if t.calendar_visibility == "COLOR"}

    stmt = select(Employee).where(Employee.tenant_id == tenant.id, Employee.active.is_(True))
    if actor.is_hr_level:
        if actor.is_supervisor_level:
            stmt = stmt.where(Employee.id.in_(await visible_employee_ids(db, actor) or set()))
        full_view = True
    else:
        team_calendar = (await get_or_create_settings(db, tenant.id)).team_calendar_for_employees
        if team_calendar and employee.department_id is not None:
            stmt = stmt.where(Employee.department_id == employee.department_id)
        else:
            stmt = stmt.where(Employee.id == employee.id)
        full_view = False
    people = {e.id: e for e in (await db.execute(stmt)).scalars().all()}

    absences = (
        await db.execute(
            select(Absence).where(
                Absence.employee_id.in_(people.keys() or [0]),
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.date_from <= last,
                Absence.date_to >= first,
            )
        )
    ).scalars().all()
    events: list[CalendarEvent] = []
    for absence in absences:
        person = people[absence.employee_id]
        own = employee is not None and person.id == employee.id
        name = type_names.get(absence.absence_type_id or 0) or CATEGORY_LABELS.get(absence.type, "Abwesend")
        if not full_view and not own:
            if absence.type == AbsenceType.WORK_TIME:
                continue
            if (absence.absence_type_id or 0) not in colored:
                name = "abwesend"
        half = "½ " if absence.half_day else ""
        summary = f"{half}{name}" if own and not full_view else f"{person.first_name} {person.last_name}: {half}{name}"
        events.append(CalendarEvent(f"absence-{absence.id}", absence.date_from, absence.date_to, summary))

    holiday_stmt = select(Holiday).where(Holiday.tenant_id == tenant.id, Holiday.date >= first, Holiday.date <= last)
    if employee is not None and not full_view:
        holiday_stmt = holiday_stmt.where(applies_to_location(employee.location_id))
    for holiday in (await db.execute(holiday_stmt)).scalars().all():
        label = f"{holiday.name} (halber Tag)" if holiday.half_day else holiday.name
        events.append(CalendarEvent(f"holiday-{holiday.id}", holiday.date, holiday.date, label))

    host = (request.headers.get("host") or "hr3000").split(":")[0]
    body = build_ics(f"HR3000 – {tenant.name}", events, host)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=900", "Content-Disposition": 'inline; filename="hr3000.ics"'},
    )
