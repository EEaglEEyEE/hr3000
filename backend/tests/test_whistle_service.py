"""Hinweisgebersystem – Bausteine des Service (app/services/whistle_service.py) und Schemas:
Fristen, Zugangscode, Erinnerungen, Entschlüsselung, Löschung der Firma, Migration."""
import asyncio
import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Notification, NotificationType, WhistleAttachment, WhistleCase
from app.schemas.whistle import WhistleAccess, WhistleCaseUpdate, WhistleOfficeMessageCreate, WhistleReportCreate
from app.services import reminder_service, whistle_service as ws
from app.services.secret_box import encrypt_secret
from app.services.tenant_lifecycle import purge_tenant
from tests.whistle_helpers import OTHER, PDF, access, company, other_company, report, set_enabled


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


def _case(received: datetime, **fields) -> WhistleCase:
    defaults = dict(status="RECEIVED", acknowledged_at=None, feedback_at=None, closed_at=None, delete_after=None,
                    ack_reminder_stage=0, feedback_reminder_stage=0, deletion_reminded=False, case_number="H-AAAAAAAA")
    return WhistleCase(received_at=received, **{**defaults, **fields})


# --- Kalendermonate und Fristen --------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 15), 3, date(2026, 4, 15)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2027, 11, 30), 3, date(2028, 2, 29)),  # Schaltjahr
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)),
        (date(2028, 2, 29), 36, date(2031, 2, 28)),
        (date(2026, 5, 31), 0, date(2026, 5, 31)),
    ],
)
def test_add_months(start: date, months: int, expected: date) -> None:
    assert ws.add_months(start, months) == expected


def test_deadlines_without_acknowledgement() -> None:
    case = _case(datetime(2026, 11, 10, 23, 30))
    assert ws.ack_due(case) == date(2026, 11, 17)
    # ohne Bestätigung: drei Monate nach Ablauf der sieben Tage
    assert ws.feedback_due(case) == date(2027, 2, 17)


def test_feedback_deadline_runs_from_acknowledgement() -> None:
    case = _case(datetime(2026, 11, 10), acknowledged_at=datetime(2026, 11, 12, 8, 0))
    assert ws.feedback_due(case) == date(2027, 2, 12)


def test_overdue_boundaries() -> None:
    case = _case(datetime(2026, 11, 10))
    assert ws.ack_overdue(case, date(2026, 11, 17)) is False  # am Fälligkeitstag noch nicht
    assert ws.ack_overdue(case, date(2026, 11, 18)) is True
    assert ws.feedback_overdue(case, date(2027, 2, 17)) is False
    assert ws.feedback_overdue(case, date(2027, 2, 18)) is True


def test_done_or_closed_is_never_overdue() -> None:
    late = date(2030, 1, 1)
    assert ws.ack_overdue(_case(datetime(2026, 1, 1), acknowledged_at=datetime(2026, 1, 2)), late) is False
    assert ws.feedback_overdue(_case(datetime(2026, 1, 1), feedback_at=datetime(2026, 3, 1)), late) is False
    closed = _case(datetime(2026, 1, 1), status="CLOSED")
    assert ws.ack_overdue(closed, late) is False and ws.feedback_overdue(closed, late) is False


def test_deletion_due() -> None:
    closed = _case(datetime(2026, 1, 1), status="CLOSED", closed_at=datetime(2026, 2, 1), delete_after=date(2029, 2, 1))
    assert ws.deletion_due(closed, date(2029, 1, 31)) is False
    assert ws.deletion_due(closed, date(2029, 2, 1)) is True
    assert ws.deletion_due(_case(datetime(2026, 1, 1), delete_after=date(2020, 1, 1)), date(2030, 1, 1)) is False  # offen
    assert ws.deletion_due(_case(datetime(2026, 1, 1), status="CLOSED"), date(2030, 1, 1)) is False  # ohne Datum
    assert ws.deletion_date(date(2026, 11, 10)) == date(2029, 11, 10)


# --- Zugangscode -----------------------------------------------------------------------------


