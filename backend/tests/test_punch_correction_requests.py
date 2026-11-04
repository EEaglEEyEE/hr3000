"""Korrekturantrag: Mitarbeiter beantragt fehlende Stempelung, HR übernimmt oder lehnt ab."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location, Notification, Punch, PunchSource
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="C1",
        login_email="erika@example.com",
        password_hash=hash_password("pw123456"),
    )
    other = Employee(
        location_id=location.id,
        first_name="Otto",
        last_name="Other",
        employee_number="C2",
        login_email="otto@example.com",
        password_hash=hash_password("pw123456"),
    )
    db_session.add_all([employee, other, HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    await db_session.refresh(employee)
    hr = (await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    me = (await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    otto = (await client.post("/auth/employee/login", json={"email": "otto@example.com", "password": "pw123456"})).json()["access_token"]
    return (
        employee,
        {"Authorization": f"Bearer {hr}"},
        {"Authorization": f"Bearer {me}"},
        {"Authorization": f"Bearer {otto}"},
    )


async def test_request_is_approved_into_punches(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, hr, me, otto = await _setup(db_session, client)
    body = {
        "work_date": "2025-03-03",
        "items": [{"punch_type": "COME", "time": "08:00"}, {"punch_type": "GO", "time": "16:30"}],
        "reason": "Tablet war aus",
    }
    r = await client.post("/punch-correction-requests", headers=me, json=body)
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    assert r.json()["status"] == "PENDING"
    assert (await client.post("/punch-correction-requests", headers=me, json=body)).status_code == 409
    assert (await client.post("/punch-correction-requests", headers=hr, json=body)).status_code == 403
    assert (await client.post("/punch-correction-requests", headers=me, json={**body, "work_date": "2099-01-01"})).status_code == 400
    bad = {**body, "items": [{"punch_type": "GO", "time": "25:00"}]}
    assert (await client.post("/punch-correction-requests", headers=me, json=bad)).status_code == 422

    # HR sieht den Antrag (und hat eine Benachrichtigung), andere Mitarbeiter nicht.
    pending = (await client.get("/punch-correction-requests", headers=hr, params={"status": "PENDING"})).json()
    assert [p["id"] for p in pending] == [request_id] and pending[0]["employee_name"] == "Muster, Erika"
    assert (await client.get("/punch-correction-requests", headers=otto)).json() == []
    notes = (await db_session.execute(select(Notification).where(Notification.recipient_hr_user_id.is_not(None)))).scalars().all()
    assert any("Zeitkorrektur" in n.message for n in notes)

    # Mitarbeiter darf nicht selbst entscheiden.
    assert (await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=me, json={"approve": True})).status_code == 403

    r = await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=hr, json={"approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"
    punches = (await db_session.execute(select(Punch).where(Punch.employee_id == employee.id).order_by(Punch.timestamp_utc))).scalars().all()
    assert [(p.punch_type.value, p.timestamp_utc.strftime("%H:%M"), p.source) for p in punches][:2] == [
        ("COME", "07:00", PunchSource.MANUAL_HR),  # 08:00 Berlin (MEZ) = 07:00 UTC
        ("GO", "15:30", PunchSource.MANUAL_HR),
    ]
    assert punches[0].correction_reason == "Korrekturantrag: Tablet war aus"

    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=hr, params={"from": "2025-03-03", "to": "2025-03-03"})).json()[0]
    assert day["status"] == "COMPLETE"
    assert (await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=hr, json={"approve": False})).status_code == 400


async def test_rejected_request_changes_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, hr, me, _ = await _setup(db_session, client)
    r = await client.post(
        "/punch-correction-requests",
        headers=me,
        json={"work_date": "2025-03-04", "items": [{"punch_type": "GO", "time": "02:00", "next_day": True}], "reason": "Nachtschicht"},
    )
    request_id = r.json()["id"]
    r = await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=hr, json={"approve": False, "note": "War nicht da"})
    assert r.json()["status"] == "REJECTED" and r.json()["decision_note"] == "War nicht da"
    assert (await db_session.execute(select(Punch).where(Punch.employee_id == employee.id))).first() is None
    mine = (await client.get("/punch-correction-requests", headers=me)).json()
    assert mine[0]["status"] == "REJECTED"
