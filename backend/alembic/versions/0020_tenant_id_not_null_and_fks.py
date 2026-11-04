"""tenant_id NOT NULL für die 8 Tabellen außer hr_users (bleibt dauerhaft nullable)

Revision ID: 0020_tenant_id_not_null_and_fks
Revises: 0019_seed_super_admin
Create Date: 2026-08-11

Die FK-Constraints selbst wurden bereits in 0017 angelegt (auch nullable
FK-Spalten erlauben das); hier folgt nur noch die NOT-NULL-Verschärfung,
nachdem 0018 alle Bestandsdaten mit tenant_id=1 befüllt hat.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_tenant_id_not_null_and_fks"
down_revision: Union[str, None] = "0019_seed_super_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = [
    "locations",
    "employees",
    "punches",
    "devices",
    "app_settings",
    "break_rules",
    "work_time_model_templates",
    "holidays",
]


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=True)
