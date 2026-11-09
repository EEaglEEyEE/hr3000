"""Dokumentvorlagen mit Platzhaltern.

Revision ID: 0127_document_templates
Revises: 0126_document_categories
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0127_document_templates"
down_revision: Union[str, None] = "0126_document_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATEGORIES = ("CONTRACT", "CERTIFICATE", "SICK_NOTE", "QUALIFICATION", "WARNING", "PAYROLL", "TIME_REPORT", "OTHER")


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.Enum(*_CATEGORIES, name="documentcategory"), nullable=False, server_default="OTHER"),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("document_categories.id"), nullable=True),
        sa.Column("employee_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("document_templates")
