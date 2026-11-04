"""Effektiv-Datierung: Pausenregeln (gültig ab/bis), archivierte Schichtvorlagen, Standort-Historie

Revision ID: 0054_effective_dated_rules_and_locations
Revises: 0053_balance_rebuild_and_adjustments
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0054_effective_dated_rules_and_locations"
down_revision: Union[str, None] = "0053_balance_rebuild_and_adjustments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("break_rules", sa.Column("valid_from", sa.Date(), nullable=False, server_default=sa.text("'2000-01-01'")))
    op.add_column("break_rules", sa.Column("valid_to", sa.Date(), nullable=True))
    # Der Fremdschlüssel auf tenant_id braucht in MySQL einen Index – erst den neuen anlegen,
    # dann die Eindeutigkeit (gleiche Schwelle in verschiedenen Zeiträumen ist jetzt erlaubt) entfernen.
    op.create_index("ix_break_rules_tenant", "break_rules", ["tenant_id"])
    op.drop_constraint("uq_break_rules_tenant_threshold", "break_rules", type_="unique")

    op.add_column("shift_templates", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "employee_location_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
    )
    op.create_index("ix_employee_location_periods_employee", "employee_location_periods", ["employee_id", "valid_from"])


def downgrade() -> None:
    op.drop_index("ix_employee_location_periods_employee", table_name="employee_location_periods")
    op.drop_table("employee_location_periods")
    op.drop_column("shift_templates", "archived")
    op.create_unique_constraint("uq_break_rules_tenant_threshold", "break_rules", ["tenant_id", "min_work_minutes"])
    op.drop_index("ix_break_rules_tenant", table_name="break_rules")
    op.drop_column("break_rules", "valid_to")
    op.drop_column("break_rules", "valid_from")
