"""Server-Auslastung für den Super-Admin: Messwerte aus /proc, Verlauf in Abschnitten, nur Super-Admin."""
from datetime import datetime, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import HrRole, Account, ServerMetricSample
from app.services import server_metrics
from app.services.auth_service import hash_password

GIB = 1024**3


def _fake_proc(tmp_path: Path, *, idle: int, busy: int) -> Path:
    proc = tmp_path / "proc"
    proc.mkdir(exist_ok=True)
    # user nice system idle iowait irq softirq steal guest guest_nice
    (proc / "stat").write_text(
        f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 0 0 1 0 0 0 0 0 0\ncpu1 1 0 0 1 0 0 0 0 0 0\nintr 1\n"
    )
    (proc / "loadavg").write_text("0.52 0.40 0.31 1/234 5678\n")
    (proc / "meminfo").write_text("MemTotal:        8000000 kB\nMemFree:  1000000 kB\nMemAvailable:    6000000 kB\n")
    (proc / "uptime").write_text("12345.67 23456.78\n")
    return proc


def test_reads_cpu_load_memory_and_uptime(tmp_path: Path) -> None:
    proc = _fake_proc(tmp_path, idle=1000, busy=1000)
    before = server_metrics.read_cpu_times(proc)
    _fake_proc(tmp_path, idle=1300, busy=1100)  # 400 Ticks, davon 100 belegt -> 25 %
    after = server_metrics.read_cpu_times(proc)
    assert server_metrics.cpu_percent_between(before, after) == 25.0
    snapshot = server_metrics.read_snapshot(25.0, proc=proc, disk_path=str(tmp_path))
    assert snapshot.cpu_count == 2
    assert (snapshot.load_1, snapshot.load_5, snapshot.load_15) == (0.52, 0.40, 0.31)
    assert snapshot.memory_total_bytes == 8000000 * 1024
    assert snapshot.memory_used_bytes == 2000000 * 1024  # gesamt − verfügbar
    assert snapshot.disk_total_bytes and snapshot.disk_used_bytes is not None
    assert snapshot.uptime_seconds == 12345.67


def test_without_proc_there_are_no_values(tmp_path: Path) -> None:
    missing = tmp_path / "nichts"
    assert server_metrics.read_cpu_times(missing) is None
    snapshot = server_metrics.read_snapshot(None, proc=missing, disk_path=str(tmp_path / "nichts"))
    assert snapshot.load_1 is None and snapshot.memory_total_bytes is None and snapshot.disk_total_bytes is None
    assert server_metrics.cpu_percent_between(None, None) is None


async def test_history_averages_per_bucket_and_purges_old(db_session: AsyncSession) -> None:
    now = datetime(2026, 11, 6, 12, 0)
    for minutes, cpu, load in [(1, 10.0, 0.2), (2, 30.0, 0.6), (10, 80.0, 1.0), (60 * 30, 99.0, 3.0)]:
        db_session.add(
            ServerMetricSample(
                sampled_at=now - timedelta(minutes=minutes), cpu_percent=cpu, load_1=load,
                memory_used_bytes=2 * GIB, memory_total_bytes=8 * GIB, disk_used_bytes=30 * GIB, disk_total_bytes=100 * GIB,
            )
        )
    await db_session.commit()
    bucket, points = await server_metrics.history(db_session, "24h", now=now)
    assert bucket == timedelta(minutes=5)
    # Die beiden Werte von 11:58 und 11:59 liegen in einem Abschnitt: Mittelwert 20 %, höchster 30 %.
    last = points[-1]
    assert (last.cpu_percent, last.cpu_max_percent, last.load_1) == (20.0, 30.0, 0.4)
    assert last.memory_percent == 25.0 and last.disk_percent == 30.0
    assert len(points) == 2  # der Wert vor 30 Stunden liegt außerhalb von 24 Std.
    _, week = await server_metrics.history(db_session, "7d", now=now)
    assert len(week) == 2  # je Stunde ein Abschnitt

    await server_metrics.purge_old(db_session, retention_days=1, now=now)
    await db_session.commit()
    remaining = (await db_session.execute(select(func.count()).select_from(ServerMetricSample))).scalar_one()
    assert remaining == 3


async def _token(client: AsyncClient, db_session: AsyncSession, role: HrRole, email: str) -> str:
    db_session.add(Account(tenant_id=None if role == HrRole.SUPER_ADMIN else 1, email=email, password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    headers = {"Host": settings.super_admin_hostname} if role == HrRole.SUPER_ADMIN else {}
    response = await client.post("/auth/login", headers=headers, json={"email": email, "password": "pw"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_endpoint_only_for_super_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _token(client, db_session, HrRole.ADMIN, "admin@example.com")
    denied = await client.get("/platform/server-metrics", headers={"Authorization": f"Bearer {admin}"})
    assert denied.status_code == 403

    db_session.add(ServerMetricSample(sampled_at=datetime.utcnow() - timedelta(minutes=3), cpu_percent=12.5, load_1=0.3))
    await db_session.commit()
    token = await _token(client, db_session, HrRole.SUPER_ADMIN, "super@example.com")
    headers = {"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname}
    response = await client.get("/platform/server-metrics", headers=headers, params={"range": "24h"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["range"] == "24h" and body["bucket_minutes"] == 5 and body["retention_days"] == 30
    assert body["points"][-1]["cpu_percent"] == 12.5
    assert body["points"][-1]["at"].endswith(("Z", "+00:00"))  # UTC mit Zeitzone
    assert (await client.get("/platform/server-metrics", headers=headers, params={"range": "1y"})).status_code == 422
