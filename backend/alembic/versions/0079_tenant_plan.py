"""Tarif je Mandant (kostenlos bis 5 aktive Mitarbeiter, bezahlt, unbegrenzt)

Revision ID: 0079_tenant_plan
Revises: 0078_more_absence_categories
Create Date: 2026-11-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0079_tenant_plan"
down_revision: Union[str, None] = "0078_more_absence_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLAN = sa.Enum("FREE", "PAID", "UNLIMITED", name="tenantplan")


def upgrade() -> None:
    _PLAN.create(op.get_bind(), checkfirst=True)
    op.add_column("tenants", sa.Column("plan", _PLAN, nullable=False, server_default="FREE"))
    # Bestehende Mandanten (vor Einführung der Tarife angelegt) bleiben ohne Grenze.
    op.execute("UPDATE tenants SET plan = 'UNLIMITED'")


def downgrade() -> None:
    op.drop_column("tenants", "plan")
    _PLAN.drop(op.get_bind(), checkfirst=True)
