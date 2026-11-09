"""Abwesenheitsarten: Pflichtkommentar; Abwesenheiten: Verweis auf den hochgeladenen Nachweis.

Revision ID: 0106_absence_comment_certificate
Revises: 0105_absence_overlaps_setting
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0106_absence_comment_certificate"
down_revision: Union[str, None] = "0105_absence_overlaps_setting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "absence_type_definitions",
        sa.Column("comment_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("absences", sa.Column("certificate_document_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_absences_certificate_document_id", "absences", "employee_documents",
        ["certificate_document_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_absences_certificate_document_id", "absences", type_="foreignkey")
    op.drop_column("absences", "certificate_document_id")
    op.drop_column("absence_type_definitions", "comment_required")
