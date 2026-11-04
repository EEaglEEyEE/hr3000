from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, HrRole, HrUser
from app.schemas.hr_user import HrUserCreateRequest, HrUserResponse
from app.services.admin_service import ensure_not_last_admin
from app.services.audit_service import log_action
from app.services.auth_service import hash_password

router = APIRouter(tags=["hr_users"])


@router.get("/hr-users", response_model=list[HrUserResponse])
async def list_hr_users(
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> list[HrUserResponse]:
    result = await db.execute(
        select(HrUser).where(HrUser.tenant_id == actor.tenant_id).order_by(HrUser.email.asc())
    )
    return [HrUserResponse.model_validate(u) for u in result.scalars().all()]


@router.post("/hr-users", response_model=HrUserResponse, status_code=201)
async def create_hr_user(
    payload: HrUserCreateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> HrUserResponse:
    if payload.role == HrRole.SUPER_ADMIN:
        raise AppError(403, "FORBIDDEN", "Diese Rolle kann hier nicht vergeben werden.")

    user = HrUser(
        tenant_id=actor.tenant_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "Diese E-Mail wird bereits verwendet.") from exc

    await db.refresh(user)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.HR_USER_CREATED,
        entity_type="hr_user",
        entity_id=user.id,
        detail=f"{user.email} ({user.role.value})",
    )
    await db.commit()

    return HrUserResponse.model_validate(user)


@router.delete("/hr-users/{hr_user_id}", status_code=204)
async def delete_hr_user(
    hr_user_id: int,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    if actor.hr_user is not None and actor.hr_user.id == hr_user_id:
        raise AppError(400, "CANNOT_DELETE_SELF", "Der eigene Account kann nicht gelöscht werden.")

    user = await db.get(HrUser, hr_user_id)
    if user is None or user.tenant_id != actor.tenant_id:
        raise AppError(404, "HR_USER_NOT_FOUND", "HR-User nicht gefunden.")

    if user.role == HrRole.ADMIN:
        await ensure_not_last_admin(db, actor.tenant_id, exclude_hr_user_id=user.id)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.HR_USER_DELETED,
        entity_type="hr_user",
        entity_id=user.id,
        detail=f"{user.email} ({user.role.value})",
    )

    await db.delete(user)
    await db.commit()
