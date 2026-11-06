"""Server-Auslastung für den Super-Admin: CPU, Last, Arbeitsspeicher und Datenträger.

Gelesen wird aus /proc (Linux). Im Docker-Container ist /proc für CPU, Last und Speicher nicht
abgeschottet – die Werte gelten also für den ganzen Server, nicht nur für den Backend-Container.
Der Datenträger ist der des Container-Dateisystems (auf dem Server dieselbe Platte wie Docker).
Ohne /proc (z. B. lokal auf macOS) gibt es keine Werte und es wird nichts gespeichert.

Ein Hintergrund-Task (run_sampler, gestartet in main.lifespan) speichert jede Minute einen Wert und
löscht Werte, die älter als die Aufbewahrung sind. Das Backend läuft als ein Prozess, daher gibt es
genau einen Sammler je Umgebung (die Testumgebung misst in ihre eigene Datenbank)."""
import asyncio
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ServerMetricSample

logger = logging.getLogger(__name__)

PROC = Path("/proc")

# Zeitraum -> (Länge, Breite eines Abschnitts): je Abschnitt ein Mittelwert (und der höchste
# CPU-Wert), damit die Kurven auch über 30 Tage lesbar bleiben.
RANGES: dict[str, tuple[timedelta, timedelta]] = {
    "24h": (timedelta(hours=24), timedelta(minutes=5)),
    "7d": (timedelta(days=7), timedelta(hours=1)),
    "30d": (timedelta(days=30), timedelta(hours=6)),
}


@dataclass
class CpuTimes:
    idle: int
    total: int


@dataclass
class HostSnapshot:
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


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def read_cpu_times(proc: Path = PROC) -> CpuTimes | None:
    """Summe der CPU-Zeiten aus der ersten Zeile von /proc/stat (idle + iowait gelten als frei)."""
    try:
        fields = (proc / "stat").read_text().splitlines()[0].split()
    except (OSError, IndexError):
        return None
    if not fields or fields[0] != "cpu":
        return None
    values = [int(v) for v in fields[1:]]
    # user nice system idle iowait irq softirq steal (guest/guest_nice sind in user schon enthalten)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values[:8])
    return CpuTimes(idle=idle, total=total)


def cpu_percent_between(before: CpuTimes | None, after: CpuTimes | None) -> float | None:
    if before is None or after is None:
        return None
    total = after.total - before.total
    if total <= 0:
        return None
    busy = total - (after.idle - before.idle)
    return round(max(0.0, min(100.0, busy * 100 / total)), 1)


def _cpu_count(proc: Path) -> int | None:
    try:
        lines = (proc / "stat").read_text().splitlines()
    except OSError:
        return None
    count = sum(1 for line in lines if line.startswith("cpu") and line[3:4].isdigit())
    return count or None


def _load(proc: Path) -> tuple[float, float, float] | None:
    try:
        parts = (proc / "loadavg").read_text().split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except (OSError, IndexError, ValueError):
        return None


