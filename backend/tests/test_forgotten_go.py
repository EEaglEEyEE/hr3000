"""Vergessenes "Gehen": Ein Tag gilt als offen ("zu klären"), sobald seit dem letzten "Kommen"
mehr Zeit vergangen ist als die maximale Schichtlänge (Einstellungen, Standard 16 Std.) – auch
wenn der Mitarbeiter danach gar nicht mehr stempelt (z.B. direkt in den Urlaub).
Nachtschichten über Mitternacht bleiben innerhalb der Schichtlänge "anwesend"."""
import uuid
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings


async def _setup(db_session: AsyncSession, client: AsyncClient, max_span_hours: int | None = None):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Max", last_name="Vergesslich", employee_number="V1")
    db_session.add_all([employee, HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    if max_span_hours is not None:
        settings_row = await get_or_create_settings(db_session, tenant_id=1)
        settings_row.max_shift_span_hours = max_span_hours
    await db_session.commit()
    token = (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return employee, {"Authorization": f"Bearer {token}"}


async def _punch(client: AsyncClient, admin, employee_id: int, punch_type: str, ts: str) -> None:
    r = await client.post(
        "/punches",
        headers=admin,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text


async def _status(client: AsyncClient, admin, employee_id: int, day: str) -> str:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})
    return r.json()[0]["status"]


async def _open_days(client: AsyncClient, admin) -> list[str]:
    return [d["work_date"] for d in (await client.get("/timesheet/open-days", headers=admin)).json()]


async def test_forgotten_go_without_any_later_punch_is_open(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _punch(client, admin, employee.id, "COME", "2026-08-10T06:00:00Z")  # danach nie wieder gestempelt
    assert await _status(client, admin, employee.id, "2026-08-10") == "OPEN_MISSING_PUNCH"
    assert await _open_days(client, admin) == ["2026-08-10"]


async def test_still_present_within_the_max_shift_span(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    employee, admin = await _setup(db_session, client)
    await _punch(client, admin, employee.id, "COME", "2026-08-10T06:00:00Z")
    at_time(datetime(2026, 8, 10, 21, 59))  # 15:59 Std. nach dem Kommen
    assert await _status(client, admin, employee.id, "2026-08-10") == "PRESENT"
    at_time(datetime(2026, 8, 10, 22, 1))  # 16:01 Std.
    assert await _status(client, admin, employee.id, "2026-08-10") == "OPEN_MISSING_PUNCH"


async def test_night_shift_over_midnight_stays_present_until_go(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    employee, admin = await _setup(db_session, client)
    await _punch(client, admin, employee.id, "COME", "2026-08-10T22:00:00Z")
    at_time(datetime(2026, 8, 11, 5, 30))  # nächster Morgen, Schicht läuft noch
    assert await _status(client, admin, employee.id, "2026-08-10") == "PRESENT"
    await _punch(client, admin, employee.id, "GO", "2026-08-11T06:00:00Z")
    at_time(datetime(2026, 8, 12, 12, 0))
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-08-10", "to": "2026-08-10"})).json()[0]
    assert day["status"] == "COMPLETE" and day["actual_minutes"] == 8 * 60


async def test_shorter_max_shift_span_from_the_settings(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    employee, admin = await _setup(db_session, client, max_span_hours=10)
    await _punch(client, admin, employee.id, "COME", "2026-08-10T06:00:00Z")
    at_time(datetime(2026, 8, 10, 15, 0))  # 9 Std.
    assert await _status(client, admin, employee.id, "2026-08-10") == "PRESENT"
    at_time(datetime(2026, 8, 10, 17, 0))  # 11 Std. > 10 Std.
    assert await _status(client, admin, employee.id, "2026-08-10") == "OPEN_MISSING_PUNCH"


async def test_forgotten_break_or_errand_end_is_open_too(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.kiosk_errand_buttons = True
    await db_session.commit()
    await _punch(client, admin, employee.id, "COME", "2026-08-10T06:00:00Z")
    await _punch(client, admin, employee.id, "BREAK_START", "2026-08-10T12:00:00Z")
    assert await _status(client, admin, employee.id, "2026-08-10") == "OPEN_MISSING_PUNCH"


async def test_open_days_pick_up_a_shift_that_ran_over_without_new_punches(
    client: AsyncClient, db_session: AsyncSession, at_time
) -> None:
    """Der Tag war beim Stempeln als "anwesend" zwischengespeichert. Ohne weitere Stempelung muss
    "Zu klären" ihn trotzdem melden, sobald die Schichtlänge überschritten ist."""
    employee, admin = await _setup(db_session, client)
    at_time(datetime(2026, 8, 10, 8, 0))
    await _punch(client, admin, employee.id, "COME", "2026-08-10T06:00:00Z")
    assert "2026-08-10" not in await _open_days(client, admin)

    at_time(datetime(2026, 8, 11, 8, 0))  # 26 Std. später, keine neue Stempelung
    assert await _open_days(client, admin) == ["2026-08-10"]
    # Wird das Gehen nachgetragen, ist der Tag wieder in Ordnung.
    await _punch(client, admin, employee.id, "GO", "2026-08-10T14:00:00Z")
    assert await _open_days(client, admin) == []
