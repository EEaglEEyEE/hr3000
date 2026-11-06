from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import AbsenceType, AbsenceTypeDefinition

# Anzeigename je Kategorie (für Abwesenheiten ohne eigene Art)
CATEGORY_LABELS: dict[AbsenceType, str] = {
    AbsenceType.VACATION: "Urlaub",
    AbsenceType.SICK: "Krank",
    AbsenceType.SPECIAL_LEAVE: "Sonderurlaub",
    AbsenceType.UNPAID: "Unbezahlt",
    AbsenceType.TIME_OFF_IN_LIEU: "Freizeitausgleich",
    AbsenceType.WORK_TIME: "Arbeitszeit",
    AbsenceType.PUBLIC_HOLIDAY: "Feiertag",
    AbsenceType.CHILD_SICK: "Kind krank",
}

def format_days(days: float) -> str:
    """Tage für Anzeige/Export: ganze Zahlen ohne Nachkommastelle, halbe Tage mit Komma ("2,5")."""
    return str(int(days)) if float(days).is_integer() else f"{days:.1f}".replace(".", ",")


# Startausstattung je Mandant: (Name, Farbe, Kategorie, Nachweis ab Tag)
DEFAULT_TYPES: list[tuple[str, str, AbsenceType, int | None]] = [
    ("Urlaub", "#10b981", AbsenceType.VACATION, None),
    ("Krank", "#ef4444", AbsenceType.SICK, 4),
    ("Sonderurlaub", "#64748b", AbsenceType.SPECIAL_LEAVE, None),
    ("Freizeitausgleich", "#0ea5e9", AbsenceType.TIME_OFF_IN_LIEU, None),
    ("Unbezahlt", "#a855f7", AbsenceType.UNPAID, None),
]


async def list_absence_types(db: AsyncSession, tenant_id: int) -> list[AbsenceTypeDefinition]:
    """Alle Abwesenheitsarten des Mandanten; legt beim ersten Zugriff die Standardarten an."""
    rows = (
        await db.execute(
            select(AbsenceTypeDefinition)
            .where(AbsenceTypeDefinition.tenant_id == tenant_id)
            .order_by(AbsenceTypeDefinition.sort_order, AbsenceTypeDefinition.id)
        )
    ).scalars().all()
    if rows:
        return list(rows)
    created = [
        AbsenceTypeDefinition(
            tenant_id=tenant_id,
            name=name,
            color=color,
            category=category,
            requires_approval=False,
            employee_can_request=True,
            certificate_from_day=certificate,
            active=True,
            sort_order=index,
        )
        for index, (name, color, category, certificate) in enumerate(DEFAULT_TYPES)
    ]
    db.add_all(created)
    await db.flush()
    return created


async def resolve_absence_type(
    db: AsyncSession, tenant_id: int, absence_type_id: int | None, category: AbsenceType | None
) -> AbsenceTypeDefinition:
    """Abwesenheitsart für eine neue/geänderte Abwesenheit: per ID oder – für ältere Clients,
    die nur die Kategorie schicken – die erste aktive Art dieser Kategorie."""
    types = await list_absence_types(db, tenant_id)
    if absence_type_id is not None:
        match = next((t for t in types if t.id == absence_type_id), None)
        if match is None:
            raise AppError(404, "ABSENCE_TYPE_NOT_FOUND", "Abwesenheitsart nicht gefunden.")
        if not match.active:
            raise AppError(400, "ABSENCE_TYPE_INACTIVE", "Diese Abwesenheitsart ist deaktiviert.")
        return match
    match = next((t for t in types if t.category == category and t.active), None) or next(
        (t for t in types if t.category == category), None
    )
    if match is None:
        raise AppError(400, "ABSENCE_TYPE_NOT_FOUND", "Für diese Kategorie gibt es keine Abwesenheitsart.")
    return match


def absence_day_values(category: AbsenceType, target_minutes: int | None, credit_minutes: int | None) -> tuple[int | None, int | None]:
    """(Ist, Soll) eines Abwesenheitstags ohne Stempelung je Kategorie:
    bezahlte Abwesenheit = Soll gutgeschrieben, unbezahlt = Soll entfällt,
    Freizeitausgleich = Soll bleibt ohne Gutschrift (Saldo sinkt)."""
    if category == AbsenceType.UNPAID:
        return 0, (0 if target_minutes is not None else None)
    if category == AbsenceType.TIME_OFF_IN_LIEU:
        return 0, target_minutes
    return credit_minutes, target_minutes
