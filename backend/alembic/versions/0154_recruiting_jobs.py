"""Recruiting: Schalter und Fristen je Firma, Stellen und Hiring Team.

Wiederholbar (MySQL führt DDL ohne Transaktion aus): jeder Schritt prüft erst den Stand.

Revision ID: 0154_recruiting_jobs
Revises: 0151_whistleblowing
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0154_recruiting_jobs"
down_revision: Union[str, None] = "0151_whistleblowing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SETTINGS = (
    ("recruiting_enabled", lambda: sa.Column("recruiting_enabled", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("recruiting_privacy_text", lambda: sa.Column("recruiting_privacy_text", sa.Text(), nullable=True)),
    ("recruiting_privacy_url", lambda: sa.Column("recruiting_privacy_url", sa.String(500), nullable=True)),
    ("recruiting_retention_months", lambda: sa.Column("recruiting_retention_months", sa.Integer(), nullable=False, server_default="6")),
    ("recruiting_talent_pool_months", lambda: sa.Column("recruiting_talent_pool_months", sa.Integer(), nullable=False, server_default="12")),
)


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    for name, column in _SETTINGS:
        if not _has_column(conn, "app_settings", name):
            op.add_column("app_settings", column())
    if not _has_table(conn, "recruiting_jobs"):
        op.create_table(
            "recruiting_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
            sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("employment_type", sa.String(20), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("application_deadline", sa.Date(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_recruiting_jobs_tenant_id", "recruiting_jobs", ["tenant_id"])
    if not _has_table(conn, "recruiting_job_members"):
        op.create_table(
            "recruiting_job_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("job_id", "account_id", name="uq_recruiting_job_members"),
        )
        op.create_index("ix_recruiting_job_members_job_id", "recruiting_job_members", ["job_id"])
        op.create_index("ix_recruiting_job_members_account_id", "recruiting_job_members", ["account_id"])


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("recruiting_job_members", "recruiting_jobs"):
        if _has_table(conn, table):
            op.drop_table(table)
    for name, _ in reversed(_SETTINGS):
        if _has_column(conn, "app_settings", name):
            op.drop_column("app_settings", name)
