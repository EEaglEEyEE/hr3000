import csv
import io

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location, SupervisorTeamAssignment, Team
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, **kwargs) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name=kwargs.pop("first_name", "Max"),
        last_name=kwargs.pop("last_name", "Mustermann"),
        employee_number=kwargs.pop("employee_number", "EMP-1"),
        active=True,
        **kwargs,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_admin_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_supervisor_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="supervisor@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "pw"})
    return response.json()["access_token"]


def _parse_csv(text: str) -> list[dict]:
    # BOM am Anfang entfernen (siehe app/api/payroll_export.py), sonst wird
    # er Teil des ersten Spaltennamens.
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    return list(reader)


async def test_payroll_export_aggregates_target_actual_and_open_days(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "dddddddd-1111-1111-1111-111111111111",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "dddddddd-2222-2222-2222-222222222222",
        },
    )

    response = await client.get(
        "/payroll-export",
        params={"employee_ids": [employee.id], "from": "2026-08-10", "to": "2026-08-14"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    rows = _parse_csv(response.text)
    assert len(rows) == 1
    row = rows[0]
    assert row["Personalnummer"] == "EMP-1"
    assert row["Nachname"] == "Mustermann"
    # Kein Schichtplan konfiguriert -> target_minutes bleibt an jedem Tag None -> Soll 0.
    assert row["Soll (Std.)"] == "0,00"
    assert row["Ist (Std.)"] == "8,00"
    assert row["Saldo (Std.)"] == "8,00"
    # Die 4 Tage ohne Stempelung haben kein Soll (kein Modell) -> nichts fehlt, nicht offen
    # (wie unter "Zu klären" und im Monatsbericht; früher zählten sie hier – auch am Wochenende).
    assert row["Offene/fehlerhafte Tage"] == "0"
    assert row["Urlaubstage"] == "0"


async def test_payroll_export_rejects_empty_employee_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.get(
        "/payroll-export",
        params={"from": "2026-08-10", "to": "2026-08-14"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "NO_EMPLOYEES"


async def test_payroll_export_unknown_employee_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.get(
        "/payroll-export",
        params={"employee_ids": [999], "from": "2026-08-10", "to": "2026-08-14"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_payroll_export_rejects_oversized_range(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.get(
        "/payroll-export",
        params={"employee_ids": [employee.id], "from": "2025-01-01", "to": "2027-01-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "RANGE_TOO_LARGE"


async def test_supervisor_cannot_export_payroll(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    supervisor = await _create_supervisor_hr_user(db_session)

    own_team = Team(name="Team Nord", location_id=location.id)
    other_team = Team(name="Team Sued", location_id=location.id)
    db_session.add_all([own_team, other_team])
    await db_session.commit()
    await db_session.refresh(own_team)
    await db_session.refresh(other_team)

    db_session.add(SupervisorTeamAssignment(team_id=own_team.id, account_id=supervisor.id))
    await db_session.commit()

    own_employee = await _create_employee(
        db_session, location, first_name="Erika", employee_number="EMP-OWN", team_id=own_team.id
    )
    other_employee = await _create_employee(
        db_session, location, first_name="Otto", employee_number="EMP-OTHER", team_id=other_team.id
    )

    token = await _token(client, "supervisor@example.com")

    own_export = await client.get(
        "/payroll-export",
        params={"employee_ids": [own_employee.id], "from": "2026-08-10", "to": "2026-08-14"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Supervisor dürfen nur ansehen (Anwesenheiten/Abwesenheiten) – kein Lohn-Export, auch nicht fürs eigene Team.
    assert own_export.status_code == 403

    other_export = await client.get(
        "/payroll-export",
        params={"employee_ids": [other_employee.id], "from": "2026-08-10", "to": "2026-08-14"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert other_export.status_code == 403
