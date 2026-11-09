from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Employee,
    Holiday,
    HrRole,
    Account,
    Location,
    SupervisorTeamAssignment,
    Team,
)
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(
    db_session: AsyncSession, location: Location, number: str, team_id: int | None = None
) -> Employee:
    employee = Employee(
        location_id=location.id,
        team_id=team_id,
        first_name="Erika",
        last_name="Musterfrau",
        employee_number=number,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_hr_user(db_session: AsyncSession, role: HrRole = HrRole.HR) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_team_calendar_shows_absence_and_holiday(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 12),
            approval_status=AbsenceApprovalStatus.APPROVED,
        )
    )
    db_session.add(Holiday(date=date(2026, 8, 15), name="Mariä Himmelfahrt", locations=[location]))
    await db_session.commit()

    response = await client.get(
        "/team-calendar?from=2026-08-01&to=2026-08-31",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    days_by_date = {d["date"]: d for d in body[0]["days"]}
    assert days_by_date["2026-08-10"]["status"] == "ABSENCE"
    assert days_by_date["2026-08-10"]["absence_type"] == "VACATION"
    assert days_by_date["2026-08-12"]["status"] == "ABSENCE"
    assert days_by_date["2026-08-13"]["status"] is None
    assert days_by_date["2026-08-15"]["status"] == "HOLIDAY"


async def test_pending_absence_not_shown(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 10),
            approval_status=AbsenceApprovalStatus.PENDING,
        )
    )
    await db_session.commit()

    response = await client.get(
        "/team-calendar?from=2026-08-01&to=2026-08-31",
        headers={"Authorization": f"Bearer {token}"},
    )

    days_by_date = {d["date"]: d for d in response.json()[0]["days"]}
    assert days_by_date["2026-08-10"]["status"] is None


async def test_location_wide_holiday_does_not_apply_to_other_location(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location_a = await _create_location(db_session, "Standort A")
    location_b = await _create_location(db_session, "Standort B")
    await _create_employee(db_session, location_a, "EMP-A")
    await _create_employee(db_session, location_b, "EMP-B")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    db_session.add(Holiday(date=date(2026, 8, 15), name="Regionaler Feiertag", locations=[location_a]))
    await db_session.commit()

    response = await client.get(
        "/team-calendar?from=2026-08-01&to=2026-08-31",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    statuses = [{d["date"]: d["status"] for d in e["days"]} for e in body]
    assert len(statuses) == 2
    holiday_count = sum(1 for s in statuses if s["2026-08-15"] == "HOLIDAY")
    assert holiday_count == 1


async def test_supervisor_sees_only_own_team(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    team = Team(name="Team Nord")
    other_team = Team(name="Team Süd")
    db_session.add_all([team, other_team])
    await db_session.commit()
    await db_session.refresh(team)
    await db_session.refresh(other_team)

    own_employee = await _create_employee(db_session, location, "EMP-OWN", team_id=team.id)
    await _create_employee(db_session, location, "EMP-OTHER", team_id=other_team.id)

    supervisor = Account(email="super@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR)
    db_session.add(supervisor)
    await db_session.commit()
    await db_session.refresh(supervisor)
    db_session.add(SupervisorTeamAssignment(team_id=team.id, account_id=supervisor.id))
    await db_session.commit()

    login_response = await client.post(
        "/auth/login", json={"email": "super@example.com", "password": "pw"}
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/team-calendar?from=2026-08-01&to=2026-08-31",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == own_employee.id


async def test_invalid_range_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get(
        "/team-calendar?from=2026-08-10&to=2026-08-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_RANGE"


async def test_birthdays_follow_tenant_and_employee_setting(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.services.settings_service import get_or_create_settings

    location = await _create_location(db_session)
    shown = await _create_employee(db_session, location, "EMP-1")
    hidden = await _create_employee(db_session, location, "EMP-2")
    leap = await _create_employee(db_session, location, "EMP-3")
    shown.birth_date = date(1990, 8, 20)
    hidden.birth_date = date(1985, 8, 21)
    hidden.show_birthday_in_calendar = False
    leap.birth_date = date(1996, 2, 29)
    await _create_hr_user(db_session)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}

    async def birthdays(start: str, end: str) -> set[tuple[int, str]]:
        body = (await client.get(f"/team-calendar?from={start}&to={end}", headers=headers)).json()
        return {(e["employee_id"], d["date"]) for e in body for d in e["days"] if d["is_birthday"]}

    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.show_birthdays_in_calendar = False
    await db_session.commit()
    assert await birthdays("2026-08-01", "2026-08-31") == set()

    settings_row.show_birthdays_in_calendar = True
    await db_session.commit()
    assert await birthdays("2026-08-01", "2026-08-31") == {(shown.id, "2026-08-20")}
    assert await birthdays("2026-02-01", "2026-03-01") == {(leap.id, "2026-02-28")}  # kein Schaltjahr
