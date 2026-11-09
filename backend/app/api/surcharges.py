from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Actor,
    get_current_admin_principal,
    get_current_full_hr_principal,
    get_current_hr_or_self,
    get_current_payroll_principal,
)
from app.db import get_db
from app.services.period_service import ensure_tenant_open_from
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
from app.services.scope_service import ensure_employee_visible

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
        valid_from=rule.valid_from,
        valid_to=rule.valid_to,
        family_id=rule.family,
    )


def _audit(db: AsyncSession, actor: Actor, rule_id: int, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
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
    include_history: bool = Query(False, description="auch abgelaufene Fassungen"),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[SurchargeRuleResponse]:
    """Regeln (aktuelle und künftige Fassungen); mit include_history auch abgelaufene."""
    rows = (
        await db.execute(select(SurchargeRule).where(SurchargeRule.tenant_id == actor.tenant_id).order_by(SurchargeRule.id))
    ).scalars().all()
    today = date.today()
    rules = [r for r in rows if include_history or r.valid_to is None or r.valid_to >= today]
    return [_response(rule) for rule in sorted(rules, key=lambda r: (r.family, r.valid_from or date.min))]


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
        valid_from=payload.valid_from,
    )
    if payload.valid_from is not None:
        # Mit "gilt ab": nicht in vorgelegte/abgeschlossene Monate hinein (ohne = wie bisher rückwirkend)
        await ensure_tenant_open_from(db, actor.tenant_id, payload.valid_from)
    db.add(rule)
    await db.flush()
    since = f", ab {payload.valid_from.isoformat()}" if payload.valid_from else ""
    _audit(db, actor, rule.id, f"Regel angelegt: {rule.name} ({payload.percent:g} %{since})")
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
    """Name, aktiv, Gruppe und Lohnart ändern die Fassung direkt. Satz, Zeitfenster und Wochentage
    gelten ab valid_from: galt die Fassung schon vorher, entsteht eine neue Fassung ab dem Stichtag,
    die bisherige endet am Vortag – zurückliegende Monate rechnen unverändert. Ohne valid_from wird
    die Fassung wie bisher direkt (auch rückwirkend) korrigiert."""
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    timed = rule.kind in (SurchargeKind.NIGHT, SurchargeKind.CUSTOM)
    values = {
        "percent": float(rule.percent) if payload.percent is None else payload.percent,
        "start_time": rule.start_time if payload.start_time is None or not timed else payload.start_time,
        "end_time": rule.end_time if payload.end_time is None or not timed else payload.end_time,
        "weekdays_mask": rule.weekdays_mask if payload.weekdays is None or not timed else _mask(payload.weekdays),
    }
    if payload.weekdays is not None and any(d < 0 or d > 6 for d in payload.weekdays):
        raise AppError(400, "INVALID_WEEKDAYS", "Wochentage müssen zwischen 0 (Montag) und 6 (Sonntag) liegen.")
    if timed and values["start_time"] == values["end_time"]:
        raise AppError(400, "INVALID_WINDOW", "Beginn und Ende dürfen nicht gleich sein.")
    calculation_changes = (
        values["percent"] != float(rule.percent)
        or values["start_time"] != rule.start_time
        or values["end_time"] != rule.end_time
        or values["weekdays_mask"] != rule.weekdays_mask
    )
    target = rule
    if calculation_changes and payload.valid_from is None:
        for key, value in values.items():
            setattr(target, key, value)
    elif calculation_changes:
        effective = payload.valid_from
        if rule.valid_to is not None and effective > rule.valid_to:
            raise AppError(400, "INVALID_RANGE", "Diese Fassung endet vor dem Stichtag – bitte die aktuelle Fassung ändern.")
        await ensure_tenant_open_from(db, actor.tenant_id, max(effective, rule.valid_from or effective))
        if rule.valid_from is None or rule.valid_from < effective:
            # Neue Fassung ab Stichtag, die bisherige gilt bis zum Vortag.
            target = SurchargeRule(
                tenant_id=rule.tenant_id, name=rule.name, kind=rule.kind, exclusive_group=rule.exclusive_group,
                active=rule.active, wage_type=rule.wage_type, valid_from=effective, valid_to=rule.valid_to,
                family_id=rule.family, **values,
            )
            rule.valid_to = effective - timedelta(days=1)
            db.add(target)
        else:
            for key, value in values.items():
                setattr(target, key, value)
    changes: list[str] = []
    if calculation_changes:
        since = f" ab {target.valid_from.isoformat()}" if target.valid_from else " (rückwirkend)"
        changes.append(f"{values['percent']:g} %{since}")
    if payload.name is not None and payload.name != target.name:
        target.name = payload.name
        changes.append(f"Name {payload.name}")
    if payload.active is not None and payload.active != target.active:
        target.active = payload.active
        changes.append("aktiv" if payload.active else "inaktiv")
    if payload.exclusive_group is not None:
        target.exclusive_group = payload.exclusive_group
    elif payload.clear_exclusive_group:
        target.exclusive_group = None
    if payload.wage_type is not None:
        target.wage_type = payload.wage_type or None
    await db.flush()
    _audit(db, actor, target.id, f"Regel geändert: {target.name}" + (f" ({', '.join(changes)})" if changes else ""))
    await db.commit()
    await db.refresh(target)
    return _response(target)


class SurchargeWageTypeRequest(BaseModel):
    # "" = keine Lohnart
    wage_type: str = Field(pattern=r"^[0-9]{0,6}$")


@router.put("/surcharge-rules/{rule_id}/wage-type", response_model=SurchargeRuleResponse)
async def set_surcharge_wage_type(
    rule_id: int,
    payload: SurchargeWageTypeRequest,
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> SurchargeRuleResponse:
    """Nur die Lohnart einer Regel (Seite „Lohnarten“) – Regeln selbst ändern bleibt Admins vorbehalten."""
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    rule.wage_type = payload.wage_type or None
    _audit(db, actor, rule.id, f"Lohnart {rule.name}: {payload.wage_type or 'leer'}")
    await db.commit()
    await db.refresh(rule)
    return _response(rule)


@router.delete("/surcharge-rules/{rule_id}", status_code=204)
async def delete_surcharge_rule(
    rule_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> None:
    """Eine Fassung löschen; die vorherige Fassung derselben Regel gilt dann bis zu deren Ende weiter."""
    rule = await _get_rule(db, rule_id, actor.tenant_id)
    siblings = (
        await db.execute(select(SurchargeRule).where(SurchargeRule.tenant_id == actor.tenant_id, SurchargeRule.id != rule.id))
    ).scalars().all()
    previous = next(
        (r for r in siblings if r.family == rule.family and rule.valid_from is not None and r.valid_to == rule.valid_from - timedelta(days=1)),
        None,
    )
    if previous is not None:
        previous.valid_to = rule.valid_to
    elif rule.family_id is None:
        # Erste Fassung gelöscht: spätere Fassungen behalten ihren Zusammenhalt über die nächste
        later = sorted((r for r in siblings if r.family_id == rule.id), key=lambda r: r.valid_from or date.min)
        for other in later:
            other.family_id = later[0].id if other is not later[0] else None
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
    if actor.has_payroll_access and not is_self:
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
                actor_account_id=actor.account_id,
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
