"""audit_log_entries

Revision ID: 0036_create_audit_log_entries
Revises: 0035_shift_template_target_period
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0036_create_audit_log_entries"
down_revision: Union[str, None] = "0035_shift_template_target_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("actor_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "PUNCH_CORRECTED",
                "PUNCH_DELETED",
                "EMPLOYEE_HR_ROLE_CHANGED",
                "ABSENCE_DECIDED",
                name="auditaction",
            ),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_entries_tenant_created", "audit_log_entries", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_entries_tenant_created", table_name="audit_log_entries")
    op.drop_table("audit_log_entries")
