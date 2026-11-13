"""Migration aus einem Altsystem: Werte bestehender Mitarbeiter per CSV übernehmen (Vorschau,
dann übernehmen), siehe app/services/migration_import_service.py – und Einstellungen eines
Mandanten als Datei exportieren/importieren (z.B. aus einer Test- in die echte Firma)."""
import re
from datetime import date, datetime, time
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.absence_types import create_absence_type
from app.api.break_rules import create_break_rule
from app.api.deps import Actor, get_current_admin_principal, get_current_full_hr_principal
from app.api.settings import update_settings
from app.api.surcharges import create_surcharge_rule
from app.api.work_time_model import set_work_time_model
from app.db import get_db
from app.errors import AppError
from app.models import (
    AbsenceTypeDefinition,
    AdjustmentKind,
    AuditAction,
    BalanceAdjustment,
    BreakRule,
    BreakRuleKind,
    Employee,
    PayComponentKind,
    PayComponentType,
    SurchargeRule,
    WageTypeItem,
)
from app.schemas.absence_type import AbsenceTypeCreateRequest
from app.schemas.break_rule import BreakRuleCreateRequest
from app.schemas.employee import BulkImportRowError
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest
from app.schemas.surcharge import SurchargeRuleCreateRequest
from app.schemas.wage_type import WAGE_TYPE_LABELS
from app.services.wage_type_service import set_wage_types, wage_type_map
from app.services.absence_type_service import list_absence_types
from app.services.settings_service import get_or_create_settings
from app.services.surcharge_service import active_rules
from app.schemas.work_time_model import WorkTimeModelSetRequest
from app.services.audit_service import log_action
from app.services.leave_service import get_or_create_entitlement
from app.services.migration_import_service import MigrationRow, parse_migration_csv
from app.services.period_service import ensure_open_from, ensure_period_open
from app.services.scope_service import ensure_employee_visible
from app.services.timesheet_service import balance_start

router = APIRouter(tags=["migration"])

_MAX_BYTES = 2_000_000


class MigrationPreviewRow(BaseModel):
    row: int
    employee_id: int
    employee_number: str
    name: str
    changes: list[str]


class MigrationImportResult(BaseModel):
    applied: bool
    rows: list[MigrationPreviewRow]
    errors: list[BulkImportRowError]


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, employee_id: int, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=action,
        entity_type="employee",
        entity_id=employee_id,
        detail=detail[:500],
    )


async def _check_row(db: AsyncSession, actor: Actor, row: MigrationRow, cutover: date) -> None:
    """Prüfungen mit Datenbank: Sichtbarkeit, gesperrte Monate, doppelter Übertrag."""
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, row.employee)
    if row.model is not None:
        await ensure_open_from(db, row.employee.id, cutover)
    if row.balance_minutes is not None:
        if cutover > date.today():
            raise AppError(400, "FUTURE_DATE", "Ein Überstunden-Übertrag ist nur bis heute möglich.")
        await ensure_period_open(db, row.employee.id, cutover)
        duplicate = (
            await db.execute(
                select(BalanceAdjustment.id).where(
                    BalanceAdjustment.employee_id == row.employee.id,
                    BalanceAdjustment.kind == AdjustmentKind.OPENING_BALANCE,
                    BalanceAdjustment.effective_date == cutover,
                )
            )
        ).first()
        if duplicate is not None:
            raise AppError(409, "OPENING_BALANCE_EXISTS", "Zum Stichtag gibt es schon einen Überstunden-Übertrag (bereits übernommen?).")
        # Rechnet das Konto schon vor dem Stichtag (Kontobeginn in den Einstellungen oder frühere
        # Stempelungen), kämen diese Tage zum Übertrag aus dem Altsystem noch dazu.
        start = await balance_start(db, row.employee)
        if start is not None and start < cutover:
            raise AppError(
                409,
                "BALANCE_STARTS_BEFORE_CUTOVER",
                f"Das Überstundenkonto rechnet schon ab {start:%d.%m.%Y} – diese Tage kämen zum Übertrag dazu. "
                "Bitte „Überstundenkonten führen ab“ auf den Stichtag setzen oder den Stichtag anpassen.",
            )


