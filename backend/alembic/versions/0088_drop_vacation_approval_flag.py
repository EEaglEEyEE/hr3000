"""Versteckten Schalter "Urlaubsgenehmigung erforderlich" in die Abwesenheitsarten überführen

Die Genehmigungspflicht steht je Abwesenheitsart ("Genehmigung nötig"). Der alte, in der
Oberfläche nicht mehr sichtbare Mandanten-Schalter wirkte zusätzlich als Oder-Regel. Wo er an
war, bekommt die Art "Urlaub" die Genehmigungspflicht – das Verhalten bleibt gleich.

Revision ID: 0088_drop_vacation_approval_flag
Revises: 0087_datev_lodas_export
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0088_drop_vacation_approval_flag"
down_revision: Union[str, None] = "0087_datev_lodas_export"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE absence_type_definitions SET requires_approval = 1 "
        "WHERE category = 'VACATION' AND tenant_id IN "
        "(SELECT tenant_id FROM app_settings WHERE vacation_approval_required = 1)"
    )
    op.drop_column("app_settings", "vacation_approval_required")


def downgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("vacation_approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
