from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(
    db_session: AsyncSession, location: Location, number: str = "EMP-1", active: bool = True
) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number=number,
        active=active,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_device(db_session: AsyncSession, location: Location, token: str) -> Device:
    device = Device(location_id=location.id, device_token=token, name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def test_hr_can_create_and_list_employees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["active"] is True

    list_response = await client.get("/employees", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_create_employee_unknown_location(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": 999, "first_name": "A", "last_name": "B", "employee_number": "X"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_NOT_FOUND"


async def test_create_employee_duplicate_number_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee(db_session, location, number="EMP-1")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-1",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EMPLOYEE_NUMBER_TAKEN"


async def test_search_filters_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_employee(db_session, location, number="EMP-1")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get(
        "/employees?search=Muster", headers={"Authorization": f"Bearer {token}"}
    )
    assert len(response.json()) == 1

    response = await client.get(
        "/employees?search=Nichtvorhanden", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.json() == []


async def test_hr_can_update_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.patch(
        f"/employees/{employee.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"active": False},
    )

    assert response.status_code == 200
    assert response.json()["active"] is False


async def test_employee_pin_can_be_set_and_updated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "pin": "1234",
        },
    )
    assert create_response.status_code == 201
    employee_id = create_response.json()["id"]
    assert create_response.json()["has_pin"] is True

    no_pin_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Max",
            "last_name": "Mustermann",
            "employee_number": "EMP-43",
        },
    )
    assert no_pin_response.json()["has_pin"] is False

    update_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"pin": "5678"},
    )
    assert update_response.json()["has_pin"] is True


async def test_employee_nfc_uid_can_be_set_updated_and_cleared(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "nfc_uid": "04:AA:BB:CC",
        },
    )
    assert create_response.status_code == 201
    employee_id = create_response.json()["id"]
    assert create_response.json()["nfc_uid"] == "04aabbcc"  # vereinheitlicht

    update_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"nfc_uid": "04:DD:EE:FF"},
    )
    assert update_response.json()["nfc_uid"] == "04ddeeff"

    clear_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"nfc_uid": ""},
    )
    assert clear_response.json()["nfc_uid"] is None


async def test_duplicate_nfc_uid_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "nfc_uid": "04:AA:BB:CC",
        },
    )

    response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Max",
            "last_name": "Mustermann",
            "employee_number": "EMP-43",
            "nfc_uid": "04:AA:BB:CC",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "NFC_UID_TAKEN"


async def test_employee_hire_and_termination_date_lifecycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "hire_date": "2020-03-01",
        },
    )
    assert create_response.status_code == 201
    employee_id = create_response.json()["id"]
    assert create_response.json()["hire_date"] == "2020-03-01"
    assert create_response.json()["termination_date"] is None

    update_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"termination_date": "2026-12-31"},
    )
    assert update_response.json()["termination_date"] == "2026-12-31"
    # active bleibt unberührt von termination_date, siehe app/models/employee.py.
    assert update_response.json()["active"] is True

    clear_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"clear_termination_date": True},
    )
    assert clear_response.json()["termination_date"] is None


async def test_employee_birth_date_lifecycle(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-44",
            "birth_date": "1990-05-20",
        },
    )
    assert create_response.status_code == 201
    employee_id = create_response.json()["id"]
    assert create_response.json()["birth_date"] == "1990-05-20"
    # Default: sichtbar, sofern die globale Einstellung es erlaubt.
    assert create_response.json()["show_birthday_in_calendar"] is True

    hide_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"show_birthday_in_calendar": False},
    )
    assert hide_response.json()["show_birthday_in_calendar"] is False
    # birth_date bleibt von einer reinen Sichtbarkeitsänderung unberührt.
    assert hide_response.json()["birth_date"] == "1990-05-20"

    clear_response = await client.patch(
        f"/employees/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"clear_birth_date": True},
    )
    assert clear_response.json()["birth_date"] is None


async def test_get_unknown_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get("/employees/999", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_kiosk_can_list_own_location_employees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    response = await client.get(
        f"/locations/{location.id}/employees", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_location_employees_report_today_status_and_has_pin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    employee.pin_hash = hash_password("1234")
    await db_session.commit()
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    before_punch = await client.get(
        f"/locations/{location.id}/employees", headers={"Authorization": f"Bearer {token}"}
    )
    assert before_punch.json()[0]["has_pin"] is True
    assert before_punch.json()[0]["today_status"] == "OPEN_MISSING_PUNCH"

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "idempotency_key": "99999999-9999-9999-9999-999999999999",
        },
    )

    after_punch = await client.get(
        f"/locations/{location.id}/employees", headers={"Authorization": f"Bearer {token}"}
    )
    assert after_punch.json()[0]["today_status"] == "PRESENT"


async def test_kiosk_cannot_list_other_location_employees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location_a = await _create_location(db_session, "Standort A")
    location_b = await _create_location(db_session, "Standort B")
    await _create_employee(db_session, location_b)
    await _create_device(db_session, location_a, "device-a")
    token = await _device_token(client, "device-a")

    response = await client.get(
        f"/locations/{location_b.id}/employees", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_NOT_FOUND"


async def test_location_employee_list_excludes_inactive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee(db_session, location, number="EMP-1", active=False)
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    response = await client.get(
        f"/locations/{location.id}/employees", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.json() == []
