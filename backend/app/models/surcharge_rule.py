import enum
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SurchargeKind(str, enum.Enum):
    NIGHT = "NIGHT"  # Zeitfenster (ggf. über Mitternacht), z.B. 23-6 Uhr
    SUNDAY = "SUNDAY"
    HOLIDAY = "HOLIDAY"
    OVERTIME = "OVERTIME"  # Mehrarbeit über das Tages-Soll hinaus
    CUSTOM = "CUSTOM"  # frei definiertes Zeitfenster an bestimmten Wochentagen


class SurchargeRule(Base):
    """Zuschlagsregel eines Mandanten. Reine Zeitauswertung (Stunden je Regel) – die
    steuerliche/tarifliche Bewertung bleibt bei der Lohnbuchhaltung. Regeln mit
    derselben exclusive_group werden nicht addiert: je Minute gilt nur die höchste."""

    __tablename__ = "surcharge_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[SurchargeKind] = mapped_column(Enum(SurchargeKind))
    percent: Mapped[float] = mapped_column(Numeric(6, 2))
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Bit 0 = Montag ... Bit 6 = Sonntag (wie EmployeeDefaultShift); gilt für den Beginn des Fensters.
    weekdays_mask: Mapped[int] = mapped_column(Integer, default=127)
    exclusive_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Lohnart für den DATEV-Export (Zuschlagsstunden); leer = nicht übertragen
    wage_type: Mapped[str | None] = mapped_column(String(6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
