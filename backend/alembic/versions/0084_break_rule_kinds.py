"""Pausenregeln: neben der gesetzlichen Staffel feste Pausenminuten und feste Pausenzeiten

Revision ID: 0084_break_rule_kinds
Revises: 0083_days_without_punches_switch
Create Date: 2026-11-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0084_break_rule_kinds"
down_revision: Union[str, None] = "0083_days_without_punches_switch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND = sa.Enum("LEGAL", "FIXED_MINUTES", "FIXED_WINDOW", name="breakrulekind")


def upgrade() -> None:
    _KIND.create(op.get_bind(), checkfirst=True)
    # Bestehende Regeln sind die gesetzliche Staffel – am Verhalten ändert sich nichts.
    op.add_column("break_rules", sa.Column("kind", _KIND, nullable=False, server_default="LEGAL"))
    op.add_column("break_rules", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("break_rules", sa.Column("end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("break_rules", "end_time")
    op.drop_column("break_rules", "start_time")
    op.drop_column("break_rules", "kind")
    _KIND.drop(op.get_bind(), checkfirst=True)
