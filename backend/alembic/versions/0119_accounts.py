"""Ein Konto je Person (docs/konzept-konten.md): Tabelle accounts statt hr_users plus Login-Feldern am
Mitarbeiter; alle „wer war das“-Spalten zeigen auf accounts.

Übernahme:
1. Jedes HR-Konto wird ein Konto (Passwort-Hash 1:1).
2. Gibt es in derselben Firma einen Mitarbeiter-Login mit derselben E-Mail, wird das Konto mit diesem
   Mitarbeiter verknüpft; Rolle und Passwort des HR-Kontos gelten (Entscheidung vom 07.11.2026),
   „Vergütung & Lohn-Export“ bleibt, wenn eines der beiden sie hatte.
3. Jeder übrige Mitarbeiter-Login wird ein Konto mit employee_id.
4. Mitarbeiter ohne Login, die irgendwo als „wer“ stehen (z. B. PIN am Tablet selbst gesetzt), bekommen
   ein Konto ohne Zugang (E-Mail/Passwort leer), damit der Verlauf erhalten bleibt.
5. Neue Spalten *_account_id aus den alten Paaren füllen, alte Spalten, hr_users und die Login-Felder
   der Mitarbeiter entfernen.

Nach dem Rollout meldet sich jeder in der Webapp einmal neu an (neue Token-Art). Tablets sind nicht
betroffen. Nur MySQL (Produktion/Testumgebung); die Tests bauen das Schema aus den Modellen.

Revision ID: 0119_accounts
Revises: 0118_device_binding
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0119_accounts"
down_revision: Union[str, None] = "0118_device_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (Tabelle, alte HR-Spalte, alte Mitarbeiter-Spalte, neue Spalte)
ACTOR_COLUMNS = [
    ("employee_checklist_items", "done_by_hr_user_id", "done_by_employee_id", "done_by_account_id"),
    ("punch_correction_requests", "decided_by", "decided_by_employee_id", "decided_by_account_id"),
    ("notifications", "recipient_hr_user_id", "recipient_employee_id", "recipient_account_id"),
    ("payroll_export_logs", "created_by_hr_user_id", None, "created_by_account_id"),
    ("period_closures", "submitted_by_hr_user_id", "submitted_by_employee_id", "submitted_by_account_id"),
    ("punches", "created_by", "created_by_employee_id", "created_by_account_id"),
    ("leave_adjustments", "created_by_hr_user_id", "created_by_employee_id", "created_by_account_id"),
    ("day_reviews", "reviewed_by_hr_user_id", "reviewed_by_employee_id", "reviewed_by_account_id"),
    ("supervisor_team_assignments", "hr_user_id", "employee_id", "account_id"),
    ("employee_documents", "uploaded_by_hr_user_id", "uploaded_by_employee_id", "uploaded_by_account_id"),
    ("shift_plan_entries", "planned_by_hr_user_id", "planned_by_employee_id", "planned_by_account_id"),
    ("account_tokens", "hr_user_id", "employee_id", "account_id"),
    ("audit_log_entries", "actor_hr_user_id", "actor_employee_id", "actor_account_id"),
    ("balance_adjustments", "created_by_hr_user_id", "created_by_employee_id", "created_by_account_id"),
    ("absences", "created_by", "created_by_employee_id", "created_by_account_id"),
    ("absences", "decided_by", "decided_by_employee_id", "decided_by_account_id"),
]
# Ohne Empfänger bzw. Konto ergibt die Zeile keinen Sinn mehr
REQUIRED = {"notifications": "recipient_account_id", "supervisor_team_assignments": "account_id", "account_tokens": "account_id"}
EMPLOYEE_LOGIN_COLUMNS = ["login_email", "password_hash", "hr_role", "hr_payroll_access", "notification_emails", "calendar_token_hash"]


def _drop_column(conn, table: str, column: str) -> None:
    """MySQL: erst Fremdschlüssel, CHECK-Constraints und eindeutige Indizes der Spalte entfernen, dann
    die Spalte. Namen stammen teils von MySQL selbst (z. B. absences_ibfk_3), darum aus
    information_schema. Nicht eindeutige Indizes bleiben stehen: MySQL nimmt die Spalte beim Löschen
    selbst heraus – ein Index wie (tenant_id, recipient_employee_id) trägt sonst noch den
    Fremdschlüssel auf tenant_id und darf nicht gelöscht werden (Fehler 1553). Eindeutige Indizes
    dagegen würden ohne die Spalte etwas anderes bedeuten (z. B. UNIQUE(tenant_id))."""
    params = {"t": table, "c": column}
    for (name,) in conn.execute(sa.text(
        "SELECT DISTINCT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = :t AND COLUMN_NAME = :c AND REFERENCED_TABLE_NAME IS NOT NULL"), params).all():
        op.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`")
    for (name,) in conn.execute(sa.text(
        "SELECT tc.CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS tc JOIN information_schema.CHECK_CONSTRAINTS cc "
        "ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
        "WHERE tc.TABLE_SCHEMA = DATABASE() AND tc.TABLE_NAME = :t AND tc.CONSTRAINT_TYPE = 'CHECK' AND cc.CHECK_CLAUSE LIKE :p"),
        {"t": table, "p": f"%`{column}`%"}).all():
        op.execute(f"ALTER TABLE `{table}` DROP CHECK `{name}`")
    for (name,) in conn.execute(sa.text(
        "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = :t AND COLUMN_NAME = :c AND INDEX_NAME <> 'PRIMARY' AND NON_UNIQUE = 0"), params).all():
        op.execute(f"ALTER TABLE `{table}` DROP INDEX `{name}`")
    op.execute(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


def _drop_index_if_exists(conn, table: str, name: str) -> None:
    exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
    ), {"t": table, "i": name}).first()
    if exists:
        op.execute(f"ALTER TABLE `{table}` DROP INDEX `{name}`")


def upgrade() -> None:
    conn = op.get_bind()
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.Enum("ADMIN", "HR", "SUPERVISOR", "SUPER_ADMIN", name="hrrole"), nullable=True),
        sa.Column("payroll_access", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_verification_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notification_emails", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("calendar_token_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("legacy_hr_user_id", sa.Integer(), nullable=True),
    )

    # 1. HR-Konten
    conn.execute(sa.text(
        "INSERT INTO accounts (tenant_id, email, password_hash, role, payroll_access, email_verification_pending, "
        "notification_emails, calendar_token_hash, legacy_hr_user_id) "
        "SELECT tenant_id, email, password_hash, role, payroll_access, email_verification_pending, notification_emails, "
        "calendar_token_hash, id FROM hr_users"))
    # 2. Gleiche E-Mail als Mitarbeiter-Login derselben Firma: verknüpfen, Rolle/Passwort des HR-Kontos bleiben
    conn.execute(sa.text(
        "UPDATE accounts a JOIN employees e ON e.tenant_id = a.tenant_id AND LOWER(e.login_email) = LOWER(a.email) "
        "SET a.employee_id = e.id, a.payroll_access = (a.payroll_access OR e.hr_payroll_access)"))
    # 3. Übrige Mitarbeiter-Logins
    conn.execute(sa.text(
        "INSERT INTO accounts (tenant_id, employee_id, email, password_hash, role, payroll_access, notification_emails, "
        "calendar_token_hash) SELECT e.tenant_id, e.id, e.login_email, e.password_hash, e.hr_role, e.hr_payroll_access, "
        "e.notification_emails, e.calendar_token_hash FROM employees e "
        "WHERE e.login_email IS NOT NULL AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.employee_id = e.id)"))
    # 4. Mitarbeiter ohne Login, die als „wer“ vorkommen: Konto ohne Zugang
    referenced = " UNION ".join(
        f"SELECT `{emp}` AS employee_id FROM `{table}` WHERE `{emp}` IS NOT NULL" for table, _, emp, _ in ACTOR_COLUMNS if emp
    )
    conn.execute(sa.text(
        "INSERT INTO accounts (tenant_id, employee_id, notification_emails) SELECT e.tenant_id, e.id, e.notification_emails "
        f"FROM employees e WHERE e.id IN (SELECT employee_id FROM ({referenced}) r) "
        "AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.employee_id = e.id)"))

    # 5. Neue Spalten füllen, alte entfernen
    for table, hr, emp, new in ACTOR_COLUMNS:
        op.add_column(table, sa.Column(new, sa.Integer(), nullable=True))
        if hr:
            conn.execute(sa.text(
                f"UPDATE `{table}` t JOIN accounts a ON a.legacy_hr_user_id = t.`{hr}` SET t.`{new}` = a.id"))
        if emp:
            conn.execute(sa.text(
                f"UPDATE `{table}` t JOIN accounts a ON a.employee_id = t.`{emp}` SET t.`{new}` = a.id WHERE t.`{new}` IS NULL"))
    # Benachrichtigungen: neuer Index (Firma, Empfänger) zuerst – er trägt danach den Fremdschlüssel auf
    # tenant_id, sodass die beiden alten Indizes (Firma, alter Empfänger) wegfallen können.
    op.create_index("ix_notifications_recipient_account", "notifications", ["tenant_id", "recipient_account_id"])
    _drop_index_if_exists(conn, "notifications", "ix_notifications_recipient_hr_user")
    _drop_index_if_exists(conn, "notifications", "ix_notifications_recipient_employee")
    for table, hr, emp, new in ACTOR_COLUMNS:
        for column in (hr, emp):
            if column:
                _drop_column(conn, table, column)
    for table, column in REQUIRED.items():
        conn.execute(sa.text(f"DELETE FROM `{table}` WHERE `{column}` IS NULL"))
        op.alter_column(table, column, existing_type=sa.Integer(), nullable=False)
    for table, _, _, new in ACTOR_COLUMNS:
        op.create_foreign_key(f"fk_{table}_{new}", table, "accounts", [new], ["id"])

    for column in EMPLOYEE_LOGIN_COLUMNS:
        _drop_column(conn, "employees", column)
    _drop_column(conn, "accounts", "legacy_hr_user_id")
    op.drop_table("hr_users")
    op.create_unique_constraint("uq_accounts_tenant_email", "accounts", ["tenant_id", "email"])
    op.create_unique_constraint("uq_accounts_employee_id", "accounts", ["employee_id"])
    op.create_unique_constraint("uq_accounts_calendar_token_hash", "accounts", ["calendar_token_hash"])


def downgrade() -> None:
    raise NotImplementedError("Zurück nur über die Sicherung vor dem Rollout (scripts/backup_db.sh).")
