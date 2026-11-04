"""teams.location_id optional (Team unabhaengig vom Standort)

Revision ID: 0032_team_location_optional
Revises: 0031_drop_work_time_models
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_team_location_optional"
down_revision: Union[str, None] = "0031_drop_work_time_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("teams", "location_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("teams", "location_id", existing_type=sa.Integer(), nullable=False)
