"""Arbeitszeit-Fassung trägt den Vertrag selbst (statt versteckter, über den Namen geteilter Vorlagen)

Jede Fassung (employee_default_shifts) bekommt Soll (Minuten + Bezugszeitraum), eigene Pause und
Kernzeit. Eine Schichtvorlage ist nur noch für Uhrzeiten nötig (shift_template_id optional).
Datenübernahme ohne Verhaltensänderung:
- Fassungen mit versteckter Modellvorlage (is_work_time_model): Soll/Zeitraum/Pause aus der Vorlage
  in die Fassung kopieren, Vorlage lösen; nicht mehr benutzte Modellvorlagen löschen, noch von
  Tagesausnahmen benutzte archivieren (ausgeblendet). Danach entfällt is_work_time_model.
- Kernzeit des Mitarbeiters (wie Einstellungen / eigene / keine Prüfung) in alle seine Fassungen;
  danach entfällt die Kernzeit am Mitarbeiter (eine Stelle statt zwei).

Revision ID: 0091_version_contract
Revises: 0090_breaks_punctuality
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0091_version_contract"
down_revision: Union[str, None] = "0090_breaks_punctuality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERIOD = sa.Enum("DAILY", "WEEKLY", "MONTHLY", name="targetperiod")
_BREAK = sa.Enum("FIXED", "FLEXIBLE", name="breakmode")


def upgrade() -> None:
    with op.batch_alter_table("employee_default_shifts") as batch:
        batch.add_column(sa.Column("target_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("target_period", _PERIOD, nullable=True))
        batch.add_column(sa.Column("break_mode", _BREAK, nullable=True))
        batch.add_column(sa.Column("fixed_break_start", sa.Time(), nullable=True))
        batch.add_column(sa.Column("fixed_break_end", sa.Time(), nullable=True))
        batch.add_column(sa.Column("min_break_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("min_break_after_minutes", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("core_time_mode", sa.String(10), nullable=True))
        batch.add_column(sa.Column("core_time_start", sa.Time(), nullable=True))
        batch.add_column(sa.Column("core_time_end", sa.Time(), nullable=True))
        batch.add_column(sa.Column("core_time_days", sa.String(100), nullable=True))
        batch.alter_column("shift_template_id", existing_type=sa.Integer(), nullable=True)

    bind = op.get_bind()
    # 1) Modellvorlagen in die Fassungen übernehmen
    bind.execute(
        sa.text(
            "UPDATE employee_default_shifts SET "
            "target_minutes = (SELECT t.target_minutes FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id), "
            "target_period = (SELECT t.target_period FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id), "
            # Nur eine echte eigene Pause übernehmen (sonst NULL = Pausenregeln)
            "break_mode = (SELECT CASE WHEN t.break_mode = 'FIXED' AND t.fixed_break_start IS NOT NULL THEN 'FIXED' "
            "WHEN t.min_break_minutes > 0 THEN 'FLEXIBLE' ELSE NULL END "
            "FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id), "
            "fixed_break_start = (SELECT t.fixed_break_start FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id), "
            "fixed_break_end = (SELECT t.fixed_break_end FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id), "
            "min_break_minutes = (SELECT t.min_break_minutes FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id), "
            "min_break_after_minutes = (SELECT t.min_break_after_minutes FROM shift_templates t WHERE t.id = employee_default_shifts.shift_template_id) "
            "WHERE shift_template_id IN (SELECT id FROM shift_templates WHERE is_work_time_model = 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE employee_default_shifts SET shift_template_id = NULL "
            "WHERE shift_template_id IN (SELECT id FROM shift_templates WHERE is_work_time_model = 1)"
        )
    )
    # 2) Kernzeit des Mitarbeiters in alle seine Fassungen
    bind.execute(
        sa.text(
            "UPDATE employee_default_shifts SET "
            "core_time_mode = (SELECT e.core_time_mode FROM employees e WHERE e.id = employee_default_shifts.employee_id), "
            "core_time_start = (SELECT e.core_time_start FROM employees e WHERE e.id = employee_default_shifts.employee_id), "
            "core_time_end = (SELECT e.core_time_end FROM employees e WHERE e.id = employee_default_shifts.employee_id), "
            "core_time_days = (SELECT e.core_time_days FROM employees e WHERE e.id = employee_default_shifts.employee_id)"
        )
    )
    # 3) Nicht mehr benutzte Modellvorlagen entfernen, von Tagesausnahmen benutzte archivieren
    bind.execute(
        sa.text(
            "DELETE FROM shift_templates WHERE is_work_time_model = 1 "
            "AND id NOT IN (SELECT shift_template_id FROM employee_default_shifts WHERE shift_template_id IS NOT NULL) "
            "AND id NOT IN (SELECT shift_template_id FROM shift_plan_entries WHERE shift_template_id IS NOT NULL)"
        )
    )
    bind.execute(sa.text("UPDATE shift_templates SET archived = 1 WHERE is_work_time_model = 1"))
    with op.batch_alter_table("shift_templates") as batch:
        batch.drop_column("is_work_time_model")
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("core_time_days")
        batch.drop_column("core_time_end")
        batch.drop_column("core_time_start")
        batch.drop_column("core_time_mode")


def downgrade() -> None:
    raise NotImplementedError("Zurück nur über die Sicherung vor dem Rollout (scripts/backup_db.sh).")
