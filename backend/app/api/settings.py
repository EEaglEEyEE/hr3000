from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal, get_current_hr_principal
from app.db import get_db
from app.models import AuditAction, Employee, Punch, ShiftPlanEntry
from app.errors import AppError
from app.schemas.core_time import parse_core_time_days, serialize_core_time_days
from app.schemas.settings import (
    FeaturesResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    SmtpTestRequest,
    SmtpTestResponse,
    TWO_FACTOR_ROLES,
)
from app.services.email_service import describe_smtp_error, ensure_public_smtp_host, resolve_smtp_config, send_email
from app.services.auth_service import hash_password
from app.services.secret_box import encrypt_secret
from app.services.audit_service import log_action
from app.services.settings_service import get_or_create_settings
from app.services.period_service import ensure_tenant_open_from
from app.services.timesheet_service import DAY_FLAGS, invalidate_tenant_balances, staffel_covers_law

_PUNCTUALITY_FLAGS = {"LATE_ARRIVAL", "EARLY_LEAVE", "OUTSIDE_FLEX_FRAME"}

router = APIRouter(tags=["settings"])


async def _first_punch_day(db: AsyncSession, tenant_id: int) -> date | None:
    first = await db.scalar(select(func.min(Punch.timestamp_utc)).where(Punch.tenant_id == tenant_id))
    return first.date() if first else None


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    return SettingsResponse.model_validate(settings_row)


