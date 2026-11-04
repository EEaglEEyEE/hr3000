from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Holiday, Location
from app.schemas.holiday import (
    HolidayCreateRequest,
    HolidayImportRequest,
    HolidayImportResponse,
    HolidayResponse,
    HolidayUpdateRequest,
)
from app.services.holiday_import_service import import_holidays_for_location
from app.services.holiday_service import applies_to_location, location_scope, scopes_overlap
from app.services.period_service import ensure_holiday_change_allowed
from app.services.timesheet_service import invalidate_tenant_balances

router = APIRouter(tags=["holidays"])


async def _load_locations(db: AsyncSession, tenant_id: int, location_ids: list[int]) -> list[Location]:
    unique_ids = sorted(set(location_ids))
    if not unique_ids:
        return []
    result = await db.execute(
        select(Location).where(Location.tenant_id == tenant_id, Location.id.in_(unique_ids))
    )
    locations = list(result.scalars().all())
    if len(locations) != len(unique_ids):
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
    return locations


async def _ensure_no_overlap(
    db: AsyncSession,
    tenant_id: int,
    holiday_date: date,
    scope: set[int] | None,
    exclude_id: int | None = None,
) -> None:
    """Pro Datum darf ein Standort höchstens von einem Feiertag abgedeckt sein
    (anwendungsseitige Eindeutigkeit, siehe app/models/holiday.py)."""
    stmt = select(Holiday).where(Holiday.tenant_id == tenant_id, Holiday.date == holiday_date)
    if exclude_id is not None:
        stmt = stmt.where(Holiday.id != exclude_id)
    for existing in (await db.execute(stmt)).scalars().all():
        if scopes_overlap(scope, location_scope(existing)):
            raise AppError(409, "HOLIDAY_DATE_TAKEN", "Für dieses Datum existiert bereits ein Feiertag.")


@router.get("/holidays", response_model=list[HolidayResponse])
async def list_holidays(
    year: int | None = Query(default=None, ge=2000, le=2100),
    # Mit location_id nur Feiertage, die für diesen Standort gelten (inkl. der
    # standortübergreifenden), siehe app/models/holiday.py.
    location_id: int | None = Query(default=None),
    # Lesbar für alle authentifizierten Akteure (auch Kiosk/Mitarbeiter), damit
    # z.B. eine künftige Kalenderansicht am Tablet Feiertage kennen könnte.
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[HolidayResponse]:
    stmt = select(Holiday).where(Holiday.tenant_id == actor.tenant_id).order_by(Holiday.date.asc(), Holiday.id.asc())
    if year is not None:
        stmt = stmt.where(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31))
    if location_id is not None:
        stmt = stmt.where(applies_to_location(location_id))
    result = await db.execute(stmt)
    return [HolidayResponse.model_validate(h) for h in result.scalars().all()]


@router.post("/holidays", response_model=HolidayResponse, status_code=201)
async def create_holiday(
    payload: HolidayCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> HolidayResponse:
    locations = await _load_locations(db, actor.tenant_id, payload.location_ids)
    await _ensure_no_overlap(db, actor.tenant_id, payload.date, {l.id for l in locations} or None)
    await ensure_holiday_change_allowed(db, actor.tenant_id, payload.date, {l.id for l in locations} or None)

    holiday = Holiday(tenant_id=actor.tenant_id, date=payload.date, name=payload.name, locations=locations)
    db.add(holiday)
    await invalidate_tenant_balances(db, actor.tenant_id, payload.date)
    await db.commit()
    await db.refresh(holiday)
    return HolidayResponse.model_validate(holiday)


@router.post("/holidays/import", response_model=HolidayImportResponse)
async def import_holidays(
    payload: HolidayImportRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> HolidayImportResponse:
    """Berechnet die gesetzlichen Feiertage eines Jahres für ein Bundesland und
    legt sie an – Feiertage, die den Standort bereits abdecken, werden
    übersprungen; gleichnamige Feiertage anderer Standorte werden um den
    Standort erweitert statt dupliziert."""
    imported, skipped = await import_holidays_for_location(
        db, actor.tenant_id, payload.year, payload.location_id, payload.bundesland
    )
    for holiday in imported:
        await ensure_holiday_change_allowed(db, actor.tenant_id, holiday.date, {l.id for l in holiday.locations} or None)
    if imported:
        await invalidate_tenant_balances(db, actor.tenant_id, min(h.date for h in imported))
    await db.commit()
    for holiday in imported:
        await db.refresh(holiday)

    return HolidayImportResponse(
        imported=[HolidayResponse.model_validate(h) for h in imported],
        skipped_existing=skipped,
    )


@router.patch("/holidays/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(
    holiday_id: int,
    payload: HolidayUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> HolidayResponse:
    holiday = await db.get(Holiday, holiday_id)
    if holiday is None or holiday.tenant_id != actor.tenant_id:
        raise AppError(404, "HOLIDAY_NOT_FOUND", "Feiertag nicht gefunden.")

    new_locations = holiday.locations
    if payload.location_ids is not None:
        new_locations = await _load_locations(db, actor.tenant_id, payload.location_ids)
    new_date = payload.date if payload.date is not None else holiday.date

    await _ensure_no_overlap(
        db, actor.tenant_id, new_date, {l.id for l in new_locations} or None, exclude_id=holiday.id
    )

    await ensure_holiday_change_allowed(db, actor.tenant_id, holiday.date, {l.id for l in holiday.locations} or None)
    await ensure_holiday_change_allowed(db, actor.tenant_id, new_date, {l.id for l in new_locations} or None)
    await invalidate_tenant_balances(db, actor.tenant_id, min(holiday.date, new_date))
    holiday.date = new_date
    holiday.locations = new_locations
    if payload.name is not None:
        holiday.name = payload.name

    await db.commit()
    await db.refresh(holiday)
    return HolidayResponse.model_validate(holiday)


@router.delete("/holidays/{holiday_id}", status_code=204)
async def delete_holiday(
    holiday_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    holiday = await db.get(Holiday, holiday_id)
    if holiday is None or holiday.tenant_id != actor.tenant_id:
        raise AppError(404, "HOLIDAY_NOT_FOUND", "Feiertag nicht gefunden.")

    await ensure_holiday_change_allowed(db, actor.tenant_id, holiday.date, {l.id for l in holiday.locations} or None)
    await invalidate_tenant_balances(db, actor.tenant_id, holiday.date)
    await db.delete(holiday)
    await db.commit()
