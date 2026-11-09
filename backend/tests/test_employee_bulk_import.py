from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, Account, Location, Team
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_team(db_session: AsyncSession, name: str = "Team Nord") -> Team:
    team = Team(name=name)
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)
    return team


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


def _upload(csv_text: str) -> dict:
    return {"file": ("mitarbeiter.csv", csv_text.encode("utf-8"), "text/csv")}


async def test_bulk_import_creates_valid_rows(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    team = await _create_team(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    csv_text = (
        "vorname;nachname;personalnummer;standort;team;aktiv;eintrittsdatum;geburtsdatum\n"
        f"Erika;Musterfrau;EMP-100;{location.name};{team.name};ja;2020-03-01;1990-05-20\n"
        f"Max;Mustermann;EMP-101;{location.name};;nein;;\n"
    )

    response = await client.post(
        "/employees/bulk-import",
        headers={"Authorization": f"Bearer {token}"},
        files=_upload(csv_text),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 2
    assert body["errors"] == []

    list_response = await client.get("/employees", headers={"Authorization": f"Bearer {token}"})
    employees = list_response.json()
    assert len(employees) == 2
    erika = next(e for e in employees if e["employee_number"] == "EMP-100")
    assert erika["team_id"] == team.id
    assert erika["hire_date"] == "2020-03-01"
    assert erika["birth_date"] == "1990-05-20"
    max_ = next(e for e in employees if e["employee_number"] == "EMP-101")
    assert max_["active"] is False
    assert max_["team_id"] is None


async def test_bulk_import_reports_row_errors_without_blocking_valid_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    csv_text = (
        "vorname;nachname;personalnummer;standort\n"
        f"Erika;Musterfrau;EMP-200;{location.name}\n"
        "Ohne;Standort;EMP-201;Unbekannter Standort\n"
        f";Leer;EMP-202;{location.name}\n"
    )

    response = await client.post(
        "/employees/bulk-import",
        headers={"Authorization": f"Bearer {token}"},
        files=_upload(csv_text),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 2
    assert body["errors"][0]["row"] == 3
    assert "Standort" in body["errors"][0]["message"]
    assert body["errors"][1]["row"] == 4


async def test_bulk_import_rejects_duplicate_employee_number_within_file(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    csv_text = (
        "vorname;nachname;personalnummer;standort\n"
        f"Erika;Musterfrau;EMP-300;{location.name}\n"
        f"Max;Mustermann;EMP-300;{location.name}\n"
    )

    response = await client.post(
        "/employees/bulk-import",
        headers={"Authorization": f"Bearer {token}"},
        files=_upload(csv_text),
    )

    body = response.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 1
    assert "bereits vergeben" in body["errors"][0]["message"]


async def test_bulk_import_rejects_duplicate_number_against_existing_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Bereits",
            "last_name": "Vorhanden",
            "employee_number": "EMP-400",
        },
    )

    csv_text = "vorname;nachname;personalnummer;standort\n" f"Neu;Angelegt;EMP-400;{location.name}\n"

    response = await client.post(
        "/employees/bulk-import",
        headers={"Authorization": f"Bearer {token}"},
        files=_upload(csv_text),
    )

    body = response.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1


async def test_bulk_import_missing_required_column_reports_single_error(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    csv_text = "vorname;nachname\nErika;Musterfrau\n"

    response = await client.post(
        "/employees/bulk-import",
        headers={"Authorization": f"Bearer {token}"},
        files=_upload(csv_text),
    )

    body = response.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "personalnummer" in body["errors"][0]["message"]


async def test_bulk_import_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    csv_text = "vorname;nachname;personalnummer;standort\n" f"Erika;Musterfrau;EMP-500;{location.name}\n"

    await client.post(
        "/employees/bulk-import",
        headers={"Authorization": f"Bearer {token}"},
        files=_upload(csv_text),
    )

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEES_BULK_IMPORTED")
    assert "1 Mitarbeiter importiert" in entry["detail"]
