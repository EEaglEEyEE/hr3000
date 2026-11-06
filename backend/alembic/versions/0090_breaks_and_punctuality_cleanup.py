"""Pausen und Pünktlichkeit aufräumen (ohne Verhaltensänderung für bestehende Firmen)

- Feste Minuten des Betriebs (FIXED_MINUTES) waren rechnerisch Zeilen der Pausenstaffel: sie werden
  zu Staffelzeilen (bei gleicher Schwelle gilt der größere Wert).
- Neu, je Firma schaltbar: Staffel darf die gesetzliche Mindestpause nach § 4 ArbZG nicht
  unterschreiten (an, wo die bisherige Staffel das Gesetz ohnehin erfüllt – sonst aus), Pausen genau
  nach § 4 rechnen und Pausenabzug höchstens bis zur Schwelle (jeweils "gilt ab"-Datum, leer = aus).
- Feste Minuten in Schichtvorlage/Arbeitszeitmodell bekommen eine Schwelle (0 = wie bisher).
- "Pünktlichkeit prüfen" war ein zweiter Schalter neben den Häkchen "Zu spät"/"Zu früh": aus wird
  zu abgeschalteten Hinweisen, der Schalter entfällt.
- Pünktlichkeits-Hinweise erst ab dem Tag der letzten Änderung (punctuality_from; leer = immer).

Revision ID: 0090_breaks_punctuality
Revises: 0089_absence_four_eyes
Create Date: 2026-11-06

"""
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0090_breaks_punctuality"
down_revision: Union[str, None] = "0089_absence_four_eyes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGAL = ((360, 30), (540, 45))


def _covers_law(rules: list[tuple[int, int]]) -> bool:
    """Erfüllt die Staffel die gesetzlichen Mindestwerte (bei jeder Arbeitszeit mindestens so viel)?"""
    def required(work: int, steps: list[tuple[int, int]]) -> int:
        return max((m for t, m in steps if work > t), default=0)

    return all(required(work, rules) >= required(work, list(_LEGAL)) for work in (361, 541, 600, 720))


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("legal_break_minimum", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_settings", sa.Column("break_precise_from", sa.Date(), nullable=True))
    op.add_column("app_settings", sa.Column("break_capped_from", sa.Date(), nullable=True))
    op.add_column("app_settings", sa.Column("punctuality_from", sa.Date(), nullable=True))
    op.add_column("shift_templates", sa.Column("min_break_after_minutes", sa.Integer(), nullable=False, server_default="0"))

    bind = op.get_bind()
    today = date.today()
    rules = bind.execute(
        sa.text("SELECT id, tenant_id, kind, min_work_minutes, deduct_minutes, valid_from, valid_to FROM break_rules")
    ).fetchall()

    # FIXED_MINUTES -> Staffelzeile
    for rule in [r for r in rules if r.kind == "FIXED_MINUTES"]:
        twin = next(
            (
                r for r in rules
                if r.kind == "LEGAL" and r.tenant_id == rule.tenant_id and r.min_work_minutes == rule.min_work_minutes
                and (r.valid_to is None or r.valid_to >= rule.valid_from) and (rule.valid_to is None or rule.valid_to >= r.valid_from)
            ),
            None,
        )
        if twin is None:
            bind.execute(sa.text("UPDATE break_rules SET kind = 'LEGAL' WHERE id = :id"), {"id": rule.id})
        else:
            bind.execute(
                sa.text("UPDATE break_rules SET deduct_minutes = :m WHERE id = :id"),
                {"id": twin.id, "m": max(twin.deduct_minutes, rule.deduct_minutes)},
            )
            bind.execute(sa.text("DELETE FROM break_rules WHERE id = :id"), {"id": rule.id})

    # Gesetzliche Mindestpause: an, wo die heute gültige Staffel das Gesetz schon erfüllt.
    rules = bind.execute(
        sa.text("SELECT tenant_id, kind, min_work_minutes, deduct_minutes, valid_from, valid_to FROM break_rules")
    ).fetchall()
    tenants = [row.tenant_id for row in bind.execute(sa.text("SELECT tenant_id FROM app_settings")).fetchall()]
    for tenant_id in tenants:
        current = [
            (r.min_work_minutes, r.deduct_minutes) for r in rules
            if r.tenant_id == tenant_id and r.kind == "LEGAL" and r.valid_from <= today and (r.valid_to is None or r.valid_to >= today)
        ]
        if _covers_law(current):
            bind.execute(sa.text("UPDATE app_settings SET legal_break_minimum = 1 WHERE tenant_id = :t"), {"t": tenant_id})

    # "Pünktlichkeit prüfen" aus -> Hinweise "zu spät"/"zu früh" abgeschaltet
    for row in bind.execute(sa.text("SELECT tenant_id, disabled_day_flags FROM app_settings WHERE punctuality_check = 0")).fetchall():
        flags = {f for f in (row.disabled_day_flags or "").split(",") if f} | {"LATE_ARRIVAL", "EARLY_LEAVE"}
        bind.execute(
            sa.text("UPDATE app_settings SET disabled_day_flags = :f WHERE tenant_id = :t"),
            {"f": ",".join(sorted(flags)), "t": row.tenant_id},
        )
    op.drop_column("app_settings", "punctuality_check")


def downgrade() -> None:
    op.add_column("app_settings", sa.Column("punctuality_check", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_column("shift_templates", "min_break_after_minutes")
    op.drop_column("app_settings", "punctuality_from")
    op.drop_column("app_settings", "break_capped_from")
    op.drop_column("app_settings", "break_precise_from")
    op.drop_column("app_settings", "legal_break_minimum")
