"""employees.time_tracking – Zeiterfassung je Mitarbeiter abschaltbar.

Manche Mitarbeiter nutzen die Webapp (Abwesenheiten, Dokumente, Personaldaten), erfassen aber keine
Arbeitszeit. Für sie entfallen Soll/Ist/Gleitzeitkonto, Tablet und „Zu klären“ (Johannes, 17.11.2026).
Bestehende Mitarbeiter behalten die Zeiterfassung (server_default true).

Revision ID: 0166_employee_time_tracking
Revises: 0165_company_enrollment_key
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0166_employee_time_tracking"
down_revision: Union[str, None] = "0165_company_enrollment_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("time_tracking", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("employees", "time_tracking")
