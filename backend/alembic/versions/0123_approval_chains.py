"""Genehmigungsketten: je Abwesenheitsart (approval_chain), aktueller Schritt am Antrag, Verlauf der
Entscheidungen (absence_approvals) und Vertretung bei Genehmigungen am Mitarbeiter.

Revision ID: 0123_approval_chains
Revises: 0122_personal_data
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0123_approval_chains"
down_revision: Union[str, None] = "0122_personal_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "absence_type_definitions",
        sa.Column("approval_chain", sa.String(20), nullable=False, server_default="DEFAULT"),
    )
    op.add_column("absences", sa.Column("approval_step", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("employees", sa.Column("approval_delegate_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_employees_approval_delegate_id", "employees", "employees", ["approval_delegate_id"], ["id"], ondelete="SET NULL"
    )
    op.create_table(
        "absence_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("absence_id", sa.Integer(), sa.ForeignKey("absences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(20), nullable=False),
        sa.Column("decided_by_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_absence_approvals_absence_id", "absence_approvals", ["absence_id"])


def downgrade() -> None:
    op.drop_table("absence_approvals")
    op.drop_constraint("fk_employees_approval_delegate_id", "employees", type_="foreignkey")
    op.drop_column("employees", "approval_delegate_id")
    op.drop_column("absences", "approval_step")
    op.drop_column("absence_type_definitions", "approval_chain")
