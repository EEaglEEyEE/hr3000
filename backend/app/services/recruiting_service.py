"""Recruiting: Regeln und Abläufe für Stellen und Bewerbungen.

- Sichtbarkeit: Admin/HR sehen alles; alle anderen Konten nur Stellen, in deren Hiring Team sie
  stehen (``visible_job_ids``). Aufrufer antworten sonst mit 404.
- Karriereseite: öffentlich ist eine Stelle nur veröffentlicht und bis einschließlich
  Bewerbungsschluss (``is_public``).
- Anhänge: nur PDF, PNG und JPEG (Prüfung am Dateikopf), verschlüsselt abgelegt wie Dokumente der
  Personalakte (``document_service``).
- Löschfristen: Abgelehnte und zurückgezogene Bewerbungen werden nach der Frist der Firma gelöscht
  (``purge_due_applications``, täglicher Hintergrundlauf). Übrig bleibt eine anonyme Zählung je
  Stelle und Phase (``RecruitingStat``).
"""
import calendar
import logging
import re
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.models import (
    Account,
    AppSettings,
    AuditAction,
    Employee,
    NotificationType,
    RecruitingApplication,
    RecruitingAttachment,
    RecruitingJob,
    RecruitingJobMember,
    RecruitingNote,
    RecruitingRating,
    RecruitingStageEvent,
    RecruitingStat,
)
from app.models.recruiting import CLOSED_STAGES, JOB_PUBLISHED, STAGE_HIRED
from app.services import document_service
from app.services.audit_service import log_action
from app.services.email_service import resolve_smtp_config, send_email
from app.services.notification_service import _notify_accounts, _signed_in_accounts, full_hr_recipients
from app.services.secret_box import decrypt_secret, encrypt_secret
from app.services.settings_service import get_or_create_settings

logger = logging.getLogger(__name__)

# Anhänge je Bewerbung und Größe je Datei
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ("application/pdf", "image/png", "image/jpeg")

EMPLOYMENT_TYPE_LABELS = {
    "FULL_TIME": "Vollzeit",
    "PART_TIME": "Teilzeit",
    "MINI_JOB": "Minijob",
    "FIXED_TERM": "Befristet",
    "APPRENTICESHIP": "Ausbildung",
    "INTERNSHIP": "Praktikum",
    "WORKING_STUDENT": "Werkstudent",
    "FREELANCE": "Freie Mitarbeit",
}
STAGE_LABELS = {
    "NEW": "Neu",
    "SCREENING": "Sichtung",
    "INTERVIEW": "Interview",
    "OFFER": "Angebot",
    "HIRED": "Eingestellt",
    "REJECTED": "Abgelehnt",
    "WITHDRAWN": "Zurückgezogen",
}

_SLUG_REPLACEMENTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def now() -> datetime:
    """Jetzt (UTC, ohne Zeitzone – wie die übrigen Zeitstempel in der Datenbank)."""
    return datetime.now(UTC).replace(tzinfo=None)


def max_attachment_bytes() -> int:
    return min(MAX_ATTACHMENT_BYTES, settings.max_document_bytes)


def slugify(title: str) -> str:
    """Lesbarer Teil der Adresse einer Stelle (``/karriere/12-sachbearbeiter-in``)."""
    lowered = title.lower()
    for source, target in _SLUG_REPLACEMENTS.items():
        lowered = lowered.replace(source, target)
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:80].strip("-") or "stelle"


def is_public(job: RecruitingJob, today: date) -> bool:
    return job.status == JOB_PUBLISHED and (job.application_deadline is None or job.application_deadline >= today)


def encrypt_text(value: str | None) -> str | None:
    return encrypt_secret(value) if value else None


def decrypt_text(value: str | None) -> str | None:
    return decrypt_secret(value) if value else None


