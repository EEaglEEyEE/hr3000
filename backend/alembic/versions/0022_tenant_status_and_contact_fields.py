"""tenants: is_active -> status ENUM(ACTIVE,TRIAL,SUSPENDED) + contact_email/contact_name/created_at

Revision ID: 0022_tenant_status_and_contact_fields
Revises: 0021_composite_unique_constraints
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_tenant_status_and_contact_fields"
down_revision: Union[str, None] = "0021_composite_unique_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_ENUM = sa.Enum("ACTIVE", "TRIAL", "SUSPENDED", name="tenantstatus")


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("status", _STATUS_ENUM, nullable=False, server_default="ACTIVE"),
    )
    op.execute("UPDATE tenants SET status = 'ACTIVE' WHERE is_active = 1")
    op.execute("UPDATE tenants SET status = 'SUSPENDED' WHERE is_active = 0")
    op.drop_column("tenants", "is_active")

    op.add_column("tenants", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("contact_name", sa.String(255), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_column("tenants", "created_at")
    op.drop_column("tenants", "contact_name")
    op.drop_column("tenants", "contact_email")

    op.add_column(
        "tenants", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.execute("UPDATE tenants SET is_active = (status != 'SUSPENDED')")
    op.drop_column("tenants", "status")
