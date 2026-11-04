from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Location, Team
from app.schemas.team import TeamCreateRequest, TeamResponse, TeamUpdateRequest
from app.services.audit_service import log_action
from app.services.team_scope_service import supervisor_team_ids

router = APIRouter(tags=["teams"])


@router.get("/teams", response_model=list[TeamResponse])
async def list_teams(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[TeamResponse]:
    """Supervisor sieht nur die eigenen Teams (siehe team_scope_service),
    Admin/HR sieht alle Teams des Mandanten."""
    stmt = select(Team).where(Team.tenant_id == actor.tenant_id)
    team_ids = await supervisor_team_ids(db, actor)
    if team_ids is not None:
        stmt = stmt.where(Team.id.in_(team_ids))
    stmt = stmt.order_by(Team.name.asc())

    result = await db.execute(stmt)
    return [TeamResponse.model_validate(t) for t in result.scalars().all()]


@router.post("/teams", response_model=TeamResponse, status_code=201)
async def create_team(
    payload: TeamCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    if payload.location_id is not None:
        location = await db.get(Location, payload.location_id)
        if location is None or location.tenant_id != actor.tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")

    team = Team(tenant_id=actor.tenant_id, name=payload.name, location_id=payload.location_id)
    db.add(team)
    await db.commit()
    await db.refresh(team)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.TEAM_CREATED,
        entity_type="team",
        entity_id=team.id,
        detail=team.name,
    )
    await db.commit()

    return TeamResponse.model_validate(team)


@router.patch("/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: int,
    payload: TeamUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    team = await db.get(Team, team_id)
    if team is None or team.tenant_id != actor.tenant_id:
        raise AppError(404, "TEAM_NOT_FOUND", "Team nicht gefunden.")

    if payload.location_id is not None:
        location = await db.get(Location, payload.location_id)
        if location is None or location.tenant_id != actor.tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
        team.location_id = payload.location_id
    elif payload.clear_location_id:
        team.location_id = None
    if payload.name is not None:
        team.name = payload.name

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.TEAM_UPDATED,
        entity_type="team",
        entity_id=team.id,
        detail=team.name,
    )

    await db.commit()
    await db.refresh(team)
    return TeamResponse.model_validate(team)


@router.delete("/teams/{team_id}", status_code=204)
async def delete_team(
    team_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    team = await db.get(Team, team_id)
    if team is None or team.tenant_id != actor.tenant_id:
        raise AppError(404, "TEAM_NOT_FOUND", "Team nicht gefunden.")

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.TEAM_DELETED,
        entity_type="team",
        entity_id=team.id,
        detail=team.name,
    )

    await db.delete(team)
    await db.commit()
