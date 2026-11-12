import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.punch_location import PunchLocationCheck


class PunchType(str, enum.Enum):
    COME = "COME"
    GO = "GO"
    BREAK_START = "BREAK_START"
    BREAK_END = "BREAK_END"
    # Dienstgang: zählt als Arbeitszeit, Mitarbeiter ist nur nicht im Haus.
    ERRAND_START = "ERRAND_START"
    ERRAND_END = "ERRAND_END"


class PunchSource(str, enum.Enum):
    KIOSK = "KIOSK"
    MANUAL_HR = "MANUAL_HR"
    AUTO_BREAK = "AUTO_BREAK"
    # Vom Mitarbeiter selbst über den Web-Login (Startseite) gestempelt, immer mit Serverzeit.
    PORTAL = "PORTAL"
    # Vom Mitarbeiter in „Mein Bereich“ selbst eingetragene Zeitspanne (Stundenzettel, Einstellung
    # „Zeiten selbst eintragen“) – sofort wirksam oder nach Genehmigung, siehe services/time_entry_service.py.
    SELF_ENTRY = "SELF_ENTRY"


class Punch(Base):
    __tablename__ = "punches"
    # Häufigste Abfrage: Stempelungen eines Mitarbeiters in einem Zeitraum (Tagesberechnung, Liste).
    __table_args__ = (Index("ix_punches_employee_time", "employee_id", "timestamp_utc"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalisiert wie location_id – Punch wird auf praktisch jedem Request
    # gefiltert, siehe Plan zur Mandantenfähigkeit.
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    punch_type: Mapped[PunchType] = mapped_column(Enum(PunchType))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[PunchSource] = mapped_column(Enum(PunchSource))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    # Standortprüfung beim Stempeln im Web-Login (nur Ergebnis, nie Koordinaten; NULL = nicht geprüft)
    location_check: Mapped[PunchLocationCheck | None] = mapped_column(Enum(PunchLocationCheck), nullable=True)
    location_check_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Projektzeiterfassung: Projekt und Tätigkeitsnotiz der Spanne ab diesem "Kommen" bis zum nächsten
    # "Gehen" (bisher nur bei selbst eingetragenen Zeiten; HR kann es bei Korrekturen ändern).
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    activity_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Client-generierte UUID zur Duplikat-Vermeidung bei der Offline-Queue, siehe Konzept Abschnitt 5.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
