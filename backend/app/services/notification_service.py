from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    Account,
    Employee,
    HrRole,
    Notification,
    NotificationType,
)
from app.services.email_service import SmtpConfig, resolve_smtp_config, send_email
from app.services.settings_service import get_or_create_settings

_FULL_HR_ROLES = (HrRole.ADMIN, HrRole.HR)


@dataclass(frozen=True)
class NotificationMailConfig:
    smtp: SmtpConfig
    # Adressen (klein geschrieben), die keine Benachrichtigungs-Mails wollen (notification_emails aus)
    opted_out: frozenset[str]


async def _notification_mail_config(db: AsyncSession, tenant_id: int) -> NotificationMailConfig | None:
    """SMTP für Benachrichtigungs-Mails: None, wenn der Mandant Mail-
    Benachrichtigungen abgeschaltet hat oder gar kein SMTP (eigener oder
    Plattform) konfiguriert ist – die In-App-Glocke bleibt davon unberührt.
    Wer selbst „keine E-Mails“ eingestellt hat, wird in _mail übersprungen."""
    row = await get_or_create_settings(db, tenant_id)
    if not row.email_notifications_enabled:
        return None
    smtp = await resolve_smtp_config(db, tenant_id)
    if smtp is None:
        return None
    result = await db.execute(
        select(Account.email).where(
            Account.tenant_id == tenant_id, Account.notification_emails.is_(False), Account.email.is_not(None)
        )
    )
    opted_out = frozenset(e.lower() for e in result.scalars() if e)
    return NotificationMailConfig(smtp, opted_out)


async def _mail(config: NotificationMailConfig | None, to: str | None, subject: str, body: str) -> None:
    if config is not None and to and to.lower() not in config.opted_out:
        await send_email(to, subject, body, config=config.smtp)


def _signed_in_accounts(tenant_id: int):
    """Konten der Firma, die sich anmelden können (E-Mail gesetzt, verknüpfter Mitarbeiter aktiv)."""
    return (
        select(Account.id, Account.email)
        .outerjoin(Employee, Employee.id == Account.employee_id)
        .where(
            Account.tenant_id == tenant_id,
            Account.email.is_not(None),
            Account.password_hash.is_not(None),
            or_(Account.employee_id.is_(None), Employee.active.is_(True)),
        )
    )


async def full_hr_recipients(
    db: AsyncSession, tenant_id: int, exclude_employee_id: int | None = None
) -> list[tuple[int, str | None]]:
    """(Konto-ID, E-Mail) aller Admins und HR der Firma."""
    stmt = _signed_in_accounts(tenant_id).where(Account.role.in_(_FULL_HR_ROLES))
    if exclude_employee_id is not None:
        stmt = stmt.where(or_(Account.employee_id.is_(None), Account.employee_id != exclude_employee_id))
    return [(account_id, email) for account_id, email in (await db.execute(stmt.order_by(Account.id))).all()]


def _employee_login(employee: Employee) -> Account | None:
    """Konto des Mitarbeiters, wenn er sich anmelden kann – sonst sieht niemand die Benachrichtigung."""
    account = employee.account
    return account if account is not None and account.email is not None else None


async def _notify_accounts(
    db: AsyncSession,
    tenant_id: int,
    recipients: list[tuple[int, str | None]],
    type_: NotificationType,
    message: str,
    subject: str,
    **extra,
) -> None:
    mail_config = await _notification_mail_config(db, tenant_id)
    for account_id, email in recipients:
        db.add(Notification(tenant_id=tenant_id, recipient_account_id=account_id, type=type_, message=message, **extra))
        await _mail(mail_config, email, subject, message)


async def _notify_employee(
    db: AsyncSession, tenant_id: int, employee: Employee, type_: NotificationType, message: str, subject: str, **extra
) -> None:
    account = _employee_login(employee)
    if account is not None:
        await _notify_accounts(db, tenant_id, [(account.id, account.email)], type_, message, subject, **extra)


