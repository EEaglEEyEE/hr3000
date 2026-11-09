from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.absence import AbsenceType
from app.models.base import Base


class AbsenceTypeDefinition(Base):
    """Vom Mandanten definierte Abwesenheitsart (z.B. "Kind krank", "Berufsschule",
    "Elternzeit"). Die Kategorie (AbsenceType) legt fest, wie der Tag zählt, siehe
    app/services/absence_type_service.py credit_for_absence:

    - VACATION / SICK / SPECIAL_LEAVE: Soll wird gutgeschrieben (Saldo neutral);
      VACATION zieht zusätzlich Urlaubstage ab.
    - UNPAID: Soll entfällt (unbezahlt, Saldo neutral, keine bezahlten Stunden).
    - TIME_OFF_IN_LIEU: Freizeitausgleich – Soll bleibt, nichts wird gutgeschrieben,
      der Saldo sinkt um das Tagessoll."""

    __tablename__ = "absence_type_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_absence_type_definitions_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    # Hex-Farbe "#rrggbb" für Kalender/Badges
    color: Mapped[str] = mapped_column(String(7), default="#64748b")
    category: Mapped[AbsenceType] = mapped_column(Enum(AbsenceType))
    # Selbst gestellte Anträge (ohne Entscheidungsbefugnis) brauchen eine Genehmigung.
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    # Mitarbeiter dürfen diese Art im Self-Service selbst beantragen/melden.
    employee_can_request: Mapped[bool] = mapped_column(Boolean, default=True)
    # Ab diesem Kalendertag der Abwesenheit ist ein Nachweis nötig (z.B. AU ab dem 4. Tag) – nur Hinweis.
    certificate_from_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Vertretung am Antrag: NONE (kein Feld), OPTIONAL oder REQUIRED (Pflicht, wenn Mitarbeiter
    # selbst beantragen; HR darf sie weglassen).
    substitute_mode: Mapped[str] = mapped_column(String(10), default="NONE", server_default="NONE")
    # Kommentar (Notiz) ist beim Eintragen Pflicht – nicht für Krankheit (Gesundheitsdaten).
    comment_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Teamkalender für Mitarbeiter: GREY = nur „abwesend“ (Standard), COLOR = mit Art
    calendar_visibility: Mapped[str] = mapped_column(String(10), default="GREY", server_default="GREY")
    # Wer genehmigt (app/services/approval_service.py): DEFAULT = Teamleitung des Teams oder Admin/HR,
    # SUPERVISOR = Führungskraft, SUPERVISOR_HR = erst Führungskraft, dann Admin/HR, HR = nur Admin/HR
    approval_chain: Mapped[str] = mapped_column(String(20), default="DEFAULT", server_default="DEFAULT")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
