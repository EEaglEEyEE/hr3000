"""Mandanten: tenants-Tabelle + Seed "Schwabenhaus" (bestehender Betrieb)

Revision ID: 0016_create_tenants
Revises: 0015_locations_holidays_employees_templates
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_create_tenants"
down_revision: Union[str, None] = "0015_locations_holidays_employees_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subdomain", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Seed-Mandant "Schwabenhaus" nur für Bestandsinstallationen mit echten Daten
    # (die vor der Mandantenfähigkeit nutzten). Frische Installationen starten
    # ohne Mandanten, den legt der Super-Admin an.
    bind = op.get_bind()
    legacy_rows = bind.execute(
        sa.text("SELECT (SELECT COUNT(*) FROM employees) + (SELECT COUNT(*) FROM locations)")
    ).scalar()
    if legacy_rows:
        op.bulk_insert(
            sa.table(
                "tenants",
                sa.column("id", sa.Integer()),
                sa.column("subdomain", sa.String()),
                sa.column("name", sa.String()),
                sa.column("is_active", sa.Boolean()),
            ),
            [{"id": 1, "subdomain": "schwabenhaus", "name": "Schwabenhaus", "is_active": True}],
        )


def downgrade() -> None:
    op.drop_table("tenants")
