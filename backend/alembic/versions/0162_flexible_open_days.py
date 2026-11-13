"""Flexible Arbeitszeitmodelle unter „Zu klären“: Schalter „Tage flexibler Modelle melden“ je Firma, neuer
Hinweis „Wochensoll nicht erreicht“ (samt Stichtag, ab dem er gilt) und im Tages-Cache die Kennung
„Tag wird nicht gemeldet“.

Bestehende Firmen behalten ihr Verhalten: Tage flexibler Modelle werden weiter gemeldet (Schalter an), der
neue Hinweis ist aus – er wird bei jeder Firma in die Liste der abgeschalteten Sonderfälle eingetragen.

Revision ID: 0162_flexible_open_days
Revises: 0161_punch_location
Create Date: 2026-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0162_flexible_open_days"
down_revision: Union[str, None] = "0161_punch_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FLAG = "WEEKLY_TARGET_MISSED"
_settings = sa.table("app_settings", sa.column("id", sa.Integer), sa.column("disabled_day_flags", sa.String))


def _rewrite_flags(change) -> None:
    bind = op.get_bind()
    for row_id, raw in bind.execute(sa.select(_settings.c.id, _settings.c.disabled_day_flags)).all():
        flags = change({flag for flag in (raw or "").split(",") if flag})
        bind.execute(
            _settings.update().where(_settings.c.id == row_id).values(disabled_day_flags=",".join(sorted(flags)) or None)
        )


def upgrade() -> None:
    op.add_column(
        "app_settings", sa.Column("report_flexible_days", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column("app_settings", sa.Column("weekly_target_from", sa.Date(), nullable=True))
    op.add_column(
        "daily_summaries", sa.Column("review_exempt", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    _rewrite_flags(lambda flags: flags | {_FLAG})


def downgrade() -> None:
    _rewrite_flags(lambda flags: flags - {_FLAG})
    op.drop_column("daily_summaries", "review_exempt")
    op.drop_column("app_settings", "weekly_target_from")
    op.drop_column("app_settings", "report_flexible_days")