async def notify_absence_requested(
    db: AsyncSession,
    tenant_id: int,
    employee: Employee,
    type_name: str = "Urlaub",
    recipients: list[tuple[int, str | None]] | None = None,
    step_note: str = "",
) -> None:
    """Benachrichtigt die zuständigen Führungskräfte (Ausnahme je Person bzw. alle Leitungen der
    Abteilung, bei Abwesenheit die handelnden Stellvertretungen) über einen neuen PENDING-Antrag – ohne
    Führungskraft mit Zugang ersatzweise alle Admin/HR-Nutzer des Mandanten, damit ein Antrag nie
    unbemerkt bleibt."""
    if recipients is not None:
        message = f"Antrag ({type_name}) von {employee.first_name} {employee.last_name} wartet auf Genehmigung{step_note}."
        await _notify_accounts(db, tenant_id, recipients, NotificationType.ABSENCE_REQUESTED, message, f"Neuer Antrag: {type_name}")
        return
    from app.services.approval_service import approver_recipients

    recipients = await approver_recipients(db, employee)
    if not recipients:
        recipients = await full_hr_recipients(db, tenant_id)

    message = f"Neuer Antrag ({type_name}) von {employee.first_name} {employee.last_name} wartet auf Genehmigung."
    await _notify_accounts(db, tenant_id, recipients, NotificationType.ABSENCE_REQUESTED, message, f"Neuer Antrag: {type_name}")


async def notify_open_days_digest(db: AsyncSession, tenant_id: int, open_day_count: int) -> None:
    """Piggyback-Digest statt eines echten Cron-Jobs (es gibt keine
    Hintergrundjob-Infrastruktur in dieser Umgebung): wird bei jedem Aufruf
    von GET /timesheet/open-days mit aufgerufen, benachrichtigt aber
    höchstens einmal pro Kalendertag und Mandant, damit nicht bei jedem
    Seitenaufruf der "Zu klären"-Liste eine neue Benachrichtigung entsteht."""
    if open_day_count == 0:
        return

    settings_row = await get_or_create_settings(db, tenant_id)
    today = date.today()
    if settings_row.open_days_digest_sent_at == today:
        return
    settings_row.open_days_digest_sent_at = today

    message = f"{open_day_count} Tag(e) benötigen Aufmerksamkeit ('Zu klären')."
    await _notify_accounts(
        db, tenant_id, await full_hr_recipients(db, tenant_id), NotificationType.OPEN_DAYS_DIGEST, message,
        "Zu klären: offene Tage",
    )


async def notify_absence_decided(
    db: AsyncSession, tenant_id: int, absence: Absence, employee: Employee
) -> None:
    """Benachrichtigt den Antragsteller über die Entscheidung – nur mit eigenem Login, sonst gibt es
    niemanden, der die Benachrichtigung sehen könnte."""
    status_label = "genehmigt" if absence.approval_status == AbsenceApprovalStatus.APPROVED else "abgelehnt"
    message = f"Dein Urlaubsantrag ({absence.date_from.isoformat()} – {absence.date_to.isoformat()}) wurde {status_label}."
    await _notify_employee(
        db, tenant_id, employee, NotificationType.ABSENCE_DECIDED, message, "Urlaubsantrag entschieden",
        related_absence_id=absence.id,
    )


async def notify_substitute_assigned(
    db: AsyncSession, tenant_id: int, absence: Absence, employee: Employee, substitute: Employee, type_name: str
) -> None:
    """Die Vertretung erfährt, wen sie wann vertritt – sobald die Abwesenheit gilt (genehmigt).
    Nur mit eigenem Login, sonst sieht es niemand."""
    if absence.approval_status != AbsenceApprovalStatus.APPROVED:
        return
    message = (
        f"Du vertrittst {employee.first_name} {employee.last_name} vom {absence.date_from:%d.%m.%Y} "
        f"bis {absence.date_to:%d.%m.%Y} ({type_name})."
    )
    await _notify_employee(
        db, tenant_id, substitute, NotificationType.SUBSTITUTE_ASSIGNED, message, "Vertretung", related_absence_id=absence.id
    )


async def notify_period_submitted(db: AsyncSession, tenant_id: int, employee: Employee, label: str) -> None:
    """Mitarbeiter soll den vorgelegten Monatsnachweis bestätigen – nur sinnvoll mit eigenem Login."""
    message = f"Dein Monatsnachweis für {label} liegt zur Bestätigung bereit (Mein Bereich → Monatsabschluss)."
    await _notify_employee(db, tenant_id, employee, NotificationType.PERIOD_SUBMITTED, message, "Monatsnachweis zur Bestätigung")


async def notify_period_disputed(db: AsyncSession, tenant_id: int, employee: Employee, label: str) -> None:
    """Admin und HR erfahren vom Widerspruch (ohne die Person selbst, falls sie HR ist)."""
    message = f"{employee.first_name} {employee.last_name} hat dem Monatsnachweis {label} widersprochen."
    await _notify_accounts(
        db, tenant_id, await full_hr_recipients(db, tenant_id, exclude_employee_id=employee.id),
        NotificationType.PERIOD_DISPUTED, message, "Monatsnachweis beanstandet",
    )


