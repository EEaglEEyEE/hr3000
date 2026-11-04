"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Revisions-IDs dieses Projekts sind länger als Alembics Standard VARCHAR(32)
    # (bis 58 Zeichen) – auf MySQL scheitert sonst schon 0004 mit "Data too long".
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE alembic_version MODIFY version_num VARCHAR(255) NOT NULL")

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
    )

    op.create_table(
        "hr_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "HR", name="hrrole"), nullable=False),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("device_token", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("device_token"),
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("employee_number", sa.String(50), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pin_hash", sa.String(255), nullable=True),
        sa.UniqueConstraint("employee_number"),
    )

    op.create_table(
        "work_time_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("hours_monday", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("hours_tuesday", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("hours_wednesday", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("hours_thursday", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("hours_friday", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("hours_saturday", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("hours_sunday", sa.Numeric(4, 2), nullable=False, server_default="0"),
    )

    op.create_table(
        "break_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("min_work_minutes", sa.Integer(), nullable=False),
        sa.Column("deduct_minutes", sa.Integer(), nullable=False),
    )

    op.create_table(
        "overtime_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("balance_date", sa.Date(), nullable=False),
        sa.Column("daily_target_minutes", sa.Integer(), nullable=False),
        sa.Column("daily_actual_minutes", sa.Integer(), nullable=False),
        sa.Column("daily_delta_minutes", sa.Integer(), nullable=False),
        sa.Column("running_balance_minutes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("employee_id", "balance_date"),
    )

    op.create_table(
        "punches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column(
            "punch_type",
            sa.Enum("COME", "GO", "BREAK_START", "BREAK_END", name="punchtype"),
            nullable=False,
        ),
        sa.Column("timestamp_utc", sa.DateTime(), nullable=False),
        sa.Column("source", sa.Enum("KIOSK", "MANUAL_HR", name="punchsource"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("correction_reason", sa.String(500), nullable=True),
    )

    op.create_table(
        "daily_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("target_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", name="summarystatus"),
            nullable=False,
        ),
        sa.UniqueConstraint("employee_id", "work_date"),
    )

    op.create_table(
        "absences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column(
            "type",
            sa.Enum("VACATION", "SICK", "SPECIAL_LEAVE", name="absencetype"),
            nullable=False,
        ),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("absences")
    op.drop_table("daily_summaries")
    op.drop_table("punches")
    op.drop_table("overtime_balances")
    op.drop_table("break_rules")
    op.drop_table("work_time_models")
    op.drop_table("employees")
    op.drop_table("devices")
    op.drop_table("hr_users")
    op.drop_table("locations")
