"""Arbeitszeitprofile: eigene Einträge je Mandant, die Mitarbeitern zugewiesen werden

- work_time_profiles (Name, archiviert) und work_time_profile_versions (effektiv-datierte Angaben
  wie eine Fassung der Arbeitszeit, dazu Gleitzeit-Rahmen und Pünktlichkeits-Toleranz)
- employee_default_shifts: profile_id (Zuweisung; leer = individuell), flex_frame_mode/-start/-end
  und late_tolerance_minutes (leer = wie in den Einstellungen)

Bestehende Fassungen bleiben individuell (profile_id leer) – am Verhalten ändert sich nichts.

Revision ID: 0101_work_time_profiles
Revises: 0100_punch_employee_time_index
Create Date: 2026-11-06 (umnummeriert 2026-11-07, zuletzt auf 0101)

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0101_work_time_profiles"
down_revision: Union[str, None] = "0100_punch_employee_time_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERIOD = sa.Enum("DAILY", "WEEKLY", "MONTHLY", name="targetperiod")
_BREAK = sa.Enum("FIXED", "FLEXIBLE", name="breakmode")


def upgrade() -> None:
    op.create_table(
        "work_time_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_work_time_profiles_name"),
    )
    op.create_table(
        "work_time_profile_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("work_time_profiles.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_templates.id"), nullable=True),
        sa.Column("weekdays_mask", sa.Integer(), nullable=False),
        sa.Column("day_minutes", sa.String(60), nullable=True),
        sa.Column("flexible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("on_demand", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("monthly_cap_minutes", sa.Integer(), nullable=True),
        sa.Column("target_minutes", sa.Integer(), nullable=True),
        sa.Column("target_period", _PERIOD, nullable=True),
        sa.Column("break_mode", _BREAK, nullable=True),
        sa.Column("fixed_break_start", sa.Time(), nullable=True),
        sa.Column("fixed_break_end", sa.Time(), nullable=True),
        sa.Column("min_break_minutes", sa.Integer(), nullable=True),
        sa.Column("min_break_after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("core_time_mode", sa.String(10), nullable=True),
        sa.Column("core_time_start", sa.Time(), nullable=True),
        sa.Column("core_time_end", sa.Time(), nullable=True),
        sa.Column("core_time_days", sa.String(100), nullable=True),
        sa.Column("flex_frame_mode", sa.String(10), nullable=True),
        sa.Column("flex_frame_start", sa.Time(), nullable=True),
        sa.Column("flex_frame_end", sa.Time(), nullable=True),
        sa.Column("late_tolerance_minutes", sa.Integer(), nullable=True),
    )
    op.create_index("ix_work_time_profile_versions_profile_id", "work_time_profile_versions", ["profile_id"])
    with op.batch_alter_table("employee_default_shifts") as batch:
        batch.add_column(sa.Column("flex_frame_mode", sa.String(10), nullable=True))
        batch.add_column(sa.Column("flex_frame_start", sa.Time(), nullable=True))
        batch.add_column(sa.Column("flex_frame_end", sa.Time(), nullable=True))
        batch.add_column(sa.Column("late_tolerance_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("profile_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_employee_default_shifts_profile_id", "work_time_profiles", ["profile_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("employee_default_shifts") as batch:
        batch.drop_constraint("fk_employee_default_shifts_profile_id", type_="foreignkey")
        batch.drop_column("profile_id")
        batch.drop_column("late_tolerance_minutes")
        batch.drop_column("flex_frame_end")
        batch.drop_column("flex_frame_start")
        batch.drop_column("flex_frame_mode")
    # Index nicht einzeln löschen: MySQL braucht ihn für den Fremdschlüssel, drop_table nimmt ihn mit.
    op.drop_table("work_time_profile_versions")
    op.drop_table("work_time_profiles")
