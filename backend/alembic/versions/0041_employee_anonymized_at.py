"""employees.anonymized_at für DSGVO-Anonymisierung

Revision ID: 0041_employee_anonymized_at
Revises: 0040_audit_action_data_export
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0041_employee_anonymized_at"
down_revision: Union[str, None] = "0040_audit_action_data_export"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("anonymized_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "anonymized_at")
