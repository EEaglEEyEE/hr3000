"""Recruiting: Bewerbungen, Anhänge, Notizen, Bewertungen, Verlauf und anonyme Zählung.

Wiederholbar: jede Tabelle wird nur angelegt, wenn sie fehlt.

Revision ID: 0155_recruiting_applications
Revises: 0154_recruiting_jobs
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0155_recruiting_applications"
down_revision: Union[str, None] = "0154_recruiting_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False)


def _application() -> sa.Column:
    return sa.Column(
        "application_id", sa.Integer(), sa.ForeignKey("recruiting_applications.id", ondelete="CASCADE"), nullable=False
    )


def _account(name: str, *, ondelete: str, nullable: bool) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("accounts.id", ondelete=ondelete), nullable=nullable)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "recruiting_applications"):
        op.create_table(
            "recruiting_applications",
            sa.Column("id", sa.Integer(), primary_key=True),
            _tenant(),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("first_name", sa.String(100), nullable=False),
            sa.Column("last_name", sa.String(100), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(40), nullable=True),
            sa.Column("cover_letter_encrypted", sa.Text(), nullable=True),
            sa.Column("salary_expectation_encrypted", sa.Text(), nullable=True),
            sa.Column("stage", sa.String(12), nullable=False),
            sa.Column("source", sa.String(12), nullable=False),
            sa.Column("rejection_reason", sa.String(20), nullable=True),
            sa.Column("rejection_note", sa.String(500), nullable=True),
            sa.Column("talent_pool", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("privacy_acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
            sa.Column("hired_at", sa.DateTime(), nullable=True),
            _account("created_by_account_id", ondelete="SET NULL", nullable=True),
            _created(),
        )
        op.create_index("ix_recruiting_applications_tenant_id", "recruiting_applications", ["tenant_id"])
        op.create_index("ix_recruiting_applications_job_id", "recruiting_applications", ["job_id"])
        op.create_index("ix_recruiting_applications_stage", "recruiting_applications", ["stage"])
    if not _has_table(conn, "recruiting_attachments"):
        op.create_table(
            "recruiting_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            _tenant(),
            _application(),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("storage_key", sa.String(64), nullable=False, unique=True),
            _created(),
        )
        op.create_index("ix_recruiting_attachments_tenant_id", "recruiting_attachments", ["tenant_id"])
        op.create_index("ix_recruiting_attachments_application_id", "recruiting_attachments", ["application_id"])
    if not _has_table(conn, "recruiting_notes"):
        op.create_table(
            "recruiting_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            _tenant(),
            _application(),
            _account("author_account_id", ondelete="SET NULL", nullable=True),
            sa.Column("body_encrypted", sa.Text(), nullable=False),
            _created(),
        )
        op.create_index("ix_recruiting_notes_application_id", "recruiting_notes", ["application_id"])
    if not _has_table(conn, "recruiting_ratings"):
        op.create_table(
            "recruiting_ratings",
            sa.Column("id", sa.Integer(), primary_key=True),
            _tenant(),
            _application(),
            _account("account_id", ondelete="CASCADE", nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("comment_encrypted", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("application_id", "account_id", name="uq_recruiting_ratings"),
        )
        op.create_index("ix_recruiting_ratings_application_id", "recruiting_ratings", ["application_id"])
    if not _has_table(conn, "recruiting_stage_events"):
        op.create_table(
            "recruiting_stage_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            _tenant(),
            _application(),
            sa.Column("from_stage", sa.String(12), nullable=True),
            sa.Column("to_stage", sa.String(12), nullable=False),
            _account("account_id", ondelete="SET NULL", nullable=True),
            _created(),
        )
        op.create_index("ix_recruiting_stage_events_application_id", "recruiting_stage_events", ["application_id"])
    if not _has_table(conn, "recruiting_stats"):
        op.create_table(
            "recruiting_stats",
            sa.Column("id", sa.Integer(), primary_key=True),
            _tenant(),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stage", sa.String(12), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False),
            sa.UniqueConstraint("job_id", "stage", name="uq_recruiting_stats"),
        )
        op.create_index("ix_recruiting_stats_job_id", "recruiting_stats", ["job_id"])


def downgrade() -> None:
    conn = op.get_bind()
    for table in (
        "recruiting_stats",
        "recruiting_stage_events",
        "recruiting_ratings",
        "recruiting_notes",
        "recruiting_attachments",
        "recruiting_applications",
    ):
        if _has_table(conn, table):
            op.drop_table(table)
