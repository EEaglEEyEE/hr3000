from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ServerMetricsRange = Literal["24h", "7d", "30d"]


class ServerSnapshotResponse(BaseModel):
    """Aktueller Stand des ganzen Servers (Bytes, Prozent, Last je Minute)."""

    cpu_count: int | None
    cpu_percent: float | None
    load_1: float | None
    load_5: float | None
    load_15: float | None
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    disk_used_bytes: int | None
    disk_total_bytes: int | None
    uptime_seconds: float | None


class ServerMetricPointResponse(BaseModel):
    """Ein Abschnitt des Verlaufs (Beginn in UTC): Mittelwerte, CPU zusätzlich mit Höchstwert."""

    at: datetime
    cpu_percent: float | None
    cpu_max_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    load_1: float | None


class ServerMetricsResponse(BaseModel):
    range: ServerMetricsRange
    bucket_minutes: int
    # Abstand der Messungen; 0 = Messung abgeschaltet (SERVER_METRICS_INTERVAL_SECONDS)
    interval_seconds: int
    retention_days: int
    # None, wenn der Server keine Werte liefert (kein /proc, z. B. lokal auf macOS)
    current: ServerSnapshotResponse | None
    points: list[ServerMetricPointResponse]