def _memory(proc: Path) -> tuple[int, int] | None:
    """(belegt, gesamt) in Bytes; belegt = gesamt − verfügbar (MemAvailable, ohne Datei-Cache)."""
    try:
        values: dict[str, int] = {}
        for line in (proc / "meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                values[key] = int(rest.split()[0]) * 1024
    except (OSError, IndexError, ValueError):
        return None
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None
    return values["MemTotal"] - values["MemAvailable"], values["MemTotal"]


def _uptime(proc: Path) -> float | None:
    try:
        return float((proc / "uptime").read_text().split()[0])
    except (OSError, IndexError, ValueError):
        return None


def _disk(path: str) -> tuple[int, int] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return usage.used, usage.total


def read_snapshot(cpu_percent: float | None, *, proc: Path = PROC, disk_path: str = "/") -> HostSnapshot:
    load = _load(proc)
    memory = _memory(proc)
    disk = _disk(disk_path)
    return HostSnapshot(
        cpu_count=_cpu_count(proc),
        cpu_percent=cpu_percent,
        load_1=load[0] if load else None,
        load_5=load[1] if load else None,
        load_15=load[2] if load else None,
        memory_used_bytes=memory[0] if memory else None,
        memory_total_bytes=memory[1] if memory else None,
        disk_used_bytes=disk[0] if disk else None,
        disk_total_bytes=disk[1] if disk else None,
        uptime_seconds=_uptime(proc),
    )


async def live_snapshot(*, proc: Path = PROC, disk_path: str = "/", window_seconds: float = 0.5) -> HostSnapshot | None:
    """Aktueller Stand; die CPU wird über ein kurzes Fenster gemessen. None ohne /proc."""
    before = read_cpu_times(proc)
    if before is None:
        return None
    await asyncio.sleep(window_seconds)
    return read_snapshot(cpu_percent_between(before, read_cpu_times(proc)), proc=proc, disk_path=disk_path)


def sample_from(snapshot: HostSnapshot, at: datetime) -> ServerMetricSample:
    return ServerMetricSample(
        sampled_at=at,
        cpu_percent=snapshot.cpu_percent,
        load_1=snapshot.load_1,
        memory_used_bytes=snapshot.memory_used_bytes,
        memory_total_bytes=snapshot.memory_total_bytes,
        disk_used_bytes=snapshot.disk_used_bytes,
        disk_total_bytes=snapshot.disk_total_bytes,
    )


async def purge_old(db: AsyncSession, retention_days: int, now: datetime | None = None) -> None:
    cutoff = (now or _utcnow()) - timedelta(days=retention_days)
    await db.execute(delete(ServerMetricSample).where(ServerMetricSample.sampled_at < cutoff))


def _percent(used: int | None, total: int | None) -> float | None:
    return round(used * 100 / total, 1) if used is not None and total else None


@dataclass
class HistoryPoint:
    at: datetime
    cpu_percent: float | None
    cpu_max_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    load_1: float | None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


async def history(db: AsyncSession, range_key: str, now: datetime | None = None) -> tuple[timedelta, list[HistoryPoint]]:
    """Verlauf des Zeitraums, je Abschnitt gemittelt (CPU zusätzlich mit Höchstwert). Abschnitte
    ohne Messwerte fehlen – die Oberfläche zeigt dort eine Lücke."""
    span, bucket = RANGES[range_key]
    now = now or _utcnow()
    start = now - span
    rows = (
        await db.execute(
            select(
                ServerMetricSample.sampled_at,
                ServerMetricSample.cpu_percent,
                ServerMetricSample.load_1,
                ServerMetricSample.memory_used_bytes,
                ServerMetricSample.memory_total_bytes,
                ServerMetricSample.disk_used_bytes,
                ServerMetricSample.disk_total_bytes,
            )
            .where(ServerMetricSample.sampled_at >= start, ServerMetricSample.sampled_at <= now)
            .order_by(ServerMetricSample.sampled_at)
        )
    ).all()
    width = bucket.total_seconds()
    groups: dict[int, list] = {}
    for row in rows:
        index = int((row.sampled_at - start).total_seconds() // width)
        groups.setdefault(index, []).append(row)
    points: list[HistoryPoint] = []
    for index in sorted(groups):
        group = groups[index]
        cpu = [r.cpu_percent for r in group if r.cpu_percent is not None]
        memory = [p for r in group if (p := _percent(r.memory_used_bytes, r.memory_total_bytes)) is not None]
        disk = [p for r in group if (p := _percent(r.disk_used_bytes, r.disk_total_bytes)) is not None]
        load = [r.load_1 for r in group if r.load_1 is not None]
        points.append(
            HistoryPoint(
                at=start + bucket * index,
                cpu_percent=_mean(cpu),
                cpu_max_percent=max(cpu) if cpu else None,
                memory_percent=_mean(memory),
                disk_percent=_mean(disk),
                load_1=_mean(load),
            )
        )
    return bucket, points


async def run_sampler(session_factory, interval_seconds: int, retention_days: int, disk_path: str) -> None:
    """Hintergrund-Task: jede `interval_seconds` einen Messwert speichern; einmal je Stunde alte
    Werte löschen. Fehler werden protokolliert, der Task läuft weiter."""
    previous = read_cpu_times()
    if previous is None:
        logger.info("Server-Auslastung: kein /proc – es wird nicht gemessen.")
        return
    purge_every = max(1, 3600 // max(1, interval_seconds))
    count = 0
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            current = read_cpu_times()
            snapshot = read_snapshot(cpu_percent_between(previous, current), disk_path=disk_path)
            previous = current
            async with session_factory() as db:
                db.add(sample_from(snapshot, _utcnow()))
                count += 1
                if count % purge_every == 1:
                    await purge_old(db, retention_days)
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Server-Auslastung: Messwert konnte nicht gespeichert werden.")