@router.get("/features", response_model=FeaturesResponse)
async def get_features(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> FeaturesResponse:
    """Nur die Feature-Schalter, die die Oberfläche für alle HR-Rollen braucht
    (z.B. zum Ein-/Ausblenden von Schichtplanungs-Tabs) – die übrigen
    Einstellungen bleiben Admin-only (GET /settings)."""
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    return FeaturesResponse(
        shift_planning_enabled=settings_row.shift_planning_enabled,
        team_calendar_for_employees=settings_row.team_calendar_for_employees,
        org_chart_for_employees=settings_row.org_chart_for_employees,
        custom_reports_enabled=settings_row.custom_reports_enabled,
        absence_requests_enabled=settings_row.absence_requests_enabled,
        recruiting_enabled=settings_row.recruiting_enabled,
        whistleblowing_enabled=settings_row.whistleblowing_enabled,
        payroll_accounting_enabled=settings_row.payroll_accounting_enabled,
        project_times_enabled=settings_row.project_times_enabled,
        default_auto_break=settings_row.default_auto_break,
        default_show_birthday=settings_row.default_show_birthday,
        default_day_minutes=[int(v) for v in settings_row.default_day_minutes.split(",")] if settings_row.default_day_minutes else None,
    )


@router.patch("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    changed: list[str] = []
    if payload.require_pin_for_punch is not None:
        settings_row.require_pin_for_punch = payload.require_pin_for_punch
        changed.append(f"require_pin_for_punch={payload.require_pin_for_punch}")
    if payload.default_bundesland is not None:
        settings_row.default_bundesland = payload.default_bundesland.value
        changed.append(f"default_bundesland={payload.default_bundesland.value}")
    if payload.default_annual_vacation_days is not None:
        settings_row.default_annual_vacation_days = payload.default_annual_vacation_days
        changed.append(f"default_annual_vacation_days={payload.default_annual_vacation_days}")
    if payload.show_birthdays_in_calendar is not None:
        settings_row.show_birthdays_in_calendar = payload.show_birthdays_in_calendar
        changed.append(f"show_birthdays_in_calendar={payload.show_birthdays_in_calendar}")
    if payload.smtp_host is not None:
        if payload.smtp_host:
            try:
                await ensure_public_smtp_host(payload.smtp_host)
            except ValueError as exc:
                raise AppError(400, "SMTP_HOST_NOT_ALLOWED", str(exc)) from exc
        settings_row.smtp_host = payload.smtp_host or None
        changed.append(f"smtp_host={payload.smtp_host or '(Plattform-SMTP)'}")
    if payload.smtp_port is not None:
        settings_row.smtp_port = payload.smtp_port
        changed.append(f"smtp_port={payload.smtp_port}")
    if payload.smtp_user is not None:
        settings_row.smtp_user = payload.smtp_user or None
        changed.append("smtp_user geändert")
    if payload.smtp_password is not None:
        settings_row.smtp_password_encrypted = (
            encrypt_secret(payload.smtp_password) if payload.smtp_password else None
        )
        changed.append("smtp_password geändert")
    if payload.smtp_from is not None:
        settings_row.smtp_from = payload.smtp_from or None
        changed.append(f"smtp_from={payload.smtp_from}")
    if payload.smtp_security is not None:
        settings_row.smtp_security = payload.smtp_security
        changed.append(f"smtp_security={payload.smtp_security}")
    if payload.email_notifications_enabled is not None:
        settings_row.email_notifications_enabled = payload.email_notifications_enabled
        changed.append(f"email_notifications_enabled={payload.email_notifications_enabled}")
    if payload.shift_planning_enabled is not None and payload.shift_planning_enabled != settings_row.shift_planning_enabled:
        # Tagesausnahmen wirken nur mit Schichtplanung – nicht in vorgelegte/abgeschlossene Monate hinein.
        first_entry = await db.scalar(
            select(func.min(ShiftPlanEntry.date)).join(Employee, Employee.id == ShiftPlanEntry.employee_id).where(
                Employee.tenant_id == actor.tenant_id
            )
        )
        if first_entry is not None:
            await ensure_tenant_open_from(db, actor.tenant_id, first_entry)
        settings_row.shift_planning_enabled = payload.shift_planning_enabled
        changed.append(f"shift_planning_enabled={payload.shift_planning_enabled}")
        await invalidate_tenant_balances(db, actor.tenant_id, None)
    if payload.default_auto_break is not None:
        settings_row.default_auto_break = payload.default_auto_break
        changed.append(f"default_auto_break={payload.default_auto_break}")
    if payload.default_show_birthday is not None:
        settings_row.default_show_birthday = payload.default_show_birthday
        changed.append(f"default_show_birthday={payload.default_show_birthday}")
    if payload.default_day_minutes is not None:
        minutes = payload.default_day_minutes
        if minutes and (len(minutes) != 7 or any(m < 0 or m > 600 for m in minutes) or not any(minutes)):
            raise AppError(400, "INVALID_DEFAULT_MODEL", "Standard-Arbeitszeitmodell: 7 Werte zwischen 0 und 600 Minuten, mindestens ein Arbeitstag.")
        settings_row.default_day_minutes = ",".join(str(m) for m in minutes) if minutes else None
        changed.append(f"default_day_minutes={settings_row.default_day_minutes}")
    if payload.prorate_part_time_vacation is not None:
        settings_row.prorate_part_time_vacation = payload.prorate_part_time_vacation
        changed.append(f"prorate_part_time_vacation={payload.prorate_part_time_vacation}")
    if payload.prorate_partial_year_vacation is not None:
        settings_row.prorate_partial_year_vacation = payload.prorate_partial_year_vacation
        changed.append(f"prorate_partial_year_vacation={payload.prorate_partial_year_vacation}")
    if payload.seniority_leave_rules is not None:
        years = [rule.years for rule in payload.seniority_leave_rules]
        if years != sorted(set(years)):
            raise AppError(400, "INVALID_SENIORITY_RULES", "Bitte jede Jahreszahl nur einmal und aufsteigend angeben.")
        value = ",".join(f"{r.years}:{r.days:g}" for r in payload.seniority_leave_rules) or None
        if value != settings_row.seniority_leave_rules:
            settings_row.seniority_leave_rules = value
            changed.append(f"seniority_leave_rules={value or 'keine'}")
    if payload.reduce_vacation_parental_leave is not None:
        settings_row.reduce_vacation_parental_leave = payload.reduce_vacation_parental_leave
        changed.append(f"reduce_vacation_parental_leave={payload.reduce_vacation_parental_leave}")
    if payload.vacation_carry_over_auto is not None:
        settings_row.vacation_carry_over_auto = payload.vacation_carry_over_auto
        changed.append(f"vacation_carry_over_auto={payload.vacation_carry_over_auto}")
    if payload.clear_vacation_carry_over_max_days:
        settings_row.vacation_carry_over_max_days = None
        changed.append("vacation_carry_over_max_days=unbegrenzt")
    elif payload.vacation_carry_over_max_days is not None:
        settings_row.vacation_carry_over_max_days = payload.vacation_carry_over_max_days
        changed.append(f"vacation_carry_over_max_days={payload.vacation_carry_over_max_days}")
    if payload.vacation_carry_over_expiry is not None:
        expiry = payload.vacation_carry_over_expiry or None
        if expiry is not None:
            month, day = (int(v) for v in expiry.split("-"))
            if day > (29 if month == 2 else 30 if month in (4, 6, 9, 11) else 31):
                raise AppError(400, "INVALID_EXPIRY", "Ungültiges Verfallsdatum.")
        settings_row.vacation_carry_over_expiry = expiry
        changed.append(f"vacation_carry_over_expiry={expiry or 'kein Verfall'}")
    if payload.disabled_day_flags is not None:
        allowed = set(DAY_FLAGS)
        if any(flag not in allowed for flag in payload.disabled_day_flags):
            raise AppError(400, "INVALID_FLAG", "Unbekannter Sonderfall.")
        before = {f for f in (settings_row.disabled_day_flags or "").split(",") if f}
        if (before - set(payload.disabled_day_flags)) & _PUNCTUALITY_FLAGS:
            settings_row.punctuality_from = date.today()  # neu eingeschaltet: erst ab heute melden
        settings_row.disabled_day_flags = ",".join(sorted(set(payload.disabled_day_flags))) or None
        changed.append(f"disabled_day_flags={settings_row.disabled_day_flags}")
        await invalidate_tenant_balances(db, actor.tenant_id, None)  # Tages-Cache ("Zu klären") neu aufbauen
    if payload.legal_break_minimum is not None and payload.legal_break_minimum != settings_row.legal_break_minimum:
        if payload.legal_break_minimum and not await staffel_covers_law(db, actor.tenant_id, date.today()):
            raise AppError(
                409,
                "STAFFEL_BELOW_LAW",
                "Die Pausenstaffel liegt unter der gesetzlichen Mindestpause (§ 4 ArbZG) – bitte zuerst anpassen.",
            )
        settings_row.legal_break_minimum = payload.legal_break_minimum
        changed.append(f"legal_break_minimum={payload.legal_break_minimum}")
    for field, clear in (("break_precise_from", payload.clear_break_precise), ("break_capped_from", payload.clear_break_capped)):
        old, new = getattr(settings_row, field), getattr(payload, field)
        if new is None and not clear:
            continue
        if new == old:
            continue
        # Ab dem früheren der beiden Tage rechnet sich alles neu – nicht in abgeschlossenen Monaten.
        effective = min(d for d in (old, new) if d is not None) if (old or new) else None
        if effective is not None:
            await ensure_tenant_open_from(db, actor.tenant_id, effective)
        setattr(settings_row, field, new)
        changed.append(f"{field}={new.isoformat() if new else 'aus'}")
        await invalidate_tenant_balances(db, actor.tenant_id, effective)
    for field in ("datev_consultant_number", "datev_client_number"):
        value = getattr(payload, field)
        if value is not None:
            setattr(settings_row, field, value or None)
            changed.append(f"{field}={value or 'leer'}")
    if payload.report_days_without_punches is not None:
        settings_row.report_days_without_punches = payload.report_days_without_punches
        changed.append(f"report_days_without_punches={payload.report_days_without_punches}")
        await invalidate_tenant_balances(db, actor.tenant_id, None)  # Tages-Cache ("Zu klären") neu aufbauen
    punctuality_changed = False
    # Erst prüfen, dann übernehmen: Kernzeit muss im (neuen bzw. bestehenden) Gleitzeit-Rahmen liegen.
    new_core = (
        (payload.core_time_start, payload.core_time_end)
        if payload.core_time_start is not None
        else (None, None) if payload.clear_core_time else (settings_row.core_time_start, settings_row.core_time_end)
    )
    new_frame = (
        (payload.flex_frame_start, payload.flex_frame_end)
        if payload.flex_frame_start is not None
        else (None, None) if payload.clear_flex_frame else (settings_row.flex_frame_start, settings_row.flex_frame_end)
    )
    if None not in new_core and None not in new_frame and not (new_frame[0] <= new_core[0] and new_core[1] <= new_frame[1]):
        raise AppError(400, "CORE_TIME_OUTSIDE_FRAME", "Die Kernzeit muss innerhalb des Gleitzeit-Rahmens liegen.")
    days_sent = "core_time_days" in payload.model_fields_set
    new_days = (
        [None if d is None else (d.start, d.end) for d in payload.core_time_days or []] or None
        if days_sent
        else None if payload.clear_core_time else parse_core_time_days(settings_row.core_time_days)
    )
    if None not in new_frame and any(d and not (new_frame[0] <= d[0] and d[1] <= new_frame[1]) for d in new_days or []):
        raise AppError(400, "CORE_TIME_OUTSIDE_FRAME", "Die Kernzeit muss an jedem Tag innerhalb des Gleitzeit-Rahmens liegen.")
    if days_sent:
        settings_row.core_time_days = serialize_core_time_days(payload.core_time_days)
        changed.append(f"core_time_days={settings_row.core_time_days or 'jeden Tag gleich'}")
        punctuality_changed = True
    elif payload.clear_core_time:
        settings_row.core_time_days = None
    if payload.core_time_start is not None:
        settings_row.core_time_start, settings_row.core_time_end = payload.core_time_start, payload.core_time_end
        changed.append(f"core_time={payload.core_time_start:%H:%M}-{payload.core_time_end:%H:%M}")
        punctuality_changed = True
    elif payload.clear_core_time:
        settings_row.core_time_start = settings_row.core_time_end = None
        changed.append("core_time=keine")
        punctuality_changed = True
    if payload.flex_frame_start is not None:
        settings_row.flex_frame_start, settings_row.flex_frame_end = payload.flex_frame_start, payload.flex_frame_end
        changed.append(f"flex_frame={payload.flex_frame_start:%H:%M}-{payload.flex_frame_end:%H:%M}")
        punctuality_changed = True
    elif payload.clear_flex_frame:
        settings_row.flex_frame_start = settings_row.flex_frame_end = None
        changed.append("flex_frame=keiner")
        punctuality_changed = True
    if payload.late_tolerance_minutes is not None and payload.late_tolerance_minutes != settings_row.late_tolerance_minutes:
        settings_row.late_tolerance_minutes = payload.late_tolerance_minutes
        changed.append(f"late_tolerance_minutes={payload.late_tolerance_minutes}")
        punctuality_changed = True
    if payload.kiosk_screen_on_from is not None:
        settings_row.kiosk_screen_on_from = payload.kiosk_screen_on_from
        settings_row.kiosk_screen_on_until = payload.kiosk_screen_on_until
        changed.append(f"kiosk_screen_hours={payload.kiosk_screen_on_from:%H:%M}-{payload.kiosk_screen_on_until:%H:%M}")
    elif payload.clear_kiosk_screen_hours:
        settings_row.kiosk_screen_on_from = settings_row.kiosk_screen_on_until = None
        changed.append("kiosk_screen_hours=immer an")
    if punctuality_changed:
        # Neue Regeln gelten ab heute – frühere Tage bekommen keine Pünktlichkeits-Hinweise.
        settings_row.punctuality_from = date.today()
        await invalidate_tenant_balances(db, actor.tenant_id, None)  # Tages-Cache ("Zu klären") neu aufbauen
    if payload.max_shift_span_hours is not None and payload.max_shift_span_hours != settings_row.max_shift_span_hours:
        # Ändert die Zuordnung von Stempelungen zu Tagen rückwirkend.
        first_punch = await _first_punch_day(db, actor.tenant_id)
        if first_punch is not None:
            await ensure_tenant_open_from(db, actor.tenant_id, first_punch)
        settings_row.max_shift_span_hours = payload.max_shift_span_hours
        changed.append(f"max_shift_span_hours={payload.max_shift_span_hours}")
        await invalidate_tenant_balances(db, actor.tenant_id, None)
    for field, clear in (("overtime_limit_max_hours", payload.clear_overtime_limit_max), ("overtime_limit_min_hours", payload.clear_overtime_limit_min)):
        value = None if clear else getattr(payload, field)
        if (clear or value is not None) and value != getattr(settings_row, field):
            setattr(settings_row, field, value)
            changed.append(f"{field}={value}")
    if payload.kiosk_rfid_enabled is not None:
        settings_row.kiosk_rfid_enabled = payload.kiosk_rfid_enabled
        changed.append(f"kiosk_rfid_enabled={payload.kiosk_rfid_enabled}")
        if not payload.kiosk_rfid_enabled and settings_row.rfid_required and not payload.rfid_required:
            # Ohne Chip-Funktion kann keine RFID-Pflicht gelten.
            settings_row.rfid_required = False
            changed.append("rfid_required=False")
    if payload.rfid_required is not None:
        if payload.rfid_required and not settings_row.kiosk_rfid_enabled:
            raise AppError(400, "RFID_DISABLED", "Die RFID-Pflicht setzt die aktivierte Chip-Funktion am Tablet voraus.")
        settings_row.rfid_required = payload.rfid_required
        changed.append(f"rfid_required={payload.rfid_required}")
    for field in (
        "kiosk_show_balance",
        "kiosk_show_vacation",
        "kiosk_break_buttons",
        "kiosk_errand_buttons",
        "portal_punching_enabled",
        "punch_location_check_enabled",
        "punch_location_mode",
        "self_time_entry_enabled",
        "self_time_entry_approval",
        "self_time_entry_backdate_days",
        "project_times_enabled",
        "project_required",
        "whistleblowing_enabled",
        "absence_requests_enabled",
        "absence_four_eyes",
        "absence_overlaps_for_employees",
        "reminders_enabled",
        "payroll_accounting_enabled",
        "team_calendar_for_employees",
        "org_chart_for_employees",
        "custom_reports_enabled",
        "kiosk_sort",
        "kiosk_theme",
        "kiosk_card_self_registration",
        "kiosk_pin_self_setup",
        "recruiting_enabled",
        "recruiting_retention_months",
        "recruiting_talent_pool_months",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(settings_row, field, value)
            changed.append(f"{field}={value}")
    if payload.two_factor_roles is not None:
        value = ",".join(role for role in TWO_FACTOR_ROLES if role in payload.two_factor_roles) or None
        if value != settings_row.two_factor_roles:
            settings_row.two_factor_roles = value
            changed.append(f"two_factor_roles={value or 'keine'}")
    for field in ("recruiting_privacy_text", "recruiting_privacy_url"):
        value = getattr(payload, field)
        if value is not None:
            setattr(settings_row, field, value.strip() or None)
            changed.append(f"{field} geändert")
    if payload.kiosk_greeting is not None:
        settings_row.kiosk_greeting = payload.kiosk_greeting.strip() or None
        changed.append("kiosk_greeting geändert")
    if payload.kiosk_admin_pin is not None:
        settings_row.kiosk_admin_pin_hash = hash_password(payload.kiosk_admin_pin) if payload.kiosk_admin_pin else None
        changed.append("kiosk_admin_pin geändert" if payload.kiosk_admin_pin else "kiosk_admin_pin entfernt")
    if payload.balance_start_date is not None or payload.clear_balance_start_date:
        new_start = None if payload.clear_balance_start_date else payload.balance_start_date
        if new_start != settings_row.balance_start_date:
            # Kontobeginn verschiebt alle Salden ab dem früheren der beiden Stichtage (leer = erste Stempelung).
            starts = [settings_row.balance_start_date, new_start]
            if None in starts:
                starts.append(await _first_punch_day(db, actor.tenant_id))
            known = [d for d in starts if d is not None]
            if known:
                await ensure_tenant_open_from(db, actor.tenant_id, min(known))
            settings_row.balance_start_date = new_start
            changed.append(f"balance_start_date={new_start}")
            await invalidate_tenant_balances(db, actor.tenant_id, None)

    if changed:
        log_action(
            db,
            tenant_id=actor.tenant_id,
            actor_account_id=actor.account_id,
            action=AuditAction.SETTINGS_CHANGED,
            entity_type="app_settings",
            entity_id=settings_row.id,
            detail=", ".join(changed),
        )

    await db.commit()
    await db.refresh(settings_row)
    return SettingsResponse.model_validate(settings_row)


@router.post("/settings/smtp-test", response_model=SmtpTestResponse)
async def send_smtp_test(
    payload: SmtpTestRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> SmtpTestResponse:
    """Schickt eine Testmail über den für den Mandanten gültigen SMTP (eigener
    Server, sonst Plattform-SMTP) und meldet Fehler im Klartext zurück."""
    recipient = payload.to or actor.account.email
    if not recipient:
        raise AppError(400, "NO_RECIPIENT", "Bitte eine Empfängeradresse angeben.")

    config = await resolve_smtp_config(db, actor.tenant_id)
    if config is None:
        raise AppError(400, "EMAIL_NOT_CONFIGURED", "Es ist kein SMTP-Server konfiguriert.")
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    try:
        if settings_row.smtp_host:
            # Nur mandantenkonfigurierte Server prüfen; der Plattform-SMTP gehört dem Betreiber.
            await ensure_public_smtp_host(config.host)
        await send_email(
            recipient,
            "HR3000 – Testmail",
            "Diese Testmail bestätigt, dass der SMTP-Versand von HR3000 funktioniert.",
            config=config,
            raise_errors=True,
        )
    except Exception as exc:
        raise AppError(400, "SMTP_TEST_FAILED", describe_smtp_error(exc)) from exc
    return SmtpTestResponse(sent_to=recipient)
