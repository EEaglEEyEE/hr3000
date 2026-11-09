"""Arbeitszeitmodelle (Einstellungen → Arbeitszeit & Pausen): anlegen, ab Stichtag ändern,
umbenennen, archivieren, löschen. Zugewiesen wird am Mitarbeiter
(PUT /employees/{id}/work-time-profile, app/api/work_time_model.py)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_principal
from app.api.work_time_model import _contract, _core_time_fields, _days_label, _describe, _flex_frame_fields, _frame_label, _times_template
from app.db import get_db
from app.errors import AppError
from app.models import (
    PROFILE_START,
    AuditAction,
    EmployeeDefaultShift,
    ShiftTemplate,
    WorkTimeProfile,
    WorkTimeProfileVersion,
)
from app.schemas.work_time_model import (
    WorkTimeProfileCreateRequest,
    WorkTimeProfileInput,
    WorkTimeProfileResponse,
    WorkTimeProfileSetRequest,
    WorkTimeProfileUpdateRequest,
    WorkTimeProfileVersionResponse,
)
from app.services.audit_service import log_action
from app.services.period_service import ensure_open_from
from app.services.shift_planning_service import check_max_daily_working_time, check_rest_period_for_default
from app.services.timesheet_service import invalidate_balance
from app.services.work_time_profile_service import (
    assigned_employee_ids,
    employee_names,
    get_profile_in_tenant,
    profile_versions,
    sync_employee,
)

router = APIRouter(tags=["work_time_profiles"])


def _version_at(versions: list[WorkTimeProfileVersion], day: date) -> WorkTimeProfileVersion:
    """Fassung, die an diesem Tag gilt (sonst die erste bzw. letzte)."""
    for version in versions:
        if version.valid_from <= day and (version.valid_to is None or version.valid_to >= day):
            return version
    return versions[-1] if versions[-1].valid_from <= day else versions[0]


async def _response(db: AsyncSession, profile: WorkTimeProfile) -> WorkTimeProfileResponse:
    today = date.today()
    current = _version_at(await profile_versions(db, profile.id), today)
    employee_ids = await assigned_employee_ids(db, profile.id, today)
    return WorkTimeProfileResponse(
        id=profile.id,
        name=profile.name,
        archived=profile.archived,
        valid_from=current.valid_from,
        employee_count=len(employee_ids),
        employees=await employee_names(db, employee_ids),
        **(await _describe(db, current)),
    )


async def _version_fields(
    db: AsyncSession, tenant_id: int, payload: WorkTimeProfileInput, inherit: WorkTimeProfileVersion | None
) -> tuple[dict, str]:
    fields, soll_label = _contract(payload)
    fields.update(_core_time_fields(payload, inherit))
    fields.update(_flex_frame_fields(payload, inherit))
    template = await _times_template(
        db, tenant_id, payload.shift_template_id, inherit.shift_template_id if inherit else None
    )
    if template is not None:
        check_max_daily_working_time(template.start_time, template.end_time)
    fields["shift_template_id"] = template.id if template else None
    frame = _frame_label(payload)
    if payload.late_tolerance_minutes is not None:
        frame += f", Toleranz {payload.late_tolerance_minutes} Min."
    return fields, f"{soll_label} an {_days_label(payload, template)}{frame}"


def _audit(db: AsyncSession, actor: Actor, profile: WorkTimeProfile, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.SETTINGS_CHANGED,
        entity_type="work_time_profile",
        entity_id=profile.id,
        detail=f"Arbeitszeitmodell „{profile.name}“: {detail}",
    )


@router.get("/work-time-profiles", response_model=list[WorkTimeProfileResponse])
async def list_work_time_profiles(
    include_archived: bool = False,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[WorkTimeProfileResponse]:
    query = select(WorkTimeProfile).where(WorkTimeProfile.tenant_id == actor.tenant_id)
    if not include_archived:
        query = query.where(WorkTimeProfile.archived.is_(False))
    profiles = (await db.execute(query.order_by(WorkTimeProfile.name))).scalars().all()
    return [await _response(db, profile) for profile in profiles]


@router.post("/work-time-profiles", response_model=WorkTimeProfileResponse, status_code=201)
async def create_work_time_profile(
    payload: WorkTimeProfileCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> WorkTimeProfileResponse:
    """Neues Modell; seine erste Fassung gilt von Anfang an (auch rückwirkend zuweisbar)."""
    fields, label = await _version_fields(db, actor.tenant_id, payload, None)
    profile = WorkTimeProfile(tenant_id=actor.tenant_id, name=payload.name, archived=False)
    db.add(profile)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "NAME_TAKEN", "Ein Arbeitszeitmodell mit diesem Namen gibt es schon.") from exc
    db.add(WorkTimeProfileVersion(profile_id=profile.id, valid_from=PROFILE_START, valid_to=None, **fields))
    _audit(db, actor, profile, f"angelegt – {label}")
    await db.commit()
    return await _response(db, profile)


@router.put("/work-time-profiles/{profile_id}/model", response_model=WorkTimeProfileResponse)
async def set_work_time_profile_model(
    profile_id: int,
    payload: WorkTimeProfileSetRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> WorkTimeProfileResponse:
    """Neue Fassung ab Stichtag – ersetzt alles ab diesem Tag und gilt für alle zugewiesenen
    Mitarbeiter. Liegt bei einem davon ein vorgelegter oder abgeschlossener Monat ab dem Stichtag,
    wird nichts geändert (Fehler nennt die Betroffenen)."""
    profile = await get_profile_in_tenant(db, profile_id, actor.tenant_id)
    if payload.valid_from < PROFILE_START:
        raise AppError(400, "INVALID_RANGE", f"Ein Modell gilt frühestens ab {PROFILE_START:%d.%m.%Y}.")
    versions = await profile_versions(db, profile.id)
    inherit = _version_at(versions, payload.valid_from)
    fields, label = await _version_fields(db, actor.tenant_id, payload, inherit)

    # Alle zugewiesenen Mitarbeiter müssen ab dem Stichtag (bzw. ab Beginn ihrer Zuweisung) offen sein.
    rows = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.profile_id == profile.id,
                (EmployeeDefaultShift.valid_to.is_(None)) | (EmployeeDefaultShift.valid_to >= payload.valid_from),
            )
        )
    ).scalars().all()
    effective: dict[int, date] = {}
    for row in rows:
        day = max(payload.valid_from, row.valid_from)
        effective[row.employee_id] = min(effective.get(row.employee_id, day), day)
    locked = []
    for employee_id, day in effective.items():
        try:
            await ensure_open_from(db, employee_id, day)
        except AppError:
            locked.append(employee_id)
    if locked:
        names = ", ".join(await employee_names(db, locked))
        raise AppError(
            409,
            "PERIOD_LOCKED",
            f"Für {names} ist ein Monat ab dem {payload.valid_from:%d.%m.%Y} vorgelegt oder abgeschlossen. "
            "Bitte einen späteren Stichtag wählen oder die Monate zuerst wieder öffnen.",
        )

    for version in versions:
        if version.valid_from >= payload.valid_from:
            await db.delete(version)
        elif version.valid_to is None or version.valid_to >= payload.valid_from:
            version.valid_to = payload.valid_from - timedelta(days=1)
    await db.flush()
    db.add(WorkTimeProfileVersion(profile_id=profile.id, valid_from=payload.valid_from, valid_to=None, **fields))
    await db.flush()
    for employee_id, day in effective.items():
        changed = await sync_employee(db, employee_id)
        if changed is not None and fields["shift_template_id"] is not None:
            await _check_rest_periods(db, employee_id, changed)
        await invalidate_balance(db, employee_id, min(day, changed or day))
    _audit(db, actor, profile, f"ab {payload.valid_from.isoformat()} {label} ({len(effective)} Mitarbeiter)")
    await db.commit()
    return await _response(db, profile)


async def _check_rest_periods(db: AsyncSession, employee_id: int, from_date: date) -> None:
    """Ruhezeit-Prüfung (ArbZG) für die nachgezogenen Fassungen mit Schichtvorlage."""
    rows = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.employee_id == employee_id,
                EmployeeDefaultShift.shift_template_id.is_not(None),
                (EmployeeDefaultShift.valid_to.is_(None)) | (EmployeeDefaultShift.valid_to >= from_date),
            )
        )
    ).scalars().all()
    for row in rows:
        template = await db.get(ShiftTemplate, row.shift_template_id)
        await check_rest_period_for_default(db, employee_id, template, row.weekdays_mask, row.valid_from, row.valid_to)


@router.patch("/work-time-profiles/{profile_id}", response_model=WorkTimeProfileResponse)
async def update_work_time_profile(
    profile_id: int,
    payload: WorkTimeProfileUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> WorkTimeProfileResponse:
    """Umbenennen oder archivieren (archiviert = nicht mehr neu zuweisbar, bestehende Zuweisungen
    gelten weiter). Ändert keine Berechnung."""
    profile = await get_profile_in_tenant(db, profile_id, actor.tenant_id)
    changes = []
    if payload.name is not None and payload.name != profile.name:
        changes.append(f"umbenannt in „{payload.name}“")
        profile.name = payload.name
    if payload.archived is not None and payload.archived != profile.archived:
        changes.append("archiviert" if payload.archived else "wieder aktiv")
        profile.archived = payload.archived
    if changes:
        _audit(db, actor, profile, ", ".join(changes))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "NAME_TAKEN", "Ein Arbeitszeitmodell mit diesem Namen gibt es schon.") from exc
    return await _response(db, profile)


@router.get("/work-time-profiles/{profile_id}/history", response_model=list[WorkTimeProfileVersionResponse])
async def get_work_time_profile_history(
    profile_id: int,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[WorkTimeProfileVersionResponse]:
    """Alle Fassungen des Modells, neueste zuerst."""
    profile = await get_profile_in_tenant(db, profile_id, actor.tenant_id)
    return [
        WorkTimeProfileVersionResponse(
            id=version.id, valid_from=version.valid_from, valid_to=version.valid_to, **(await _describe(db, version))
        )
        for version in reversed(await profile_versions(db, profile.id))
    ]


@router.delete("/work-time-profiles/{profile_id}", status_code=204)
async def delete_work_time_profile(
    profile_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Löschen nur, solange das Modell nie zugewiesen war – sonst archivieren."""
    profile = await get_profile_in_tenant(db, profile_id, actor.tenant_id)
    used = (
        await db.execute(select(func.count()).select_from(EmployeeDefaultShift).where(EmployeeDefaultShift.profile_id == profile.id))
    ).scalar_one()
    if used:
        raise AppError(
            409,
            "WORK_TIME_PROFILE_IN_USE",
            "Das Modell ist (oder war) Mitarbeitern zugewiesen und kann nicht gelöscht werden – bitte archivieren.",
        )
    for version in await profile_versions(db, profile.id):
        await db.delete(version)
    _audit(db, actor, profile, "gelöscht")
    await db.flush()
    await db.delete(profile)
    await db.commit()
