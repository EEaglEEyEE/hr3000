"""On-/Offboarding-Checklisten: Vorlagen und Mitarbeiter-Instanzen

Revision ID: 0052_checklists
Revises: 0051_surcharge_rules
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0052_checklists"
down_revision: Union[str, None] = "0051_surcharge_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND = ("ONBOARDING", "OFFBOARDING")
_ROLE = ("HR", "IT", "SUPERVISOR", "EMPLOYEE", "OTHER")


def upgrade() -> None:
    op.create_table(
        "checklist_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.Enum(*_KIND, name="checklistkind"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "checklist_template_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("responsible", sa.Enum(*_ROLE, name="checklistrole"), nullable=False),
        sa.Column("due_offset_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "employee_checklists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("kind", sa.Enum(*_KIND, name="checklistkind"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_checklists_employee", "employee_checklists", ["employee_id"])
    op.create_table(
        "employee_checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checklist_id", sa.Integer(), sa.ForeignKey("employee_checklists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("responsible", sa.Enum(*_ROLE, name="checklistrole"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("done_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("done_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
    )
    op.create_index("ix_employee_checklist_items_open", "employee_checklist_items", ["done", "due_date"])


def downgrade() -> None:
    op.drop_index("ix_employee_checklist_items_open", table_name="employee_checklist_items")
    op.drop_table("employee_checklist_items")
    op.drop_index("ix_employee_checklists_employee", table_name="employee_checklists")
    op.drop_table("employee_checklists")
    op.drop_table("checklist_template_items")
    op.drop_table("checklist_templates")
