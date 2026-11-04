"""Feiertage mit mehreren Standorten: holiday_locations statt holidays.location_id

Revision ID: 0047_holiday_locations
Revises: 0046_smtp_settings_and_password_reset_audit
Create Date: 2026-10-12

Bisher stand ein Feiertag je Standort als eigene Zeile (holidays.location_id).
Jetzt steht er einmal da und wird über holiday_locations beliebig vielen
Standorten zugeordnet; keine Zuordnung = alle Standorte. Bestehende Zeilen
mit gleichem Mandanten, Datum und Namen werden zu einer Zeile zusammengeführt.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0047_holiday_locations"
down_revision: Union[str, None] = "0046_smtp_settings_and_password_reset_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "holiday_locations",
        sa.Column("holiday_id", sa.Integer(), sa.ForeignKey("holidays.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True),
    )

    rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, date, name, location_id FROM holidays "
            "WHERE location_id IS NOT NULL ORDER BY id"
        )
    ).fetchall()
    keeper_by_key: dict[tuple, int] = {}
    linked: set[tuple[int, int]] = set()
    for holiday_id, tenant_id, holiday_date, name, location_id in rows:
        keeper = keeper_by_key.setdefault((tenant_id, holiday_date, name), holiday_id)
        if (keeper, location_id) not in linked:
            linked.add((keeper, location_id))
            bind.execute(
                sa.text("INSERT INTO holiday_locations (holiday_id, location_id) VALUES (:h, :l)"),
                {"h": keeper, "l": location_id},
            )
        if keeper != holiday_id:
            bind.execute(sa.text("DELETE FROM holidays WHERE id = :id"), {"id": holiday_id})

    # Neuen Index zuerst anlegen: der tenant_id-Fremdschlüssel braucht auf MySQL
    # durchgehend einen stützenden Index, bevor der alte Mehrspalten-Index fällt.
    op.create_index("ix_holidays_tenant_date", "holidays", ["tenant_id", "date"])

    inspector = sa.inspect(bind)
    for foreign_key in inspector.get_foreign_keys("holidays"):
        if foreign_key["constrained_columns"] == ["location_id"] and foreign_key.get("name"):
            op.drop_constraint(foreign_key["name"], "holidays", type_="foreignkey")
    for index in inspector.get_indexes("holidays"):
        if "location_id" in index["column_names"] and index["name"] != "ix_holidays_tenant_date":
            op.drop_index(index["name"], table_name="holidays")
    op.drop_column("holidays", "location_id")


def downgrade() -> None:
    bind = op.get_bind()
    op.add_column("holidays", sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True))
    # Mehrfachzuordnungen lassen sich nicht verlustfrei zurückführen: je Feiertag
    # bleibt der erste Standort, die übrigen Zuordnungen gehen verloren.
    bind.execute(
        sa.text(
            "UPDATE holidays SET location_id = "
            "(SELECT MIN(location_id) FROM holiday_locations WHERE holiday_id = holidays.id)"
        )
    )
    op.drop_table("holiday_locations")
    op.create_index("ix_holidays_tenant_date_location", "holidays", ["tenant_id", "date", "location_id"])
    op.drop_index("ix_holidays_tenant_date", table_name="holidays")
