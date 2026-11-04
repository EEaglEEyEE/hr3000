"""absences: Genehmigungsworkflow (approval_status, decided_by, decided_by_employee_id, decided_at)

Revision ID: 0028_absence_approval_workflow
Revises: 0027_summary_status_planned_off
Create Date: 2026-08-12

Backfill: alle bestehenden Zeilen -> APPROVED (entspricht dem bisherigen
"HR trägt final ein"-Verhalten, keine Verhaltensänderung für Altdaten).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028_absence_approval_workflow"
down_revision: Union[str, None] = "0027_summary_status_planned_off"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "absences",
        sa.Column(
            "approval_status",
            sa.Enum("APPROVED", "PENDING", "REJECTED", name="absenceapprovalstatus"),
            nullable=False,
            server_default="APPROVED",
        ),
    )
    op.add_column("absences", sa.Column("decided_by", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True))
    op.add_column(
        "absences", sa.Column("decided_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True)
    )
    op.add_column("absences", sa.Column("decided_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("absences", "decided_at")
    op.drop_column("absences", "decided_by_employee_id")
    op.drop_column("absences", "decided_by")
    op.drop_column("absences", "approval_status")
