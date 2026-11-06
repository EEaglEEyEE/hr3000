"""Hilfen für Tests rund um Abwesenheiten (wird von den Testmodulen direkt importiert)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AbsenceType
from app.services.absence_type_service import list_absence_types


async def require_vacation_approval(db_session: AsyncSession, tenant_id: int = 1) -> None:
    """Urlaub braucht eine Genehmigung (Einstellung je Abwesenheitsart „Genehmigung nötig“)."""
    for row in await list_absence_types(db_session, tenant_id):
        if row.category == AbsenceType.VACATION:
            row.requires_approval = True
    await db_session.commit()
