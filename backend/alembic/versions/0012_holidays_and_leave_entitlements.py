"""Feiertage (holidays), Urlaubsanspruch (leave_entitlements) + SummaryStatus.HOLIDAY

Revision ID: 0012_holidays_and_leave_entitlements
Revises: 0011_summary_status_break_error
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_holidays_and_leave_entitlements"
down_revision: Union[str, None] = "0011_summary_status_break_error"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_VALUES = ("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", "ON_BREAK", "ERROR")
_NEW_VALUES = (*_OLD_VALUES, "HOLIDAY")


def upgrade() -> None:
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Kein unique=True: mit standortbezogenen Feiertagen (siehe Migration
        # 0015) sind mehrere Zeilen mit demselben Datum zulässig. Eindeutigkeit
        # wird anwendungsseitig geprüft, siehe app/api/holidays.py.
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "leave_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("entitled_days", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("carried_over_days", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("employee_id", "year", name="uq_leave_entitlements_employee_year"),
    )
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum(*_OLD_VALUES, name="summarystatus"),
        type_=sa.Enum(*_NEW_VALUES, name="summarystatus"),
    )


def downgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum(*_NEW_VALUES, name="summarystatus"),
        type_=sa.Enum(*_OLD_VALUES, name="summarystatus"),
    )
    op.drop_table("leave_entitlements")
    op.drop_table("holidays")