async def _apply_row(db: AsyncSession, actor: Actor, row: MigrationRow, cutover: date) -> None:
    employee = row.employee
    if row.balance_minutes is not None:
        db.add(
            BalanceAdjustment(
                tenant_id=actor.tenant_id,
                employee_id=employee.id,
                effective_date=cutover,
                minutes=row.balance_minutes,
                kind=AdjustmentKind.OPENING_BALANCE,
                note="Übertrag aus Altsystem (Migration)",
                created_by_account_id=actor.account_id,
            )
        )
    if row.entitled_days is not None or row.carried_over_days is not None:
        entitlement = await get_or_create_entitlement(db, employee.id, cutover.year, actor.tenant_id)
        if row.entitled_days is not None:
            entitlement.entitled_days = row.entitled_days
            entitlement.entitled_manual = True
        if row.carried_over_days is not None:
            entitlement.carried_over_days = row.carried_over_days
            entitlement.carried_over_manual = True
    _audit(db, actor, AuditAction.BALANCE_ADJUSTED, employee.id, f"Migration zum {cutover.isoformat()}: {', '.join(row.changes)}")
    await db.commit()
    if row.model is not None:
        await set_work_time_model(employee.id, WorkTimeModelSetRequest.from_input(row.model, cutover), actor, db)


