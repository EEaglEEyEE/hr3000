"""Momentwerte für ``GET /metrics`` (app/api/metrics.py) aus der Datenbank.

Liest bewusst mandantenübergreifend: Der Endpunkt hat keinen Mandanten-Kontext (steht in
``_NO_TENANT_PATHS`` der Mandanten-Middleware) und bündelt nur Zählwerte je Mandant. Label
``tenant`` ist die Subdomain, ``device`` die Geräte-ID – keine Namen, E-Mail-Adressen oder Inhalte.

Zeitstempel stehen in der Datenbank als naives UTC (MySQL ``DATETIME`` wie SQLite); verglichen wird
daher mit naivem UTC, Werte mit Zeitzone werden vorher umgerechnet.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    CorrectionRequestKind,
    CorrectionRequestStatus,
    DataChangeRequest,
    Device,
    Employee,
    Punch,
    PunchCorrectionRequest,
    Tenant,
)

logger = logging.getLogger(__name__)

PUNCH_WINDOW = timedelta(hours=24)

# Art des offenen Antrags (Label ``kind``)
KIND_ABSENCE = "absence"
KIND_PUNCH_CORRECTION = "punch_correction"
KIND_TIME_ENTRY = "time_entry"
KIND_DATA_CHANGE = "data_change"
REQUEST_KINDS = (KIND_ABSENCE, KIND_PUNCH_CORRECTION, KIND_TIME_ENTRY, KIND_DATA_CHANGE)
_CORRECTION_KINDS = {
    CorrectionRequestKind.CORRECTION: KIND_PUNCH_CORRECTION,
    CorrectionRequestKind.TIME_ENTRY: KIND_TIME_ENTRY,
}

UP_HELP = "1 = Datenbank erreichbar, 0 = nicht erreichbar (dann fehlen die übrigen Momentwerte)"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def naive_utc(value: datetime) -> datetime:
    """Zeitstempel als naives UTC (Spalten sind naiv; manche Stellen schreiben mit Zeitzone)."""
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def seconds_since(value: datetime, now: datetime) -> float:
    """Sekunden zwischen ``value`` und ``now`` (beide naiv oder mit Zeitzone), nie negativ."""
    return max(0.0, (naive_utc(now) - naive_utc(value)).total_seconds())


def up_lines(up: bool) -> list[str]:
    return metrics.gauge_lines("hr_up", UP_HELP, (), [((), 1 if up else 0)])


async def database_gauges(db: AsyncSession, now: Callable[[], datetime] | None = None) -> list[str]:
    """Alle Momentwerte. Ist die Datenbank nicht lesbar, nur ``hr_up 0`` (Abruf scheitert nie)."""
    current = naive_utc((now or _utcnow)())
    try:
        tenants = (await db.execute(select(Tenant.id, Tenant.subdomain))).all()
        employees = (
            await db.execute(
                select(Employee.tenant_id, func.count(Employee.id))
                .where(Employee.active.is_(True))
                .group_by(Employee.tenant_id)
            )
        ).all()
        punches = (
            await db.execute(
                select(Punch.tenant_id, func.count(Punch.id))
                .where(Punch.timestamp_utc >= current - PUNCH_WINDOW, Punch.timestamp_utc <= current)
                .group_by(Punch.tenant_id)
            )
        ).all()
        # Abwesenheiten haben keine eigene tenant_id – Mandant über den Mitarbeiter.
        absences = (
            await db.execute(
                select(Employee.tenant_id, func.count(Absence.id))
                .join(Employee, Employee.id == Absence.employee_id)
                .where(Absence.approval_status == AbsenceApprovalStatus.PENDING)
                .group_by(Employee.tenant_id)
            )
        ).all()
        corrections = (
            await db.execute(
                select(PunchCorrectionRequest.tenant_id, PunchCorrectionRequest.kind, func.count(PunchCorrectionRequest.id))
                .where(PunchCorrectionRequest.status == CorrectionRequestStatus.PENDING)
                .group_by(PunchCorrectionRequest.tenant_id, PunchCorrectionRequest.kind)
            )
        ).all()
        data_changes = (
            await db.execute(
                select(DataChangeRequest.tenant_id, func.count(DataChangeRequest.id))
                .where(DataChangeRequest.status == "PENDING")
                .group_by(DataChangeRequest.tenant_id)
            )
        ).all()
        devices = (
            await db.execute(
                select(Device.tenant_id, Device.id, Device.last_seen)
                .where(Device.last_seen.is_not(None))
                .order_by(Device.tenant_id, Device.id)
            )
        ).all()
    except Exception:  # noqa: BLE001 - Metriken dürfen den Abruf nie scheitern lassen
        logger.exception("Metriken aus der Datenbank nicht lesbar")
        return up_lines(False)

    subdomains = {tenant_id: subdomain for tenant_id, subdomain in tenants}
    order = sorted(subdomains, key=lambda tid: subdomains[tid])

    def per_tenant(rows) -> list[tuple[tuple[str], int]]:
        counts = dict(rows)
        return [((subdomains[tid],), counts.get(tid, 0)) for tid in order]

    open_requests: dict[tuple[int, str], int] = {(tid, kind): 0 for tid in order for kind in REQUEST_KINDS}
    for tid, n in absences:
        open_requests[(tid, KIND_ABSENCE)] = open_requests.get((tid, KIND_ABSENCE), 0) + n
    for tid, kind, n in corrections:
        label = _CORRECTION_KINDS.get(kind, KIND_PUNCH_CORRECTION)
        open_requests[(tid, label)] = open_requests.get((tid, label), 0) + n
    for tid, n in data_changes:
        open_requests[(tid, KIND_DATA_CHANGE)] = open_requests.get((tid, KIND_DATA_CHANGE), 0) + n

    lines = up_lines(True)
    lines += metrics.gauge_lines("hr_tenants", "Anzahl der Mandanten (alle Status)", (), [((), len(tenants))])
    lines += metrics.gauge_lines(
        "hr_employees_active", "Aktive Mitarbeiter je Mandant", ("tenant",), per_tenant(employees)
    )
    lines += metrics.gauge_lines(
        "hr_punches_24h", "Stempelungen der letzten 24 Stunden je Mandant", ("tenant",), per_tenant(punches)
    )
    lines += metrics.gauge_lines(
        "hr_open_requests",
        "Offene Anträge je Mandant und Art (absence, punch_correction, time_entry, data_change)",
        ("tenant", "kind"),
        [((subdomains[tid], kind), n) for (tid, kind), n in sorted(
            open_requests.items(), key=lambda item: (subdomains.get(item[0][0], ""), item[0][1])
        ) if tid in subdomains],
    )
    lines += metrics.gauge_lines(
        "hr_kiosk_last_seen_seconds",
        "Sekunden seit der letzten Meldung eines Kiosk-Tablets (nur Tablets, die sich schon gemeldet haben)",
        ("tenant", "device"),
        [
            ((subdomains[tid], str(device_id)), seconds_since(last_seen, current))
            for tid, device_id, last_seen in devices
            if tid in subdomains
        ],
    )
    return lines
