from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import BreakRule, BreakRuleKind
from app.schemas.break_rule import (
    BreakRuleCreateRequest,
    BreakRuleResponse,
    BreakRuleUpdateRequest,
    check_window,
    window_length,
)
from app.services.period_service import ensure_tenant_open_from
from app.services.settings_service import get_or_create_settings
from app.services.timesheet_service import invalidate_tenant_balances, staffel_covers_law

router = APIRouter(tags=["break_rules"])

# Änderungen wirken ab einem Stichtag (Standard: heute): bereits gerechnete Tage – insbesondere
# vorgelegte/abgeschlossene Monate – behalten die Staffel, die damals galt.


async def _get_rule(db: AsyncSession, rule_id: int, tenant_id: int) -> BreakRule:
    rule = await db.get(BreakRule, rule_id)
    if rule is None or rule.tenant_id != tenant_id:
        raise AppError(404, "BREAK_RULE_NOT_FOUND", "Pausenregel nicht gefunden.")
    return rule


async def _ensure_no_conflict(
    db: AsyncSession, tenant_id: int, rule: BreakRule, valid_from: date, exclude_id: int | None = None
) -> None:
    """Je Art und Zeitraum: Staffel/feste Minuten mit eindeutiger Schwelle, feste Pausenzeiten
    ohne Überschneidung."""
    stmt = select(BreakRule).where(
        BreakRule.tenant_id == tenant_id,
        or_(BreakRule.valid_to.is_(None), BreakRule.valid_to >= valid_from),
    )
    if exclude_id is not None:
        stmt = stmt.where(BreakRule.id != exclude_id)
    def family(kind: BreakRuleKind | None) -> str:
        return "window" if kind == BreakRuleKind.FIXED_WINDOW else "staffel"

    kind = rule.kind or BreakRuleKind.LEGAL
    for other in (await db.execute(stmt)).scalars().all():
        if family(other.kind) != family(kind):
            continue
        if kind == BreakRuleKind.FIXED_WINDOW:
            if other.start_time < rule.end_time and rule.start_time < other.end_time:
                raise AppError(409, "WINDOW_OVERLAP", "Diese Pausenzeit überschneidet sich mit einer anderen.")
        elif other.min_work_minutes == rule.min_work_minutes:
            raise AppError(409, "THRESHOLD_TAKEN", "Für diese Arbeitszeitschwelle gibt es bereits eine Regel.")


async def _ensure_legal_minimum(
    db: AsyncSession, tenant_id: int, effective: date, rule_id: int, replacement: list[tuple[int, int]]
) -> None:
    """Mit "Gesetzliche Mindestpause einhalten" darf die Staffel nach der Änderung nicht unter § 4
    ArbZG liegen."""
    settings_row = await get_or_create_settings(db, tenant_id)
    if settings_row.legal_break_minimum and not await staffel_covers_law(db, tenant_id, effective, rule_id, replacement):
        raise AppError(
            409,
            "STAFFEL_BELOW_LAW",
            "So läge die Pausenstaffel unter der gesetzlichen Mindestpause (§ 4 ArbZG: ab 6 Std. 30 Min., ab 9 Std. "
            "45 Min.). Abweichungen nur mit Tarifvertrag – dann zuerst „Gesetzliche Mindestpause einhalten“ ausschalten.",
        )


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
    rules = (await db.execute(stmt)).scalars().all()
    order = list(BreakRuleKind)
    rules = sorted(
        rules,
        key=lambda r: (order.index(r.kind or BreakRuleKind.LEGAL), r.start_time or time.min, r.min_work_minutes, r.valid_from),
    )
    return [BreakRuleResponse.model_validate(r) for r in rules]


@router.post("/break-rules", response_model=BreakRuleResponse, status_code=201)
async def create_break_rule(
    payload: BreakRuleCreateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> BreakRuleResponse:
    valid_from = payload.valid_from or date.today()
    await ensure_tenant_open_from(db, actor.tenant_id, valid_from)
    rule = BreakRule(
        tenant_id=actor.tenant_id,
        kind=payload.kind,
        min_work_minutes=payload.min_work_minutes,
        deduct_minutes=payload.deduct_minutes,
        start_time=payload.start_time,
        end_time=payload.end_time,
        valid_from=valid_from,
    )
    await _ensure_no_conflict(db, actor.tenant_id, rule, valid_from)
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
    changed = BreakRule(
        tenant_id=actor.tenant_id,
        kind=rule.kind or BreakRuleKind.LEGAL,
        min_work_minutes=payload.min_work_minutes if payload.min_work_minutes is not None else rule.min_work_minutes,
        deduct_minutes=payload.deduct_minutes if payload.deduct_minutes is not None else rule.deduct_minutes,
        start_time=payload.start_time or rule.start_time,
        end_time=payload.end_time or rule.end_time,
    )
    if changed.kind == BreakRuleKind.FIXED_WINDOW:
        try:
            check_window(changed.start_time, changed.end_time)
        except ValueError as exc:
            raise AppError(422, "INVALID_WINDOW", str(exc)) from exc
        changed.min_work_minutes = 0
        changed.deduct_minutes = window_length(changed.start_time, changed.end_time)

    if changed.kind != BreakRuleKind.FIXED_WINDOW:
        await _ensure_legal_minimum(db, actor.tenant_id, effective, rule.id, [(changed.min_work_minutes, changed.deduct_minutes)])
    if rule.valid_from >= effective:
        # Regel wirkt noch nicht bzw. erst ab heute: direkt ändern.
        await _ensure_no_conflict(db, actor.tenant_id, changed, rule.valid_from, exclude_id=rule.id)
        rule.min_work_minutes = changed.min_work_minutes
        rule.deduct_minutes = changed.deduct_minutes
        rule.start_time, rule.end_time = changed.start_time, changed.end_time
        target = rule
    else:
        # Bisherige Fassung endet am Vortag, neue Fassung gilt ab Stichtag.
        old_end = rule.valid_to
        rule.valid_to = effective - timedelta(days=1)
        await _ensure_no_conflict(db, actor.tenant_id, changed, effective, exclude_id=rule.id)
        changed.valid_from, changed.valid_to = effective, old_end
        db.add(changed)
        target = changed
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
    if rule.kind != BreakRuleKind.FIXED_WINDOW:
        await _ensure_legal_minimum(db, actor.tenant_id, effective, rule.id, [])
    if rule.valid_from >= effective:
        await db.delete(rule)
    else:
        rule.valid_to = effective - timedelta(days=1)
    await invalidate_tenant_balances(db, actor.tenant_id, effective)
    await db.commit()
