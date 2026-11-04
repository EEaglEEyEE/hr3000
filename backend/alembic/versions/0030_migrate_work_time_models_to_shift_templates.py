"""Datenmigration: WorkTimeModel -> shift_templates + employee_default_shifts

Revision ID: 0030_migrate_work_time_models_to_shift_templates
Revises: 0029_app_settings_vacation_approval_required
Create Date: 2026-08-12

WorkTimeModel kennt nur weekly_hours + work_days_per_week, keine Wochentage
und keine Uhrzeiten. Diese Migration überführt jede bestehende Zeile in
eine äquivalente ShiftTemplate + EmployeeDefaultShift, mit einer klar
begrenzten Heuristik (siehe _MASK_BY_DAYS) statt geratener Annahmen –
alles, was sich nicht defensibel ableiten lässt, wird nicht migriert,
sondern am Ende als Blocker ausgegeben.

start_time/end_time bleiben bei allen generierten Vorlagen NULL (siehe
app/models/shift_template.py) – aus den Altdaten lassen sich keine echten
Schichtzeiten ableiten, ein erfundener Platzhalter wäre gefährlicher als
ein sichtbares NULL (würde später die ArbZG-Ruhezeitprüfung verfälschen).

Erzeugte Vorlagen werden pro (tenant_id, weekly_hours, work_days_per_week)
wiederverwendet (Name-Präfix "[MIGRIERT]"), nicht pro Mitarbeiter – der
Report listet pro Vorlage alle zugeordneten Mitarbeiter, falls HR sie
später trennen muss.
"""
from collections import defaultdict
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_migrate_work_time_models_to_shift_templates"
down_revision: Union[str, None] = "0029_app_settings_vacation_approval_required"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Nur diese drei Werte sind ohne Raten eindeutig auf Wochentage abbildbar.
# Bit 0 = Montag ... Bit 6 = Sonntag (siehe app/models/employee_default_shift.py).
_MASK_BY_DAYS = {5: 0b0011111, 6: 0b0111111, 7: 0b1111111}
_TEMPLATE_NAME_PREFIX = "[MIGRIERT]"