@router.post("/migration/employee-values", response_model=MigrationImportResult)
async def import_employee_values(
    file: UploadFile = File(...),
    cutover: date = Form(..., description="Stichtag der Übernahme"),
    apply: bool = Form(False, description="false = nur Vorschau"),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> MigrationImportResult:
    """Werte aus dem Altsystem für bestehende Mitarbeiter (über die Personalnummer). Ohne apply nur
    Vorschau. Fehlerhafte Zeilen werden übersprungen und gemeldet, gültige trotzdem übernommen."""
    raw = await file.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise AppError(400, "FILE_TOO_LARGE", "Die Datei ist zu groß (max. 2 MB).")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(400, "INVALID_ENCODING", "Die Datei muss UTF-8-kodiert sein.") from exc

    employees = (await db.execute(select(Employee).where(Employee.tenant_id == actor.tenant_id))).scalars().all()
    rows, errors = parse_migration_csv(content, {e.employee_number: e for e in employees})
    valid: list[MigrationRow] = []
    for row in rows:
        try:
            await _check_row(db, actor, row, cutover)
        except AppError as exc:
            errors.append(BulkImportRowError(row=row.line, message=exc.message))
            continue
        valid.append(row)
    errors.sort(key=lambda error: error.row)

    if apply:
        for row in valid:
            await _apply_row(db, actor, row, cutover)
        if valid:
            _audit(
                db, actor, AuditAction.EMPLOYEES_BULK_IMPORTED, 0,
                f"Migration zum {cutover.isoformat()}: Werte für {len(valid)} Mitarbeiter übernommen, {len(errors)} Zeile(n) übersprungen",
            )
            await db.commit()

    return MigrationImportResult(
        applied=apply,
        rows=[
            MigrationPreviewRow(
                row=row.line,
                employee_id=row.employee.id,
                employee_number=row.employee.employee_number,
                name=f"{row.employee.last_name}, {row.employee.first_name}",
                changes=row.changes,
            )
            for row in valid
        ],
        errors=errors,
    )


# --- Einstellungen eines Mandanten übertragen (Datei exportieren / importieren, nur Admin) ----------

# Übertragbar sind fachliche Einstellungen. Nicht übertragen werden firmenbezogene Werte: Mailserver
# (inkl. Passwort), Tablet-Admin-PIN, "Überstundenkonten führen ab", DATEV-Berater-/Mandantennummer.
PORTABLE_SETTINGS = (
    "require_pin_for_punch", "default_bundesland", "default_annual_vacation_days",
    "show_birthdays_in_calendar", "shift_planning_enabled", "default_auto_break", "default_show_birthday",
    "default_day_minutes", "prorate_part_time_vacation", "prorate_partial_year_vacation", "reduce_vacation_parental_leave", "seniority_leave_rules", "team_calendar_for_employees", "vacation_carry_over_auto", "vacation_carry_over_max_days",
    "vacation_carry_over_expiry", "disabled_day_flags", "report_days_without_punches", "report_flexible_days",
    "max_shift_span_hours", "core_time_start", "core_time_end", "core_time_days", "legal_break_minimum", "break_precise_from", "break_capped_from",
    "late_tolerance_minutes", "flex_frame_start", "flex_frame_end", "rfid_required", "kiosk_rfid_enabled",
    "kiosk_card_self_registration", "kiosk_pin_self_setup", "kiosk_show_balance", "kiosk_show_vacation",
    "kiosk_break_buttons", "kiosk_errand_buttons", "portal_punching_enabled", "self_time_entry_enabled",
    "self_time_entry_approval", "self_time_entry_backdate_days", "project_times_enabled", "project_required",
    "absence_requests_enabled", "absence_four_eyes",
    "absence_overlaps_for_employees", "overtime_limit_max_hours", "overtime_limit_min_hours", "reminders_enabled", "payroll_accounting_enabled",
    "kiosk_greeting", "kiosk_sort", "kiosk_theme", "kiosk_screen_on_from", "kiosk_screen_on_until",
    "custom_reports_enabled", "punch_location_check_enabled", "punch_location_mode",
)


class PortableBreakRule(BaseModel):
    kind: BreakRuleKind
    min_work_minutes: int = Field(ge=0, le=24 * 60)
    deduct_minutes: int = Field(ge=0, le=240)
    start_time: time | None = None
    end_time: time | None = None


class PortablePayComponentType(BaseModel):
    kind: PayComponentKind
    name: str = Field(min_length=1, max_length=100)
    wage_type: str | None = Field(default=None, pattern=r"^[0-9]{1,6}$")
    active: bool = True


class TenantSettingsFile(BaseModel):
    """Datei "Einstellungen exportieren": fachliche Einstellungen, aktuelle Pausenregeln,
    Abwesenheitsarten, Zuschlagsregeln, Lohnarten je Zeitart und Zulagenarten. Beim Import wird alles
    erneut validiert. Ältere Dateien (mit settings.datev_hours_wage_type) gehen weiterhin."""

    format: Literal["hr3000-settings"] = "hr3000-settings"
    version: Literal[1] = 1
    exported_at: datetime | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    break_rules: list[PortableBreakRule] = Field(default_factory=list, max_length=50)
    absence_types: list[AbsenceTypeCreateRequest] = Field(default_factory=list, max_length=100)
    surcharge_rules: list[SurchargeRuleCreateRequest] = Field(default_factory=list, max_length=100)
    wage_types: dict[WageTypeItem, str] = Field(default_factory=dict, max_length=len(WageTypeItem))
    pay_component_types: list[PortablePayComponentType] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _old_hours_wage_type(self) -> "TenantSettingsFile":
        # Dateien von vor dem Hinweis "Wochensoll nicht erreicht" kennen ihn nicht – er bleibt dann aus
        # (sonst würde er durch die fehlende Nennung in der Liste eingeschaltet).
        flags = self.settings.get("disabled_day_flags")
        if isinstance(flags, list) and "report_flexible_days" not in self.settings and "WEEKLY_TARGET_MISSED" not in flags:
            self.settings["disabled_day_flags"] = [*flags, "WEEKLY_TARGET_MISSED"]
        legacy = self.settings.pop("datev_hours_wage_type", None)
        if legacy and WageTypeItem.WORKED not in self.wage_types:
            self.wage_types[WageTypeItem.WORKED] = legacy
        for item, value in self.wage_types.items():
            if not re.fullmatch(r"[0-9]{1,6}", value or ""):
                raise ValueError(f"Lohnart für {item.value} ungültig.")
        return self


class SettingsImportResult(BaseModel):
    applied: bool
    changes: list[str]
    skipped: list[str]


@router.get("/migration/settings-export", response_model=TenantSettingsFile)
async def export_tenant_settings(
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantSettingsFile:
    current = SettingsResponse.model_validate(await get_or_create_settings(db, actor.tenant_id)).model_dump(mode="json")
    today = date.today()
    rules = (
        await db.execute(
            select(BreakRule).where(
                BreakRule.tenant_id == actor.tenant_id,
                BreakRule.valid_from <= today,
                or_(BreakRule.valid_to.is_(None), BreakRule.valid_to >= today),
            )
        )
    ).scalars().all()
    absence_types = await list_absence_types(db, actor.tenant_id)
    # je Regel nur die offene (neueste) Fassung
    surcharges = [r for r in await active_rules(db, actor.tenant_id) if r.valid_to is None]
    wage_types = await wage_type_map(db, actor.tenant_id)
    component_types = (
        await db.execute(select(PayComponentType).where(PayComponentType.tenant_id == actor.tenant_id).order_by(PayComponentType.name))
    ).scalars().all()
    await db.commit()
    return TenantSettingsFile(
        exported_at=datetime.now(),
        settings={key: current[key] for key in PORTABLE_SETTINGS if key in current},
        break_rules=[
            PortableBreakRule(
                kind=r.kind or BreakRuleKind.LEGAL,
                min_work_minutes=r.min_work_minutes,
                deduct_minutes=r.deduct_minutes,
                start_time=r.start_time,
                end_time=r.end_time,
            )
            for r in rules
        ],
        absence_types=[
            AbsenceTypeCreateRequest(
                name=t.name,
                color=t.color,
                category=t.category,
                requires_approval=t.requires_approval,
                employee_can_request=t.employee_can_request,
                certificate_from_day=t.certificate_from_day,
                sort_order=t.sort_order,
            )
            for t in absence_types
            if t.active
        ],
        surcharge_rules=[
            SurchargeRuleCreateRequest(
                name=r.name,
                kind=r.kind,
                percent=float(r.percent),
                start_time=r.start_time,
                end_time=r.end_time,
                weekdays=[d for d in range(7) if (r.weekdays_mask >> d) & 1],
                exclusive_group=r.exclusive_group,
                active=r.active,
                wage_type=r.wage_type,
            )
            for r in surcharges
        ],
        wage_types=dict(wage_types),
        pay_component_types=[
            PortablePayComponentType(kind=t.kind, name=t.name, wage_type=t.wage_type, active=t.active) for t in component_types
        ],
    )


def _settings_update(values: dict[str, Any]) -> SettingsUpdateRequest:
    """Übertragbare Werte als Änderung; leere Zeitfenster werden ausdrücklich entfernt."""
    data = {key: values[key] for key in PORTABLE_SETTINGS if key in values}
    for start, flag in (("core_time_start", "clear_core_time"), ("flex_frame_start", "clear_flex_frame"),
                        ("kiosk_screen_on_from", "clear_kiosk_screen_hours"), ("break_precise_from", "clear_break_precise"),
                        ("break_capped_from", "clear_break_capped")):
        if start in data and data[start] is None:
            data[flag] = True
    if "vacation_carry_over_max_days" in data and data["vacation_carry_over_max_days"] is None:
        data["clear_vacation_carry_over_max_days"] = True
    if data.get("vacation_carry_over_expiry") is None and "vacation_carry_over_expiry" in data:
        data["vacation_carry_over_expiry"] = ""
    for key in ("kiosk_greeting",):
        if key in data and data[key] is None:
            data[key] = ""
    if "default_day_minutes" in data and data["default_day_minutes"] is None:
        data["default_day_minutes"] = []
    return SettingsUpdateRequest.model_validate(data)


async def _new_absence_types(
    db: AsyncSession, tenant_id: int, wanted: list[AbsenceTypeCreateRequest]
) -> list[AbsenceTypeCreateRequest]:
    names = (
        await db.execute(select(AbsenceTypeDefinition.name).where(AbsenceTypeDefinition.tenant_id == tenant_id))
    ).scalars().all()
    existing = {name.strip().lower() for name in names}
    return [t for t in wanted if t.name.strip().lower() not in existing]


@router.post("/migration/settings-import", response_model=SettingsImportResult)
async def import_tenant_settings(
    payload: TenantSettingsFile,
    apply: bool = Query(False, description="false = nur Vorschau"),
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> SettingsImportResult:
    """Übernimmt eine exportierte Datei: Einstellungen werden überschrieben, Pausenregeln,
    Abwesenheitsarten und Zuschläge nur ergänzt (vorhandene bleiben unverändert). Ohne apply nur
    Vorschau."""
    try:
        update = _settings_update(payload.settings)
    except ValidationError as exc:
        raise AppError(422, "INVALID_SETTINGS_FILE", f"Einstellungen ungültig: {exc.errors()[0]['loc'][0]}") from exc
    current = SettingsResponse.model_validate(await get_or_create_settings(db, actor.tenant_id)).model_dump(mode="json")
    wanted = {key: value for key, value in payload.settings.items() if key in PORTABLE_SETTINGS}
    changes = [f"Einstellung {key}" for key, value in wanted.items() if current.get(key) != value]
    skipped: list[str] = []

    today = date.today()
    existing_rules = (
        await db.execute(
            select(BreakRule).where(
                BreakRule.tenant_id == actor.tenant_id, or_(BreakRule.valid_to.is_(None), BreakRule.valid_to >= today)
            )
        )
    ).scalars().all()
    new_rules: list[PortableBreakRule] = []
    for rule in payload.break_rules:
        same = [r for r in existing_rules if (r.kind or BreakRuleKind.LEGAL) == rule.kind]
        if rule.kind == BreakRuleKind.FIXED_WINDOW:
            label = f"Feste Pausenzeit {rule.start_time:%H:%M}–{rule.end_time:%H:%M}" if rule.start_time and rule.end_time else "Feste Pausenzeit"
            identical = any(r.start_time == rule.start_time and r.end_time == rule.end_time for r in same)
            taken = any(r.start_time < rule.end_time and rule.start_time < r.end_time for r in same) if rule.start_time and rule.end_time else False
        else:
            label = f"Pausenregel ab {rule.min_work_minutes} Min.: {rule.deduct_minutes} Min." + (" (fest)" if rule.kind == BreakRuleKind.FIXED_MINUTES else "")
            identical = any(r.min_work_minutes == rule.min_work_minutes and r.deduct_minutes == rule.deduct_minutes for r in same)
            taken = any(r.min_work_minutes == rule.min_work_minutes for r in same)
        if identical:
            continue
        if taken:
            skipped.append(f"{label}: kollidiert mit einer vorhandenen Regel – bitte unter „Pausenregeln“ anpassen")
            continue
        new_rules.append(rule)
        changes.append(label)

    # Vorschau schreibt nichts – daher die Namen direkt lesen (ohne Standardarten anzulegen).
    new_absences = await _new_absence_types(db, actor.tenant_id, payload.absence_types)
    changes += [f"Abwesenheitsart {t.name}" for t in new_absences]
    surcharge_names = {
        name.strip().lower()
        for name in (await db.execute(select(SurchargeRule.name).where(SurchargeRule.tenant_id == actor.tenant_id))).scalars().all()
    }
    new_surcharges = [r for r in payload.surcharge_rules if r.name.strip().lower() not in surcharge_names]
    changes += [f"Zuschlag {r.name}" for r in new_surcharges]
    current_wage_types = await wage_type_map(db, actor.tenant_id)
    wage_type_updates = {item: value for item, value in payload.wage_types.items() if current_wage_types.get(item) != value}
    changes += [f"Lohnart {WAGE_TYPE_LABELS[item]}: {value}" for item, value in wage_type_updates.items()]
    type_names = {
        (kind, name.strip().lower())
        for kind, name in (
            await db.execute(select(PayComponentType.kind, PayComponentType.name).where(PayComponentType.tenant_id == actor.tenant_id))
        ).all()
    }
    new_component_types = [t for t in payload.pay_component_types if (t.kind, t.name.strip().lower()) not in type_names]
    changes += [f"Zulagenart {t.name}" for t in new_component_types]

    if apply:
        await update_settings(update, actor, db)
        for rule in new_rules:
            data = rule.model_dump()
            if rule.kind == BreakRuleKind.FIXED_WINDOW:
                data = {"kind": rule.kind, "start_time": rule.start_time, "end_time": rule.end_time}
            await create_break_rule(BreakRuleCreateRequest(**data, valid_from=today), actor, db)
        await list_absence_types(db, actor.tenant_id)  # Standardarten zuerst anlegen, dann nur Fehlende
        for absence in await _new_absence_types(db, actor.tenant_id, payload.absence_types):
            await create_absence_type(absence, actor, db)
        for surcharge in new_surcharges:
            # wie Pausenregeln: ab heute (vorgelegte/abgeschlossene Monate bleiben unberührt)
            await create_surcharge_rule(surcharge.model_copy(update={"valid_from": today}), actor, db)
        await set_wage_types(db, actor.tenant_id, dict(wage_type_updates))
        for component_type in new_component_types:
            db.add(
                PayComponentType(
                    tenant_id=actor.tenant_id, kind=component_type.kind, name=component_type.name.strip(),
                    wage_type=component_type.wage_type, active=component_type.active,
                )
            )
        _audit(db, actor, AuditAction.SETTINGS_CHANGED, 0, f"Einstellungen aus Datei übernommen: {len(changes)} Änderung(en)")
        await db.commit()
    return SettingsImportResult(applied=apply, changes=changes, skipped=skipped)
