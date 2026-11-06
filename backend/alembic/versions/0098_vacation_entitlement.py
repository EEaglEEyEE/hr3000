"""Urlaubsanspruch dauerhaft im Vertrag statt je Jahr: Jahresurlaub je Vertragsabschnitt, das
Jahr wird berechnet (Teilzeit, Teilurlaub bei Ein-/Austritt); fest eingetragene Jahreswerte bleiben.

- employment_contracts.annual_vacation_days (leer = Standard-Jahresurlaub der Firma)
- leave_entitlements.entitled_manual: Jahreswert fest eingetragen. Bestehende Einträge bleiben fest
  (an bisherigen Jahren ändert sich nichts); neue Jahre werden berechnet.
- app_settings.prorate_partial_year_vacation: Teilurlaub bei Ein-/Austritt. Bestehende Mandanten
  aus (server_default false, bisher galt der volle Jahresurlaub); neue bekommen den ORM-Default (an).

Revision ID: 0098_vacation_entitlement
Revises: 0097_closure_three_states
Create Date: 2026-11-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0098_vacation_entitlement"
down_revision: Union[str, None] = "0097_closure_three_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employment_contracts", sa.Column("annual_vacation_days", sa.Numeric(5, 2), nullable=True))
    op.add_column("leave_entitlements", sa.Column("entitled_manual", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.get_bind().execute(sa.text("UPDATE leave_entitlements SET entitled_manual = 1"))
    op.add_column(
        "app_settings", sa.Column("prorate_partial_year_vacation", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("app_settings", "prorate_partial_year_vacation")
    op.drop_column("leave_entitlements", "entitled_manual")
    op.drop_column("employment_contracts", "annual_vacation_days")
