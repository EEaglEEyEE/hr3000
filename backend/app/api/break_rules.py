from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import BreakRule
from app.schemas.break_rule import BreakRuleCreateRequest, BreakRuleResponse, BreakRuleUpdateRequest
from app.services.period_service import ensure_tenant_open_from
from app.services.timesheet_service import invalidate_tenant_balances

router = APIRouter(tags=["break_rules"])

# Änderungen wirken ab einem Stichtag (Standard: heute): bereits gerechnete Tage – insbesondere
# vorgelegte/abgeschlossene Monate – behalten die Staffel, die damals galt.


async def _get_rule(db: AsyncSession, rule_id: int, tenant_id: int) -> BreakRule:
    rule = await db.get(BreakRule, rule_id)
    if rule is None or rule.tenant_id != tenant_id:
        raise AppError(404, "BREAK_RULE_NOT_FOUND", "Pausenregel nicht gefunden.")
    return rule


async def _ensure_unique_threshold(db: AsyncSession, tenant_id: int, threshold: int, valid_from: date, exclude_id: int | None = None) -> None:
    stmt = select(BreakRule.id).where(
        BreakRule.tenant_id == tenant_id,
        BreakRule.min_work_minutes == threshold,
        or_(BreakRule.valid_to.is_(None), BreakRule.valid_to >= valid_from),
    )
    if exclude_id is not None:
        stmt = stmt.where(BreakRule.id != exclude_id)
    if (await db.execute(stmt.limit(1))).first() is not None:
        raise AppError(409, "THRESHOLD_TAKEN", "Für diese Arbeitszeitschwelle gibt es bereits eine Regel.")


@router.get("/break-rules", response_model=list[BreakRuleResponse])
async def list_break_rules(
    include_history: bool = Query(default=False),
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> list[BreakRuleResponse]:
    """Standard: aktuell und künftig gültige Regeln; mit include_history auch beendete."""
    stmt = select(BreakRule).where(BreakRule.tenant_id == actor.tenant_id)
    if not include_history:
        stmt = stmt.where(or_(BreakRule.valid_to.is_(None), BreakRule.valid_to >= date.today()))
    result = await db.execute(stmt.order_by(BreakRule.min_work_minutes.asc(), BreakRule.valid_from.asc()))
    return [BreakRuleResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/break-rules", response_model=BreakRuleResponse, status_code=201)
async def create_break_rule(
    payload: BreakRuleCreateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> BreakRuleResponse:
    valid_from = payload.valid_from or date.today()
    await ensure_tenant_open_from(db, actor.tenant_id, valid_from)
    await _ensure_unique_threshold(db, actor.tenant_id, payload.min_work_minutes, valid_from)
    rule = BreakRule(
        tenant_id=actor.tenant_id,
        min_work_minutes=payload.min_work_minutes,
        deduct_minutes=payload.deduct_minutes,
        valid_from=valid_from,
    )
    db.add(rule)
    await invalidate_tenant_balances(db, actor.tenant_id, valid_from)
    await db.commit()
    await db.refresh(rule)
    return BreakRuleResponse.model_validate(rule)


@router.patch("/break-rules/{rule_id}", response_model=BreakRuleResponse)
async def update_break_rule(
    rule_id: int,
    payload: BreakRuleUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> BreakRuleResponse:
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    effective = max(payload.valid_from or date.today(), rule.valid_from)
    await ensure_tenant_open_from(db, actor.tenant_id, effective)
    threshold = payload.min_work_minutes if payload.min_work_minutes is not None else rule.min_work_minutes
    deduct = payload.deduct_minutes if payload.deduct_minutes is not None else rule.deduct_minutes

    if rule.valid_from >= effective:
        # Regel wirkt noch nicht bzw. erst ab heute: direkt ändern.
        await _ensure_unique_threshold(db, actor.tenant_id, threshold, rule.valid_from, exclude_id=rule.id)
        rule.min_work_minutes = threshold
        rule.deduct_minutes = deduct
        target = rule
    else:
        # Bisherige Fassung endet am Vortag, neue Fassung gilt ab Stichtag.
        old_end = rule.valid_to
        rule.valid_to = effective - timedelta(days=1)
        await _ensure_unique_threshold(db, actor.tenant_id, threshold, effective, exclude_id=rule.id)
        target = BreakRule(
            tenant_id=actor.tenant_id, min_work_minutes=threshold, deduct_minutes=deduct, valid_from=effective, valid_to=old_end
        )
        db.add(target)
    await invalidate_tenant_balances(db, actor.tenant_id, effective)
    await db.commit()
    await db.refresh(target)
    return BreakRuleResponse.model_validate(target)


@router.delete("/break-rules/{rule_id}", status_code=204)
async def delete_break_rule(
    rule_id: int,
    valid_from: date | None = Query(default=None, description="Ab wann die Regel nicht mehr gilt (Standard: heute)."),
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    effective = max(valid_from or date.today(), rule.valid_from)
    await ensure_tenant_open_from(db, actor.tenant_id, effective)
    if rule.valid_from >= effective:
        await db.delete(rule)
    else:
        rule.valid_to = effective - timedelta(days=1)
    await invalidate_tenant_balances(db, actor.tenant_id, effective)
    await db.commit()
