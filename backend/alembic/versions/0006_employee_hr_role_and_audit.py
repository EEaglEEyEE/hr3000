"""add employees.hr_role and created_by_employee_id audit columns

Revision ID: 0006_employee_hr_role_and_audit
Revises: 0005_employee_self_service_login
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_employee_hr_role_and_audit"
down_revision: Union[str, None] = "0005_employee_self_service_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees", sa.Column("hr_role", sa.Enum("ADMIN", "HR", name="hrrole"), nullable=True)
    )
    op.add_column("punches", sa.Column("created_by_employee_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_punches_created_by_employee_id", "punches", "employees", ["created_by_employee_id"], ["id"]
    )
    op.add_column("absences", sa.Column("created_by_employee_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_absences_created_by_employee_id", "absences", "employees", ["created_by_employee_id"], ["id"]
    )
    op.alter_column("absences", "created_by", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("absences", "created_by", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_absences_created_by_employee_id", "absences", type_="foreignkey")
    op.drop_column("absences", "created_by_employee_id")
    op.drop_constraint("fk_punches_created_by_employee_id", "punches", type_="foreignkey")
    op.drop_column("punches", "created_by_employee_id")
    op.drop_column("employees", "hr_role")
