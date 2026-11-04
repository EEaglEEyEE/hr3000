"""Globale Unique-Constraints -> (tenant_id, spalte)

Revision ID: 0021_composite_unique_constraints
Revises: 0020_tenant_id_not_null_and_fks
Create Date: 2026-08-11

Betroffen: hr_users.email, employees.employee_number/nfc_uid/login_email,
devices.device_token, work_time_model_templates.name (+ neu:
break_rules(tenant_id, min_work_minutes), die vorher keine eigene
Unique-Constraint hatte).

Für die Spalten, deren Alt-Constraint 2026-08-10 unbenannt über
op.create_table(...) bzw. Column(unique=True) angelegt wurde (email,
employee_number, device_token, name), wird der tatsächliche Indexname zur
Laufzeit über information_schema ermittelt statt geraten – MySQL vergibt
bei unbenannten Unique-Constraints selbst einen Namen, der nicht zwingend
dem Spaltennamen entspricht.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_composite_unique_constraints"
down_revision: Union[str, None] = "0020_tenant_id_not_null_and_fks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _find_unique_index_name(bind, table: str, column: str) -> str:
    result = bind.execute(
        sa.text(
            """
            SELECT INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table
              AND COLUMN_NAME = :column
              AND NON_UNIQUE = 0
              AND SEQ_IN_INDEX = 1
              AND INDEX_NAME != 'PRIMARY'
            LIMIT 1
            """
        ),
        {"table": table, "column": column},
    ).scalar()
    if result is None:
        raise RuntimeError(f"Kein Unique-Index für {table}.{column} gefunden.")
    return result


def upgrade() -> None:
    bind = op.get_bind()

    old_name = _find_unique_index_name(bind, "hr_users", "email")
    op.drop_constraint(old_name, "hr_users", type_="unique")
    op.create_unique_constraint("uq_hr_users_tenant_email", "hr_users", ["tenant_id", "email"])

    old_name = _find_unique_index_name(bind, "employees", "employee_number")
    op.drop_constraint(old_name, "employees", type_="unique")
    op.create_unique_constraint(
        "uq_employees_tenant_number", "employees", ["tenant_id", "employee_number"]
    )

    op.drop_constraint("uq_employees_nfc_uid", "employees", type_="unique")
    op.create_unique_constraint(
        "uq_employees_tenant_nfc_uid", "employees", ["tenant_id", "nfc_uid"]
    )

    op.drop_constraint("uq_employees_login_email", "employees", type_="unique")
    op.create_unique_constraint(
        "uq_employees_tenant_login_email", "employees", ["tenant_id", "login_email"]
    )

    old_name = _find_unique_index_name(bind, "devices", "device_token")
    op.drop_constraint(old_name, "devices", type_="unique")
    op.create_unique_constraint("uq_devices_tenant_token", "devices", ["tenant_id", "device_token"])

    old_name = _find_unique_index_name(bind, "work_time_model_templates", "name")
    op.drop_constraint(old_name, "work_time_model_templates", type_="unique")
    op.create_unique_constraint(
        "uq_work_time_model_templates_tenant_name",
        "work_time_model_templates",
        ["tenant_id", "name"],
    )

    op.create_unique_constraint(
        "uq_break_rules_tenant_threshold", "break_rules", ["tenant_id", "min_work_minutes"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_break_rules_tenant_threshold", "break_rules", type_="unique")

    op.drop_constraint(
        "uq_work_time_model_templates_tenant_name", "work_time_model_templates", type_="unique"
    )
    op.create_unique_constraint("name", "work_time_model_templates", ["name"])

    op.drop_constraint("uq_devices_tenant_token", "devices", type_="unique")
    op.create_unique_constraint("device_token", "devices", ["device_token"])

    op.drop_constraint("uq_employees_tenant_login_email", "employees", type_="unique")
    op.create_unique_constraint("uq_employees_login_email", "employees", ["login_email"])

    op.drop_constraint("uq_employees_tenant_nfc_uid", "employees", type_="unique")
    op.create_unique_constraint("uq_employees_nfc_uid", "employees", ["nfc_uid"])

    op.drop_constraint("uq_employees_tenant_number", "employees", type_="unique")
    op.create_unique_constraint("employee_number", "employees", ["employee_number"])

    op.drop_constraint("uq_hr_users_tenant_email", "hr_users", type_="unique")
    op.create_unique_constraint("email", "hr_users", ["email"])
