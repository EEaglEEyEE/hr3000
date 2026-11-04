"""app_settings.default_annual_vacation_days

Revision ID: 0033_app_settings_default_annual_vacation_days
Revises: 0032_team_location_optional
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_app_settings_default_annual_vacation_days"
down_revision: Union[str, None] = "0032_team_location_optional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "default_annual_vacation_days", sa.Numeric(5, 2), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "default_annual_vacation_days")
