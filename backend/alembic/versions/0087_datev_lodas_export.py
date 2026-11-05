"""DATEV-LODAS-Export: Berater-/Mandantennummer, Lohnarten für Ist-Stunden und Zuschläge

Revision ID: 0087_datev_lodas_export
Revises: 0086_pay_components
Create Date: 2026-11-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0087_datev_lodas_export"
down_revision: Union[str, None] = "0086_pay_components"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("datev_consultant_number", sa.String(7), nullable=True))
    op.add_column("app_settings", sa.Column("datev_client_number", sa.String(5), nullable=True))
    op.add_column("app_settings", sa.Column("datev_hours_wage_type", sa.String(6), nullable=True))
    op.add_column("surcharge_rules", sa.Column("wage_type", sa.String(6), nullable=True))


def downgrade() -> None:
    op.drop_column("surcharge_rules", "wage_type")
    op.drop_column("app_settings", "datev_hours_wage_type")
    op.drop_column("app_settings", "datev_client_number")
    op.drop_column("app_settings", "datev_consultant_number")
