"""employees: nfc_uid (NFC/RFID-Karte als Alternative zum PIN)

Revision ID: 0014_employee_nfc_uid
Revises: 0013_app_settings_bundesland
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_employee_nfc_uid"
down_revision: Union[str, None] = "0013_app_settings_bundesland"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("nfc_uid", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_employees_nfc_uid", "employees", ["nfc_uid"])


def downgrade() -> None:
    op.drop_constraint("uq_employees_nfc_uid", "employees", type_="unique")
    op.drop_column("employees", "nfc_uid")
