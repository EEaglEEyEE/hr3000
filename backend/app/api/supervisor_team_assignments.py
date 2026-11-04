from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Employee, HrUser, SupervisorTeamAssignment, Team
from app.schemas.supervisor_team_assignment import (
    SupervisorTeamAssignmentCreateRequest,
    SupervisorTeamAssignmentResponse,
)

router = APIRouter(tags=["supervisor_team_assignments"])


@router.get("/supervisor-team-assignments", response_model=list[SupervisorTeamAssignmentResponse])
async def list_supervisor_team_assignments(
    team_id: int | None = Query(default=None),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[SupervisorTeamAssignmentResponse]:
    stmt = select(SupervisorTeamAssignment).join(Team, Team.id == SupervisorTeamAssignment.team_id).where(
        Team.tenant_id == actor.tenant_id
    )
    if team_id is not None:
        stmt = stmt.where(SupervisorTeamAssignment.team_id == team_id)

    result = await db.execute(stmt)
    return [SupervisorTeamAssignmentResponse.model_validate(a) for a in result.scalars().all()]


@router.post(
    "/supervisor-team-assignments", response_model=SupervisorTeamAssignmentResponse, status_code=201
)
async def create_supervisor_team_assignment(
    payload: SupervisorTeamAssignmentCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> SupervisorTeamAssignmentResponse:
    team = await db.get(Team, payload.team_id)
    if team is None or team.tenant_id != actor.tenant_id:
        raise AppError(404, "TEAM_NOT_FOUND", "Team nicht gefunden.")

    if payload.hr_user_id is not None:
        hr_user = await db.get(HrUser, payload.hr_user_id)
        if hr_user is None or hr_user.tenant_id != actor.tenant_id:
            raise AppError(404, "HR_USER_NOT_FOUND", "HR-User nicht gefunden.")
    else:
        employee = await db.get(Employee, payload.employee_id)
        if employee is None or employee.tenant_id != actor.tenant_id:
            raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")

    assignment = SupervisorTeamAssignment(
        team_id=payload.team_id,
        hr_user_id=payload.hr_user_id,
        employee_id=payload.employee_id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return SupervisorTeamAssignmentResponse.model_validate(assignment)


@router.delete("/supervisor-team-assignments/{assignment_id}", status_code=204)
async def delete_supervisor_team_assignment(
    assignment_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(SupervisorTeamAssignment)
        .join(Team, Team.id == SupervisorTeamAssignment.team_id)
        .where(SupervisorTeamAssignment.id == assignment_id, Team.tenant_id == actor.tenant_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise AppError(404, "ASSIGNMENT_NOT_FOUND", "Zuordnung nicht gefunden.")

    await db.delete(assignment)
    await db.commit()
