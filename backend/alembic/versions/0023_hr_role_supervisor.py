"""hr_users.role + employees.hr_role: SUPERVISOR hinzufügen

Revision ID: 0023_hr_role_supervisor
Revises: 0022_tenant_status_and_contact_fields
Create Date: 2026-08-12

employees.hr_role bekommt SUPERVISOR ebenfalls (Dual-Actor-Muster: ein
Supervisor kann ein eigener HrUser-Account ODER ein Mitarbeiter mit
hr_role sein, wie bei ADMIN/HR schon so gehandhabt) – aber bewusst NICHT
SUPER_ADMIN, das bleibt ausschließlich hr_users vorbehalten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_hr_role_supervisor"
down_revision: Union[str, None] = "0022_tenant_status_and_contact_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_HR_USER_ROLE_ENUM = sa.Enum("ADMIN", "HR", "SUPER_ADMIN", name="hrrole")
_NEW_HR_USER_ROLE_ENUM = sa.Enum("ADMIN", "HR", "SUPERVISOR", "SUPER_ADMIN", name="hrrole")

_OLD_EMPLOYEE_HR_ROLE_ENUM = sa.Enum("ADMIN", "HR", name="hrrole")
_NEW_EMPLOYEE_HR_ROLE_ENUM = sa.Enum("ADMIN", "HR", "SUPERVISOR", name="hrrole")


def upgrade() -> None:
    op.alter_column(
        "hr_users",
        "role",
        existing_type=_OLD_HR_USER_ROLE_ENUM,
        type_=_NEW_HR_USER_ROLE_ENUM,
        existing_nullable=False,
    )
    op.alter_column(
        "employees",
        "hr_role",
        existing_type=_OLD_EMPLOYEE_HR_ROLE_ENUM,
        type_=_NEW_EMPLOYEE_HR_ROLE_ENUM,
        existing_nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE employees SET hr_role = 'HR' WHERE hr_role = 'SUPERVISOR'")
    op.alter_column(
        "employees",
        "hr_role",
        existing_type=_NEW_EMPLOYEE_HR_ROLE_ENUM,
        type_=_OLD_EMPLOYEE_HR_ROLE_ENUM,
        existing_nullable=True,
    )
    op.execute("UPDATE hr_users SET role = 'HR' WHERE role = 'SUPERVISOR'")
    op.alter_column(
        "hr_users",
        "role",
        existing_type=_NEW_HR_USER_ROLE_ENUM,
        type_=_OLD_HR_USER_ROLE_ENUM,
        existing_nullable=False,
    )
