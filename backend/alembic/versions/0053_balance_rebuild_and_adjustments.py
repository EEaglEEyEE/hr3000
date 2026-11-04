"""Gleitzeitkonto: Neuberechnungs-Marker, Saldo-Beginn, Korrekturbuchungen

Revision ID: 0053_balance_rebuild_and_adjustments
Revises: 0052_checklists
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0053_balance_rebuild_and_adjustments"
down_revision: Union[str, None] = "0052_checklists"
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
    "CHECKLIST_STARTED", "SURCHARGE_RULES_CHANGED",
]
_OLD_ENUM = sa.Enum(*_AUDIT_BASE, name="auditaction")
_NEW_ENUM = sa.Enum(*_AUDIT_BASE, "BALANCE_ADJUSTED", name="auditaction")


def upgrade() -> None:
    # NULL = beim nächsten Zugriff komplett neu berechnen (bisherige Salden zählten nur Tage mit Stempelungen).
    op.add_column("employees", sa.Column("balance_through", sa.Date(), nullable=True))
    op.add_column("app_settings", sa.Column("balance_start_date", sa.Date(), nullable=True))
    op.create_table(
        "balance_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.Enum("OPENING_BALANCE", "PAYOUT", "CORRECTION", name="adjustmentkind"), nullable=False
        ),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("created_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("created_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_balance_adjustments_employee", "balance_adjustments", ["employee_id", "effective_date"])
    op.alter_column("audit_log_entries", "action", existing_type=_OLD_ENUM, type_=_NEW_ENUM, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("audit_log_entries", "action", existing_type=_NEW_ENUM, type_=_OLD_ENUM, existing_nullable=False)
    op.drop_index("ix_balance_adjustments_employee", table_name="balance_adjustments")
    op.drop_table("balance_adjustments")
    op.drop_column("app_settings", "balance_start_date")
    op.drop_column("employees", "balance_through")
