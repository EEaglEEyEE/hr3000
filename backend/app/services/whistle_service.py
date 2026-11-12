"""Hinweisgebersystem: interne Meldestelle nach dem Hinweisgeberschutzgesetz (HinSchG).

Vertraulichkeit (§ 8 HinSchG)
- Meldungen sieht nur, wer als Meldestellen-Beauftragte:r benannt ist (whistle_officers) – nicht
  automatisch Admins oder HR, nie der Super-Admin. Alle anderen bekommen 404, auch für die Liste.
- Zur meldenden Person wird nichts gespeichert, was sie nicht selbst angegeben hat (keine IP-Adresse,
  kein Konto). Die öffentlichen Endpoints werten keinen Anmelde-Header aus und stehen nicht im
  Zugriffsprotokoll (main.SkipPublicAccessLog). Die Begrenzung von Fehlversuchen läuft nur flüchtig
  im Speicher (rate_limiter).
- Inhalte liegen verschlüsselt (secret_box / Dokumentenspeicher). Das Audit-Protokoll nennt nur
  „Meldung X angesehen/geändert“ mit dem Konto der Meldestelle, nie Inhalte, und diese Einträge
  erscheinen nicht im allgemeinen Audit-Protokoll der Firma (api/audit_log.py), nur am Vorgang.

Zugangscode
- 20 Zeichen aus 32 eindeutigen Zeichen = 100 Bit Zufall (secrets), serverseitig erzeugt, einmalig
  ausgegeben. Gespeichert wird nur SHA-256 über Firma, Vorgangsnummer und Code. Ein langsamer Hash
  (bcrypt) schützt schwache, von Menschen gewählte Passwörter; bei 100 Bit Zufall bringt er keinen
  Gewinn, wäre auf einem Endpoint ohne Anmeldung aber ein Hebel, den Server mit teuren Hash-Rechnungen
  zu belasten.
- Unbekannter Vorgang, Vorgang einer anderen Firma und falscher Code liefern dieselbe Antwort.

Fristen (§ 17 HinSchG)
- Eingangsbestätigung: 7 Tage nach Eingang. Rückmeldung: 3 Monate nach der Eingangsbestätigung –
  ohne Bestätigung 3 Monate nach Ablauf der 7 Tage. Gerechnet wird mit dem UTC-Datum des Eingangs
  (liegt nie nach dem deutschen Datum, die Frist endet also eher einen Tag zu früh als zu spät).

Aufbewahrung (§ 11 Abs. 5 HinSchG)
- Drei Jahre nach Abschluss ist ein Vorgang „zur Löschung fällig“. Gelöscht wird bewusst nicht
  automatisch, sondern durch die Meldestelle per Knopf (mit Erinnerung über die Glocke): Das Gesetz
  erlaubt eine längere Aufbewahrung, solange sie erforderlich ist – ein Hintergrundlauf kann das nicht
  beurteilen und würde unwiderruflich löschen. Vor dem Löschdatum lässt sich nichts löschen.
"""
import calendar
import hashlib
import hmac
import json
import secrets
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (
    Account,
    AuditAction,
    AuditLogEntry,
    Notification,
    NotificationType,
    WhistleAttachment,
    WhistleCase,
    WhistleMessage,
    WhistleMessageKind,
    WhistleOfficer,
    WhistleStatus,
)
from app.schemas.whistle import (
    WhistleAttachmentResponse,
    WhistleCaseDetail,
    WhistleCaseSummary,
    WhistleCaseUpdate,
    WhistleMessageResponse,
    WhistleOfficeMessageCreate,
    WhistleOfficerAccount,
    WhistleProtocolEntry,
    WhistlePublicAttachment,
    WhistlePublicCase,
    WhistlePublicMessage,
    WhistleReportCreate,
)
from app.services import rate_limiter
from app.services.audit_service import log_action
from app.services.document_service import (
    delete_document_file,
    read_document_bytes,
    sanitize_filename,
    save_document_bytes,
    sniff_content_type,
)
from app.services.notification_service import _mail, _notification_mail_config, _signed_in_accounts
from app.services.secret_box import decrypt_secret, encrypt_secret
from app.services.settings_service import get_or_create_settings

ENTITY_TYPE = "whistle_case"

# Ohne I, O, 0 und 1 – der Code wird abgeschrieben.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CASE_NUMBER_LENGTH = 8
ACCESS_CODE_LENGTH = 20

