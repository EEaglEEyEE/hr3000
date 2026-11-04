from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_hr_principal
from app.db import get_db
from app.schemas.plan import PlanResponse
from app.services.plan_service import plan_status

router = APIRouter(tags=["plan"])


@router.get("/plan", response_model=PlanResponse)
async def get_plan(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """Tarif des Mandanten und Auslastung (aktive Mitarbeiter) – für Einstellungen und Hinweise."""
    status = await plan_status(db, actor.tenant_id)
    return PlanResponse(
        plan=status.plan, active_employees=status.active_employees, limit=status.limit, remaining=status.remaining
    )
