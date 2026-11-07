from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings, BreakRule, Location
from app.schemas.auth import KioskConfigResponse

# §4 ArbZG-Mindestpausen – Vorlage für neue Mandanten, siehe
# seed_default_break_rules. Historisch identisch zur ursprünglichen globalen
# Seed-Migration (0003_seed_break_rules).
_DEFAULT_BREAK_RULES = [
    {"min_work_minutes": 360, "deduct_minutes": 30},
    {"min_work_minutes": 540, "deduct_minutes": 45},
]


async def get_or_create_settings(db: AsyncSession, tenant_id: int, commit: bool = True) -> AppSettings:
    """Eine Zeile pro Mandant – legt sie beim ersten Zugriff eines neuen
    Mandanten automatisch mit Standardwerten an (dient als Tenant-Provisioning,
    ohne dass ein separater "Einstellungen einrichten"-Schritt nötig wäre)."""
    result = await db.execute(select(AppSettings).where(AppSettings.tenant_id == tenant_id))
    settings_row = result.scalar_one_or_none()
    if settings_row is None:
        settings_row = AppSettings(tenant_id=tenant_id)
        db.add(settings_row)
        if commit:
            await db.commit()
            await db.refresh(settings_row)
        else:
            await db.flush()
    return settings_row


async def tenant_logo_data_url(db: AsyncSession, tenant_id: int) -> str | None:
    """Firmenlogo als data:-URL oder None. `logo_data` ist deferred und wird nur hier gezielt gelesen."""
    row = (
        await db.execute(
            select(AppSettings.logo_content_type, AppSettings.logo_data).where(AppSettings.tenant_id == tenant_id)
        )
    ).first()
    if row is None or not row.logo_data or not row.logo_content_type:
        return None
    return f"data:{row.logo_content_type};base64,{row.logo_data}"


async def seed_default_break_rules(db: AsyncSession, tenant_id: int, commit: bool = True) -> None:
    """Legt für einen neuen Mandanten die gesetzliche §4-ArbZG-Staffel an –
    im Gegensatz zu WorkTimeModelTemplate bewusst automatisch, da es sich um
    gesetzliche Mindestwerte handelt, die kein Mandant von Null aus selbst
    definieren sollte."""
    for rule in _DEFAULT_BREAK_RULES:
        db.add(BreakRule(tenant_id=tenant_id, **rule))
    if commit:
        await db.commit()


def _screen_hours(settings_row: AppSettings, device) -> tuple[str | None, str | None]:
    """Aufgelöstes Bildschirm-Zeitfenster als "HH:MM" (Gerät vor Mandant); (None, None) = immer an."""
    if device is not None and device.screen_hours_mode == "ALWAYS":
        return None, None
    if device is not None and device.screen_hours_mode == "CUSTOM":
        start, end = device.screen_on_from, device.screen_on_until
    else:
        start, end = settings_row.kiosk_screen_on_from, settings_row.kiosk_screen_on_until
    if start is None or end is None:
        return None, None
    return start.strftime("%H:%M"), end.strftime("%H:%M")


def kiosk_config(settings_row: AppSettings, device=None, timezone: str = "Europe/Berlin") -> KioskConfigResponse:
    """Was das Tablet anzeigen/erlauben soll – beim Geräte-Login und über GET /device/config."""
    screen_on_from, screen_on_until = _screen_hours(settings_row, device)
    return KioskConfigResponse(
        screen_on_from=screen_on_from,
        screen_on_until=screen_on_until,
        timezone=timezone,
        require_pin=settings_row.require_pin_for_punch,
        rfid_required=settings_row.rfid_required,
        rfid_enabled=settings_row.kiosk_rfid_enabled,
        card_self_registration=settings_row.kiosk_rfid_enabled and settings_row.kiosk_card_self_registration,
        pin_self_setup=settings_row.kiosk_pin_self_setup,
        show_balance=settings_row.kiosk_show_balance,
        show_vacation=settings_row.kiosk_show_vacation,
        break_buttons=settings_row.kiosk_break_buttons,
        errand_buttons=settings_row.kiosk_errand_buttons,
        greeting=settings_row.kiosk_greeting,
        sort=settings_row.kiosk_sort,
        # Eigene Darstellung des Tablets hat Vorrang vor dem Mandanten-Standard.
        theme=(device.theme if device is not None and device.theme else settings_row.kiosk_theme),
    )


async def device_kiosk_config(db: AsyncSession, device) -> KioskConfigResponse:
    """Kiosk-Einstellungen für ein Tablet inkl. Zeitzone seines Standorts (für die Bildschirmzeiten)."""
    location = await db.get(Location, device.location_id)
    timezone = location.timezone if location is not None and location.tenant_id == device.tenant_id else "Europe/Berlin"
    return kiosk_config(await get_or_create_settings(db, device.tenant_id), device, timezone)
