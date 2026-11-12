"""Standort beim Stempeln (A18): Schalter und Modus je Firma, Kreis (Mittelpunkt, Radius) je Standort und
das Ergebnis der Prüfung an der Stempelung (innerhalb/außerhalb/unbekannt, ggf. Standort). Koordinaten von
Mitarbeitern werden nie gespeichert – es gibt dafür bewusst keine Spalte.

Bestehende Firmen: Prüfung aus, Modus „nur vermerken“; Standorte ohne Kreis; Stempelungen ungeprüft (NULL).
Der Ergebnis-Enum ist neu (eigener Typ) – keine bestehende Werteliste wird verändert.

Revision ID: 0161_punch_location
Revises: 0158_project_times
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0161_punch_location"
down_revision: Union[str, None] = "0158_project_times"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK = sa.Enum("INSIDE", "OUTSIDE", "UNKNOWN", name="punchlocationcheck")
_FK = "fk_punches_location_check_location_id"


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("punch_location_check_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "app_settings",
        sa.Column("punch_location_mode", sa.String(10), nullable=False, server_default="RECORD"),
    )
    op.add_column("locations", sa.Column("geo_latitude", sa.Double(), nullable=True))
    op.add_column("locations", sa.Column("geo_longitude", sa.Double(), nullable=True))
    op.add_column("locations", sa.Column("geo_radius_m", sa.Integer(), nullable=True))
    op.add_column("punches", sa.Column("location_check", _CHECK, nullable=True))
    op.add_column("punches", sa.Column("location_check_location_id", sa.Integer(), nullable=True))
    if op.get_bind().dialect.name == "mysql":
        # SQLite kann keine Fremdschlüssel nachträglich anlegen (nur die Migrationstests laufen dort).
        op.create_foreign_key(_FK, "punches", "locations", ["location_check_location_id"], ["id"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.drop_constraint(_FK, "punches", type_="foreignkey")
    op.drop_column("punches", "location_check_location_id")
    op.drop_column("punches", "location_check")
    for column in ("geo_radius_m", "geo_longitude", "geo_latitude"):
        op.drop_column("locations", column)
    op.drop_column("app_settings", "punch_location_mode")
    op.drop_column("app_settings", "punch_location_check_enabled")
