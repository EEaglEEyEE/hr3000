"""On-/Offboarding: Aktionen je Aufgabe (Abhaken, Dokument hochladen, Daten ausfüllen, E-Mail senden).

Revision ID: 0128_checklist_actions
Revises: 0127_document_templates
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0128_checklist_actions"
down_revision: Union[str, None] = "0127_document_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("checklist_template_items", "employee_checklist_items"):
        op.add_column(table, sa.Column("action", sa.String(20), nullable=False, server_default="TASK"))
        op.add_column(table, sa.Column("action_category_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_action_category_id", table, "document_categories", ["action_category_id"], ["id"])


def downgrade() -> None:
    for table in ("employee_checklist_items", "checklist_template_items"):
        op.drop_constraint(f"fk_{table}_action_category_id", table, type_="foreignkey")
        op.drop_column(table, "action_category_id")
        op.drop_column(table, "action")
