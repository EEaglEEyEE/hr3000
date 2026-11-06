from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ServerMetricSample(Base):
    """Auslastung des ganzen Servers, einmal je Minute (services/server_metrics.py) – plattformweit,
    nur für den Super-Admin, ohne Mandantenbezug. Ältere Werte als die Aufbewahrung werden gelöscht."""

    __tablename__ = "server_metric_samples"
    __table_args__ = (Index("ix_server_metric_samples_sampled_at", "sampled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime)  # UTC, naiv
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
