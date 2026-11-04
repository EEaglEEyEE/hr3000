"""Mandanten-Logo (Anzeige in Web-App, Kiosk und Berichten)

Revision ID: 0057_tenant_logo
Revises: 0056_day_flags_and_reviews
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0057_tenant_logo"
down_revision: Union[str, None] = "0056_day_flags_and_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("logo_content_type", sa.String(50), nullable=True))
    op.add_column("app_settings", sa.Column("logo_data", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "logo_data")
    op.drop_column("app_settings", "logo_content_type")