def upgrade() -> None:
    bind = op.get_bind()

    work_time_models = sa.table(
        "work_time_models",
        sa.column("id", sa.Integer),
        sa.column("employee_id", sa.Integer),
        sa.column("valid_from", sa.Date),
        sa.column("valid_to", sa.Date),
        sa.column("weekly_hours", sa.Numeric),
        sa.column("work_days_per_week", sa.Integer),
    )
    employees = sa.table(
        "employees",
        sa.column("id", sa.Integer),
        sa.column("tenant_id", sa.Integer),
        sa.column("first_name", sa.String),
        sa.column("last_name", sa.String),
    )
    shift_templates = sa.table(
        "shift_templates",
        sa.column("id", sa.Integer),
        sa.column("tenant_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("break_mode", sa.String),
        sa.column("target_minutes", sa.Integer),
    )
    employee_default_shifts = sa.table(
        "employee_default_shifts",
        sa.column("id", sa.Integer),
        sa.column("employee_id", sa.Integer),
        sa.column("shift_template_id", sa.Integer),
        sa.column("valid_from", sa.Date),
        sa.column("valid_to", sa.Date),
        sa.column("weekdays_mask", sa.Integer),
    )

    rows = bind.execute(
        sa.select(
            work_time_models.c.employee_id,
            work_time_models.c.valid_from,
            work_time_models.c.valid_to,
            work_time_models.c.weekly_hours,
            work_time_models.c.work_days_per_week,
            employees.c.tenant_id,
            employees.c.first_name,
            employees.c.last_name,
        ).select_from(employees.join(work_time_models, work_time_models.c.employee_id == employees.c.id))
    ).fetchall()

    if not rows:
        print("Keine WorkTimeModel-Zeilen vorhanden – nichts zu migrieren.")
        return

    # Overlap-Sicherheitscheck pro Mitarbeiter (Migrationsplan Abschnitt C.5):
    # nicht blind vertrauen, dass das bestehende App-seitige Overlap-Verbot
    # in jedem Bestand tatsächlich eingehalten wurde.
    by_employee: dict[int, list] = defaultdict(list)
    for row in rows:
        by_employee[row.employee_id].append(row)

    skip_employee_ids: set[int] = set()
    skipped_overlap: list[str] = []
    for employee_id, employee_rows in by_employee.items():
        ordered = sorted(employee_rows, key=lambda r: r.valid_from)
        for a, b in zip(ordered, ordered[1:]):
            a_end = a.valid_to or date.max
            if a_end >= b.valid_from:
                skip_employee_ids.add(employee_id)
                first = ordered[0]
                skipped_overlap.append(f"{first.first_name} {first.last_name} (employee_id={employee_id})")
                break

    template_cache: dict[tuple[int, str, int], int] = {}
    template_employees: dict[int, list[str]] = defaultdict(list)
    skipped_unknown_mask: list[str] = []
    drift_report: list[str] = []

    for row in rows:
        employee_label = f"{row.first_name} {row.last_name} (employee_id={row.employee_id})"
        if row.employee_id in skip_employee_ids:
            continue

        mask = _MASK_BY_DAYS.get(row.work_days_per_week)
        if mask is None:
            skipped_unknown_mask.append(
                f"{employee_label}: work_days_per_week={row.work_days_per_week} "
                "– keine eindeutige Wochentage-Zuordnung möglich"
            )
            continue

        weekly_minutes = float(row.weekly_hours) * 60
        target_minutes = round(weekly_minutes / row.work_days_per_week)
        drift = target_minutes * row.work_days_per_week - weekly_minutes
        if drift != 0:
            drift_report.append(
                f"{employee_label}: {row.weekly_hours}h / {row.work_days_per_week} Tage -> "
                f"{target_minutes} Min./Tag (Rundungsdrift {drift:+.0f} Min./Woche)"
            )

        cache_key = (row.tenant_id, str(row.weekly_hours), row.work_days_per_week)
        template_id = template_cache.get(cache_key)
        if template_id is None:
            template_name = f"{_TEMPLATE_NAME_PREFIX} {row.weekly_hours}h / {row.work_days_per_week} Tage"
            result = bind.execute(
                shift_templates.insert().values(
                    tenant_id=row.tenant_id,
                    name=template_name,
                    break_mode="FLEXIBLE",
                    target_minutes=target_minutes,
                )
            )
            template_id = result.inserted_primary_key[0]
            template_cache[cache_key] = template_id

        template_employees[template_id].append(employee_label)

        bind.execute(
            employee_default_shifts.insert().values(
                employee_id=row.employee_id,
                shift_template_id=template_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                weekdays_mask=mask,
            )
        )

    _print_report(template_employees, drift_report, skipped_unknown_mask, skipped_overlap)


def _print_report(
    template_employees: dict[int, list[str]],
    drift_report: list[str],
    skipped_unknown_mask: list[str],
    skipped_overlap: list[str],
) -> None:
    print("\n" + "=" * 78)
    print("Migration WorkTimeModel -> Schichtplanung (shift_templates/employee_default_shifts)")
    print("=" * 78)
    print("\nErzeugte Vorlagen:")
    for template_id, employee_labels in template_employees.items():
        print(f"  ShiftTemplate #{template_id}: {', '.join(employee_labels)}")

    if drift_report:
        print("\nRundungsdrift (Summe der Tagesziele weicht vom alten Wochen-Soll ab):")
        for line in drift_report:
            print(f"  - {line}")

    if skipped_unknown_mask:
        print("\nBLOCKER – work_days_per_week war nicht 5/6/7, KEINE Migration durchgeführt für:")
        for line in skipped_unknown_mask:
            print(f"  - {line}")
        print("  -> Für diese Mitarbeiter muss die Schichtzuordnung manuell in der HR-Webapp angelegt werden.")

    if skipped_overlap:
        print("\nBLOCKER – überlappende WorkTimeModel-Zeiträume gefunden, KOMPLETT übersprungen für:")
        for line in skipped_overlap:
            print(f"  - {line}")
        print("  -> Bestand vor manueller Nacherfassung prüfen.")

    print(
        "\nHinweis: Alle generierten Vorlagen haben KEINE echten Start-/Endzeiten "
        "(bewusst NULL, siehe app/models/shift_template.py) – die ArbZG-"
        "Ruhezeitprüfung (§5) greift erst, nachdem HR echte Zeiten pro Vorlage "
        "nachträgt."
    )
    print("=" * 78 + "\n")


def downgrade() -> None:
    op.execute(
        "DELETE FROM employee_default_shifts WHERE shift_template_id IN "
        f"(SELECT id FROM shift_templates WHERE name LIKE '{_TEMPLATE_NAME_PREFIX}%')"
    )
    op.execute(f"DELETE FROM shift_templates WHERE name LIKE '{_TEMPLATE_NAME_PREFIX}%'")