ACK_DAYS = 7
FEEDBACK_MONTHS = 3
RETENTION_YEARS = 3
ACK_WARN_DAYS = 2
FEEDBACK_WARN_DAYS = 14

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_CASE = 10
MAX_TENANT_ATTACHMENT_BYTES = 1024 * 1024 * 1024
MAX_REPORTER_MESSAGES_PER_CASE = 200

# Begrenzungen (nur im Speicher): Fehlversuche je IP und je Vorgang, neue Meldungen je IP und je Firma
ACCESS_WINDOW_SECONDS = 15 * 60
ACCESS_FAILURES_PER_IP = 10
ACCESS_FAILURES_PER_CASE = 5
REPORT_WINDOW_SECONDS = 3600
REPORTS_PER_IP = 5
REPORTS_PER_TENANT_PER_DAY = 100
MESSAGES_PER_CASE_PER_HOUR = 20
_DAY_SECONDS = 24 * 3600

STATUS_LABELS = {
    WhistleStatus.RECEIVED.value: "Eingegangen",
    WhistleStatus.IN_REVIEW.value: "In Prüfung",
    WhistleStatus.FEEDBACK_GIVEN.value: "Rückmeldung erteilt",
    WhistleStatus.CLOSED.value: "Abgeschlossen",
}
UNREADABLE = "(nicht lesbar)"
_INVALID_NUMBER = "H-INVALID"


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def today() -> date:
    return date.today()


# --- Fehler ----------------------------------------------------------------------------------


def not_found() -> AppError:
    """Eine Antwort für „aus“, „nicht benannt“, „fremde Firma“ und „gibt es nicht“."""
    return AppError(404, "NOT_FOUND", "Nicht gefunden.")


def invalid_access() -> AppError:
    return AppError(401, "WHISTLE_ACCESS_INVALID", "Vorgangsnummer oder Zugangscode stimmen nicht.")


# --- Zugangscode -----------------------------------------------------------------------------


