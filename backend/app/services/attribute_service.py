"""Werte eigener Felder prüfen, speichern und lesen (siehe app/models/attribute.py)."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import AttributeDefinition, AttributeValue, Employee


def options_of(definition: AttributeDefinition) -> list[str]:
    return json.loads(definition.options or "[]")


async def normalize(db: AsyncSession, definition: AttributeDefinition, value: str | None, tenant_id: int) -> str | None:
    """Wert je Feldtyp prüfen und einheitlich speichern; None = leer."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    kind = definition.field_type
    if kind == "NUMBER":
        try:
            return str(Decimal(value.replace(",", ".")))
        except InvalidOperation as exc:
            raise AppError(400, "ATTRIBUTE_INVALID", f"„{definition.label}“: bitte eine Zahl angeben.") from exc
    if kind == "DATE":
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise AppError(400, "ATTRIBUTE_INVALID", f"„{definition.label}“: bitte ein Datum angeben.") from exc
    if kind == "SELECT":
        if value not in options_of(definition):
            raise AppError(400, "ATTRIBUTE_INVALID", f"„{definition.label}“: bitte einen der Auswahlwerte nehmen.")
        return value
    if kind == "BOOLEAN":
        if value.lower() not in ("true", "false"):
            raise AppError(400, "ATTRIBUTE_INVALID", f"„{definition.label}“: Ja oder Nein.")
        return value.lower()
    if kind == "EMPLOYEE":
        person = await db.get(Employee, int(value)) if value.isdigit() else None
        if person is None or person.tenant_id != tenant_id:
            raise AppError(400, "ATTRIBUTE_INVALID", f"„{definition.label}“: Person nicht gefunden.")
        return str(person.id)
    return value


async def display(db: AsyncSession, definition: AttributeDefinition, value: str | None) -> str | None:
    if value is None:
        return None
    if definition.field_type == "BOOLEAN":
        return "Ja" if value == "true" else "Nein"
    if definition.field_type == "DATE":
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    if definition.field_type == "NUMBER":
        return value.replace(".", ",")
    if definition.field_type == "EMPLOYEE":
        person = await db.get(Employee, int(value))
        return f"{person.first_name} {person.last_name}" if person else None
    return value


def current(values: list[AttributeValue], today: date | None = None) -> AttributeValue | None:
    """Jüngster Wert bis heute (Werte ohne Gültig-ab zählen als gültig)."""
    today = today or date.today()
    valid = [v for v in values if v.valid_from is None or v.valid_from <= today]
    return max(valid, key=lambda v: (v.valid_from or date.min, v.id)) if valid else None


async def values_for(db: AsyncSession, employee_id: int) -> dict[int, list[AttributeValue]]:
    rows = (
        await db.execute(select(AttributeValue).where(AttributeValue.employee_id == employee_id).order_by(AttributeValue.id))
    ).scalars().all()
    grouped: dict[int, list[AttributeValue]] = {}
    for row in rows:
        grouped.setdefault(row.attribute_id, []).append(row)
    return grouped
