"""Arbeitszeitmodelle: Zuweisungen an Mitarbeiter aus den Modell-Fassungen ableiten und nachziehen.

Eine Zuweisung ist eine Fassung der Arbeitszeit (EmployeeDefaultShift) mit profile_id. Ihre Angaben
(Arbeitstage, Soll, Pause, Kernzeit, Gleitzeit-Rahmen, Toleranz, Schichtvorlage) werden aus der
Modell-Fassung übernommen, die im jeweiligen Zeitraum gilt – an Modell-Fassungsgrenzen wird die
Zuweisung geteilt. So rechnen Tagesberechnung, Urlaub, Lohn-Export & Co. weiter nur mit den
Fassungen der Mitarbeiter, und eine Modelländerung ab Stichtag wirkt auf alle Zugewiesenen
("verknüpft"), ohne die Vergangenheit zu ändern.

Nach jeder Änderung, die Zuweisungen oder Modell-Fassungen betrifft, sync_employee aufrufen; es
liefert den frühesten geänderten Tag (für invalidate_balance) oder None.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Employee, EmployeeDefaultShift, WorkTimeProfile, WorkTimeProfileVersion

# Angaben, die eine Zuweisung aus der Modell-Fassung übernimmt.
CONTRACT_FIELDS = (
    "shift_template_id",
    "weekdays_mask",
    "day_minutes",
    "flexible",
    "on_demand",
    "monthly_cap_minutes",
    "target_minutes",
    "target_period",
    "break_mode",
    "fixed_break_start",
    "fixed_break_end",
    "fixed_break_windows",
    "min_break_minutes",
    "min_break_after_minutes",
    "core_time_mode",
    "core_time_start",
    "core_time_end",
    "core_time_days",
    "flex_frame_mode",
    "flex_frame_start",
    "flex_frame_end",
    "flex_frame_days",
    "late_tolerance_minutes",
)


def contract_of(row: EmployeeDefaultShift | WorkTimeProfileVersion) -> dict:
    return {key: getattr(row, key) for key in CONTRACT_FIELDS}


async def profile_versions(db: AsyncSession, profile_id: int) -> list[WorkTimeProfileVersion]:
    return list(
        (
            await db.execute(
                select(WorkTimeProfileVersion)
                .where(WorkTimeProfileVersion.profile_id == profile_id)
                .order_by(WorkTimeProfileVersion.valid_from)
            )
        ).scalars().all()
    )


async def get_profile_in_tenant(db: AsyncSession, profile_id: int, tenant_id: int) -> WorkTimeProfile:
    profile = await db.get(WorkTimeProfile, profile_id)
    if profile is None or profile.tenant_id != tenant_id:
        raise AppError(404, "WORK_TIME_PROFILE_NOT_FOUND", "Arbeitszeitmodell nicht gefunden.")
    return profile


def _overlaps(start: date, end: date | None, other_start: date, other_end: date | None) -> bool:
    return (end is None or other_start <= end) and (other_end is None or start <= other_end)


async def materialize(
    db: AsyncSession, employee_id: int, profile_id: int, start: date, end: date | None
) -> list[EmployeeDefaultShift]:
    """Fassungen der Arbeitszeit für eine Zuweisung von start bis end (None = offen) – geteilt an
    den Grenzen der Modell-Fassungen. Noch nicht in der Session."""
    rows = []
    for version in await profile_versions(db, profile_id):
        if not _overlaps(start, end, version.valid_from, version.valid_to):
            continue
        row_end = end if version.valid_to is None else (version.valid_to if end is None else min(end, version.valid_to))
        rows.append(
            EmployeeDefaultShift(
                employee_id=employee_id,
                profile_id=profile_id,
                valid_from=max(start, version.valid_from),
                valid_to=row_end,
                **contract_of(version),
            )
        )
    return rows


async def _employee_versions(db: AsyncSession, employee_id: int) -> list[EmployeeDefaultShift]:
    return list(
        (
            await db.execute(
                select(EmployeeDefaultShift)
                .where(EmployeeDefaultShift.employee_id == employee_id)
                .order_by(EmployeeDefaultShift.valid_from)
            )
        ).scalars().all()
    )


def _segments(rows: list[EmployeeDefaultShift]) -> list[list[EmployeeDefaultShift]]:
    """Aufeinanderfolgende, lückenlose Fassungen mit demselben Modell = eine Zuweisung."""
    segments: list[list[EmployeeDefaultShift]] = []
    for row in rows:
        if row.profile_id is None:
            continue
        last = segments[-1][-1] if segments else None
        if (
            last is not None
            and last.profile_id == row.profile_id
            and last.valid_to is not None
            and last.valid_to + timedelta(days=1) == row.valid_from
        ):
            segments[-1].append(row)
        else:
            segments.append([row])
    return segments


def _key(row: EmployeeDefaultShift) -> tuple:
    return (row.valid_from, row.valid_to, tuple(contract_of(row).values()))


async def sync_employee(db: AsyncSession, employee_id: int) -> date | None:
    """Zieht alle Modell-Zuweisungen eines Mitarbeiters auf den Stand ihrer Modelle nach (teilt bzw.
    fasst an den Grenzen der Modell-Fassungen zusammen). Liefert den frühesten Tag, an dem sich
    etwas geändert hat, sonst None. Erwartet geflushte Fassungen."""
    earliest: date | None = None
    for segment in _segments(await _employee_versions(db, employee_id)):
        start, end = segment[0].valid_from, segment[-1].valid_to
        wanted = await materialize(db, employee_id, segment[0].profile_id, start, end)
        current = [_key(row) for row in segment]
        target = [_key(row) for row in wanted]
        if current == target:
            continue
        differs = next((min(a[0], b[0]) for a, b in zip(current, target) if a != b), None)
        if differs is None:
            # gleicher Anfang, nur unterschiedlich viele Fassungen: ab der ersten zusätzlichen
            longer = current if len(current) > len(target) else target
            differs = longer[min(len(current), len(target))][0]
        earliest = differs if earliest is None else min(earliest, differs)
        for row in segment:
            await db.delete(row)
        await db.flush()
        db.add_all(wanted)
        await db.flush()
    return earliest


async def assigned_employee_ids(db: AsyncSession, profile_id: int, from_date: date | None = None) -> list[int]:
    """Mitarbeiter mit einer Zuweisung dieses Modells (ab from_date bzw. irgendwann)."""
    query = select(EmployeeDefaultShift.employee_id).where(EmployeeDefaultShift.profile_id == profile_id)
    if from_date is not None:
        query = query.where((EmployeeDefaultShift.valid_to.is_(None)) | (EmployeeDefaultShift.valid_to >= from_date))
    return sorted(set((await db.execute(query)).scalars().all()))


async def employee_names(db: AsyncSession, employee_ids: list[int]) -> list[str]:
    if not employee_ids:
        return []
    rows = (await db.execute(select(Employee.first_name, Employee.last_name).where(Employee.id.in_(employee_ids)))).all()
    return sorted(f"{first} {last}".strip() for first, last in rows)
