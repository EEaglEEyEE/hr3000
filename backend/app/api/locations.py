from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Location
from app.schemas.location import LocationCreateRequest, LocationResponse, LocationUpdateRequest

router = APIRouter(tags=["locations"])


@router.get("/locations", response_model=list[LocationResponse])
async def list_locations(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[LocationResponse]:
    result = await db.execute(
        select(Location).where(Location.tenant_id == actor.tenant_id).order_by(Location.name.asc())
    )
    return [LocationResponse.model_validate(loc) for loc in result.scalars().all()]


@router.post("/locations", response_model=LocationResponse, status_code=201)
async def create_location(
    payload: LocationCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> LocationResponse:
    location = Location(
        tenant_id=actor.tenant_id,
        name=payload.name,
        timezone=payload.timezone,
        bundesland=payload.bundesland.value if payload.bundesland else None,
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return LocationResponse.model_validate(location)


@router.patch("/locations/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: int,
    payload: LocationUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> LocationResponse:
    location = await db.get(Location, location_id)
    if location is None or location.tenant_id != actor.tenant_id:
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")

    if payload.name is not None:
        location.name = payload.name
    if payload.timezone is not None:
        location.timezone = payload.timezone
    if payload.bundesland is not None:
        location.bundesland = payload.bundesland.value
    elif payload.clear_bundesland:
        location.bundesland = None

    await db.commit()
    await db.refresh(location)
    return LocationResponse.model_validate(location)
