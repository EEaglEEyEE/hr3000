import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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
    created_by: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    # Gesetzt statt created_by, wenn ein Mitarbeiter mit hr_role (statt eines
    # separaten HrUser-Accounts) die Aktion ausgeführt hat.
    created_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Client-generierte UUID zur Duplikat-Vermeidung bei der Offline-Queue, siehe Konzept Abschnitt 5.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