def add_months(day: date, months: int) -> date:
    """Kalendermonate addieren; den Tag bei kürzeren Monaten auf den Monatsletzten kürzen."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def delete_on(application: RecruitingApplication, settings_row: AppSettings) -> date | None:
    """Tag, ab dem die Bewerbung gelöscht wird: Abschluss (abgelehnt/zurückgezogen) plus Frist der
    Firma, im Talentpool die verlängerte Frist. Laufende und eingestellte Bewerbungen: nie."""
    if application.stage not in CLOSED_STAGES or application.closed_at is None:
        return None
    months = settings_row.recruiting_talent_pool_months if application.talent_pool else settings_row.recruiting_retention_months
    return add_months(application.closed_at.date(), months)


def account_name(account: Account | None, employee: Employee | None) -> str | None:
    if employee is not None:
        return f"{employee.first_name} {employee.last_name}"
    if account is not None:
        return account.email or "Entferntes Konto"
    return None


async def account_names(db: AsyncSession, tenant_id: int, account_ids: set[int]) -> dict[int, str]:
    """Anzeigenamen der Konten (Mitarbeitername, sonst E-Mail)."""
    if not account_ids:
        return {}
    rows = (
        await db.execute(
            select(Account, Employee)
            .outerjoin(Employee, Employee.id == Account.employee_id)
            .where(Account.tenant_id == tenant_id, Account.id.in_(account_ids))
        )
    ).all()
    return {account.id: account_name(account, employee) or "" for account, employee in rows}


# --- Sichtbarkeit ----------------------------------------------------------------------------


async def member_job_ids(db: AsyncSession, tenant_id: int, account_id: int) -> set[int]:
    return set(
        (
            await db.scalars(
                select(RecruitingJobMember.job_id).where(
                    RecruitingJobMember.tenant_id == tenant_id, RecruitingJobMember.account_id == account_id
                )
            )
        ).all()
    )


async def visible_job_ids(db: AsyncSession, actor) -> set[int] | None:
    """None = alle Stellen der Firma (Admin/HR); sonst die Stellen, in deren Hiring Team das Konto steht."""
    if actor.is_full_hr_level:
        return None
    return await member_job_ids(db, actor.tenant_id, actor.account_id)


async def team_candidates(db: AsyncSession, tenant_id: int) -> list[tuple[Account, Employee | None]]:
    """Konten der Firma, die sich anmelden können – nur sie können ins Hiring Team."""
    ids = [account_id for account_id, _ in (await db.execute(_signed_in_accounts(tenant_id))).all()]
    if not ids:
        return []
    rows = (
        await db.execute(
            select(Account, Employee)
            .outerjoin(Employee, Employee.id == Account.employee_id)
            .where(Account.tenant_id == tenant_id, Account.id.in_(ids))
            .order_by(Account.id)
        )
    ).all()
    return [(account, employee) for account, employee in rows]


async def set_members(db: AsyncSession, job: RecruitingJob, account_ids: list[int]) -> bool:
    """Setzt das Hiring Team; True, wenn sich etwas geändert hat. Nur Konten der Firma mit Zugang."""
    allowed = {account.id for account, _ in await team_candidates(db, job.tenant_id)}
    current = set(
        (await db.scalars(select(RecruitingJobMember.account_id).where(RecruitingJobMember.job_id == job.id))).all()
    )
    wanted = set(account_ids)
    # Wer schon im Team steht, darf bleiben, auch wenn der Zugang inzwischen entfernt wurde.
    if not wanted - current <= allowed:
        raise AppError(400, "RECRUITING_MEMBER_INVALID", "Ins Hiring Team können nur Konten dieser Firma mit Zugang.")
    if wanted == current:
        return False
    if current - wanted:
        await db.execute(
            delete(RecruitingJobMember).where(
                RecruitingJobMember.job_id == job.id, RecruitingJobMember.account_id.in_(current - wanted)
            )
        )
    for account_id in sorted(wanted - current):
        db.add(RecruitingJobMember(tenant_id=job.tenant_id, job_id=job.id, account_id=account_id))
    return True


# --- Anhänge ---------------------------------------------------------------------------------


def check_attachment(data: bytes, filename: str) -> str:
    """Prüft Größe und Typ (am Dateikopf) und gibt den erkannten Typ zurück."""
    if not data:
        raise AppError(400, "EMPTY_FILE", "Die Datei ist leer.")
    limit = max_attachment_bytes()
    if len(data) > limit:
        raise AppError(413, "DOCUMENT_TOO_LARGE", f"Die Datei ist größer als {limit // (1024 * 1024)} MB.")
    detected = document_service.sniff_content_type(data, filename)
    if detected not in ALLOWED_CONTENT_TYPES:
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", "Erlaubt sind nur PDF, PNG und JPEG.")
    return detected


async def attachment_count(db: AsyncSession, application_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(RecruitingAttachment).where(RecruitingAttachment.application_id == application_id)
    ) or 0


async def add_attachment(
    db: AsyncSession, application: RecruitingApplication, data: bytes, filename: str, kind: str, content_type: str | None = None
) -> RecruitingAttachment:
    """Legt einen (bereits geprüften oder hier zu prüfenden) Anhang verschlüsselt ab; committet nicht."""
    detected = content_type or check_attachment(data, filename)
    await document_service.ensure_tenant_quota(db, application.tenant_id, len(data))
    storage_key = await document_service.save_document_bytes(data)
    attachment = RecruitingAttachment(
        tenant_id=application.tenant_id,
        application_id=application.id,
        kind=kind,
        original_filename=document_service.sanitize_filename(filename),
        content_type=detected,
        size_bytes=len(data),
        sha256=document_service.sha256_hex(data),
        storage_key=storage_key,
    )
    db.add(attachment)
    return attachment


async def attachment_storage_keys(db: AsyncSession, tenant_id: int) -> list[str]:
    """Alle Dateien der Firma (für die endgültige Löschung einer Firma)."""
    return list(
        (await db.scalars(select(RecruitingAttachment.storage_key).where(RecruitingAttachment.tenant_id == tenant_id))).all()
    )


# --- Phasen ----------------------------------------------------------------------------------


def record_stage(db: AsyncSession, application: RecruitingApplication, from_stage: str | None, account_id: int | None) -> None:
    db.add(
        RecruitingStageEvent(
            tenant_id=application.tenant_id, application_id=application.id, from_stage=from_stage,
            to_stage=application.stage, account_id=account_id, created_at=now(),
        )
    )


def change_stage(
    db: AsyncSession,
    application: RecruitingApplication,
    stage: str,
    account_id: int | None,
    rejection_reason: str | None = None,
    rejection_note: str | None = None,
) -> bool:
    """Phasenwechsel mit Verlauf; True, wenn sich die Phase geändert hat. Abschluss (abgelehnt/
    zurückgezogen) startet die Löschfrist, das Wiederaufnehmen setzt sie zurück."""
    if application.employee_id is not None and stage != STAGE_HIRED:
        raise AppError(409, "RECRUITING_ALREADY_HIRED", "Die Bewerbung wurde bereits als Mitarbeiter übernommen.")
    previous = application.stage
    changed = previous != stage
    application.stage = stage
    if stage in CLOSED_STAGES:
        if changed or application.closed_at is None:
            application.closed_at = now()
        application.rejection_reason = rejection_reason
        application.rejection_note = rejection_note or None
    else:
        application.closed_at = None
        application.rejection_reason = None
        application.rejection_note = None
    if changed:
        record_stage(db, application, previous, account_id)
    return changed


# --- Löschen ---------------------------------------------------------------------------------


async def _count_deleted(db: AsyncSession, application: RecruitingApplication) -> None:
    stat = (
        await db.execute(
            select(RecruitingStat).where(
                RecruitingStat.job_id == application.job_id, RecruitingStat.stage == application.stage
            )
        )
    ).scalar_one_or_none()
    if stat is None:
        stat = RecruitingStat(tenant_id=application.tenant_id, job_id=application.job_id, stage=application.stage, count=0)
        db.add(stat)
    stat.count += 1


async def delete_application(
    db: AsyncSession, application: RecruitingApplication, *, actor_account_id: int | None, detail: str
) -> list[str]:
    """Löscht eine Bewerbung mit Notizen, Bewertungen, Verlauf und Anhängen; übrig bleibt die anonyme
    Zählung je Stelle und Phase. Gibt die Schlüssel der Dateien zurück – der Aufrufer löscht sie nach
    dem Commit (``delete_files``). Das Audit-Protokoll nennt keine Inhalte. Committet nicht."""
    await _count_deleted(db, application)
    keys = list(
        (
            await db.scalars(
                select(RecruitingAttachment.storage_key).where(RecruitingAttachment.application_id == application.id)
            )
        ).all()
    )
    for model in (RecruitingAttachment, RecruitingNote, RecruitingRating, RecruitingStageEvent):
        await db.execute(delete(model).where(model.application_id == application.id))
    log_action(
        db, tenant_id=application.tenant_id, actor_account_id=actor_account_id, action=AuditAction.RECRUITING_DELETED,
        entity_type="recruiting_application", entity_id=application.id,
        detail=f"{detail} (Stelle {application.job_id}, Phase {application.stage}, {len(keys)} Anhänge)",
    )
    await db.delete(application)
    return keys


async def delete_files(keys: list[str]) -> None:
    for key in keys:
        await document_service.delete_document_file(key)


async def due_applications(
    db: AsyncSession, tenant_id: int, until: date, job_ids: set[int] | None = None
) -> list[tuple[RecruitingApplication, date]]:
    """Abgeschlossene Bewerbungen, deren Löschtag bis ``until`` (einschließlich) erreicht ist,
    aufsteigend nach Löschtag."""
    settings_row = await get_or_create_settings(db, tenant_id)
    stmt = select(RecruitingApplication).where(
        RecruitingApplication.tenant_id == tenant_id,
        RecruitingApplication.stage.in_(CLOSED_STAGES),
        RecruitingApplication.closed_at.is_not(None),
    )
    if job_ids is not None:
        stmt = stmt.where(RecruitingApplication.job_id.in_(job_ids or {0}))
    result = []
    for application in (await db.execute(stmt.order_by(RecruitingApplication.id))).scalars().all():
        day = delete_on(application, settings_row)
        if day is not None and day <= until:
            result.append((application, day))
    return sorted(result, key=lambda item: (item[1], item[0].id))


async def purge_due_applications(db: AsyncSession, tenant_id: int, today: date) -> int:
    """Hintergrundlauf: löscht alle Bewerbungen der Firma, deren Löschfrist abgelaufen ist – auch wenn
    Recruiting inzwischen ausgeschaltet ist (die Frist gilt weiter). Committet selbst."""
    due = await due_applications(db, tenant_id, today)
    if not due:
        return 0
    keys: list[str] = []
    for application, _ in due:
        keys += await delete_application(db, application, actor_account_id=None, detail="Löschfrist abgelaufen")
    await db.commit()
    await delete_files(keys)
    logger.info("Recruiting: %s Bewerbung(en) der Firma %s nach Ablauf der Löschfrist gelöscht", len(due), tenant_id)
    return len(due)


# --- Benachrichtigungen ----------------------------------------------------------------------


async def notify_new_application(db: AsyncSession, job: RecruitingJob) -> int:
    """Glocke (und E-Mail, wenn eingerichtet) an das Hiring Team; ohne Team an Admin/HR. Der Text
    nennt nur die Stelle, keine Bewerberdaten. Gibt die Zahl der Empfänger zurück."""
    member_ids = set(
        (await db.scalars(select(RecruitingJobMember.account_id).where(RecruitingJobMember.job_id == job.id))).all()
    )
    recipients = [
        (account_id, email)
        for account_id, email in (await db.execute(_signed_in_accounts(job.tenant_id).order_by(Account.id))).all()
        if account_id in member_ids
    ]
    if not recipients:
        recipients = await full_hr_recipients(db, job.tenant_id)
    message = f"Neue Bewerbung für „{job.title}“."[:500]
    await _notify_accounts(db, job.tenant_id, recipients, NotificationType.RECRUITING_APPLICATION, message, "Neue Bewerbung")
    return len(recipients)


async def send_confirmation(db: AsyncSession, tenant_id: int, company_name: str, to: str, first_name: str, job_title: str) -> bool:
    """Eingangsbestätigung an die Bewerberin/den Bewerber über den Mailversand der Firma – nur wenn
    einer eingerichtet ist; ein Fehler blockiert die Bewerbung nie."""
    try:
        config = await resolve_smtp_config(db, tenant_id)
        if config is None:
            return False
        body = (
            f"Guten Tag {first_name},\n\n"
            f"vielen Dank für Ihre Bewerbung als „{job_title}“ bei {company_name}. "
            "Wir haben Ihre Unterlagen erhalten und melden uns bei Ihnen.\n\n"
            f"Freundliche Grüße\n{company_name}\n"
        )
        return await send_email(to, f"Ihre Bewerbung bei {company_name}", body, config=config)
    except Exception:
        logger.exception("Eingangsbestätigung für eine Bewerbung konnte nicht verschickt werden.")
        return False
