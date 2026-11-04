"""teams + supervisor_team_assignments + employees.team_id

Revision ID: 0024_create_teams_and_supervisor_assignments
Revises: 0023_hr_role_supervisor
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_create_teams_and_supervisor_assignments"
down_revision: Union[str, None] = "0023_hr_role_supervisor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
    )

    op.create_table(
        "supervisor_team_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.CheckConstraint(
            "(hr_user_id IS NOT NULL) <> (employee_id IS NOT NULL)",
            name="ck_supervisor_team_assignment_exactly_one_actor",
        ),
    )

    op.add_column("employees", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_employees_team_id_teams", "employees", "teams", ["team_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_employees_team_id_teams", "employees", type_="foreignkey")
    op.drop_column("employees", "team_id")
    op.drop_table("supervisor_team_assignments")
    op.drop_table("teams")
