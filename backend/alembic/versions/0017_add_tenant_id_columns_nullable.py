"""tenant_id (nullable) + FK auf tenants.id für alle mandantenscoped Tabellen

Revision ID: 0017_add_tenant_id_columns_nullable
Revises: 0016_create_tenants
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_add_tenant_id_columns_nullable"
down_revision: Union[str, None] = "0016_create_tenants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# hr_users bleibt dauerhaft nullable (NULL = plattformweiter Super-Admin), die
# übrigen 8 werden in 0020 auf NOT NULL umgestellt. Die FK-Constraints entstehen
# hier bereits (auch bei nullable Spalten unproblematisch), nicht erst in 0020.
_TABLES = [
    "locations",
    "employees",
    "punches",
    "devices",
    "hr_users",
    "app_settings",
    "break_rules",
    "work_time_model_templates",
    "holidays",
]


def _fk_name(table: str) -> str:
    return f"fk_{table}_tenant_id_tenants"


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))
        op.create_foreign_key(_fk_name(table), table, "tenants", ["tenant_id"], ["id"])

    # Eine Zeile pro Mandant, siehe app/services/settings_service.py.
    op.create_unique_constraint("uq_app_settings_tenant", "app_settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_constraint("uq_app_settings_tenant", "app_settings", type_="unique")

    for table in reversed(_TABLES):
        op.drop_constraint(_fk_name(table), table, type_="foreignkey")
        op.drop_column(table, "tenant_id")
