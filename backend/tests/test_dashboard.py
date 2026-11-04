"""Startseite: eigene Kennzahlen, Anwesenheit heute (HR) und nächste Termine."""
import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Device, Employee, Holiday, HrRole, HrUser, Location
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    other_location = Location(name="Filiale", timezone="UTC")
    db_session.add_all([location, other_location])
    await db_session.commit()
    today = date.today()
    me = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="D1",
        login_email="erika@example.com",
        password_hash=hash_password("pw123456"),
        birth_date=date(1990, (today + timedelta(days=3)).month, (today + timedelta(days=3)).day),
    )
    colleague = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Kollege",
        employee_number="D2",
        birth_date=date(1985, (today + timedelta(days=5)).month, (today + timedelta(days=5)).day),
    )
    db_session.add_all(
        [me, colleague, HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)]
    )
    db_session.add(Device(name="Tablet", location_id=location.id, device_token="tok-dashboard"))
    await db_session.commit()
    db_session.add_all(
        [
            Holiday(date=today + timedelta(days=10), name="Standortfeiertag", locations=[location]),
            Holiday(date=today + timedelta(days=11), name="Nur Filiale", locations=[other_location]),
            Absence(
                employee_id=colleague.id,
                type=AbsenceType.SICK,
                date_from=today - timedelta(days=1),
                date_to=today + timedelta(days=1),
                approval_status=AbsenceApprovalStatus.APPROVED,
            ),
            Absence(
                employee_id=me.id,
                type=AbsenceType.VACATION,
                date_from=today + timedelta(days=20),
                date_to=today + timedelta(days=24),
                approval_status=AbsenceApprovalStatus.PENDING,
            ),
        ]
    )
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.show_birthdays_in_calendar = True
    await db_session.commit()
    hr = (await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    mine = (await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "pw123456"})).json()[
        "access_token"
    ]
    return me, colleague, {"Authorization": f"Bearer {hr}"}, {"Authorization": f"Bearer {mine}"}


async def test_employee_sees_own_figures_and_events_only(client: AsyncClient, db_session: AsyncSession) -> None:
    me, colleague, _, mine = await _setup(db_session, client)
    body = (await client.get("/dashboard", headers=mine)).json()
    assert body["team"] is None
    assert body["me"]["employee_id"] == me.id and body["me"]["pending_absences"] == 1
    kinds = {(e["kind"], e["title"], e["employee_id"]) for e in body["events"]}
    assert ("HOLIDAY", "Standortfeiertag", None) in kinds
    assert not any(e["title"] == "Nur Filiale" for e in body["events"])  # anderer Standort
    assert ("PENDING_ABSENCE", "Urlaub (beantragt)", me.id) in kinds
    assert not any(e["employee_id"] == colleague.id for e in body["events"])  # keine Kollegen-Daten
    assert any(e["kind"] == "BIRTHDAY" and e["employee_id"] == me.id for e in body["events"])
    dates = [e["date"] for e in body["events"]]
    assert dates == sorted(dates)
    # Zeitraum-Filter: in 7 Tagen nur der eigene Geburtstag (Tag +3), nicht Feiertag (+10) und Urlaub (+20).
    week = (await client.get("/dashboard", headers=mine, params={"days": 7})).json()
    assert [e["kind"] for e in week["events"]] == ["BIRTHDAY"]
    assert week["horizon_date"] == (date.today() + timedelta(days=7)).isoformat()
    assert (await client.get("/dashboard", headers=mine, params={"days": 0})).status_code == 422


async def test_hr_sees_presence_absences_and_birthdays(client: AsyncClient, db_session: AsyncSession) -> None:
    me, colleague, hr, _ = await _setup(db_session, client)
    device = (await client.post("/auth/device/login", json={"device_token": "tok-dashboard"})).json()["access_token"]
    r = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device}"},
        json={
            "employee_id": me.id,
            "punch_type": "COME",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 201, r.text

    body = (await client.get("/dashboard", headers=hr)).json()
    assert body["me"] is None
    assert [p["employee_id"] for p in body["team"]["present"]] == [me.id]
    assert [p["employee_id"] for p in body["team"]["absent"]] == [colleague.id]
    assert body["team"]["absent"][0]["detail"].startswith("Krank bis")
    birthdays = {e["employee_id"] for e in body["events"] if e["kind"] == "BIRTHDAY"}
    assert birthdays == {me.id, colleague.id}
    assert any(e["title"] == "Nur Filiale" for e in body["events"])  # HR sieht alle Standorte

    # Ohne Freigabe in den Einstellungen keine Geburtstage.
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.show_birthdays_in_calendar = False
    await db_session.commit()
    body = (await client.get("/dashboard", headers=hr)).json()
    assert not any(e["kind"] == "BIRTHDAY" for e in body["events"])
    assert (await client.get("/dashboard", headers={"Authorization": f"Bearer {device}"})).status_code == 403


async def test_employee_learns_whether_shift_planning_is_used(client: AsyncClient, db_session: AsyncSession) -> None:
    # "Mein Bereich" zeigt den Reiter Schichtplanung nur, wenn die Firma Schichtplanung nutzt.
    _, _, _, mine = await _setup(db_session, client)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    for enabled in (False, True):
        settings_row.shift_planning_enabled = enabled
        await db_session.commit()
        assert (await client.get("/dashboard", headers=mine)).json()["shift_planning_enabled"] is enabled
