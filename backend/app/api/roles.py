"""Eigene Rollen je Firma (nur Admin): anlegen, ändern, löschen; Bereiche und Vorlagen für die Matrix.
Zugewiesen werden sie am Mitarbeiter-Zugang (PATCH /employees/{id}/hr-role) bzw. am Verwaltungskonto
(/hr-users). Durchgesetzt in app/api/deps.py, siehe app/services/role_permissions.py."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, HrRole, Role
from app.schemas.role import (
    RoleAreaInfo,
    RoleCreateRequest,
    RoleMetaResponse,
    RoleResponse,
    RoleTemplate,
    RoleUpdateRequest,
)
from app.services import role_permissions
from app.services.audit_service import log_action
from app.services.role_permissions import AREA_INFO, TEMPLATES, Level

router = APIRouter(tags=["roles"])

_LEVEL_LABELS = {Level.NONE: "kein Zugriff", Level.VIEW: "ansehen", Level.EDIT: "bearbeiten"}


def permissions_summary(permissions: role_permissions.Permissions) -> str:
    """Für das Audit-Protokoll: nur Bereiche mit Zugriff, in Reihenfolge der Oberfläche."""
    parts = [
        f"{AREA_INFO[area][0]}: {_LEVEL_LABELS[level]}"
        for area, level in role_permissions.normalize(permissions).items()
        if level != Level.NONE
    ]
    return ", ".join(parts) or "kein Zugriff"


async def _account_counts(db: AsyncSession, tenant_id: int) -> dict[int, int]:
    rows = await db.execute(
        select(Account.custom_role_id, func.count(Account.id))
        .where(Account.tenant_id == tenant_id, Account.custom_role_id.is_not(None))
        .group_by(Account.custom_role_id)
    )
    return {role_id: count for role_id, count in rows.all()}


def _response(role: Role, count: int) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=role_permissions.parse_permissions(role.permissions),
        account_count=count,
    )


async def get_tenant_role(db: AsyncSession, role_id: int, tenant_id: int) -> Role:
    """Rolle der eigenen Firma; fremde und unbekannte Rollen gleich behandeln (404)."""
    role = await db.get(Role, role_id)
    if role is None or role.tenant_id != tenant_id:
        raise AppError(404, "ROLE_NOT_FOUND", "Rolle nicht gefunden.")
    return role


def _audit(db: AsyncSession, actor: Actor, role: Role, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.ROLE_CHANGED,
        entity_type="role",
        entity_id=role.id,
        detail=detail[:500],
    )


@router.get("/roles/meta", response_model=RoleMetaResponse)
async def roles_meta(actor: Actor = Depends(get_current_admin_principal)) -> RoleMetaResponse:
    return RoleMetaResponse(
        areas=[RoleAreaInfo(key=area, label=label, description=text) for area, (label, text) in AREA_INFO.items()],
        templates=[
            RoleTemplate(key=key, name=name, description=text, permissions=role_permissions.normalize(perms))
            for key, (name, text, perms) in TEMPLATES.items()
        ],
    )


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> list[RoleResponse]:
    counts = await _account_counts(db, actor.tenant_id)
    roles = (await db.execute(select(Role).where(Role.tenant_id == actor.tenant_id).order_by(Role.name))).scalars()
    return [_response(role, counts.get(role.id, 0)) for role in roles]


@router.post("/roles", response_model=RoleResponse, status_code=201)
async def create_role(
    payload: RoleCreateRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> RoleResponse:
    role = Role(
        tenant_id=actor.tenant_id,
        name=payload.name,
        description=payload.description or None,
        permissions=role_permissions.dump_permissions(payload.permissions),
    )
    db.add(role)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "ROLE_NAME_TAKEN", "Eine Rolle mit diesem Namen gibt es schon.") from exc
    _audit(db, actor, role, f"Rolle „{role.name}“ angelegt: {permissions_summary(payload.permissions)}")
    await db.commit()
    return _response(role, 0)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    payload: RoleUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> RoleResponse:
    role = await get_tenant_role(db, role_id, actor.tenant_id)
    changes = []
    if payload.name is not None and payload.name != role.name:
        changes.append(f"Name „{role.name}“ → „{payload.name}“")
        role.name = payload.name
    if "description" in payload.model_fields_set:
        new_description = payload.description or None
        if new_description != role.description:
            changes.append("Beschreibung geändert")
            role.description = new_description
    if payload.permissions is not None:
        new_permissions = role_permissions.dump_permissions(payload.permissions)
        if new_permissions != role.permissions:
            changes.append(f"Rechte: {permissions_summary(payload.permissions)}")
            role.permissions = new_permissions
    if changes:
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise AppError(409, "ROLE_NAME_TAKEN", "Eine Rolle mit diesem Namen gibt es schon.") from exc
        _audit(db, actor, role, f"Rolle „{role.name}“ geändert: " + "; ".join(changes))
        await db.commit()
    counts = await _account_counts(db, actor.tenant_id)
    return _response(role, counts.get(role.id, 0))


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> None:
    """Nur Rollen, die keinem Konto zugewiesen sind – sonst 409 (erst die Konten umstellen)."""
    role = await get_tenant_role(db, role_id, actor.tenant_id)
    in_use = await db.scalar(select(func.count(Account.id)).where(Account.custom_role_id == role.id))
    if in_use:
        raise AppError(409, "ROLE_IN_USE", f"Die Rolle ist noch {in_use} Konto/Konten zugewiesen.")
    _audit(db, actor, role, f"Rolle „{role.name}“ gelöscht")
    await db.delete(role)
    await db.commit()


async def assign_custom_role(
    db: AsyncSession, actor: Actor, account: Account, role_id: int | None, *, label: str
) -> str | None:
    """Weist einem Konto eine eigene Rolle zu bzw. entzieht sie (role_id None). Nur Rolle HR kann eine
    eigene Rolle haben. Gibt den Audit-Text zurück (None = keine Änderung); protokolliert selbst."""
    if role_id is not None and account.role != HrRole.HR:
        raise AppError(
            400, "CUSTOM_ROLE_REQUIRES_HR", "Eine eigene Rolle gibt es nur für die Verwaltungsrolle HR."
        )
    new_role = await get_tenant_role(db, role_id, actor.tenant_id) if role_id is not None else None
    old_role = account.custom_role
    if (old_role.id if old_role else None) == (new_role.id if new_role else None):
        return None
    account.custom_role = new_role
    detail = (
        f"{label}: eigene Rolle „{old_role.name if old_role else 'keine'}“ → „{new_role.name if new_role else 'keine'}“"
    )
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.ROLE_CHANGED,
        entity_type="account",
        entity_id=account.id,
        detail=detail[:500],
    )
    return detail
