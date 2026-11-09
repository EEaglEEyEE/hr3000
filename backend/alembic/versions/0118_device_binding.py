"""Tablet-Sicherheit: Geräte-Token nur als SHA-256, Bindung an genau ein Tablet (Installations-ID),
Warnung bei weiteren Geräten (Benachrichtigung und Audit-Aktion).

Bestehende Tokens werden in Hashes umgerechnet – gekoppelte Tablets melden sich unverändert an und
binden sich beim ersten Anmelden mit der neuen Tablet-Version an ihr Gerät.

Revision ID: 0118_device_binding
Revises: 0117_calendar_tokens
Create Date: 2026-11-07

"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0118_device_binding"
down_revision: Union[str, None] = "0117_calendar_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "DEVICE_LOGIN_REJECTED", name="auditaction")
_NOTIFY_BASE = ['ABSENCE_REQUESTED', 'ABSENCE_DECIDED', 'OPEN_DAYS_DIGEST', 'PERIOD_SUBMITTED', 'PERIOD_DISPUTED', 'CORRECTION_REQUESTED', 'CORRECTION_DECIDED', 'SUBSTITUTE_ASSIGNED', 'REMINDER']
_NOTIFY_OLD = sa.Enum(*_NOTIFY_BASE, name="notificationtype")
_NOTIFY_NEW = sa.Enum(*_NOTIFY_BASE, "DEVICE_ALERT", name="notificationtype")


def upgrade() -> None:
    op.add_column("devices", sa.Column("token_hash", sa.String(64), nullable=True))
    op.add_column("devices", sa.Column("installation_hash", sa.String(64), nullable=True))
    op.add_column("devices", sa.Column("bound_at", sa.DateTime(), nullable=True))
    op.add_column("devices", sa.Column("rejected_at", sa.DateTime(), nullable=True))
    conn = op.get_bind()
    for device_id, token in conn.execute(sa.text("SELECT id, device_token FROM devices")).all():
        conn.execute(
            sa.text("UPDATE devices SET token_hash = :h WHERE id = :id"),
            {"h": hashlib.sha256(token.encode()).hexdigest(), "id": device_id},
        )
    op.alter_column("devices", "token_hash", existing_type=sa.String(64), nullable=False)
    # Erst den neuen Index anlegen: MySQL löscht keinen Index, der gerade den Fremdschlüssel auf tenant_id trägt.
    op.create_unique_constraint("uq_devices_tenant_token_hash", "devices", ["tenant_id", "token_hash"])
    op.drop_constraint("uq_devices_tenant_token", "devices", type_="unique")
    op.drop_column("devices", "device_token")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)
    op.alter_column("notifications", "type", existing_type=_NOTIFY_OLD, type_=_NOTIFY_NEW, existing_nullable=False)


def downgrade() -> None:
    # Die Klartext-Tokens lassen sich nicht zurückgewinnen: nach einem Downgrade alle Tablets neu koppeln.
    op.execute("DELETE FROM notifications WHERE type = 'DEVICE_ALERT'")
    op.alter_column("notifications", "type", existing_type=_NOTIFY_NEW, type_=_NOTIFY_OLD, existing_nullable=False)
    op.execute("DELETE FROM audit_log_entries WHERE action = 'DEVICE_LOGIN_REJECTED'")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.add_column("devices", sa.Column("device_token", sa.String(255), nullable=True))
    op.execute("UPDATE devices SET device_token = token_hash")
    op.alter_column("devices", "device_token", existing_type=sa.String(255), nullable=False)
    op.create_unique_constraint("uq_devices_tenant_token", "devices", ["tenant_id", "device_token"])
    op.drop_constraint("uq_devices_tenant_token_hash", "devices", type_="unique")
    for column in ("rejected_at", "bound_at", "installation_hash", "token_hash"):
        op.drop_column("devices", column)
