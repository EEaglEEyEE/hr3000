"""Lohnarten an einer Stelle: Zulagenarten-Katalog und Lohnarten je Zeitart

- wage_type_mappings: Lohnart je Zeitart (gearbeitete Stunden, Urlaub, Krankheit, Kind krank,
  Sonderurlaub, Feiertag, Arbeitszeit-Angaben, ausgezahlte Überstunden). Die bisherige
  "Lohnart gearbeitete Stunden" (app_settings.datev_hours_wage_type) wird zur Zeile WORKED.
- pay_component_types: Zulagen- und Einmalzahlungsarten je Mandant mit Lohnart. Bestehende Zulagen
  bekommen eine Art je Name; hatte derselbe Name verschiedene Lohnarten, gibt es je Lohnart eine
  eigene Art (Name mit Lohnart in Klammern) – die DATEV-Datei bleibt so unverändert.
  pay_components.name/wage_type entfallen (stehen jetzt an der Art).

Revision ID: 0092_wage_types
Revises: 0091_version_contract
Create Date: 2026-11-06

"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0092_wage_types"
down_revision: Union[str, None] = "0091_version_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND = sa.Enum("ALLOWANCE", "ONE_TIME", name="paycomponentkind")


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "wage_type_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("item", sa.String(20), nullable=False),
        sa.Column("wage_type", sa.String(6), nullable=False),
        sa.UniqueConstraint("tenant_id", "item", name="uq_wage_type_mappings_item"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO wage_type_mappings (tenant_id, item, wage_type) "
            "SELECT tenant_id, 'WORKED', datev_hours_wage_type FROM app_settings "
            "WHERE datev_hours_wage_type IS NOT NULL AND datev_hours_wage_type <> ''"
        )
    )
    with op.batch_alter_table("app_settings") as batch:
        batch.drop_column("datev_hours_wage_type")

    op.create_table(
        "pay_component_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", _KIND, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("wage_type", sa.String(10), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", "name", name="uq_pay_component_types_name"),
    )
    with op.batch_alter_table("pay_components") as batch:
        batch.add_column(sa.Column("type_id", sa.Integer(), nullable=True))

    types = sa.Table(
        "pay_component_types",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer()),
        sa.Column("kind", sa.String(9)),
        sa.Column("name", sa.String(100)),
        sa.Column("wage_type", sa.String(10)),
        sa.Column("active", sa.Boolean()),
    )
    rows = bind.execute(sa.text("SELECT id, tenant_id, kind, name, wage_type FROM pay_components")).fetchall()
    wage_types_by_name: dict[tuple, set] = defaultdict(set)
    for row in rows:
        wage_types_by_name[(row.tenant_id, row.kind, row.name)].add(row.wage_type or None)
    created: dict[tuple, int] = {}
    for row in rows:
        key = (row.tenant_id, row.kind, row.name)
        wage_type = row.wage_type or None
        variant = key + (wage_type,)
        if variant not in created:
            name = row.name if len(wage_types_by_name[key]) == 1 else f"{row.name} ({wage_type or 'ohne Lohnart'})"[:100]
            result = bind.execute(
                types.insert().values(tenant_id=row.tenant_id, kind=row.kind, name=name, wage_type=wage_type, active=True)
            )
            created[variant] = result.inserted_primary_key[0]
        bind.execute(
            sa.text("UPDATE pay_components SET type_id = :type_id WHERE id = :id"), {"type_id": created[variant], "id": row.id}
        )

    with op.batch_alter_table("pay_components") as batch:
        batch.alter_column("type_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_pay_components_type", "pay_component_types", ["type_id"], ["id"])
        batch.drop_column("wage_type")
        batch.drop_column("name")


def downgrade() -> None:
    raise NotImplementedError("Zurück nur über die Sicherung vor dem Rollout (scripts/backup_db.sh).")
