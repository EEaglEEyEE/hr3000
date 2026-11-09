"""Eigene Abwesenheitsarten: Kategorien (bezahlt/unbezahlt/Freizeitausgleich), Genehmigung je Art,
Self-Service-Freigabe und Verwaltung."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="A1",
        login_email="erika@example.com",
        password_hash=hash_password("pw123456"),
    )
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2025-01-01"},
    )
    assert r.status_code == 200, r.text
    return employee, headers


async def _types(client: AsyncClient, headers: dict) -> dict[str, dict]:
    r = await client.get("/absence-types", headers=headers)
    assert r.status_code == 200, r.text
    return {t["name"]: t for t in r.json()}


async def _day(client: AsyncClient, headers: dict, employee_id: int, day: str) -> dict:
    days = (
        await client.get(f"/employees/{employee_id}/timesheet", headers=headers, params={"from": day, "to": day})
    ).json()
    return days[0]


async def test_default_types_are_seeded(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _setup(db_session, client)
    types = await _types(client, headers)
    assert set(types) == {"Urlaub", "Krank", "Sonderurlaub", "Freizeitausgleich", "Unbezahlt"}
    assert types["Krank"]["certificate_from_day"] == 4
    assert types["Unbezahlt"]["category"] == "UNPAID"


async def test_categories_change_the_balance_effect(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    types = await _types(client, headers)

    for name, day in (("Krank", "2025-03-03"), ("Unbezahlt", "2025-03-04"), ("Freizeitausgleich", "2025-03-05")):
        r = await client.post(
            "/absences",
            headers=headers,
            json={"employee_id": employee.id, "absence_type_id": types[name]["id"], "date_from": day, "date_to": day},
        )
        assert r.status_code == 201, r.text
        assert r.json()["absence_type_id"] == types[name]["id"]

    sick = await _day(client, headers, employee.id, "2025-03-03")
    assert (sick["target_minutes"], sick["actual_minutes"], sick["absence_type_id"]) == (480, 480, types["Krank"]["id"])
    unpaid = await _day(client, headers, employee.id, "2025-03-04")
    assert (unpaid["target_minutes"], unpaid["actual_minutes"]) == (0, 0)
    time_off = await _day(client, headers, employee.id, "2025-03-05")
    assert (time_off["target_minutes"], time_off["actual_minutes"]) == (480, 0)  # Saldo sinkt um 8 Std.


async def test_custom_type_and_self_service_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    r = await client.post(
        "/absence-types",
        headers=headers,
        json={"name": "Kind krank", "color": "#f97316", "category": "SICK", "requires_approval": True},
    )
    assert r.status_code == 201, r.text
    child_sick = r.json()
    assert (await client.post("/absence-types", headers=headers, json={"name": "Kind krank", "category": "SICK"})).status_code == 409
    assert (await client.post("/absence-types", headers=headers, json={"name": "X", "color": "red", "category": "SICK"})).status_code == 422

    employee_token = (
        await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})
    ).json()["access_token"]
    employee_headers = {"Authorization": f"Bearer {employee_token}"}
    assert any(t["name"] == "Kind krank" for t in (await client.get("/absence-types", headers=employee_headers)).json())

    # Art mit Genehmigungspflicht: Selbstmeldung bleibt offen.
    r = await client.post(
        "/absences",
        headers=employee_headers,
        json={"employee_id": employee.id, "absence_type_id": child_sick["id"], "date_from": "2025-03-10", "date_to": "2025-03-10"},
    )
    assert r.status_code == 201 and r.json()["approval_status"] == "PENDING" and r.json()["type"] == "SICK"

    # Nur HR darf die Art eintragen.
    types = await _types(client, headers)
    await client.patch(f"/absence-types/{types['Unbezahlt']['id']}", headers=headers, json={"employee_can_request": False})
    r = await client.post(
        "/absences",
        headers=employee_headers,
        json={"employee_id": employee.id, "absence_type_id": types["Unbezahlt"]["id"], "date_from": "2025-03-11", "date_to": "2025-03-11"},
    )
    assert r.status_code == 403 and r.json()["code"] == "ABSENCE_TYPE_NOT_REQUESTABLE"

    # Deaktivierte Art lässt sich nicht mehr neu buchen; Verwaltung nur für Admins.
    await client.patch(f"/absence-types/{child_sick['id']}", headers=headers, json={"active": False})
    r = await client.post(
        "/absences",
        headers=headers,
        json={"employee_id": employee.id, "absence_type_id": child_sick["id"], "date_from": "2025-03-12", "date_to": "2025-03-12"},
    )
    assert r.status_code == 400 and r.json()["code"] == "ABSENCE_TYPE_INACTIVE"
    assert (await client.post("/absence-types", headers=employee_headers, json={"name": "Y", "category": "SICK"})).status_code in (401, 403)


async def test_payroll_categories_like_unpaid_with_own_export_column(client: AsyncClient, db_session: AsyncSession) -> None:
    """Mutterschutz/Elternzeit, Kurzarbeit, Unentschuldigt, Pflege rechnen wie „Unbezahlt“ (Soll
    entfällt). Im Lohn-Export bekommen sie eine eigene Spalte – aber nur, wenn sie im Zeitraum
    vorkommen; sonst bleibt der Export unverändert."""
    import csv
    import io

    employee, headers = await _setup(db_session, client)

    def export_rows(text: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";"))

    params = {"employee_ids": [employee.id], "from": "2025-03-03", "to": "2025-03-07"}
    before = await client.get("/payroll-export", headers=headers, params=params)
    assert before.status_code == 200, before.text
    assert "Elternzeit" not in before.text.splitlines()[0] and "Kurzarbeit" not in before.text.splitlines()[0]

    created = {}
    for name, category in (("Elternzeit", "PARENTAL_LEAVE"), ("Kurzarbeit", "SHORT_TIME_WORK"), ("Unentschuldigt", "UNEXCUSED"), ("Pflegezeit", "CARE_LEAVE")):
        r = await client.post("/absence-types", headers=headers, json={"name": name, "category": category})
        assert r.status_code == 201, r.text
        created[name] = r.json()["id"]

    for name, day_from, day_to in (("Elternzeit", "2025-03-03", "2025-03-04"), ("Kurzarbeit", "2025-03-05", "2025-03-05")):
        r = await client.post(
            "/absences",
            headers=headers,
            json={"employee_id": employee.id, "absence_type_id": created[name], "date_from": day_from, "date_to": day_to},
        )
        assert r.status_code == 201, r.text

    for day in ("2025-03-03", "2025-03-05"):
        values = await _day(client, headers, employee.id, day)
        assert (values["target_minutes"], values["actual_minutes"]) == (0, 0)

    after = await client.get("/payroll-export", headers=headers, params=params)
    row = export_rows(after.text)[0]
    assert row["Mutterschutz/Elternzeit-Tage"] == "2"
    assert row["Kurzarbeit-Tage"] == "1"
    assert row["Unbezahlte Tage"] == "0"  # bleibt der Kategorie „Unbezahlt“ vorbehalten
    assert "Unentschuldigte Tage" not in row and "Pflege-Tage" not in row  # nicht genutzt