async def notify_correction_requested(db: AsyncSession, tenant_id: int, employee: Employee, work_date: date) -> None:
    message = (
        f"{employee.first_name} {employee.last_name} beantragt eine Zeitkorrektur für den "
        f"{work_date.strftime('%d.%m.%Y')} (Zu klären → Korrekturanträge)."
    )
    await _notify_accounts(
        db, tenant_id, await full_hr_recipients(db, tenant_id, exclude_employee_id=employee.id),
        NotificationType.CORRECTION_REQUESTED, message, "Neuer Korrekturantrag",
    )


async def notify_correction_decided(
    db: AsyncSession, tenant_id: int, employee: Employee, work_date: date, approved: bool
) -> None:
    message = f"Dein Korrekturantrag für den {work_date.strftime('%d.%m.%Y')} wurde {'übernommen' if approved else 'abgelehnt'}."
    await _notify_employee(db, tenant_id, employee, NotificationType.CORRECTION_DECIDED, message, "Korrekturantrag entschieden")


async def notify_device_enrolled(db: AsyncSession, device, reported_name: str | None) -> None:
    """Info an Admin/HR: ein vorbereiteter Tablet-Eintrag wurde per Registrierungsschlüssel (MDM) belegt."""
    message = (
        f"Das Gerät „{reported_name or '?'}“ hat sich per MDM als Tablet „{device.name}“ eingerichtet. "
        "War das nicht geplant, in der HR-Webapp unter „Tablets“ die Kopplung aufheben und den "
        "Registrierungsschlüssel erneuern."
    )
    await _notify_accounts(
        db, device.tenant_id, await full_hr_recipients(db, device.tenant_id), NotificationType.DEVICE_ALERT, message,
        "Tablet per MDM eingerichtet",
    )


async def notify_enrollment_requested(
    db: AsyncSession,
    tenant_id: int,
    location_name: str,
    reported_name: str | None,
    verify_code: str,
    conflict_device_name: str | None,
) -> None:
    """Admin/HR: ein Gerät mit gültigem Registrierungsschlüssel wartet auf Freigabe."""
    message = (
        f"Ein Gerät „{reported_name or 'ohne Namen'}“ möchte sich am Standort „{location_name}“ als Tablet "
        f"einrichten (Prüfcode {verify_code}). Freigeben oder ablehnen in der HR-Webapp unter „Tablets“."
    )
    if conflict_device_name:
        message += (
            f" Achtung: Das Tablet „{conflict_device_name}“ mit diesem Gerätenamen ist bereits in Benutzung – "
            "nur freigeben, wenn das Gerät wirklich ersetzt wurde."
        )
    await _notify_accounts(
        db, tenant_id, await full_hr_recipients(db, tenant_id), NotificationType.DEVICE_ALERT, message,
        "Tablet wartet auf Freigabe",
    )


async def notify_device_replaced(db: AsyncSession, device) -> None:
    """Warnung an Admin/HR: ein verbundenes Tablet wurde per QR-Code an ein anderes Gerät vergeben."""
    message = (
        f"Das Tablet „{device.name}“ wurde per QR-Code mit einem anderen Gerät gekoppelt; das bisherige Gerät ist "
        "abgemeldet. War das nicht geplant, in der HR-Webapp unter „Tablets“ prüfen, welches Gerät den Zugang hat."
    )
    await _notify_accounts(
        db, device.tenant_id, await full_hr_recipients(db, device.tenant_id), NotificationType.DEVICE_ALERT, message,
        "Tablet an anderes Gerät vergeben",
    )


async def notify_device_rejected(db: AsyncSession, device) -> None:
    """Warnung an Admin/HR: ein weiteres Gerät wollte sich mit dem Zugang eines Tablets anmelden."""
    message = (
        f"Ein weiteres Gerät wollte sich als Tablet „{device.name}“ anmelden und wurde abgewiesen. "
        "Wurde das Tablet getauscht, in der HR-Webapp unter „Tablets“ neu koppeln – sonst prüfen, wer den Zugang hat."
    )
    await _notify_accounts(
        db, device.tenant_id, await full_hr_recipients(db, device.tenant_id), NotificationType.DEVICE_ALERT, message,
        "Warnung: Tablet-Zugang",
    )
