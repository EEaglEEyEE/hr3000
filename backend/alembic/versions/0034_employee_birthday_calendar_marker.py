"""employees.birth_date/show_birthday_in_calendar + app_settings.show_birthdays_in_calendar

Revision ID: 0034_employee_birthday_calendar_marker
Revises: 0033_app_settings_default_annual_vacation_days
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_employee_birthday_calendar_marker"
down_revision: Union[str, None] = "0033_app_settings_default_annual_vacation_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column(
        "employees",
        sa.Column("show_birthday_in_calendar", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "app_settings",
        sa.Column("show_birthdays_in_calendar", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "show_birthdays_in_calendar")
    op.drop_column("employees", "show_birthday_in_calendar")
    op.drop_column("employees", "birth_date")
