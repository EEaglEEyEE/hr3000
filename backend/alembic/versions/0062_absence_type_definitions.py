"""Eigene Abwesenheitsarten je Mandant (Name, Farbe, Kategorie, Genehmigung, Nachweis)

Revision ID: 0062_absence_type_definitions
Revises: 0061_rfid_required
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0062_absence_type_definitions"
down_revision: Union[str, None] = "0061_rfid_required"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = sa.Enum("VACATION", "SICK", "SPECIAL_LEAVE", name="absencetype")
_NEW = sa.Enum("VACATION", "SICK", "SPECIAL_LEAVE", "UNPAID", "TIME_OFF_IN_LIEU", name="absencetype")

# (Name, Farbe, Kategorie, Nachweis ab Tag, Reihenfolge) – wie app/services/absence_type_service.py DEFAULT_TYPES
_DEFAULTS = [
    ("Urlaub", "#10b981", "VACATION", None, 0),
    ("Krank", "#ef4444", "SICK", 4, 1),
    ("Sonderurlaub", "#64748b", "SPECIAL_LEAVE", None, 2),
    ("Freizeitausgleich", "#0ea5e9", "TIME_OFF_IN_LIEU", None, 3),
    ("Unbezahlt", "#a855f7", "UNPAID", None, 4),
]


def upgrade() -> None:
    op.alter_column("absences", "type", existing_type=_OLD, type_=_NEW, existing_nullable=False)
    op.create_table(
        "absence_type_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("color", sa.String(7), nullable=False, server_default="#64748b"),
        sa.Column("category", _NEW, nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("employee_can_request", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("certificate_from_day", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_absence_type_definitions_tenant_name"),
    )
    op.create_index("ix_absence_type_definitions_tenant_id", "absence_type_definitions", ["tenant_id"])
    op.add_column("absences", sa.Column("absence_type_id", sa.Integer(), nullable=True))
    op.create_index("ix_absences_absence_type_id", "absences", ["absence_type_id"])
    op.create_foreign_key(
        "fk_absences_absence_type_id", "absences", "absence_type_definitions", ["absence_type_id"], ["id"]
    )

    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM tenants")).scalars().all()
    for tenant_id in tenants:
        approval = conn.execute(
            sa.text("SELECT vacation_approval_required FROM app_settings WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar()
        for name, color, category, certificate, order in _DEFAULTS:
            conn.execute(
                sa.text(
                    "INSERT INTO absence_type_definitions "
                    "(tenant_id, name, color, category, requires_approval, employee_can_request, "
                    "certificate_from_day, active, sort_order) "
                    "VALUES (:t, :n, :c, :cat, :appr, 1, :cert, 1, :o)"
                ),
                {
                    "t": tenant_id,
                    "n": name,
                    "c": color,
                    "cat": category,
                    "appr": bool(approval) and category == "VACATION",
                    "cert": certificate,
                    "o": order,
                },
            )
        # Bestehende Abwesenheiten der Standardart ihrer Kategorie zuordnen.
        for _, _, category, _, _ in _DEFAULTS[:3]:
            type_id = conn.execute(
                sa.text("SELECT id FROM absence_type_definitions WHERE tenant_id = :t AND category = :cat"),
                {"t": tenant_id, "cat": category},
            ).scalar()
            conn.execute(
                sa.text(
                    "UPDATE absences SET absence_type_id = :id WHERE type = :cat AND employee_id IN "
                    "(SELECT id FROM employees WHERE tenant_id = :t)"
                ),
                {"id": type_id, "cat": category, "t": tenant_id},
            )
    # Die Urlaubsgenehmigung steckt jetzt in der Abwesenheitsart "Urlaub".
    conn.execute(sa.text("UPDATE app_settings SET vacation_approval_required = 0"))


def downgrade() -> None:
    op.drop_constraint("fk_absences_absence_type_id", "absences", type_="foreignkey")
    op.drop_index("ix_absences_absence_type_id", table_name="absences")
    op.drop_column("absences", "absence_type_id")
    op.drop_index("ix_absence_type_definitions_tenant_id", table_name="absence_type_definitions")
    op.drop_table("absence_type_definitions")
    op.alter_column("absences", "type", existing_type=_NEW, type_=_OLD, existing_nullable=False)
