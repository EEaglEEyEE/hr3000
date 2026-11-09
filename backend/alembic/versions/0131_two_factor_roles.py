"""Zwei-Faktor-Pflicht je Gruppe statt eines Schalters: app_settings.two_factor_roles (ADMIN, HR,
SUPERVISOR, EMPLOYEE, durch Komma getrennt) ersetzt two_factor_required. War der Schalter an, gilt
die Pflicht danach wie bisher für Admin, HR und Führungskräfte.

Revision ID: 0131_two_factor_roles
Revises: 0130_device_enrollment
Create Date: 2026-11-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0131_two_factor_roles"
down_revision: Union[str, None] = "0130_device_enrollment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("two_factor_roles", sa.String(100), nullable=True))
    op.execute("UPDATE app_settings SET two_factor_roles = 'ADMIN,HR,SUPERVISOR' WHERE two_factor_required")
    op.drop_column("app_settings", "two_factor_required")


def downgrade() -> None:
    op.add_column("app_settings", sa.Column("two_factor_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Zurück auf den Schalter (Rollen-Konten); eine Pflicht nur für Mitarbeiter ohne Rolle geht dabei verloren
    op.execute(
        "UPDATE app_settings SET two_factor_required = TRUE WHERE two_factor_roles LIKE '%ADMIN%' "
        "OR two_factor_roles LIKE '%HR%' OR two_factor_roles LIKE '%SUPERVISOR%'"
    )
    op.drop_column("app_settings", "two_factor_roles")
