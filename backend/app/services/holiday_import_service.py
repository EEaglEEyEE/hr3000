import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Holiday, Location, Tenant, TenantStatus
from app.services.holiday_calendar import Bundesland, public_holidays
from app.services.holiday_service import location_scope
from app.services.settings_service import get_or_create_settings

logger = logging.getLogger(__name__)


async def _resolve_bundesland(
    db: AsyncSession, tenant_id: int, explicit: Bundesland | None, location: Location | None
) -> Bundesland:
    if explicit is not None:
        return explicit
    if location is not None and location.bundesland is not None:
        return Bundesland(location.bundesland)
    settings_row = await get_or_create_settings(db, tenant_id)
    if settings_row.default_bundesland is not None:
        return Bundesland(settings_row.default_bundesland)
    raise AppError(
        400,
        "BUNDESLAND_REQUIRED",
        "Kein Bundesland angegeben und kein Standard-Bundesland in den Einstellungen hinterlegt.",
    )


async def import_holidays_for_location(
    db: AsyncSession,
    tenant_id: int,
    year: int,
    location_id: int | None,
    bundesland: Bundesland | None = None,
) -> tuple[list[Holiday], int]:
    """Kernlogik für manuellen (siehe app/api/holidays.py) und automatischen
    Import (siehe ensure_holidays_imported_for_tenant) – committet nicht selbst,
    das steuert der Aufrufer. location_id=None importiert firmenweite
    Feiertage (alle Standorte) für diesen Mandanten.

    Ein Feiertag steht nur einmal da und trägt mehrere Standorte (siehe
    app/models/holiday.py): deckt bereits ein Feiertag dieses Datums den Standort
    ab, wird übersprungen; gibt es denselben Feiertag (Datum + Name) schon für
    andere Standorte, wird der Standort dort ergänzt statt eine zweite Zeile
    anzulegen."""
    location: Location | None = None
    if location_id is not None:
        location = await db.get(Location, location_id)
        if location is None or location.tenant_id != tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")

    resolved_bundesland = await _resolve_bundesland(db, tenant_id, bundesland, location)
    computed = public_holidays(year, resolved_bundesland)

    result = await db.execute(
        select(Holiday).where(
            Holiday.tenant_id == tenant_id,
            Holiday.date >= date(year, 1, 1),
            Holiday.date <= date(year, 12, 31),
        )
    )
    existing_by_date: dict[date, list[Holiday]] = {}
    for holiday in result.scalars().all():
        existing_by_date.setdefault(holiday.date, []).append(holiday)

    imported: list[Holiday] = []
    skipped = 0
    for holiday_date, name in computed.items():
        existing = existing_by_date.get(holiday_date, [])
        if location is None:
            # Firmenweit: jedes bereits vorhandene Feiertags-Datum genügt.
            if existing:
                skipped += 1
                continue
        elif any(location_scope(h) is None or location.id in (location_scope(h) or set()) for h in existing):
            skipped += 1
            continue

        same_name = next((h for h in existing if h.name == name and location_scope(h) is not None), None)
        if location is not None and same_name is not None:
            same_name.locations = [*same_name.locations, location]
            imported.append(same_name)
            continue

        holiday = Holiday(
            tenant_id=tenant_id,
            date=holiday_date,
            name=name,
            locations=[location] if location is not None else [],
        )
        db.add(holiday)
        existing_by_date.setdefault(holiday_date, []).append(holiday)
        imported.append(holiday)

    return imported, skipped


async def _scope_default_state_holidays(
    db: AsyncSession, tenant_id: int, default: Bundesland, locations, years: tuple[int, ...], today: date
) -> list[date]:
    """Liegen Standorte in verschiedenen Bundesländern, gelten die (früher firmenweit) importierten
    gesetzlichen Feiertage des Standard-Bundeslands künftig nur noch für dessen Standorte. Betrifft
    nur kommende Tage und nur Feiertage, die genau dem gesetzlichen Kalender entsprechen – eigene
    Feiertage der Firma bleiben firmenweit."""
    keep = [loc for loc in locations if loc.bundesland in (None, default.value)]
    changed: list[date] = []
    for year in years:
        computed = public_holidays(year, default)
        rows = (
            await db.execute(
                select(Holiday).where(
                    Holiday.tenant_id == tenant_id,
                    Holiday.date >= max(today, date(year, 1, 1)),
                    Holiday.date <= date(year, 12, 31),
                )
            )
        ).scalars().all()
        for holiday in rows:
            if location_scope(holiday) is not None or computed.get(holiday.date) != holiday.name:
                continue
            if keep:
                holiday.locations = list(keep)
            else:
                await db.delete(holiday)
            changed.append(holiday.date)
    await db.flush()
    return changed


async def ensure_holidays_imported_for_tenant(db: AsyncSession, tenant_id: int) -> None:
    """Sorgt für einen einzelnen Mandanten für das laufende und das kommende
    Jahr für vollständige Feiertage – standortübergreifend, falls
    AppSettings.default_bundesland gesetzt ist, und zusätzlich je Standort mit
    eigenem (abweichendem) Bundesland. Ein Standort ohne auflösbares
    Bundesland wird einfach übersprungen, es wird nichts erzwungen."""
    today = date.today()
    years = (today.year, today.year + 1)
    imported_dates: list[date] = []

    settings_row = await get_or_create_settings(db, tenant_id)
    locations = (await db.execute(select(Location).where(Location.tenant_id == tenant_id))).scalars().all()
    default = settings_row.default_bundesland
    # Firmenweit (für alle Standorte) nur, solange kein Standort in einem anderen Bundesland liegt –
    # sonst bekäme er fremde Feiertage. Dann je Standort: eigenes Bundesland oder das Standard-Bundesland.
    mixed = any(loc.bundesland is not None and loc.bundesland != default for loc in locations)
    if default is not None and mixed:
        imported_dates += await _scope_default_state_holidays(db, tenant_id, Bundesland(default), locations, years, today)
    if default is not None and not mixed:
        for year in years:
            imported, _ = await import_holidays_for_location(db, tenant_id, year, location_id=None)
            imported_dates += [h.date for h in imported]

    for location in locations:
        if location.bundesland is None and (default is None or not mixed):
            continue  # hat schon die firmenweiten bzw. kann nichts auflösen
        for year in years:
            imported, _ = await import_holidays_for_location(db, tenant_id, year, location_id=location.id)
            imported_dates += [h.date for h in imported]

    if imported_dates:
        from app.services.timesheet_service import invalidate_tenant_balances

        await invalidate_tenant_balances(db, tenant_id, min(imported_dates))
    await db.commit()


async def ensure_holidays_imported_for_all_tenants(db: AsyncSession) -> None:
    """Wird beim Start automatisch aufgerufen (siehe app/main.py lifespan) –
    läuft für jeden aktiven Mandanten einzeln, damit nie manuell auf
    "Feiertage importieren" geklickt werden muss."""
    result = await db.execute(select(Tenant).where(Tenant.status != TenantStatus.SUSPENDED))
    for tenant in result.scalars().all():
        try:
            await ensure_holidays_imported_for_tenant(db, tenant.id)
        except Exception:
            # Ein defekter Mandant darf den Import für alle übrigen nicht abbrechen.
            await db.rollback()
            logger.exception("Feiertags-Import für Mandant %s fehlgeschlagen.", tenant.id)
