"""Eigene Dokumentkategorien mit Rechten, Kategorie am Dokument, Benachrichtigung bei Upload durch
Mitarbeiter.

Revision ID: 0126_document_categories
Revises: 0125_change_requests
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0126_document_categories"
down_revision: Union[str, None] = "0125_change_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFY_BASE = ['ABSENCE_REQUESTED', 'ABSENCE_DECIDED', 'OPEN_DAYS_DIGEST', 'PERIOD_SUBMITTED', 'PERIOD_DISPUTED', 'CORRECTION_REQUESTED', 'CORRECTION_DECIDED', 'SUBSTITUTE_ASSIGNED', 'REMINDER', 'DEVICE_ALERT', 'DATA_CHANGE_REQUESTED', 'DATA_CHANGE_DECIDED']
_NOTIFY_OLD = sa.Enum(*_NOTIFY_BASE, name="notificationtype")
_NOTIFY_NEW = sa.Enum(*_NOTIFY_BASE, "DOCUMENT_UPLOADED", name="notificationtype")


def upgrade() -> None:
    op.create_table(
        "document_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("employee_upload", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("employee_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidential", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("employee_documents", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_employee_documents_category_id", "employee_documents", "document_categories", ["category_id"], ["id"]
    )
    op.alter_column("notifications", "type", existing_type=_NOTIFY_OLD, type_=_NOTIFY_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'DOCUMENT_UPLOADED'")
    op.alter_column("notifications", "type", existing_type=_NOTIFY_NEW, type_=_NOTIFY_OLD, existing_nullable=False)
    op.drop_constraint("fk_employee_documents_category_id", "employee_documents", type_="foreignkey")
    op.drop_column("employee_documents", "category_id")
    op.drop_table("document_categories")