def _random(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def generate_case_number() -> str:
    return "H-" + _random(CASE_NUMBER_LENGTH)


def generate_access_code() -> str:
    return _random(ACCESS_CODE_LENGTH)


def format_access_code(code: str) -> str:
    """In Fünfergruppen, damit sich der Code abschreiben lässt."""
    return "-".join(code[i : i + 5] for i in range(0, len(code), 5))


def hash_access_code(tenant_id: int, case_number: str, code: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{case_number}:{code}".encode("utf-8")).hexdigest()


# --- Fristen ---------------------------------------------------------------------------------


def add_months(day: date, months: int) -> date:
    """Kalendermonate; gibt es den Tag im Zielmonat nicht, gilt dessen letzter Tag (31.01. + 1 = 28./29.02.)."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def ack_due(case: WhistleCase) -> date:
    return case.received_at.date() + timedelta(days=ACK_DAYS)


def feedback_due(case: WhistleCase) -> date:
    start = case.acknowledged_at.date() if case.acknowledged_at is not None else ack_due(case)
    return add_months(start, FEEDBACK_MONTHS)


def deletion_date(closed_on: date) -> date:
    return add_months(closed_on, 12 * RETENTION_YEARS)


def _open(case: WhistleCase) -> bool:
    return case.status != WhistleStatus.CLOSED.value


def ack_overdue(case: WhistleCase, on: date) -> bool:
    return _open(case) and case.acknowledged_at is None and on > ack_due(case)


def feedback_overdue(case: WhistleCase, on: date) -> bool:
    return _open(case) and case.feedback_at is None and on > feedback_due(case)


def deletion_due(case: WhistleCase, on: date) -> bool:
    return not _open(case) and case.delete_after is not None and on >= case.delete_after


# --- Verschlüsselte Inhalte ------------------------------------------------------------------


def _decrypt(token: str | None) -> str | None:
    if token is None:
        return None
    plain = decrypt_secret(token)
    return UNREADABLE if plain is None else plain


def _details(case: WhistleCase) -> dict[str, str]:
    if case.details_encrypted is None:
        return {}
    plain = decrypt_secret(case.details_encrypted)
    if plain is None:
        return {}
    try:
        data = json.loads(plain)
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


# --- Schalter und Beauftragte ----------------------------------------------------------------


async def is_enabled(db: AsyncSession, tenant_id: int) -> bool:
    return bool((await get_or_create_settings(db, tenant_id)).whistleblowing_enabled)


async def is_officer(db: AsyncSession, tenant_id: int, account_id: int) -> bool:
    row = await db.scalar(
        select(WhistleOfficer.id).where(WhistleOfficer.tenant_id == tenant_id, WhistleOfficer.account_id == account_id)
    )
    return row is not None


async def officer_recipients(db: AsyncSession, tenant_id: int) -> list[tuple[int, str | None]]:
    """(Konto-ID, E-Mail) der Beauftragten, die sich anmelden können."""
    stmt = (
        _signed_in_accounts(tenant_id)
        .join(WhistleOfficer, WhistleOfficer.account_id == Account.id)
        .where(WhistleOfficer.tenant_id == tenant_id)
        .order_by(Account.id)
    )
    return [(account_id, email) for account_id, email in (await db.execute(stmt)).all()]


async def accepting_reports(db: AsyncSession, tenant_id: int) -> bool:
    """Neue Meldungen nur, wenn sie jemand lesen kann."""
    return bool(await officer_recipients(db, tenant_id))


def _officer_account(account: Account) -> WhistleOfficerAccount:
    return WhistleOfficerAccount(account_id=account.id, name=account.display_name, email=account.email)


async def list_officers(db: AsyncSession, tenant_id: int) -> tuple[list[WhistleOfficerAccount], list[WhistleOfficerAccount]]:
    """(benannte Konten, weitere Konten der Firma mit Zugang), je nach Name sortiert."""
    officer_ids = set(
        (await db.scalars(select(WhistleOfficer.account_id).where(WhistleOfficer.tenant_id == tenant_id))).all()
    )
    accounts = (await db.scalars(select(Account).where(Account.tenant_id == tenant_id))).all()
    officers = [_officer_account(a) for a in accounts if a.id in officer_ids]
    candidates = [_officer_account(a) for a in accounts if a.id not in officer_ids and a.has_login]
    key = lambda entry: entry.name.lower()  # noqa: E731
    return sorted(officers, key=key), sorted(candidates, key=key)


async def appoint_officer(db: AsyncSession, tenant_id: int, account_id: int, by_account_id: int | None) -> None:
    account = await db.scalar(select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id))
    if account is None:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Dieses Konto gibt es nicht.")
    if not account.has_login:
        raise AppError(400, "ACCOUNT_WITHOUT_LOGIN", "Dieses Konto hat keinen Zugang zur Webapp.")
    if await is_officer(db, tenant_id, account_id):
        raise AppError(409, "WHISTLE_OFFICER_EXISTS", "Dieses Konto ist bereits benannt.")
    db.add(
        WhistleOfficer(
            tenant_id=tenant_id, account_id=account_id, created_by_account_id=by_account_id, created_at=now_utc()
        )
    )
    log_action(
        db,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action=AuditAction.WHISTLE_OFFICER_CHANGED,
        entity_type="account",
        entity_id=account_id,
        detail=f"Als Meldestellen-Beauftragte:r benannt: {account.display_name}"[:500],
    )
    await db.commit()


async def dismiss_officer(db: AsyncSession, tenant_id: int, account_id: int, by_account_id: int | None) -> None:
    officer = await db.scalar(
        select(WhistleOfficer).where(WhistleOfficer.tenant_id == tenant_id, WhistleOfficer.account_id == account_id)
    )
    if officer is None:
        raise AppError(404, "WHISTLE_OFFICER_NOT_FOUND", "Dieses Konto ist nicht benannt.")
    account = await db.get(Account, account_id)
    await db.delete(officer)
    log_action(
        db,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action=AuditAction.WHISTLE_OFFICER_CHANGED,
        entity_type="account",
        entity_id=account_id,
        detail=f"Als Meldestellen-Beauftragte:r abberufen: {account.display_name if account else account_id}"[:500],
    )
    await db.commit()


# --- Benachrichtigungen ----------------------------------------------------------------------

_MAIL_SUBJECT = "HR3000: Hinweisgebersystem"
# Die E-Mail nennt bewusst weder Vorgang noch Inhalt – Postfächer lesen oft auch Vertretungen.
_MAIL_BODY = (
    "Im Hinweisgebersystem gibt es etwas Neues oder eine Frist steht an. "
    "Bitte melden Sie sich an und öffnen Sie den Menüpunkt „Hinweise“."
)


async def _notify_officers(db: AsyncSession, tenant_id: int, message: str) -> int:
    recipients = await officer_recipients(db, tenant_id)
    if not recipients:
        return 0
    mail_config = await _notification_mail_config(db, tenant_id)
    for account_id, email in recipients:
        db.add(
            Notification(
                tenant_id=tenant_id,
                recipient_account_id=account_id,
                type=NotificationType.WHISTLEBLOWING,
                message=message[:500],
            )
        )
        await _mail(mail_config, email, _MAIL_SUBJECT, _MAIL_BODY)
    return len(recipients)


# --- Meldende Person (ohne Konto) ------------------------------------------------------------


def check_report_limits(tenant_id: int, ip: str) -> None:
    rate_limiter.check_rate_limit(f"whistle-report-ip:{ip}", REPORTS_PER_IP, REPORT_WINDOW_SECONDS, code="TOO_MANY_REPORTS")
    rate_limiter.check_rate_limit(
        f"whistle-report-tenant:{tenant_id}", REPORTS_PER_TENANT_PER_DAY, _DAY_SECONDS, code="TOO_MANY_REPORTS"
    )


def count_report(tenant_id: int, ip: str) -> None:
    rate_limiter.record_failure(f"whistle-report-ip:{ip}")
    rate_limiter.record_failure(f"whistle-report-tenant:{tenant_id}")


async def create_report(db: AsyncSession, tenant_id: int, payload: WhistleReportCreate) -> tuple[WhistleCase, str]:
    """Legt die Meldung an und gibt sie mit dem Zugangscode im Klartext zurück (nur hier verfügbar)."""
    case_number = generate_case_number()
    while await db.scalar(
        select(WhistleCase.id).where(WhistleCase.tenant_id == tenant_id, WhistleCase.case_number == case_number)
    ):
        case_number = generate_case_number()
    code = generate_access_code()
    details = {
        key: value
        for key, value in (
            ("occurred_when", payload.occurred_when),
            ("occurred_where", payload.occurred_where),
            ("contact_name", payload.contact_name),
            ("contact_email", str(payload.contact_email) if payload.contact_email else None),
        )
        if value
    }
    case = WhistleCase(
        tenant_id=tenant_id,
        case_number=case_number,
        access_code_hash=hash_access_code(tenant_id, case_number, code),
        category=payload.category.value,
        status=WhistleStatus.RECEIVED.value,
        description_encrypted=encrypt_secret(payload.description),
        details_encrypted=encrypt_secret(json.dumps(details, ensure_ascii=False)) if details else None,
        anonymous=payload.anonymous,
        received_at=now_utc(),
        unread_for_office=True,
    )
    db.add(case)
    await _notify_officers(db, tenant_id, f"Hinweisgebersystem: Neue Meldung {case_number} eingegangen.")
    await db.commit()
    return case, code


async def verify_access(db: AsyncSession, tenant_id: int, ip: str, case_number: str, code: str) -> WhistleCase:
    """Prüft Vorgangsnummer und Code in dieser Firma. Fehlversuche zählen je IP und je Vorgang – auch für
    Nummern, die es nicht gibt, damit die Antwort nichts über deren Existenz verrät."""
    ip_key = f"whistle-access-ip:{ip}"
    case_key = f"whistle-access-case:{tenant_id}:{case_number}"
    counts_per_case = case_number != _INVALID_NUMBER
    rate_limiter.check_rate_limit(ip_key, ACCESS_FAILURES_PER_IP, ACCESS_WINDOW_SECONDS)
    if counts_per_case:
        rate_limiter.check_rate_limit(case_key, ACCESS_FAILURES_PER_CASE, ACCESS_WINDOW_SECONDS)
    case = await db.scalar(
        select(WhistleCase).where(WhistleCase.tenant_id == tenant_id, WhistleCase.case_number == case_number)
    )
    expected = case.access_code_hash if case is not None else "0" * 64
    matches = hmac.compare_digest(expected, hash_access_code(tenant_id, case_number, code))
    if case is None or not matches:
        rate_limiter.record_failure(ip_key)
        if counts_per_case:
            rate_limiter.record_failure(case_key)
        raise invalid_access()
    return case


async def _messages(db: AsyncSession, case: WhistleCase) -> list[WhistleMessage]:
    stmt = (
        select(WhistleMessage)
        .where(WhistleMessage.tenant_id == case.tenant_id, WhistleMessage.case_id == case.id)
        .order_by(WhistleMessage.created_at, WhistleMessage.id)
    )
    return list((await db.scalars(stmt)).all())


async def _attachments(db: AsyncSession, case: WhistleCase) -> list[WhistleAttachment]:
    stmt = (
        select(WhistleAttachment)
        .where(WhistleAttachment.tenant_id == case.tenant_id, WhistleAttachment.case_id == case.id)
        .order_by(WhistleAttachment.created_at, WhistleAttachment.id)
    )
    return list((await db.scalars(stmt)).all())


async def public_view(db: AsyncSession, case: WhistleCase) -> WhistlePublicCase:
    visible = (WhistleMessageKind.REPORTER.value, WhistleMessageKind.OFFICE.value)
    return WhistlePublicCase(
        case_number=case.case_number,
        category=case.category,
        status=case.status,
        description=_decrypt(case.description_encrypted),
        received_at=case.received_at,
        acknowledged_at=case.acknowledged_at,
        messages=[
            WhistlePublicMessage(
                from_office=m.kind == WhistleMessageKind.OFFICE.value,
                body=_decrypt(m.body_encrypted),
                created_at=m.created_at,
                mark=m.mark,
            )
            for m in await _messages(db, case)
            if m.kind in visible
        ],
        attachments=[
            WhistlePublicAttachment(filename=_decrypt(a.filename_encrypted), size_bytes=a.size_bytes, created_at=a.created_at)
            for a in await _attachments(db, case)
        ],
    )


async def _flag_unread(db: AsyncSession, case: WhistleCase, message: str) -> None:
    """Ungelesen-Marke setzen; die Glocke nur beim ersten neuen Eintrag seit dem letzten Öffnen."""
    if not case.unread_for_office:
        case.unread_for_office = True
        await _notify_officers(db, case.tenant_id, message)


async def add_reporter_message(db: AsyncSession, case: WhistleCase, body: str) -> None:
    key = f"whistle-message:{case.tenant_id}:{case.case_number}"
    rate_limiter.check_rate_limit(key, MESSAGES_PER_CASE_PER_HOUR, 3600, code="TOO_MANY_MESSAGES")
    count = await db.scalar(
        select(func.count()).select_from(WhistleMessage).where(
            WhistleMessage.tenant_id == case.tenant_id,
            WhistleMessage.case_id == case.id,
            WhistleMessage.kind == WhistleMessageKind.REPORTER.value,
        )
    )
    if count >= MAX_REPORTER_MESSAGES_PER_CASE:
        raise AppError(409, "WHISTLE_MESSAGE_LIMIT", "Zu diesem Vorgang sind keine weiteren Nachrichten möglich.")
    rate_limiter.record_failure(key)
    db.add(
        WhistleMessage(
            tenant_id=case.tenant_id,
            case_id=case.id,
            kind=WhistleMessageKind.REPORTER.value,
            body_encrypted=encrypt_secret(body),
            author_account_id=None,
            created_at=now_utc(),
        )
    )
    await _flag_unread(db, case, f"Hinweisgebersystem: Neue Nachricht zur Meldung {case.case_number}.")
    await db.commit()


async def add_attachment(db: AsyncSession, case: WhistleCase, filename: str | None, data: bytes) -> WhistleAttachment:
    if not data:
        raise AppError(400, "EMPTY_FILE", "Die Datei ist leer.")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", f"Die Datei ist größer als {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB.")
    # Nur der letzte Pfadteil, ohne Steuer- und Sonderzeichen; der Typ kommt aus dem Dateikopf.
    safe_name = sanitize_filename(filename)
    content_type = sniff_content_type(data, safe_name)
    if content_type is None:
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", "Erlaubt sind PDF, PNG, JPEG, DOCX und XLSX.")
    count = await db.scalar(
        select(func.count()).select_from(WhistleAttachment).where(
            WhistleAttachment.tenant_id == case.tenant_id, WhistleAttachment.case_id == case.id
        )
    )
    if count >= MAX_ATTACHMENTS_PER_CASE:
        raise AppError(409, "WHISTLE_ATTACHMENT_LIMIT", f"Je Vorgang sind höchstens {MAX_ATTACHMENTS_PER_CASE} Anhänge möglich.")
    used = await db.scalar(
        select(func.coalesce(func.sum(WhistleAttachment.size_bytes), 0)).where(WhistleAttachment.tenant_id == case.tenant_id)
    )
    if used + len(data) > MAX_TENANT_ATTACHMENT_BYTES:
        raise AppError(413, "DOCUMENT_QUOTA_EXCEEDED", "Derzeit können keine weiteren Dateien angenommen werden.")
    storage_key = await save_document_bytes(data)
    attachment = WhistleAttachment(
        tenant_id=case.tenant_id,
        case_id=case.id,
        filename_encrypted=encrypt_secret(safe_name),
        content_type=content_type,
        size_bytes=len(data),
        storage_key=storage_key,
        created_at=now_utc(),
    )
    db.add(attachment)
    try:
        await _flag_unread(db, case, f"Hinweisgebersystem: Neuer Anhang zur Meldung {case.case_number}.")
        await db.commit()
    except Exception:
        await delete_document_file(storage_key)
        raise
    return attachment


# --- Meldestelle -----------------------------------------------------------------------------


def _summary_fields(case: WhistleCase, on: date) -> dict:
    return dict(
        id=case.id,
        case_number=case.case_number,
        category=case.category,
        status=case.status,
        anonymous=case.anonymous,
        unread=case.unread_for_office,
        received_at=case.received_at,
        acknowledged_at=case.acknowledged_at,
        feedback_at=case.feedback_at,
        closed_at=case.closed_at,
        ack_due=ack_due(case),
        ack_overdue=ack_overdue(case, on),
        feedback_due=feedback_due(case),
        feedback_overdue=feedback_overdue(case, on),
        delete_after=case.delete_after,
        deletion_due=deletion_due(case, on),
    )


async def list_cases(db: AsyncSession, tenant_id: int) -> list[WhistleCaseSummary]:
    cases = (
        await db.scalars(
            select(WhistleCase).where(WhistleCase.tenant_id == tenant_id).order_by(WhistleCase.received_at.desc(), WhistleCase.id.desc())
        )
    ).all()
    on = today()
    return [WhistleCaseSummary(**_summary_fields(case, on)) for case in cases]


async def get_case(db: AsyncSession, tenant_id: int, case_id: int) -> WhistleCase:
    case = await db.scalar(select(WhistleCase).where(WhistleCase.id == case_id, WhistleCase.tenant_id == tenant_id))
    if case is None:
        raise not_found()
    return case


def _audit(db: AsyncSession, case: WhistleCase, account_id: int | None, action: AuditAction, what: str) -> None:
    """Nie Inhalte: nur Vorgangsnummer und was geschah."""
    log_action(
        db,
        tenant_id=case.tenant_id,
        actor_account_id=account_id,
        action=action,
        entity_type=ENTITY_TYPE,
        entity_id=case.id,
        detail=f"{case.case_number}: {what}",
    )


async def _labels(db: AsyncSession, tenant_id: int, account_ids: set[int]) -> dict[int, str]:
    if not account_ids:
        return {}
    accounts = (await db.scalars(select(Account).where(Account.tenant_id == tenant_id, Account.id.in_(account_ids)))).all()
    return {a.id: a.display_name for a in accounts}


async def case_detail(db: AsyncSession, case: WhistleCase) -> WhistleCaseDetail:
    messages = await _messages(db, case)
    attachments = await _attachments(db, case)
    # Die Vorgangsnummer im Detail grenzt ab, falls die Datenbank die ID eines gelöschten Vorgangs neu vergibt.
    entries = (
        await db.scalars(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.tenant_id == case.tenant_id,
                AuditLogEntry.entity_type == ENTITY_TYPE,
                AuditLogEntry.entity_id == case.id,
                AuditLogEntry.detail.like(f"{case.case_number}:%"),
            )
            .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
            .limit(200)
        )
    ).all()
    account_ids = {m.author_account_id for m in messages if m.author_account_id is not None}
    account_ids |= {e.actor_account_id for e in entries if e.actor_account_id is not None}
    labels = await _labels(db, case.tenant_id, account_ids)
    details = _details(case)
    prefix = len(case.case_number) + 2
    return WhistleCaseDetail(
        **_summary_fields(case, today()),
        description=_decrypt(case.description_encrypted),
        occurred_when=details.get("occurred_when"),
        occurred_where=details.get("occurred_where"),
        contact_name=details.get("contact_name"),
        contact_email=details.get("contact_email"),
        closing_note=_decrypt(case.closing_note_encrypted),
        messages=[
            WhistleMessageResponse(
                id=m.id,
                kind=m.kind,
                body=_decrypt(m.body_encrypted),
                mark=m.mark,
                author_label=None
                if m.kind == WhistleMessageKind.REPORTER.value
                else labels.get(m.author_account_id, "Meldestelle"),
                created_at=m.created_at,
            )
            for m in messages
        ],
        attachments=[
            WhistleAttachmentResponse(
                id=a.id,
                filename=_decrypt(a.filename_encrypted),
                content_type=a.content_type,
                size_bytes=a.size_bytes,
                created_at=a.created_at,
            )
            for a in attachments
        ],
        protocol=[
            WhistleProtocolEntry(
                action=e.action,
                actor_label=labels.get(e.actor_account_id, "Unbekannt") if e.actor_account_id is not None else "System",
                detail=(e.detail or "")[prefix:] or None,
                created_at=e.created_at,
            )
            for e in entries
        ],
    )


async def open_case(db: AsyncSession, case: WhistleCase, account_id: int) -> WhistleCaseDetail:
    """Ansehen durch die Meldestelle: protokolliert, Ungelesen-Marke entfällt."""
    case.unread_for_office = False
    _audit(db, case, account_id, AuditAction.WHISTLE_CASE_VIEWED, "angesehen")
    await db.commit()
    return await case_detail(db, case)


async def add_office_message(
    db: AsyncSession, case: WhistleCase, account_id: int, payload: WhistleOfficeMessageCreate
) -> WhistleCaseDetail:
    now = now_utc()
    if payload.kind == "NOTE":
        kind, what = WhistleMessageKind.NOTE.value, "interne Notiz ergänzt"
    else:
        kind, what = WhistleMessageKind.OFFICE.value, "Nachricht an die meldende Person"
    if payload.mark == "ACKNOWLEDGEMENT":
        if case.acknowledged_at is not None:
            raise AppError(409, "WHISTLE_ALREADY_ACKNOWLEDGED", "Der Eingang wurde bereits bestätigt.")
        case.acknowledged_at = now
        if case.status == WhistleStatus.RECEIVED.value:
            case.status = WhistleStatus.IN_REVIEW.value
        what = "Eingangsbestätigung gesendet"
    elif payload.mark == "FEEDBACK":
        if case.feedback_at is None:
            case.feedback_at = now
        if _open(case):
            case.status = WhistleStatus.FEEDBACK_GIVEN.value
        what = "Rückmeldung gesendet"
    db.add(
        WhistleMessage(
            tenant_id=case.tenant_id,
            case_id=case.id,
            kind=kind,
            body_encrypted=encrypt_secret(payload.body),
            mark=payload.mark,
            author_account_id=account_id,
            created_at=now,
        )
    )
    _audit(db, case, account_id, AuditAction.WHISTLE_CASE_CHANGED, what)
    await db.commit()
    return await case_detail(db, case)


async def update_case(
    db: AsyncSession, case: WhistleCase, account_id: int, payload: WhistleCaseUpdate
) -> WhistleCaseDetail:
    now = now_utc()
    new_status = payload.status.value
    was_closed = not _open(case)
    if new_status == case.status and not was_closed:
        return await case_detail(db, case)
    if was_closed and new_status != WhistleStatus.CLOSED.value:
        # Wieder geöffnet: der bisherige Abschlussvermerk bleibt als interne Notiz erhalten.
        previous = _decrypt(case.closing_note_encrypted)
        if previous:
            closed_on = case.closed_at.strftime("%d.%m.%Y") if case.closed_at else "?"
            db.add(
                WhistleMessage(
                    tenant_id=case.tenant_id,
                    case_id=case.id,
                    kind=WhistleMessageKind.NOTE.value,
                    body_encrypted=encrypt_secret(f"Abschlussvermerk vom {closed_on} (Vorgang wieder geöffnet):\n{previous}"),
                    author_account_id=account_id,
                    created_at=now,
                )
            )
        case.closed_at = None
        case.delete_after = None
        case.closing_note_encrypted = None
        case.deletion_reminded = False
    if new_status == WhistleStatus.CLOSED.value:
        if not was_closed:
            case.closed_at = now
            case.delete_after = deletion_date(now.date())
            case.deletion_reminded = False
        case.closing_note_encrypted = encrypt_secret(payload.closing_note)
    if new_status == WhistleStatus.FEEDBACK_GIVEN.value and case.feedback_at is None:
        case.feedback_at = now
    what = "Abschlussvermerk geändert" if was_closed and new_status == case.status else f"Status {STATUS_LABELS[new_status]}"
    case.status = new_status
    _audit(db, case, account_id, AuditAction.WHISTLE_CASE_CHANGED, what)
    await db.commit()
    return await case_detail(db, case)


async def read_attachment(
    db: AsyncSession, case: WhistleCase, attachment_id: int, account_id: int
) -> tuple[str, str, bytes]:
    """(Dateiname, Typ, Inhalt); der Abruf wird protokolliert."""
    attachment = await db.scalar(
        select(WhistleAttachment).where(
            WhistleAttachment.id == attachment_id,
            WhistleAttachment.case_id == case.id,
            WhistleAttachment.tenant_id == case.tenant_id,
        )
    )
    if attachment is None:
        raise not_found()
    data = await read_document_bytes(attachment.storage_key)
    if data is None:
        raise AppError(410, "DOCUMENT_FILE_MISSING", "Die Datei ist nicht mehr lesbar.")
    _audit(db, case, account_id, AuditAction.WHISTLE_CASE_VIEWED, "Anhang heruntergeladen")
    await db.commit()
    return sanitize_filename(decrypt_secret(attachment.filename_encrypted)), attachment.content_type, data


async def delete_case(db: AsyncSession, case: WhistleCase, account_id: int) -> None:
    """Endgültig löschen – nur abgeschlossene Vorgänge ab dem Löschdatum."""
    if not deletion_due(case, today()):
        raise AppError(
            409, "WHISTLE_RETENTION_ACTIVE", "Der Vorgang lässt sich erst ab dem Löschdatum löschen (drei Jahre nach Abschluss)."
        )
    storage_keys = [a.storage_key for a in await _attachments(db, case)]
    _audit(db, case, account_id, AuditAction.WHISTLE_CASE_DELETED, "gelöscht")
    scope = lambda model: (model.tenant_id == case.tenant_id, model.case_id == case.id)  # noqa: E731
    await db.execute(delete(WhistleAttachment).where(*scope(WhistleAttachment)))
    await db.execute(delete(WhistleMessage).where(*scope(WhistleMessage)))
    await db.delete(case)
    await db.commit()
    # Dateien erst nach dem Commit: scheitert die DB, bleiben sie lieber liegen als umgekehrt.
    for key in storage_keys:
        await delete_document_file(key)


# --- Erinnerungen (Hintergrundlauf) ----------------------------------------------------------


def _fmt(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def due_reminders(case: WhistleCase, on: date) -> list[str]:
    """Heute fällige Erinnerungen dieses Vorgangs; setzt die Stufen, damit jede nur einmal kommt."""
    messages: list[str] = []
    label = f"Hinweisgebersystem: Meldung {case.case_number}"
    if _open(case) and case.acknowledged_at is None:
        due = ack_due(case)
        if on > due and case.ack_reminder_stage < 2:
            case.ack_reminder_stage = 2
            messages.append(f"{label} – die Eingangsbestätigung ist seit {_fmt(due)} überfällig.")
        elif on >= due - timedelta(days=ACK_WARN_DAYS) and case.ack_reminder_stage < 1:
            case.ack_reminder_stage = 1
            messages.append(f"{label} – die Eingangsbestätigung ist bis {_fmt(due)} fällig.")
    if _open(case) and case.feedback_at is None:
        due = feedback_due(case)
        if on > due and case.feedback_reminder_stage < 2:
            case.feedback_reminder_stage = 2
            messages.append(f"{label} – die Rückmeldung ist seit {_fmt(due)} überfällig.")
        elif on >= due - timedelta(days=FEEDBACK_WARN_DAYS) and case.feedback_reminder_stage < 1:
            case.feedback_reminder_stage = 1
            messages.append(f"{label} – die Rückmeldung ist bis {_fmt(due)} fällig.")
    if deletion_due(case, on) and not case.deletion_reminded:
        case.deletion_reminded = True
        messages.append(f"{label} ist seit {_fmt(case.delete_after)} zur Löschung fällig.")
    return messages


async def send_whistle_reminders(db: AsyncSession, tenant_id: int, on: date) -> int:
    """Fristen-Erinnerungen an die Beauftragten (Glocke, dazu eine neutrale E-Mail). Unabhängig vom
    Schalter „Erinnerungen“, aber nur bei eingeschaltetem Hinweisgebersystem. Ohne benannte Beauftragte
    bleibt alles offen, damit die Erinnerung nach der Benennung noch kommt. Committet selbst."""
    if not await is_enabled(db, tenant_id):
        return 0
    if not await officer_recipients(db, tenant_id):
        return 0
    cases = (await db.scalars(select(WhistleCase).where(WhistleCase.tenant_id == tenant_id))).all()
    sent = 0
    for case in cases:
        for message in due_reminders(case, on):
            sent += await _notify_officers(db, tenant_id, message)
    await db.commit()
    return sent
