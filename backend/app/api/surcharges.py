from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Actor,
    get_current_admin_principal,
    get_current_full_hr_principal,
    get_current_hr_or_self,
)
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Compensation, Employee, PayType, SurchargeKind, SurchargeRule
from app.schemas.surcharge import (
    SurchargeLine,
    SurchargeReportResponse,
    SurchargeRuleCreateRequest,
    SurchargeRuleResponse,
    SurchargeRuleUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.surcharge_service import compute_surcharges
from app.services.team_scope_service import ensure_employee_visible

router = APIRouter(tags=["surcharges"])

_MAX_RANGE_DAYS = 366

# Vorschlag orientiert an den steuerfreien Höchstsätzen nach §3b EStG – die tatsächlichen Sätze
# richten sich nach Vertrag/Tarif und müssen vom Administrator geprüft werden.
_DEFAULTS = [
    dict(name="Nachtarbeit (20–6 Uhr)", kind=SurchargeKind.NIGHT, percent=25, start_time="20:00", end_time="06:00", exclusive_group=None),
    dict(name="Sonntagsarbeit", kind=SurchargeKind.SUNDAY, percent=50, exclusive_group="sonn_feiertag"),
    dict(name="Feiertagsarbeit", kind=SurchargeKind.HOLIDAY, percent=125, exclusive_group="sonn_feiertag"),
]


def _mask(weekdays: list[int]) -> int:
    return sum(1 << day for day in set(weekdays))


def _days(mask: int) -> list[int]:
    return [day for day in range(7) if (mask >> day) & 1]


def _response(rule: SurchargeRule) -> SurchargeRuleResponse:
    return SurchargeRuleResponse(
        id=rule.id,
        name=rule.name,
        kind=rule.kind,
        percent=float(rule.percent),
        start_time=rule.start_time,
        end_time=rule.end_time,
        weekdays=_days(rule.weekdays_mask),
        exclusive_group=rule.exclusive_group,
        active=rule.active,
        wage_type=rule.wage_type,
    )


def _audit(db: AsyncSession, actor: Actor, rule_id: int, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.SURCHARGE_RULES_CHANGED,
        entity_type="surcharge_rule",
        entity_id=rule_id,
        detail=detail,
    )


async def _get_rule(db: AsyncSession, rule_id: int, tenant_id: int) -> SurchargeRule:
    rule = await db.get(SurchargeRule, rule_id)
    if rule is None or rule.tenant_id != tenant_id:
        raise AppError(404, "SURCHARGE_RULE_NOT_FOUND", "Zuschlagsregel nicht gefunden.")
    return rule


@router.get("/surcharge-rules", response_model=list[SurchargeRuleResponse])
async def list_surcharge_rules(
    actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[SurchargeRuleResponse]:
    rows = await db.execute(select(SurchargeRule).where(SurchargeRule.tenant_id == actor.tenant_id).order_by(SurchargeRule.id))
    return [_response(rule) for rule in rows.scalars().all()]


@router.post("/surcharge-rules", response_model=SurchargeRuleResponse, status_code=201)
async def create_surcharge_rule(
    payload: SurchargeRuleCreateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> SurchargeRuleResponse:
    rule = SurchargeRule(
        tenant_id=actor.tenant_id,
        name=payload.name,
        kind=payload.kind,
        percent=payload.percent,
        start_time=payload.start_time,
        end_time=payload.end_time,
        weekdays_mask=_mask(payload.weekdays),
        exclusive_group=payload.exclusive_group,
        active=payload.active,
        wage_type=payload.wage_type,
    )
    db.add(rule)
    await db.flush()
    _audit(db, actor, rule.id, f"Regel angelegt: {rule.name} ({payload.percent:g} %)")
    await db.commit()
    await db.refresh(rule)
    return _response(rule)


@router.post("/surcharge-rules/defaults", response_model=list[SurchargeRuleResponse], status_code=201)
async def create_default_surcharge_rules(
    actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> list[SurchargeRuleResponse]:
    existing = (await db.execute(select(SurchargeRule.id).where(SurchargeRule.tenant_id == actor.tenant_id))).first()
    if existing is not None:
        raise AppError(409, "SURCHARGE_RULES_EXIST", "Es sind bereits Zuschlagsregeln vorhanden.")
    from datetime import time as _time

    created: list[SurchargeRule] = []
    for spec in _DEFAULTS:
        spec = dict(spec)
        for key in ("start_time", "end_time"):
            if key in spec:
                hours, minutes = spec[key].split(":")
                spec[key] = _time(int(hours), int(minutes))
        rule = SurchargeRule(tenant_id=actor.tenant_id, weekdays_mask=127, active=True, **spec)
        db.add(rule)
        created.append(rule)
    await db.flush()
    _audit(db, actor, created[0].id, "Standard-Zuschlagsregeln angelegt")
    await db.commit()
    return [_response(rule) for rule in created]


@router.patch("/surcharge-rules/{rule_id}", response_model=SurchargeRuleResponse)
async def update_surcharge_rule(
    rule_id: int,
    payload: SurchargeRuleUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> SurchargeRuleResponse:
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    if payload.name is not None:
        rule.name = payload.name
    if payload.percent is not None:
        rule.percent = payload.percent
    if payload.active is not None:
        rule.active = payload.active
    if rule.kind in (SurchargeKind.NIGHT, SurchargeKind.CUSTOM):
        if payload.start_time is not None:
            rule.start_time = payload.start_time
        if payload.end_time is not None:
            rule.end_time = payload.end_time
        if rule.start_time == rule.end_time:
            raise AppError(400, "INVALID_WINDOW", "Beginn und Ende dürfen nicht gleich sein.")
        if payload.weekdays is not None:
            if any(d < 0 or d > 6 for d in payload.weekdays):
                raise AppError(400, "INVALID_WEEKDAYS", "Wochentage müssen zwischen 0 (Montag) und 6 (Sonntag) liegen.")
            rule.weekdays_mask = _mask(payload.weekdays)
    if payload.exclusive_group is not None:
        rule.exclusive_group = payload.exclusive_group
    elif payload.clear_exclusive_group:
        rule.exclusive_group = None
    if payload.wage_type is not None:
        rule.wage_type = payload.wage_type or None
    _audit(db, actor, rule.id, f"Regel geändert: {rule.name}")
    await db.commit()
    await db.refresh(rule)
    return _response(rule)


@router.delete("/surcharge-rules/{rule_id}", status_code=204)
async def delete_surcharge_rule(
    rule_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> None:
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    _audit(db, actor, rule.id, f"Regel gelöscht: {rule.name}")
    await db.delete(rule)
    await db.commit()


@router.get("/employees/{employee_id}/surcharges", response_model=SurchargeReportResponse)
async def employee_surcharges(
    employee_id: int,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> SurchargeReportResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    is_self = actor.employee is not None and actor.employee.id == employee_id
    if actor.is_full_hr_level and not is_self:
        await ensure_employee_visible(db, actor, employee)
    elif not is_self:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(400, "RANGE_TOO_LARGE", f"Zeitraum darf maximal {_MAX_RANGE_DAYS} Tage umfassen.")

    totals = await compute_surcharges(db, employee, date_from, date_to)

    hourly_rate: float | None = None
    if actor.is_admin_level and not is_self:
        comp = (
            await db.execute(
                select(Compensation)
                .where(
                    Compensation.employee_id == employee_id,
                    Compensation.pay_type == PayType.HOURLY,
                    # Beträge nur, wenn EIN Stundensatz den ganzen Zeitraum abdeckt – bei Satzwechsel
                    # bewertet die Lohnkosten-Auswertung abschnittsweise.
                    Compensation.valid_from <= date_from,
                    (Compensation.valid_to.is_(None)) | (Compensation.valid_to >= date_to),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if comp is not None:
            hourly_rate = float(comp.amount)
            log_action(
                db,
                tenant_id=actor.tenant_id,
                actor_hr_user_id=actor.audit_hr_user_id,
                actor_employee_id=actor.audit_employee_id,
                action=AuditAction.COMPENSATION_VIEWED,
                entity_type="employee",
                entity_id=employee_id,
                detail="Zuschlagsbeträge berechnet",
            )
            await db.commit()

    lines = [
        SurchargeLine(
            rule_id=t.rule.id,
            name=t.rule.name,
            kind=t.rule.kind,
            percent=float(t.rule.percent),
            minutes=t.minutes,
            equivalent_minutes=round(t.equivalent_minutes, 2),
            amount=round(t.equivalent_minutes / 60 * hourly_rate, 2) if hourly_rate is not None else None,
        )
        for t in totals
    ]
    return SurchargeReportResponse(employee_id=employee_id, lines=lines, hourly_rate=hourly_rate)
