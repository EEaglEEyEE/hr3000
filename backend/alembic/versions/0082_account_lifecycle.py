"""Kündigung/Löschung von Firmen, E-Mail-Bestätigung bei Selbstregistrierung, Einmal-Links
(Passwort vergessen, E-Mail bestätigen)

Revision ID: 0082_account_lifecycle
Revises: 0081_tenant_self_signup
Create Date: 2026-11-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0082_account_lifecycle"
down_revision: Union[str, None] = "0081_tenant_self_signup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Kündigung: Zeitpunkt, Vertragsende (Monatsende), Löschtermin (Vertragsende + 30 Tage).
    op.add_column("tenants", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("tenants", sa.Column("contract_end", sa.Date(), nullable=True))
    op.add_column("tenants", sa.Column("deletion_due_on", sa.Date(), nullable=True))
    # Nur bei Selbstregistrierung mit Mailversand: Login erst nach Klick auf den Bestätigungslink.
    op.add_column(
        "hr_users",
        sa.Column("email_verification_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        # SHA-256 des Links – der Link selbst wird nie gespeichert.
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("account_tokens")
    op.drop_column("hr_users", "email_verification_pending")
    op.drop_column("tenants", "deletion_due_on")
    op.drop_column("tenants", "contract_end")
    op.drop_column("tenants", "cancelled_at")
