from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _base(db_session: AsyncSession):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1",
        login_email="erika@example.com", password_hash=hash_password("geheim-123"),
        pin_hash=hash_password("1234"),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return location, employee


async def _admin_headers(client: AsyncClient) -> dict:
    login = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_deactivated_employee_loses_access_immediately(client: AsyncClient, db_session: AsyncSession) -> None:
    _, employee = await _base(db_session)
    login = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "geheim-123"})
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get(f"/employees/{employee.id}", headers=headers)).status_code == 200

    employee.active = False
    await db_session.commit()

    assert (await client.get(f"/employees/{employee.id}", headers=headers)).status_code == 401
    refresh = await client.post("/auth/employee/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401
    again = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "geheim-123"})
    assert again.status_code == 401


async def test_password_reset_ends_existing_sessions(client: AsyncClient, db_session: AsyncSession) -> None:
    _, employee = await _base(db_session)
    login = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "geheim-123"})
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get(f"/employees/{employee.id}", headers=headers)).status_code == 200

    reset = await client.post(
        f"/employees/{employee.id}/reset-password", headers=await _admin_headers(client), json={"send_email": False}
    )
    assert reset.status_code == 200

    assert (await client.get(f"/employees/{employee.id}", headers=headers)).status_code == 401
    refresh = await client.post("/auth/employee/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401


async def test_login_is_rate_limited_and_success_resets(client: AsyncClient, db_session: AsyncSession) -> None:
    await _base(db_session)
    wrong = {"email": "erika@example.com", "password": "falsch"}

    for _ in range(8):
        assert (await client.post("/auth/employee/login", json=wrong)).status_code == 401
    blocked = await client.post("/auth/employee/login", json=wrong)
    still_blocked = await client.post(
        "/auth/employee/login", json={"email": "erika@example.com", "password": "geheim-123"}
    )
    other_account = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})

    assert blocked.status_code == 429 and blocked.json()["code"] == "TOO_MANY_ATTEMPTS"
    assert still_blocked.status_code == 429  # auch das richtige Passwort zählt während der Sperre nicht
    assert other_account.status_code == 200  # andere Konten sind nicht betroffen


async def test_successful_login_resets_failure_counter(client: AsyncClient, db_session: AsyncSession) -> None:
    await _base(db_session)

    for _ in range(5):
        await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "falsch"})
    ok = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "geheim-123"})
    for _ in range(5):
        await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "falsch"})
    ok_again = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "geheim-123"})

    assert ok.status_code == 200 and ok_again.status_code == 200


async def test_overlong_password_is_a_clean_401_not_a_500(client: AsyncClient, db_session: AsyncSession) -> None:
    await _base(db_session)

    response = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "x" * 200})
    too_long = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "x" * 300})

    assert response.status_code == 401
    assert too_long.status_code == 422


async def test_password_policy_for_new_passwords(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _base(db_session)
    headers = await _admin_headers(client)
    base = {"location_id": location.id, "first_name": "A", "last_name": "B"}

    short = await client.post("/employees", headers=headers, json={**base, "employee_number": "N1", "password": "kurz"})
    long_ = await client.post("/employees", headers=headers, json={**base, "employee_number": "N2", "password": "x" * 80})
    ok = await client.post("/employees", headers=headers, json={**base, "employee_number": "N3", "password": "lang-genug-1"})
    hr_short = await client.post("/hr-users", headers=headers, json={"email": "a@b.de", "password": "kurz", "role": "HR"})

    assert short.status_code == 422 and long_.status_code == 422 and hr_short.status_code == 422
    assert ok.status_code == 201


async def test_pin_is_locked_after_repeated_failures(client: AsyncClient, db_session: AsyncSession) -> None:
    location, employee = await _base(db_session)
    db_session.add(Device(location_id=location.id, device_token="dev-1", name="Kiosk"))
    await db_session.commit()
    await client.patch("/settings", headers=await _admin_headers(client), json={"require_pin_for_punch": True})
    device = (await client.post("/auth/device/login", json={"device_token": "dev-1"})).json()
    headers = {"Authorization": f"Bearer {device['access_token']}"}

    def punch(pin: str, n: int):
        return client.post(
            "/punches",
            headers=headers,
            json={"employee_id": employee.id, "punch_type": "COME", "timestamp_utc": "2026-08-10T06:00:00Z",
                  "idempotency_key": f"aaaaaaaa-0000-0000-0000-{n:012d}", "pin": pin},
        )

    for n in range(5):
        assert (await punch("0000", n)).status_code == 401
    locked = await punch("1234", 99)  # richtige PIN, aber gesperrt

    assert locked.status_code == 429 and locked.json()["code"] == "PIN_LOCKED"
