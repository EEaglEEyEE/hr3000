from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    Employee,
    HrRole,
    HrUser,
    Notification,
    NotificationType,
    SupervisorTeamAssignment,
)
from app.services.email_service import SmtpConfig, resolve_smtp_config, send_email
from app.services.settings_service import get_or_create_settings

_FULL_HR_ROLES = (HrRole.ADMIN, HrRole.HR)


async def _notification_mail_config(db: AsyncSession, tenant_id: int) -> SmtpConfig | None:
    """SMTP für Benachrichtigungs-Mails: None, wenn der Mandant Mail-
    Benachrichtigungen abgeschaltet hat oder gar kein SMTP (eigener oder
    Plattform) konfiguriert ist – die In-App-Glocke bleibt davon unberührt."""
    row = await get_or_create_settings(db, tenant_id)
    if not row.email_notifications_enabled:
        return None
    return await resolve_smtp_config(db, tenant_id)


async def _mail(config: SmtpConfig | None, to: str | None, subject: str, body: str) -> None:
    if config is not None and to:
        await send_email(to, subject, body, config=config)


async def _hr_user_emails(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    result = await db.execute(select(HrUser.id, HrUser.email).where(HrUser.id.in_(ids)))
    return dict(result.all())


async def _employee_emails(db: AsyncSession, ids: set[int]) -> dict[int, str | None]:
    if not ids:
        return {}
    result = await db.execute(select(Employee.id, Employee.login_email).where(Employee.id.in_(ids)))
    return dict(result.all())


async def notify_absence_requested(
    db: AsyncSession, tenant_id: int, employee: Employee, type_name: str = "Urlaub"
) -> None:
    """Benachrichtigt die Supervisor des Teams des Mitarbeiters (siehe
    SupervisorTeamAssignment) über einen neuen PENDING-Urlaubsantrag – ist
    kein Team zugeordnet oder hat es keinen Supervisor, fällt die
    Benachrichtigung ersatzweise an alle Admin/HR-Nutzer des Mandanten,
    damit ein Antrag nie unbemerkt bleibt."""
    hr_user_ids: set[int] = set()
    employee_ids: set[int] = set()

    if employee.team_id is not None:
        result = await db.execute(
            select(SupervisorTeamAssignment).where(SupervisorTeamAssignment.team_id == employee.team_id)
        )
        for assignment in result.scalars().all():
            if assignment.hr_user_id is not None:
                hr_user_ids.add(assignment.hr_user_id)
            if assignment.employee_id is not None:
                employee_ids.add(assignment.employee_id)

    if not hr_user_ids and not employee_ids:
        result = await db.execute(
            select(HrUser.id).where(HrUser.tenant_id == tenant_id, HrUser.role.in_(_FULL_HR_ROLES))
        )
        hr_user_ids = set(result.scalars().all())
        result = await db.execute(
            select(Employee.id).where(Employee.tenant_id == tenant_id, Employee.hr_role.in_(_FULL_HR_ROLES))
        )
        employee_ids = set(result.scalars().all())

    message = f"Neuer Antrag ({type_name}) von {employee.first_name} {employee.last_name} wartet auf Genehmigung."
    subject = f"Neuer Antrag: {type_name}"

    hr_emails = await _hr_user_emails(db, hr_user_ids)
    employee_emails = await _employee_emails(db, employee_ids)
    mail_config = await _notification_mail_config(db, tenant_id)

    for hr_user_id in hr_user_ids:
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_hr_user_id=hr_user_id,
                type=NotificationType.ABSENCE_REQUESTED,
                message=message,
            )
        )
        await _mail(mail_config, hr_emails.get(hr_user_id), subject, message)
    for employee_id in employee_ids:
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_employee_id=employee_id,
                type=NotificationType.ABSENCE_REQUESTED,
                message=message,
            )
        )
        await _mail(mail_config, employee_emails.get(employee_id), subject, message)


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
    subject = "Zu klären: offene Tage"
    mail_config = await _notification_mail_config(db, tenant_id)

    result = await db.execute(
        select(HrUser.id, HrUser.email).where(HrUser.tenant_id == tenant_id, HrUser.role.in_(_FULL_HR_ROLES))
    )
    for hr_user_id, email in result.all():
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_hr_user_id=hr_user_id,
                type=NotificationType.OPEN_DAYS_DIGEST,
                message=message,
            )
        )
        await _mail(mail_config, email, subject, message)
    result = await db.execute(
        select(Employee.id, Employee.login_email).where(
            Employee.tenant_id == tenant_id, Employee.hr_role.in_(_FULL_HR_ROLES)
        )
    )
    for employee_id, login_email in result.all():
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_employee_id=employee_id,
                type=NotificationType.OPEN_DAYS_DIGEST,
                message=message,
            )
        )
        await _mail(mail_config, login_email, subject, message)


