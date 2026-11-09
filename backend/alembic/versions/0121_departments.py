"""Abteilungen (hierarchisch), Position und Führungskraft am Mitarbeiter, Einstellung „Organigramm für
Mitarbeiter“, Audit-Aktion DEPARTMENT_CHANGED.

Revision ID: 0121_departments
Revises: 0120_two_factor
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0121_departments"
down_revision: Union[str, None] = "0120_two_factor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED', 'DEVICE_LOGIN_REJECTED', 'TWO_FACTOR_CHANGED']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "DEPARTMENT_CHANGED", name="auditaction")


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_departments_tenant_name"),
    )
    op.add_column("employees", sa.Column("department_id", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("position", sa.String(150), nullable=True))
    op.add_column("employees", sa.Column("supervisor_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_employees_department_id", "employees", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_employees_supervisor_id", "employees", "employees", ["supervisor_id"], ["id"], ondelete="SET NULL")
    op.add_column("app_settings", sa.Column("org_chart_for_employees", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM audit_log_entries WHERE action = 'DEPARTMENT_CHANGED'")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_column("app_settings", "org_chart_for_employees")
    op.drop_constraint("fk_employees_supervisor_id", "employees", type_="foreignkey")
    op.drop_constraint("fk_employees_department_id", "employees", type_="foreignkey")
    for column in ("supervisor_id", "position", "department_id"):
        op.drop_column("employees", column)
    op.drop_table("departments")
