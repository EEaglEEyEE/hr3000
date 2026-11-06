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
    created_by: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    created_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    approval_status: Mapped[AbsenceApprovalStatus] = mapped_column(
        Enum(AbsenceApprovalStatus), default=AbsenceApprovalStatus.APPROVED
    )
    # Wer entschieden hat (Supervisor/Admin/HR) – dasselbe Dual-Actor-Muster
    # wie created_by/created_by_employee_id.
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    decided_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
