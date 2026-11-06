"""Lohnarten je Zeitart und Zulagenarten-Katalog (Seite „Lohnarten“)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import PayComponent, PayComponentKind, PayComponentType, WageTypeItem, WageTypeMapping


async def wage_type_map(db: AsyncSession, tenant_id: int) -> dict[WageTypeItem, str]:
    rows = (await db.execute(select(WageTypeMapping).where(WageTypeMapping.tenant_id == tenant_id))).scalars().all()
    return {WageTypeItem(row.item): row.wage_type for row in rows if row.item in WageTypeItem.__members__}


async def set_wage_types(db: AsyncSession, tenant_id: int, values: dict[WageTypeItem, str | None]) -> list[str]:
    """Setzt bzw. entfernt Lohnarten je Zeitart; gibt die Änderungen fürs Audit-Log zurück."""
    rows = {
        row.item: row
        for row in (await db.execute(select(WageTypeMapping).where(WageTypeMapping.tenant_id == tenant_id))).scalars().all()
    }
    changes: list[str] = []
    for item, wage_type in values.items():
        row = rows.get(item.value)
        if wage_type is None:
            if row is not None:
                await db.delete(row)
                changes.append(f"{item.value}=leer")
        elif row is None:
            db.add(WageTypeMapping(tenant_id=tenant_id, item=item.value, wage_type=wage_type))
            changes.append(f"{item.value}={wage_type}")
        elif row.wage_type != wage_type:
            row.wage_type = wage_type
            changes.append(f"{item.value}={wage_type}")
    return changes


async def component_type(db: AsyncSession, tenant_id: int, type_id: int) -> PayComponentType:
    item = await db.get(PayComponentType, type_id)
    if item is None or item.tenant_id != tenant_id:
        raise AppError(404, "PAY_COMPONENT_TYPE_NOT_FOUND", "Zulagenart nicht gefunden.")
    return item


async def find_or_create_component_type(
    db: AsyncSession, tenant_id: int, kind: PayComponentKind, name: str, wage_type: str | None = None
) -> PayComponentType:
    """Art nach Name (ohne Groß-/Kleinschreibung) finden oder neu anlegen. Eine gefundene Art ohne
    Lohnart übernimmt die angegebene; eine vorhandene Lohnart bleibt (der Katalog ist maßgeblich)."""
    existing = (
        await db.execute(
            select(PayComponentType).where(
                PayComponentType.tenant_id == tenant_id,
                PayComponentType.kind == kind,
                func.lower(PayComponentType.name) == name.strip().lower(),
            )
        )
    ).scalars().first()
    if existing is not None:
        if existing.wage_type is None and wage_type:
            existing.wage_type = wage_type
        return existing
    item = PayComponentType(tenant_id=tenant_id, kind=kind, name=name.strip(), wage_type=wage_type, active=True)
    db.add(item)
    await db.flush()
    return item


async def component_type_usage(db: AsyncSession, tenant_id: int) -> dict[int, int]:
    rows = await db.execute(
        select(PayComponent.type_id, func.count()).where(PayComponent.tenant_id == tenant_id).group_by(PayComponent.type_id)
    )
    return {type_id: count for type_id, count in rows.all()}
