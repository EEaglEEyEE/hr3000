"""Erinnerungen: Probezeit- und Befristungsende, bevorstehender Austritt und
verfallender Resturlaub – als Benachrichtigung (Glocke) und E-Mail, sofern ein Mailversand
eingerichtet ist.

Läuft als Hintergrundaufgabe (main.lifespan, ein Uvicorn-Prozess) und verschickt je Mandant
höchstens einmal pro Kalendertag (AppSettings.reminders_sent_on). Ausgelöst wird genau am Tag
„X Tage vorher“; fällt der Server an diesem Tag ganz aus, entfällt die Erinnerung (bewusst einfach).
Nur mit AppSettings.reminders_enabled (Standard aus).
"""
import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Employee, EmploymentContract, Notification, NotificationType, Tenant
from app.services.leave_service import leave_balance
from app.services.notification_service import _employee_login, _mail, _notification_mail_config, full_hr_recipients
from app.services.settings_service import get_or_create_settings

logger = logging.getLogger(__name__)

# Vorlauf in Tagen
PROBATION_DAYS = 14
FIXED_TERM_DAYS = 30
TERMINATION_DAYS = 14
VACATION_EXPIRY_DAYS = 30


def _name(employee: Employee) -> str:
    return f"{employee.first_name} {employee.last_name}"


async def _hr_messages(db: AsyncSession, tenant_id: int, today: date) -> list[str]:
    """Erinnerungen für Admin/HR."""
    messages: list[str] = []
    employees = (
        await db.execute(select(Employee).where(Employee.tenant_id == tenant_id, Employee.active.is_(True)))
    ).scalars().all()
    by_id = {e.id: e for e in employees}
    contracts = (
        await db.execute(
            select(EmploymentContract).where(
                EmploymentContract.tenant_id == tenant_id,
                EmploymentContract.employee_id.in_(by_id.keys() or [0]),
            )
        )
    ).scalars().all()
    for contract in contracts:
        employee = by_id[contract.employee_id]
        if contract.probation_end == today + timedelta(days=PROBATION_DAYS):
            messages.append(f"Probezeit von {_name(employee)} endet am {contract.probation_end:%d.%m.%Y}.")
        if contract.fixed_term_end == today + timedelta(days=FIXED_TERM_DAYS):
            messages.append(f"Befristung von {_name(employee)} endet am {contract.fixed_term_end:%d.%m.%Y}.")
    for employee in employees:
        if employee.termination_date == today + timedelta(days=TERMINATION_DAYS):
            messages.append(
                f"{_name(employee)} scheidet am {employee.termination_date:%d.%m.%Y} aus – Offboarding prüfen."
            )
    return messages


async def _vacation_expiry(db: AsyncSession, tenant_id: int, today: date) -> list[tuple[Employee, str]]:
    """(Mitarbeiter, Text) für Resturlaub aus dem Vorjahr, der in VACATION_EXPIRY_DAYS verfällt."""
    result = []
    employees = (
        await db.execute(select(Employee).where(Employee.tenant_id == tenant_id, Employee.active.is_(True)))
    ).scalars().all()
    for employee in employees:
        balance = await leave_balance(db, employee.id, today.year)
        if balance.expiry_date == today + timedelta(days=VACATION_EXPIRY_DAYS) and balance.expiring_days > 0:
            days = f"{balance.expiring_days:g}".replace(".", ",")
            result.append((employee, f"{days} Tag(e) Resturlaub aus dem Vorjahr verfallen am {balance.expiry_date:%d.%m.%Y}."))
    return result


async def send_due_reminders(db: AsyncSession, tenant_id: int, today: date) -> int:
    """Verschickt die heute fälligen Erinnerungen eines Mandanten (einmal pro Tag). Gibt die Zahl der
    angelegten Benachrichtigungen zurück; committet selbst."""
    settings_row = await get_or_create_settings(db, tenant_id)
    if not settings_row.reminders_enabled or settings_row.reminders_sent_on == today:
        return 0
    settings_row.reminders_sent_on = today

    hr_messages = await _hr_messages(db, tenant_id, today)
    expiring = await _vacation_expiry(db, tenant_id, today)
    hr_messages += [f"{_name(employee)}: {text}" for employee, text in expiring]

    mail_config = await _notification_mail_config(db, tenant_id)
    count = 0
    recipients = await full_hr_recipients(db, tenant_id)
    for message in hr_messages:
        for account_id, email in recipients:
            db.add(
                Notification(
                    tenant_id=tenant_id, recipient_account_id=account_id, type=NotificationType.REMINDER, message=message[:500]
                )
            )
            count += 1
            await _mail(mail_config, email, "Erinnerung", message)
    # Verfallender Urlaub zusätzlich an die Person selbst (mit Login).
    for employee, text in expiring:
        account = _employee_login(employee)
        if account is None:
            continue
        db.add(
            Notification(
                tenant_id=tenant_id, recipient_account_id=account.id, type=NotificationType.REMINDER,
                message=f"Erinnerung: {text}"[:500],
            )
        )
        count += 1
        await _mail(mail_config, account.email, "Erinnerung: Resturlaub", text)
    await db.commit()
    return count


async def run_reminders(session_factory: async_sessionmaker, interval_seconds: int) -> None:
    """Hintergrundschleife: prüft alle interval_seconds alle Mandanten (einmal pro Tag je Mandant)."""
    while True:
        try:
            async with session_factory() as db:
                tenant_ids = (await db.execute(select(Tenant.id))).scalars().all()
            for tenant_id in tenant_ids:
                async with session_factory() as db:
                    await send_due_reminders(db, tenant_id, date.today())
        except Exception:
            logger.exception("Erinnerungen konnten nicht verschickt werden.")
        await asyncio.sleep(interval_seconds)
