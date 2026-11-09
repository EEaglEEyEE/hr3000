"""Arbeitszeitmodelle: eigene Einträge je Mandant, die Mitarbeitern ab einem Stichtag zugewiesen werden.
Eine Modelländerung ab Stichtag gilt für alle Zugewiesenen (verknüpft), die Vergangenheit bleibt.
Je Mitarbeiter gilt entweder ein Modell oder die individuelle Eingabe; Gleitzeit-Rahmen und
Pünktlichkeits-Toleranz lassen sich je Modell festlegen."""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    EmployeeDefaultShift,
    Employee,
    HrRole,
    Account,
    Location,
    PeriodClosure,
    PeriodStatus,
    Tenant,
    WorkTimeProfile,
    WorkTimeProfileVersion,
)
from app.services.auth_service import hash_password

FULL_TIME = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]}
PART_TIME = {"weekly_hours": 30, "weekdays": [0, 1, 2, 3, 4]}
MONDAY, TUESDAY = "2026-10-05", "2026-10-06"
LATER_MONDAY = "2026-11-02"


@pytest.fixture(autouse=True)
def _rules_changed_before_test_days(monkeypatch):
    """Pünktlichkeits-Hinweise gelten erst ab der letzten Regeländerung – hier ab 01.10.2026."""
    import app.api.settings as settings_api

    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 1)

    monkeypatch.setattr(settings_api, "date", _Date)


async def _admin(db_session: AsyncSession, client: AsyncClient) -> dict:
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _employee(db_session: AsyncSession, number: str, first: str = "Erika") -> Employee:
    location = (await db_session.execute(select(Location))).scalars().first()
    if location is None:
        location = Location(name="Zentrale", timezone="UTC")
        db_session.add(location)
        await db_session.commit()
    employee = Employee(location_id=location.id, first_name=first, last_name="Muster", employee_number=number, auto_break_enabled=False)
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _profile(client: AsyncClient, admin: dict, name: str = "Vollzeit Büro", **model) -> dict:
    r = await client.post("/work-time-profiles", headers=admin, json={"name": name, **(model or FULL_TIME)})
    assert r.status_code == 201, r.text
    return r.json()