async def notify_absence_decided(
    db: AsyncSession, tenant_id: int, absence: Absence, employee: Employee
) -> None:
    """Benachrichtigt den Antragsteller über die Entscheidung – nur wenn er
    überhaupt einen eigenen Login hat (login_email gesetzt), sonst gibt es
    niemanden, der die Benachrichtigung sehen könnte."""
    if employee.login_email is None:
        return

    status_label = "genehmigt" if absence.approval_status == AbsenceApprovalStatus.APPROVED else "abgelehnt"
    message = f"Dein Urlaubsantrag ({absence.date_from.isoformat()} – {absence.date_to.isoformat()}) wurde {status_label}."
    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_employee_id=employee.id,
            type=NotificationType.ABSENCE_DECIDED,
            message=message,
            related_absence_id=absence.id,
        )
    )
    await _mail(await _notification_mail_config(db, tenant_id), employee.login_email, "Urlaubsantrag entschieden", message)


async def notify_period_submitted(db: AsyncSession, tenant_id: int, employee: Employee, label: str) -> None:
    """Mitarbeiter soll den vorgelegten Monatsnachweis bestätigen – nur sinnvoll mit eigenem Login."""
    if employee.login_email is None:
        return
    message = f"Dein Monatsnachweis für {label} liegt zur Bestätigung bereit (Mein Bereich → Monatsabschluss)."
    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_employee_id=employee.id,
            type=NotificationType.PERIOD_SUBMITTED,
            message=message,
        )
    )
    await _mail(await _notification_mail_config(db, tenant_id), employee.login_email, "Monatsnachweis zur Bestätigung", message)


async def notify_period_disputed(db: AsyncSession, tenant_id: int, employee: Employee, label: str) -> None:
    """HR (Admin/HR, HrUser und Mitarbeiter mit hr_role) erfährt vom Widerspruch."""
    message = f"{employee.first_name} {employee.last_name} hat dem Monatsnachweis {label} widersprochen."
    subject = "Monatsnachweis beanstandet"
    mail_config = await _notification_mail_config(db, tenant_id)

    result = await db.execute(
        select(HrUser.id, HrUser.email).where(HrUser.tenant_id == tenant_id, HrUser.role.in_(_FULL_HR_ROLES))
    )
    for hr_user_id, email in result.all():
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_hr_user_id=hr_user_id,
                type=NotificationType.PERIOD_DISPUTED,
                message=message,
            )
        )
        await _mail(mail_config, email, subject, message)
    result = await db.execute(
        select(Employee.id, Employee.login_email).where(
            Employee.tenant_id == tenant_id, Employee.hr_role.in_(_FULL_HR_ROLES), Employee.id != employee.id
        )
    )
    for employee_id, login_email in result.all():
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_employee_id=employee_id,
                type=NotificationType.PERIOD_DISPUTED,
                message=message,
            )
        )
        await _mail(mail_config, login_email, subject, message)


async def _notify_full_hr(
    db: AsyncSession, tenant_id: int, type_: NotificationType, message: str, subject: str, exclude_employee_id: int
) -> None:
    """Glocke + Mail an alle Admin/HR (HrUser und Mitarbeiter mit hr_role)."""
    mail_config = await _notification_mail_config(db, tenant_id)
    result = await db.execute(
        select(HrUser.id, HrUser.email).where(HrUser.tenant_id == tenant_id, HrUser.role.in_(_FULL_HR_ROLES))
    )
    for hr_user_id, email in result.all():
        db.add(Notification(tenant_id=tenant_id, recipient_hr_user_id=hr_user_id, type=type_, message=message))
        await _mail(mail_config, email, subject, message)
    result = await db.execute(
        select(Employee.id, Employee.login_email).where(
            Employee.tenant_id == tenant_id, Employee.hr_role.in_(_FULL_HR_ROLES), Employee.id != exclude_employee_id
        )
    )
    for employee_id, login_email in result.all():
        db.add(Notification(tenant_id=tenant_id, recipient_employee_id=employee_id, type=type_, message=message))
        await _mail(mail_config, login_email, subject, message)


async def notify_correction_requested(db: AsyncSession, tenant_id: int, employee: Employee, work_date: date) -> None:
    message = (
        f"{employee.first_name} {employee.last_name} beantragt eine Zeitkorrektur für den "
        f"{work_date.strftime('%d.%m.%Y')} (Zu klären → Korrekturanträge)."
    )
    await _notify_full_hr(db, tenant_id, NotificationType.CORRECTION_REQUESTED, message, "Neuer Korrekturantrag", employee.id)


async def notify_correction_decided(
    db: AsyncSession, tenant_id: int, employee: Employee, work_date: date, approved: bool
) -> None:
    message = f"Dein Korrekturantrag für den {work_date.strftime('%d.%m.%Y')} wurde {'übernommen' if approved else 'abgelehnt'}."
    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_employee_id=employee.id,
            type=NotificationType.CORRECTION_DECIDED,
            message=message,
        )
    )
    await _mail(await _notification_mail_config(db, tenant_id), employee.login_email, "Korrekturantrag entschieden", message)