def test_generated_numbers_and_codes() -> None:
    codes = {ws.generate_access_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(len(c) == 20 and set(c) <= set(ws.ALPHABET) for c in codes)
    assert not set("IO01") & set(ws.ALPHABET) and len(ws.ALPHABET) == 32  # 5 Bit je Zeichen = 100 Bit
    number = ws.generate_case_number()
    assert number.startswith("H-") and len(number) == 10


def test_format_and_hash() -> None:
    assert ws.format_access_code("ABCDEFGHJKLMNPQRSTUV") == "ABCDE-FGHJK-LMNPQ-RSTUV"
    first = ws.hash_access_code(1, "H-AAAAAAAA", "X" * 20)
    assert len(first) == 64 and first == ws.hash_access_code(1, "H-AAAAAAAA", "X" * 20)
    assert first != ws.hash_access_code(2, "H-AAAAAAAA", "X" * 20)
    assert first != ws.hash_access_code(1, "H-AAAAAAAB", "X" * 20)


@pytest.mark.parametrize(
    ("number", "code", "expected"),
    [
        ("h-abcdefgh", "abcde-fghjk-lmnpq-rstuv", ("H-ABCDEFGH", "ABCDEFGHJKLMNPQRSTUV")),
        (" H-ABCD EFGH ", "ABCDE FGHJK LMNPQ RSTUV", ("H-ABCDEFGH", "ABCDEFGHJKLMNPQRSTUV")),
        ("H-ABCDEFG1", "ABCDEFGHJKLMNPQRSTU", ("H-INVALID", "INVALID")),
        ("12345678", "ABCDEFGHJKLMNPQRSTUVW", ("H-INVALID", "INVALID")),
    ],
)
def test_access_normalization(number: str, code: str, expected: tuple[str, str]) -> None:
    parsed = WhistleAccess(case_number=number, access_code=code)
    assert (parsed.case_number, parsed.access_code) == expected


# --- Schemas ---------------------------------------------------------------------------------


def test_report_schema_cleans_text() -> None:
    parsed = WhistleReportCreate(
        category="SAFETY", description="  Zeile\r\neins\x00 und zwei  ", occurred_when="  gestern\n  abend ",
        anonymous=False, contact_email=" hanna@example.com ",
    )
    assert parsed.description == "Zeile\neins und zwei"
    assert parsed.occurred_when == "gestern abend" and parsed.contact_email == "hanna@example.com"
    blank = WhistleReportCreate(category="OTHER", description="x" * 10, contact_email="  ", occurred_where="   ")
    assert blank.contact_email is None and blank.occurred_where is None


def test_office_schemas() -> None:
    with pytest.raises(ValidationError):
        WhistleOfficeMessageCreate(kind="NOTE", body="x", mark="FEEDBACK")
    assert WhistleOfficeMessageCreate(kind="MESSAGE", body=" x ", mark="FEEDBACK").body == "x"
    with pytest.raises(ValidationError):
        WhistleCaseUpdate(status="CLOSED", closing_note="   ")
    assert WhistleCaseUpdate(status="CLOSED", closing_note=" Fertig ").closing_note == "Fertig"


# --- Entschlüsselung -------------------------------------------------------------------------


def test_unreadable_content_is_marked() -> None:
    assert ws._decrypt(None) is None
    assert ws._decrypt("kein-token") == ws.UNREADABLE
    assert ws._details(_case(datetime(2026, 1, 1), details_encrypted=None)) == {}
    assert ws._details(_case(datetime(2026, 1, 1), details_encrypted="kaputt")) == {}
    assert ws._details(_case(datetime(2026, 1, 1), details_encrypted=encrypt_secret("kein json"))) == {}
    assert ws._details(_case(datetime(2026, 1, 1), details_encrypted=encrypt_secret("[1]"))) == {}
    assert ws._details(_case(datetime(2026, 1, 1), details_encrypted=encrypt_secret('{"a": "b", "c": 1}'))) == {"a": "b"}


# --- Erinnerungen ----------------------------------------------------------------------------


def test_due_reminders_stages() -> None:
    case = _case(datetime(2026, 11, 10))  # Bestätigung bis 17.11., Rückmeldung bis 17.02.2027
    assert ws.due_reminders(case, date(2026, 11, 14)) == []
    warn = ws.due_reminders(case, date(2026, 11, 15))
    assert len(warn) == 1 and "Eingangsbestätigung ist bis 17.11.2026 fällig" in warn[0]
    assert ws.due_reminders(case, date(2026, 11, 16)) == []
    late = ws.due_reminders(case, date(2026, 11, 18))
    assert len(late) == 1 and "seit 17.11.2026 überfällig" in late[0]
    assert ws.due_reminders(case, date(2026, 11, 25)) == []

    assert ws.due_reminders(case, date(2027, 2, 2)) == []
    feedback_warn = ws.due_reminders(case, date(2027, 2, 3))
    assert feedback_warn == ["Hinweisgebersystem: Meldung H-AAAAAAAA – die Rückmeldung ist bis 17.02.2027 fällig."]
    assert "überfällig" in ws.due_reminders(case, date(2027, 2, 18))[0]
    assert ws.due_reminders(case, date(2027, 3, 1)) == []


def test_late_first_run_sends_only_the_overdue_reminder() -> None:
    case = _case(datetime(2026, 1, 1))
    messages = ws.due_reminders(case, date(2026, 6, 1))
    assert len(messages) == 2 and all("überfällig" in m for m in messages)
    assert case.ack_reminder_stage == 2 and case.feedback_reminder_stage == 2


def test_no_deadline_reminders_for_done_cases_but_deletion_reminder() -> None:
    done = _case(datetime(2026, 1, 1), acknowledged_at=datetime(2026, 1, 2), feedback_at=datetime(2026, 2, 1))
    assert ws.due_reminders(done, date(2027, 1, 1)) == []
    closed = _case(datetime(2026, 1, 1), status="CLOSED", closed_at=datetime(2026, 2, 1), delete_after=date(2029, 2, 1))
    assert ws.due_reminders(closed, date(2029, 1, 31)) == []
    message = ws.due_reminders(closed, date(2029, 2, 1))
    assert message == ["Hinweisgebersystem: Meldung H-AAAAAAAA ist seit 01.02.2029 zur Löschung fällig."]
    assert ws.due_reminders(closed, date(2029, 3, 1)) == []


async def _old_case(db: AsyncSession) -> WhistleCase:
    case = await db.scalar(select(WhistleCase))
    case.received_at = datetime(2026, 1, 1)
    await db.commit()
    await db.execute(sa.delete(Notification))
    await db.commit()
    return case


async def test_send_whistle_reminders_goes_to_officers_once(client, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    await _old_case(db_session)
    assert await ws.send_whistle_reminders(db_session, 1, date(2026, 6, 1)) == 2
    notes = (await db_session.scalars(select(Notification))).all()
    assert {n.recipient_account_id for n in notes} == {people.officer_id}
    assert all(n.type == NotificationType.WHISTLEBLOWING for n in notes)
    assert await ws.send_whistle_reminders(db_session, 1, date(2026, 6, 2)) == 0


async def test_reminders_wait_for_switch_and_officers(client, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await _old_case(db_session)
    await set_enabled(db_session, False)
    assert await ws.send_whistle_reminders(db_session, 1, date(2026, 6, 1)) == 0
    await set_enabled(db_session, True)
    await client.delete(f"/whistle/officers/{people.officer_id}", headers=people.admin)
    assert await ws.send_whistle_reminders(db_session, 1, date(2026, 6, 1)) == 0
    await db_session.refresh(case)
    assert case.ack_reminder_stage == 0  # nichts verbraucht – kommt nach der Benennung
    await client.post("/whistle/officers", headers=people.admin, json={"account_id": people.officer_id})
    assert await ws.send_whistle_reminders(db_session, 1, date(2026, 6, 1)) == 2


async def test_background_loop_runs_whistle_reminders(client, db_session: AsyncSession, monkeypatch) -> None:
    await company(db_session, client)
    await report(client)
    await _old_case(db_session)
    calls: list[int] = []
    original = reminder_service.send_whistle_reminders

    async def spy(db, tenant_id, on):
        calls.append(tenant_id)
        return await original(db, tenant_id, on)

    async def stop(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(reminder_service, "send_whistle_reminders", spy)
    monkeypatch.setattr(reminder_service.asyncio, "sleep", stop)
    factory = lambda: _SessionProxy(db_session)  # noqa: E731
    with pytest.raises(asyncio.CancelledError):
        await reminder_service.run_reminders(factory, 60)
    assert calls == [1]
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 2


class _SessionProxy:
    """async with session_factory() as db – liefert die Test-Session, ohne sie zu schließen."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, *_exc) -> None:
        return None


# --- Firma löschen ---------------------------------------------------------------------------


async def test_purge_tenant_removes_whistle_files(client, db_session: AsyncSession, tmp_path) -> None:
    await company(db_session, client)
    await other_company(db_session, client)
    own = await report(client)
    foreign = await report(client, headers=OTHER)
    for created, headers in ((own, {}), (foreign, OTHER)):
        response = await client.post(
            "/public/whistle/attachments", headers=headers, data=access(created), files={"file": ("a.pdf", PDF, "application/pdf")}
        )
        assert response.status_code == 201
    keys = {a.tenant_id: a.storage_key for a in (await db_session.scalars(select(WhistleAttachment))).all()}
    path = lambda key: Path(settings.documents_dir) / key[:2] / key  # noqa: E731
    assert path(keys[2]).exists()

    counts = await purge_tenant(db_session, 2)
    assert counts["whistle_cases"] == 1 and counts["whistle_attachments"] == 1 and counts["whistle_officers"] == 1
    assert not path(keys[2]).exists() and path(keys[1]).exists()
    assert await db_session.scalar(select(func.count()).select_from(WhistleCase)) == 1


# --- Migration 0151 --------------------------------------------------------------------------

_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0151_whistleblowing.py"
_spec = importlib.util.spec_from_file_location("migration_0151", _PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

_SCHEMA = (
    "CREATE TABLE tenants (id INTEGER PRIMARY KEY)",
    "CREATE TABLE accounts (id INTEGER PRIMARY KEY)",
    "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER)",
    "CREATE TABLE audit_log_entries (id INTEGER PRIMARY KEY, action TEXT)",
    "CREATE TABLE notifications (id INTEGER PRIMARY KEY, type TEXT)",
)


@pytest.fixture
def migration_conn(monkeypatch):
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in _SCHEMA:
            connection.execute(sa.text(statement))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        yield connection
    engine.dispose()


def test_parse_enum_values() -> None:
    assert migration.parse_enum_values("enum('A','B_C','LOGIN')") == ["A", "B_C", "LOGIN"]
    assert migration.parse_enum_values("varchar(20)") == []


def test_migration_upgrade_is_repeatable_and_downgrade_removes_everything(migration_conn) -> None:
    migration.upgrade()
    inspector = sa.inspect(migration_conn)
    for table in ("whistle_officers", "whistle_cases", "whistle_messages", "whistle_attachments"):
        assert inspector.has_table(table)
    assert "whistleblowing_enabled" in {c["name"] for c in inspector.get_columns("app_settings")}
    assert {c["name"] for c in inspector.get_columns("whistle_cases")} == {c.name for c in WhistleCase.__table__.columns}
    migration.upgrade()  # zweiter Lauf ändert nichts
    migration_conn.execute(sa.text("INSERT INTO audit_log_entries (action) VALUES ('WHISTLE_CASE_VIEWED'), ('LOGIN')"))
    migration.downgrade()
    inspector = sa.inspect(migration_conn)
    assert not inspector.has_table("whistle_cases")
    assert "whistleblowing_enabled" not in {c["name"] for c in inspector.get_columns("app_settings")}
    assert migration_conn.execute(sa.text("SELECT action FROM audit_log_entries")).scalars().all() == ["LOGIN"]


class _FakeMysql:
    """Verbindung, die sich als MySQL ausgibt und die aktuelle Enum-Definition liefert."""

    class dialect:  # noqa: N801
        name = "mysql"

    def __init__(self, column_type: str) -> None:
        self.column_type = column_type

    def execute(self, *_args, **_kwargs):
        column_type = self.column_type

        class _Result:
            def first(self):
                return (column_type, "NO")

        return _Result()


class _RecordingOp:
    def __init__(self) -> None:
        self.calls: list = []

    def alter_column(self, table, column, existing_type, type_, existing_nullable):
        self.calls.append((table, column, list(existing_type.enums), list(type_.enums), existing_nullable))


def test_enum_change_keeps_values_added_by_other_migrations(monkeypatch) -> None:
    fake = _RecordingOp()
    monkeypatch.setattr(migration, "op", fake)
    # Ein paralleler Zweig hat schon RECRUITING ergänzt – der Wert bleibt erhalten
    conn = _FakeMysql("enum('LOGIN','RECRUITING')")
    migration._change_enum(conn, "audit_log_entries", "action", "auditaction", add=["WHISTLE_CASE_VIEWED"], remove=[])
    assert fake.calls == [
        ("audit_log_entries", "action", ["LOGIN", "RECRUITING"], ["LOGIN", "RECRUITING", "WHISTLE_CASE_VIEWED"], False)
    ]
    # Schon vorhanden: keine Änderung
    migration._change_enum(_FakeMysql("enum('LOGIN','WHISTLE_CASE_VIEWED')"), "t", "c", "n", add=["WHISTLE_CASE_VIEWED"], remove=[])
    assert len(fake.calls) == 1
    # Zurück: nur die eigenen Werte entfernen
    migration._change_enum(_FakeMysql("enum('LOGIN','WHISTLE_CASE_VIEWED','RECRUITING')"), "t", "c", "n", add=[], remove=["WHISTLE_CASE_VIEWED"])
    assert fake.calls[-1][3] == ["LOGIN", "RECRUITING"]


def test_model_enums_match_migration_values() -> None:
    from app.models import AuditAction

    assert set(migration.AUDIT_VALUES) <= {a.value for a in AuditAction}
    assert migration.NOTIFICATION_VALUES == [NotificationType.WHISTLEBLOWING.value]


def test_case_dates_are_independent_of_server_timezone() -> None:
    assert ws.now_utc().tzinfo is None
    assert abs(ws.now_utc() - datetime.utcnow()) < timedelta(seconds=5)  # noqa: DTZ003