async def _assign(client: AsyncClient, admin: dict, employee_id: int, profile_id: int, valid_from: str = "2026-10-01") -> dict:
    r = await client.put(
        f"/employees/{employee_id}/work-time-profile", headers=admin, json={"profile_id": profile_id, "valid_from": valid_from}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _day(client: AsyncClient, admin: dict, employee_id: int, day: str) -> dict:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})
    assert r.status_code == 200, r.text
    return r.json()[0]


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, come: str, go: str) -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _history(client: AsyncClient, admin: dict, employee_id: int) -> list[dict]:
    r = await client.get(f"/employees/{employee_id}/work-time-model/history", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


async def test_create_list_and_assign_profile(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    assert (profile["name"], profile["weekly_minutes"], profile["employee_count"]) == ("Vollzeit Büro", 2400, 0)
    assert profile["valid_from"] == "2000-01-01"  # erste Fassung gilt von Anfang an

    model = await _assign(client, admin, employee.id, profile["id"])
    assert (model["profile_id"], model["profile_name"], model["weekly_minutes"]) == (profile["id"], "Vollzeit Büro", 2400)
    assert (await _day(client, admin, employee.id, MONDAY))["target_minutes"] == 480

    listed = (await client.get("/work-time-profiles", headers=admin)).json()
    assert [(p["name"], p["employee_count"], p["employees"]) for p in listed] == [("Vollzeit Büro", 1, ["Erika Muster"])]


async def test_profile_validation_and_unique_name(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    await _profile(client, admin)
    duplicate = await client.post("/work-time-profiles", headers=admin, json={"name": "Vollzeit Büro", **FULL_TIME})
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "NAME_TAKEN"
    no_frame_times = await client.post("/work-time-profiles", headers=admin, json={"name": "X", **FULL_TIME, "flex_frame_mode": "CUSTOM"})
    assert no_frame_times.status_code == 422
    core_outside = await client.post(
        "/work-time-profiles",
        headers=admin,
        json={
            "name": "Y", **FULL_TIME, "flex_frame_mode": "CUSTOM", "flex_frame_start": "08:00", "flex_frame_end": "18:00",
            "core_time_mode": "CUSTOM", "core_time_start": "07:00", "core_time_end": "15:00",
        },
    )
    assert core_outside.status_code == 422
    too_tolerant = await client.post("/work-time-profiles", headers=admin, json={"name": "Z", **FULL_TIME, "late_tolerance_minutes": 500})
    assert too_tolerant.status_code == 422
    blank = await client.post("/work-time-profiles", headers=admin, json={"name": "   ", **FULL_TIME})
    assert blank.status_code == 422


async def test_profile_change_applies_to_all_assigned_from_date(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    first, second = await _employee(db_session, "E1"), await _employee(db_session, "E2", "Max")
    profile = await _profile(client, admin)
    await _assign(client, admin, first.id, profile["id"])
    await _assign(client, admin, second.id, profile["id"], "2026-10-15")

    r = await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-11-01"})
    assert r.status_code == 200, r.text
    assert r.json()["employee_count"] == 2
    for employee in (first, second):
        assert (await _day(client, admin, employee.id, LATER_MONDAY))["target_minutes"] == 360
    # Vergangenheit bleibt: Oktober weiter mit 8 Std.
    assert (await _day(client, admin, first.id, MONDAY))["target_minutes"] == 480
    assert (await _day(client, admin, second.id, "2026-10-19"))["target_minutes"] == 480
    history = await _history(client, admin, first.id)
    assert [(v["valid_from"], v["valid_to"], v["weekly_minutes"], v["profile_name"]) for v in history] == [
        ("2026-11-01", None, 1800, "Vollzeit Büro"),
        ("2026-10-01", "2026-10-31", 2400, "Vollzeit Büro"),
    ]
    profile_history = (await client.get(f"/work-time-profiles/{profile['id']}/history", headers=admin)).json()
    assert [(v["valid_from"], v["weekly_minutes"]) for v in profile_history] == [("2026-11-01", 1800), ("2000-01-01", 2400)]


async def test_profile_assigned_retroactively_uses_the_version_of_the_time(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    assert (await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-11-01"})).status_code == 200
    # Zuweisung erst danach, aber ab Oktober: Oktober nach der alten, November nach der neuen Fassung
    await _assign(client, admin, employee.id, profile["id"])
    assert (await _day(client, admin, employee.id, MONDAY))["target_minutes"] == 480
    assert (await _day(client, admin, employee.id, LATER_MONDAY))["target_minutes"] == 360


async def test_profile_change_rejected_when_an_assigned_month_is_locked(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    open_one, locked_one = await _employee(db_session, "E1"), await _employee(db_session, "E2", "Lena")
    profile = await _profile(client, admin)
    await _assign(client, admin, open_one.id, profile["id"])
    await _assign(client, admin, locked_one.id, profile["id"])
    db_session.add(
        PeriodClosure(tenant_id=1, employee_id=locked_one.id, year=2026, month=10, status=PeriodStatus.CLOSED,
                      target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 11, 1))
    )
    await db_session.commit()

    blocked = await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-10-15"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "PERIOD_LOCKED"
    assert "Lena Muster" in blocked.json()["detail"] and "Erika" not in blocked.json()["detail"]
    # Nichts geändert – auch nicht beim Mitarbeiter mit offenem Monat
    assert (await _day(client, admin, open_one.id, "2026-10-19"))["target_minutes"] == 480
    assert len((await client.get(f"/work-time-profiles/{profile['id']}/history", headers=admin)).json()) == 1
    # Nach dem gesperrten Monat geht es
    ok = await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-11-01"})
    assert ok.status_code == 200, ok.text


async def test_manual_model_ends_profile_and_later_profile_changes_do_not_reach_it(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    await _assign(client, admin, employee.id, profile["id"])
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={"weekly_hours": 20, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-11-01"})
    assert r.status_code == 200 and r.json()["profile_id"] is None

    assert (await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-10-15"})).status_code == 200
    # Modell wirkt bis Ende Oktober (ab 15.10. mit der neuen Fassung), danach die individuelle Eingabe
    assert (await _day(client, admin, employee.id, MONDAY))["target_minutes"] == 480
    assert (await _day(client, admin, employee.id, "2026-10-19"))["target_minutes"] == 360
    assert (await _day(client, admin, employee.id, LATER_MONDAY))["target_minutes"] == 240


async def test_editing_a_profile_version_makes_it_individual(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    await _assign(client, admin, employee.id, profile["id"])
    version_id = (await _history(client, admin, employee.id))[0]["id"]
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{version_id}", headers=admin, json={**FULL_TIME, "weekly_hours": 35, "valid_from": "2026-10-01"}
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["profile_id"] is None
    assert (await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-10-15"})).status_code == 200
    assert (await _day(client, admin, employee.id, "2026-10-19"))["target_minutes"] == 420  # 35/5, nicht das Modell


async def test_deleting_a_later_version_extends_the_profile_assignment_with_its_versions(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    await _assign(client, admin, employee.id, profile["id"])
    await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={"weekly_hours": 20, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-11-01"})
    # Modelländerung ab Dezember erreicht den Mitarbeiter zunächst nicht …
    assert (await client.put(f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**PART_TIME, "valid_from": "2026-12-01"})).status_code == 200
    manual = (await _history(client, admin, employee.id))[0]
    assert manual["profile_id"] is None
    # … nach dem Löschen der individuellen Fassung gilt wieder das Modell – mit seiner Dezember-Fassung
    assert (await client.delete(f"/employees/{employee.id}/work-time-model/versions/{manual['id']}", headers=admin)).status_code == 204
    history = await _history(client, admin, employee.id)
    assert [(v["valid_from"], v["valid_to"], v["weekly_minutes"], v["profile_id"]) for v in history] == [
        ("2026-12-01", None, 1800, profile["id"]),
        ("2026-10-01", "2026-11-30", 2400, profile["id"]),
    ]
    assert (await _day(client, admin, employee.id, LATER_MONDAY))["target_minutes"] == 480


async def test_reassigning_the_same_profile_keeps_one_assignment(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    await _assign(client, admin, employee.id, profile["id"])
    await _assign(client, admin, employee.id, profile["id"], "2026-11-01")
    history = await _history(client, admin, employee.id)
    assert [(v["valid_from"], v["valid_to"]) for v in history] == [("2026-10-01", None)]


async def test_switching_between_profiles(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    full = await _profile(client, admin)
    part = await _profile(client, admin, "Teilzeit 30", **PART_TIME)
    await _assign(client, admin, employee.id, full["id"])
    model = await _assign(client, admin, employee.id, part["id"], "2026-11-01")
    assert model["profile_name"] == "Teilzeit 30"
    assert (await _day(client, admin, employee.id, MONDAY))["target_minutes"] == 480
    assert (await _day(client, admin, employee.id, LATER_MONDAY))["target_minutes"] == 360
    names = {p["name"]: p["employee_count"] for p in (await client.get("/work-time-profiles", headers=admin)).json()}
    assert names == {"Vollzeit Büro": 0, "Teilzeit 30": 1}  # heute (Testlauf) zählt die aktuelle Zuweisung


async def test_flex_frame_and_tolerance_per_profile(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    tolerant, strict, frameless = (
        await _employee(db_session, "E1", "Toni"),
        await _employee(db_session, "E2", "Stefan"),
        await _employee(db_session, "E3", "Frieda"),
    )
    r = await client.patch(
        "/settings",
        headers=admin,
        json={"core_time_start": "09:00", "core_time_end": "15:00", "late_tolerance_minutes": 0,
              "flex_frame_start": "07:00", "flex_frame_end": "19:00", "disabled_day_flags": []},
    )
    assert r.status_code == 200, r.text
    relaxed = await _profile(client, admin, "Gleitzeit locker", **FULL_TIME, late_tolerance_minutes=15, flex_frame_mode="CUSTOM",
                             flex_frame_start="06:00", flex_frame_end="20:00")
    no_frame = await _profile(client, admin, "Ohne Rahmen", **FULL_TIME, flex_frame_mode="NONE")
    await _assign(client, admin, tolerant.id, relaxed["id"])
    await _assign(client, admin, frameless.id, no_frame["id"])
    await client.put(f"/employees/{strict.id}/work-time-model", headers=admin, json={**FULL_TIME, "valid_from": "2026-10-01"})

    for employee in (tolerant, strict, frameless):
        await _work(client, admin, employee.id, MONDAY, "09:10", "17:10")
        await _work(client, admin, employee.id, TUESDAY, "06:30", "15:00")
    assert (await _day(client, admin, tolerant.id, MONDAY))["flags"] == []  # 10 Min. < 15 Min. Toleranz
    assert (await _day(client, admin, strict.id, MONDAY))["flags"] == ["LATE_ARRIVAL"]  # Toleranz der Firma: 0
    assert (await _day(client, admin, frameless.id, MONDAY))["flags"] == ["LATE_ARRIVAL"]  # Toleranz wie Firma
    assert (await _day(client, admin, tolerant.id, TUESDAY))["flags"] == []  # eigener Rahmen ab 06:00
    assert (await _day(client, admin, strict.id, TUESDAY))["flags"] == ["OUTSIDE_FLEX_FRAME"]  # Rahmen der Firma ab 07:00
    assert (await _day(client, admin, frameless.id, TUESDAY))["flags"] == []  # kein Rahmen

    model = (await client.get(f"/employees/{tolerant.id}/work-time-model", headers=admin)).json()
    assert (model["flex_frame_mode"], model["flex_frame_start"], model["late_tolerance_minutes"]) == ("CUSTOM", "06:00:00", 15)


async def test_archive_delete_and_tenant_isolation(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    unused = await _profile(client, admin, "Unbenutzt")
    used = await _profile(client, admin)
    await _assign(client, admin, employee.id, used["id"])

    assert (await client.delete(f"/work-time-profiles/{unused['id']}", headers=admin)).status_code == 204
    in_use = await client.delete(f"/work-time-profiles/{used['id']}", headers=admin)
    assert in_use.status_code == 409 and in_use.json()["code"] == "WORK_TIME_PROFILE_IN_USE"

    archived = await client.patch(f"/work-time-profiles/{used['id']}", headers=admin, json={"archived": True, "name": "Vollzeit alt"})
    assert archived.status_code == 200 and archived.json()["archived"] is True
    assert (await client.get("/work-time-profiles", headers=admin)).json() == []
    assert [p["name"] for p in (await client.get("/work-time-profiles", headers=admin, params={"include_archived": True})).json()] == ["Vollzeit alt"]
    other = await _employee(db_session, "E2", "Max")
    blocked = await client.put(f"/employees/{other.id}/work-time-profile", headers=admin, json={"profile_id": used["id"], "valid_from": "2026-10-01"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "WORK_TIME_PROFILE_ARCHIVED"
    # Bestehende Zuweisung gilt weiter
    assert (await _day(client, admin, employee.id, MONDAY))["target_minutes"] == 480

    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    foreign = WorkTimeProfile(tenant_id=2, name="Fremd", archived=False)
    db_session.add(foreign)
    await db_session.commit()
    db_session.add(WorkTimeProfileVersion(profile_id=foreign.id, valid_from=date(2000, 1, 1), weekdays_mask=31, target_minutes=2400))
    await db_session.commit()
    for response in (
        await client.put(f"/employees/{other.id}/work-time-profile", headers=admin, json={"profile_id": foreign.id, "valid_from": "2026-10-01"}),
        await client.get(f"/work-time-profiles/{foreign.id}/history", headers=admin),
        await client.put(f"/work-time-profiles/{foreign.id}/model", headers=admin, json={**FULL_TIME, "valid_from": "2026-10-01"}),
    ):
        assert response.status_code == 404 and response.json()["code"] == "WORK_TIME_PROFILE_NOT_FOUND"


async def test_assignment_into_locked_month_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    db_session.add(
        PeriodClosure(tenant_id=1, employee_id=employee.id, year=2026, month=10, status=PeriodStatus.CLOSED,
                      target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 11, 1))
    )
    await db_session.commit()
    r = await client.put(f"/employees/{employee.id}/work-time-profile", headers=admin, json={"profile_id": profile["id"], "valid_from": "2026-10-01"})
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"


async def test_shift_template_break_change_follows_through_profile(client: AsyncClient, db_session: AsyncSession) -> None:
    """Eine Modell-Fassung ohne eigene Pause nutzt die der Schichtvorlage. Ändert sich die Pause der
    Vorlage ab Stichtag, teilen sich Modell und Zuweisung gleich – nichts springt zurück."""
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    r = await client.post(
        "/shift-templates", headers=admin,
        json={"name": "Früh", "start_time": "06:00", "end_time": "14:30", "break_mode": "FLEXIBLE", "min_break_minutes": 30, "target_minutes": 480},
    )
    assert r.status_code == 201, r.text
    template_id = r.json()["id"]
    profile = await _profile(client, admin, "Frühschicht", **FULL_TIME, shift_template_id=template_id)
    await _assign(client, admin, employee.id, profile["id"])
    in_use = await client.delete(f"/shift-templates/{template_id}", headers=admin)
    assert in_use.status_code == 409

    changed = await client.patch(f"/shift-templates/{template_id}", headers=admin, json={"min_break_minutes": 45, "valid_from": "2026-11-01"})
    assert changed.status_code == 200, changed.text
    rows = (
        await db_session.execute(
            select(EmployeeDefaultShift).where(EmployeeDefaultShift.employee_id == employee.id).order_by(EmployeeDefaultShift.valid_from)
        )
    ).scalars().all()
    versions = (
        await db_session.execute(
            select(WorkTimeProfileVersion).where(WorkTimeProfileVersion.profile_id == profile["id"]).order_by(WorkTimeProfileVersion.valid_from)
        )
    ).scalars().all()
    assert [(row.valid_from, row.shift_template_id) for row in rows] == [
        (date(2026, 10, 1), template_id),
        (date(2026, 11, 1), changed.json()["id"]),
    ]
    assert [v.shift_template_id for v in versions] == [template_id, changed.json()["id"]]
    assert changed.json()["id"] != template_id
    # Nachziehen ändert nichts mehr (konsistent)
    from app.services.work_time_profile_service import sync_employee

    assert await sync_employee(db_session, employee.id) is None


async def test_deprecated_default_shift_endpoints_leave_profile_rows_alone(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = await _profile(client, admin)
    await _assign(client, admin, employee.id, profile["id"])
    row_id = (await _history(client, admin, employee.id))[0]["id"]
    r = await client.patch(f"/employees/{employee.id}/default-shifts/{row_id}", headers=admin, json={"weekdays_mask": 3})
    assert r.status_code == 409 and r.json()["code"] == "WORK_TIME_PROFILE_ASSIGNED"
    r = await client.delete(f"/employees/{employee.id}/default-shifts/{row_id}", headers=admin)
    assert r.status_code == 409


async def test_new_employee_with_profile(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    profile = await _profile(client, admin)
    base = {"location_id": location.id, "first_name": "Nina", "last_name": "Neu", "hire_date": "2026-10-01"}

    r = await client.post("/employees", headers=admin, json={**base, "employee_number": "N1", "work_time_profile_id": profile["id"]})
    assert r.status_code == 201, r.text
    model = (await client.get(f"/employees/{r.json()['id']}/work-time-model", headers=admin)).json()
    assert (model["profile_id"], model["valid_from"], model["weekly_minutes"]) == (profile["id"], "2026-10-01", 2400)

    both = await client.post(
        "/employees", headers=admin, json={**base, "employee_number": "N2", "work_time_profile_id": profile["id"], "work_time_model": FULL_TIME}
    )
    assert both.status_code == 422
    await client.patch(f"/work-time-profiles/{profile['id']}", headers=admin, json={"archived": True})
    archived = await client.post("/employees", headers=admin, json={**base, "employee_number": "N3", "work_time_profile_id": profile["id"]})
    assert archived.status_code == 409 and archived.json()["code"] == "WORK_TIME_PROFILE_ARCHIVED"
    # Kein halb angelegter Mitarbeiter
    numbers = [e["employee_number"] for e in (await client.get("/employees", headers=admin)).json()]
    assert "N3" not in numbers and "N2" not in numbers
