"""Zwei-Faktor-Anmeldung: Geheimnis (verschlüsselt), Einrichtungszeitpunkt, letzter Zeitschritt und
Wiederherstellungscodes am Konto; Firmeneinstellung „Pflicht für Konten mit Rolle“; Audit-Aktion.

Revision ID: 0120_two_factor
Revises: 0119_accounts
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0120_two_factor"
down_revision: Union[str, None] = "0119_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED', 'DEVICE_LOGIN_REJECTED']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "TWO_FACTOR_CHANGED", name="auditaction")


def upgrade() -> None:
    op.add_column("accounts", sa.Column("totp_secret", sa.String(255), nullable=True))
    op.add_column("accounts", sa.Column("totp_enabled_at", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("accounts", sa.Column("totp_recovery_hashes", sa.Text(), nullable=True))
    op.add_column("app_settings", sa.Column("two_factor_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM audit_log_entries WHERE action = 'TWO_FACTOR_CHANGED'")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_column("app_settings", "two_factor_required")
    for column in ("totp_recovery_hashes", "totp_last_step", "totp_enabled_at", "totp_secret"):
        op.drop_column("accounts", column)
