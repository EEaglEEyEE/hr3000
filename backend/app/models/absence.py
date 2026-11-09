import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AbsenceType(str, enum.Enum):
    VACATION = "VACATION"
    SICK = "SICK"
    SPECIAL_LEAVE = "SPECIAL_LEAVE"
    # Unbezahlte Abwesenheit (z.B. Elternzeit): Soll entfällt.
    UNPAID = "UNPAID"
    # Freizeitausgleich/Gleittag: Soll bleibt, Saldo sinkt.
    TIME_OFF_IN_LIEU = "TIME_OFF_IN_LIEU"
    # Arbeitszeit außerhalb der Stempeluhr (Homeoffice, zusätzliche Stunden, Dienstreise): zählt als
    # gearbeitete Zeit (Gutschrift), ist aber kein Abwesenheitstag.
    WORK_TIME = "WORK_TIME"
    # Feiertagsvergütung (z.B. "Feiertag GfB" für Aushilfen): Gutschrift, zählt als Feiertag.
    PUBLIC_HOLIDAY = "PUBLIC_HOLIDAY"
    # Krankheit eines Kindes: Gutschrift wie Krankheit, wird aber getrennt gezählt (kein BEM).
    CHILD_SICK = "CHILD_SICK"
    # Rechnen wie UNPAID (Soll entfällt), sind aber für die Lohnabrechnung zu unterscheiden: eigene
    # Spalte im Lohn-Export (nur wenn im Zeitraum genutzt), in Berichten unter „Unbezahlt“.
    PARENTAL_LEAVE = "PARENTAL_LEAVE"  # Mutterschutz/Elternzeit
    SHORT_TIME_WORK = "SHORT_TIME_WORK"  # Kurzarbeit
    UNEXCUSED = "UNEXCUSED"  # Unentschuldigtes Fehlen
    CARE_LEAVE = "CARE_LEAVE"  # Pflege von Angehörigen


# Kategorien ohne Gutschrift, bei denen das Soll entfällt.
UNPAID_CATEGORIES = frozenset(
    {
        AbsenceType.UNPAID,
        AbsenceType.PARENTAL_LEAVE,
        AbsenceType.SHORT_TIME_WORK,
        AbsenceType.UNEXCUSED,
        AbsenceType.CARE_LEAVE,
    }
)
# Davon mit eigener Spalte im Lohn-Export (UNPAID hat seine feste Spalte „Unbezahlte Tage“).
SEPARATE_UNPAID_CATEGORIES = UNPAID_CATEGORIES - {AbsenceType.UNPAID}


class AbsenceApprovalStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class Absence(Base):
    """Urlaub/Krankheit. Optionaler Genehmigungsworkflow je Abwesenheitsart
    (AbsenceTypeDefinition.requires_approval) – ohne Genehmigungspflicht direkt
    final (APPROVED)."""

    __tablename__ = "absences"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    # Kategorie (bestimmt die Berechnung) – bei eigener Abwesenheitsart deren Kategorie.
    type: Mapped[AbsenceType] = mapped_column(Enum(AbsenceType))
    # Vom Mandanten definierte Abwesenheitsart (Name/Farbe), NULL = Standardart der Kategorie.
    absence_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("absence_type_definitions.id"), nullable=True, index=True
    )
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    # Nur halber Tag (nur bei date_from == date_to): halbe Gutschrift bzw. ein halber Urlaubstag.
    # Zwei halbe Tage verschiedener Art (z.B. ½ Sonderurlaub + ½ Urlaub an Heiligabend) ergeben
    # zusammen einen ganzen Abwesenheitstag.
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    # Genaue Dauer in Minuten statt ganzem/halbem Tag (nur einzelner Tag), z.B. 3 Std. Homeoffice:
    # bezahlte Arten schreiben genau diese Zeit gut, unbezahlte senken das Soll um diese Zeit.
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Vertretung während der Abwesenheit (anderer Mitarbeiter desselben Mandanten), optional.
    substitute_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    # Hochgeladener Nachweis (z. B. AU-Bescheinigung), liegt als Dokument „Krankmeldung“ in der Akte.
    certificate_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_documents.id", ondelete="SET NULL"), nullable=True
    )

    approval_status: Mapped[AbsenceApprovalStatus] = mapped_column(
        Enum(AbsenceApprovalStatus), default=AbsenceApprovalStatus.APPROVED
    )
    # Wer entschieden hat (Konto mit Rolle Führungskraft/Admin/HR).
    decided_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Aktueller Schritt der Genehmigungskette (1 = erster), siehe app/services/approval_service.py
    approval_step: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class AbsenceApproval(Base):
    """Eine Entscheidung in der Genehmigungskette eines Antrags (Verlauf: wer hat welchen Schritt
    genehmigt bzw. abgelehnt)."""

    __tablename__ = "absence_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    absence_id: Mapped[int] = mapped_column(ForeignKey("absences.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column(Integer)
    # SUPERVISOR, HR oder TEAM (Art des Schritts zum Zeitpunkt der Entscheidung)
    step_type: Mapped[str] = mapped_column(String(20))
    decided_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime)
