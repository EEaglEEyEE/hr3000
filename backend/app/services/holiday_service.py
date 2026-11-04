from datetime import date

from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.models import Holiday
from app.models.holiday import holiday_locations


def applies_to_location(location_id: int | ColumnElement) -> ColumnElement:
    """SQL-Bedingung: der Feiertag gilt für diesen Standort – entweder weil er
    keinem Standort zugeordnet ist (= alle) oder weil der Standort dabei ist."""
    has_any_location = exists().where(holiday_locations.c.holiday_id == Holiday.id)
    has_this_location = exists().where(
        and_(holiday_locations.c.holiday_id == Holiday.id, holiday_locations.c.location_id == location_id)
    )
    return or_(not_(has_any_location), has_this_location)


async def is_holiday_for_location(db: AsyncSession, tenant_id: int, work_date: date, location_id: int) -> bool:
    result = await db.execute(
        select(Holiday.id).where(
            Holiday.tenant_id == tenant_id, Holiday.date == work_date, applies_to_location(location_id)
        )
    )
    return result.first() is not None


def location_scope(holiday: Holiday) -> set[int] | None:
    """None = alle Standorte, sonst die Menge der betroffenen Standort-IDs."""
    return {location.id for location in holiday.locations} or None


def scopes_overlap(first: set[int] | None, second: set[int] | None) -> bool:
    if first is None or second is None:
        return True
    return bool(first & second)
