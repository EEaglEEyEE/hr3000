"""Vertragsdaten und Vergütung (effektiv-datiert) + Audit-Aktionen

Revision ID: 0048_contracts_and_compensation
Revises: 0047_holiday_locations
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0048_contracts_and_compensation"
down_revision: Union[str, None] = "0047_holiday_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = [
    "PUNCH_CORRECTED", "PUNCH_DELETED", "EMPLOYEE_HR_ROLE_CHANGED", "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED", "SETTINGS_CHANGED", "HR_USER_CREATED", "HR_USER_DELETED",
    "TEAM_CREATED", "TEAM_UPDATED", "TEAM_DELETED", "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED", "EMPLOYEE_DATA_EXPORTED", "EMPLOYEE_ANONYMIZED",
    "EMPLOYEE_WORK_TIME_MODEL_SET", "EMPLOYEE_PASSWORD_RESET",
]
_NEW_AUDIT = ["CONTRACT_CHANGED", "COMPENSATION_CHANGED", "COMPENSATION_VIEWED"]
_OLD_ENUM = sa.Enum(*_AUDIT_BASE, name="auditaction")
_NEW_ENUM = sa.Enum(*_AUDIT_BASE, *_NEW_AUDIT, name="auditaction")


def upgrade() -> None:
    op.create_table(
        "employment_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "contract_type",
            sa.Enum(
                "PERMANENT", "FIXED_TERM", "APPRENTICESHIP", "MINI_JOB", "WORKING_STUDENT",
                "INTERNSHIP", "FREELANCE", name="contracttype",
            ),
            nullable=False,
        ),
        sa.Column("job_title", sa.String(150), nullable=True),
        sa.Column("probation_end", sa.Date(), nullable=True),
        sa.Column("fixed_term_end", sa.Date(), nullable=True),
        sa.Column("notice_period", sa.String(100), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employment_contracts_employee", "employment_contracts", ["employee_id", "valid_from"])
    op.create_table(
        "compensations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("pay_type", sa.Enum("HOURLY", "MONTHLY", name="paytype"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_compensations_employee", "compensations", ["employee_id", "valid_from"])
    op.alter_column(
        "audit_log_entries", "action", existing_type=_OLD_ENUM, type_=_NEW_ENUM, existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "audit_log_entries", "action", existing_type=_NEW_ENUM, type_=_OLD_ENUM, existing_nullable=False
    )
    op.drop_index("ix_compensations_employee", table_name="compensations")
    op.drop_table("compensations")
    op.drop_index("ix_employment_contracts_employee", table_name="employment_contracts")
    op.drop_table("employment_contracts")
