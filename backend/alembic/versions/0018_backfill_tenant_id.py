"""Backfill tenant_id = 1 (Schwabenhaus, einziger bisheriger Mandant)

Revision ID: 0018_backfill_tenant_id
Revises: 0017_add_tenant_id_columns_nullable
Create Date: 2026-08-11

Hinweis zur Reversibilität: diese Migration ist nur sicher rückrollbar,
solange es noch genau einen Mandanten gibt. Sobald ein zweiter Mandant
angelegt wurde, würde ein downgrade auch dessen Zeilen fälschlich betreffen
(setzt tenant_id auf allen Zeilen zurück auf NULL, nicht nur bei Mandant 1).

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_backfill_tenant_id"
down_revision: Union[str, None] = "0017_add_tenant_id_columns_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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


def upgrade() -> None:
    seed_tenant_exists = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM tenants WHERE id = 1")).scalar()
    for table in _TABLES:
        if seed_tenant_exists:
            op.execute(f"UPDATE {table} SET tenant_id = 1 WHERE tenant_id IS NULL")
        else:
            # Frische Installation ohne Seed-Mandant: die globalen Standardzeilen der
            # frühen Migrationen (Pausenregeln, Einstellungen, Vorlagen) gehören
            # niemandem – neue Mandanten bekommen ihre Defaults beim Anlegen.
            op.execute(f"DELETE FROM {table} WHERE tenant_id IS NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET tenant_id = NULL WHERE tenant_id = 1")
