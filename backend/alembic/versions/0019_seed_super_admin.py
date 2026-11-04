"""HrRole.SUPER_ADMIN im DB-Enum + Seed-Zeile für den plattformweiten Super-Admin

Revision ID: 0019_seed_super_admin
Revises: 0018_backfill_tenant_id
Create Date: 2026-08-11

Legt genau einen Super-Admin an (tenant_id=NULL, role=SUPER_ADMIN). Das
Passwort wird bei jedem Ausführen dieser Migration frisch generiert und
einmalig auf stdout ausgegeben (analog zu bisherigen Passwort-Resets in
diesem Projekt) – es wird nirgends im Klartext gespeichert.

"""
import os
import secrets
from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op

revision: str = "0019_seed_super_admin"
down_revision: Union[str, None] = "0018_backfill_tenant_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Per Env-Variable SUPER_ADMIN_EMAIL festlegen (siehe .env.example).
_SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL") or "admin@example.com"
_OLD_ROLE_ENUM = sa.Enum("ADMIN", "HR", name="hrrole")
_NEW_ROLE_ENUM = sa.Enum("ADMIN", "HR", "SUPER_ADMIN", name="hrrole")


def upgrade() -> None:
    op.alter_column(
        "hr_users",
        "role",
        existing_type=_OLD_ROLE_ENUM,
        type_=_NEW_ROLE_ENUM,
        existing_nullable=False,
    )

    password = secrets.token_urlsafe(18)
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    op.bulk_insert(
        sa.table(
            "hr_users",
            sa.column("tenant_id", sa.Integer()),
            sa.column("email", sa.String()),
            sa.column("password_hash", sa.String()),
            sa.column("role", sa.String()),
        ),
        [
            {
                "tenant_id": None,
                "email": _SUPER_ADMIN_EMAIL,
                "password_hash": password_hash,
                "role": "SUPER_ADMIN",
            }
        ],
    )

    print(
        "\n"
        "==================================================================\n"
        f"Super-Admin angelegt: {_SUPER_ADMIN_EMAIL}\n"
        "Einmaliges Passwort (jetzt sichern, wird nicht erneut angezeigt):\n"
        f"  {password}\n"
        "==================================================================\n"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM hr_users WHERE email = :email"), {"email": _SUPER_ADMIN_EMAIL})

    op.alter_column(
        "hr_users",
        "role",
        existing_type=_NEW_ROLE_ENUM,
        type_=_OLD_ROLE_ENUM,
        existing_nullable=False,
    )
