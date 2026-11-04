"""PIN beim ersten Stempeln am Kiosk selbst festlegen (Einstellung + Audit-Aktion)

Revision ID: 0071_kiosk_pin_self_setup
Revises: 0070_on_demand_work_time_model
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0071_kiosk_pin_self_setup"
down_revision: Union[str, None] = "0070_on_demand_work_time_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = [
    "PUNCH_CORRECTED", "PUNCH_DELETED", "EMPLOYEE_HR_ROLE_CHANGED", "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED", "SETTINGS_CHANGED", "HR_USER_CREATED", "HR_USER_DELETED",
    "TEAM_CREATED", "TEAM_UPDATED", "TEAM_DELETED", "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED", "EMPLOYEE_DATA_EXPORTED", "EMPLOYEE_ANONYMIZED",
    "EMPLOYEE_WORK_TIME_MODEL_SET", "EMPLOYEE_PASSWORD_RESET",
    "CONTRACT_CHANGED", "COMPENSATION_CHANGED", "COMPENSATION_VIEWED",
    "DOCUMENT_UPLOADED", "DOCUMENT_UPDATED", "DOCUMENT_DELETED", "DOCUMENT_ACCESSED",
    "PERIOD_SUBMITTED", "PERIOD_CONFIRMED", "PERIOD_DISPUTED", "PERIOD_CLOSED", "PERIOD_REOPENED",
    "CHECKLIST_STARTED", "SURCHARGE_RULES_CHANGED", "BALANCE_ADJUSTED", "PUNCH_CORRECTION_DECIDED",
    "EMPLOYEE_CARD_REGISTERED",
]
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "EMPLOYEE_PIN_SET_AT_KIOSK", name="auditaction")


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("kiosk_pin_self_setup", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_column("app_settings", "kiosk_pin_self_setup")
