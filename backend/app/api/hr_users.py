from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, HrRole
from app.schemas.hr_user import HrUserCreateRequest, HrUserResponse
from app.services.admin_service import ensure_not_last_admin
from app.services.audit_service import log_action
from app.services.auth_service import hash_password

router = APIRouter(tags=["hr_users"])

# Reine Verwaltungskonten (ohne Mitarbeiter), z. B. der erste Admin einer Firma oder ein externes
# Lohnbüro. Zugänge von Mitarbeitern werden am Mitarbeiter gepflegt (app/api/employees.py).


@router.get("/hr-users", response_model=list[HrUserResponse])
async def list_hr_users(
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> list[HrUserResponse]:
    result = await db.execute(
        select(Account)
        .where(
            Account.tenant_id == actor.tenant_id,
            Account.employee_id.is_(None),
            Account.role.is_not(None),
            Account.password_hash.is_not(None),
        )
        .order_by(Account.email.asc())
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

    # Früher entferntes Verwaltungskonto mit derselben Adresse: wieder aktivieren (Verlauf bleibt dran).
    user = await db.scalar(
        select(Account).where(
            Account.tenant_id == actor.tenant_id,
            func.lower(Account.email) == payload.email.lower(),
            Account.employee_id.is_(None),
            Account.password_hash.is_(None),
        )
    )
    if user is None:
        user = Account(tenant_id=actor.tenant_id, email=payload.email)
        db.add(user)
    user.password_hash = hash_password(payload.password)
    user.role = payload.role
    user.payroll_access = payload.payroll_access and payload.role == HrRole.HR
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "Diese E-Mail wird bereits verwendet.") from exc

    await db.refresh(user)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.HR_USER_CREATED,
        entity_type="account",
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
    if actor.account_id == hr_user_id:
        raise AppError(400, "CANNOT_DELETE_SELF", "Der eigene Account kann nicht gelöscht werden.")

    user = await db.get(Account, hr_user_id)
    if user is None or user.tenant_id != actor.tenant_id or user.employee_id is not None or user.role is None:
        raise AppError(404, "HR_USER_NOT_FOUND", "HR-User nicht gefunden.")

    if user.role == HrRole.ADMIN:
        await ensure_not_last_admin(db, actor.tenant_id, exclude_account_id=user.id)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.HR_USER_DELETED,
        entity_type="account",
        entity_id=user.id,
        detail=f"{user.email} ({user.role.value})",
    )

    # Das Konto bleibt für den Verlauf („erstellt von“, Audit-Protokoll) mit seiner E-Mail bestehen,
    # nur ohne Zugang; legt ein Admin die Adresse später neu an, wird es wieder aktiviert.
    user.password_hash = None
    user.role = None
    user.payroll_access = False
    user.calendar_token_hash = None
    await db.commit()
