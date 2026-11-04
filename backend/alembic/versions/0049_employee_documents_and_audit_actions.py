"""Personalakte: employee_documents + weitere Audit-Aktionen (Dokumente, Perioden, Checklisten, Zuschläge)

Revision ID: 0049_employee_documents_and_audit_actions
Revises: 0048_contracts_and_compensation
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0049_employee_documents_and_audit_actions"
down_revision: Union[str, None] = "0048_contracts_and_compensation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = [
    "PUNCH_CORRECTED", "PUNCH_DELETED", "EMPLOYEE_HR_ROLE_CHANGED", "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED", "SETTINGS_CHANGED", "HR_USER_CREATED", "HR_USER_DELETED",
    "TEAM_CREATED", "TEAM_UPDATED", "TEAM_DELETED", "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED", "EMPLOYEE_DATA_EXPORTED", "EMPLOYEE_ANONYMIZED",
    "EMPLOYEE_WORK_TIME_MODEL_SET", "EMPLOYEE_PASSWORD_RESET",
    "CONTRACT_CHANGED", "COMPENSATION_CHANGED", "COMPENSATION_VIEWED",
]
_NEW_AUDIT = [
    "DOCUMENT_UPLOADED", "DOCUMENT_UPDATED", "DOCUMENT_DELETED", "DOCUMENT_ACCESSED",
    "PERIOD_SUBMITTED", "PERIOD_CONFIRMED", "PERIOD_DISPUTED", "PERIOD_CLOSED", "PERIOD_REOPENED",
    "CHECKLIST_STARTED", "SURCHARGE_RULES_CHANGED",
]
_OLD_ENUM = sa.Enum(*_AUDIT_BASE, name="auditaction")
_NEW_ENUM = sa.Enum(*_AUDIT_BASE, *_NEW_AUDIT, name="auditaction")


def upgrade() -> None:
    op.create_table(
        "employee_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "CONTRACT", "CERTIFICATE", "SICK_NOTE", "QUALIFICATION", "WARNING", "PAYROLL",
                "TIME_REPORT", "OTHER", name="documentcategory",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False, unique=True),
        sa.Column("confidential", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("employee_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column("uploaded_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("uploaded_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_documents_employee", "employee_documents", ["employee_id", "created_at"])
    op.alter_column(
        "audit_log_entries", "action", existing_type=_OLD_ENUM, type_=_NEW_ENUM, existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "audit_log_entries", "action", existing_type=_NEW_ENUM, type_=_OLD_ENUM, existing_nullable=False
    )
    op.drop_index("ix_employee_documents_employee", table_name="employee_documents")
    op.drop_table("employee_documents")
