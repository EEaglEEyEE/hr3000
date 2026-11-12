"""Nacharbeiten zu Phase 7–10:
- öffentliche API: Stempelungen nennen Projekt und Ergebnis der Standortprüfung
- DATEV-LODAS: Hinweis auf mit dem Gehalt abgegoltene Überstunden (keine Buchung)
- Mitarbeiter-Import: mehrwöchiges Modell (tagesstunden_woche2 …, turnus_beginn) und abgegoltene
  Überstunden (abgegoltene_ueberstunden)"""
import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Employee, HrRole, Location, Project, Punch, PunchSource, PunchType
from app.models.punch_location import PunchLocationCheck
from app.services import employee_import_service as imp
from app.services.auth_service import hash_password

PW = "pw123456"


async def _admin(client: AsyncClient, db: AsyncSession) -> tuple[Location, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db.add_all([location, Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN,
                                  payroll_access=True)])
    await db.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": PW})).json()["access_token"]
    return location, {"Authorization": f"Bearer {token}"}


async def _employee(db: AsyncSession, location: Location, number: str = "700", **kwargs) -> Employee:
    employee = Employee(location_id=location.id, first_name="Tea", last_name="Test", employee_number=number,
                        auto_break_enabled=False, **kwargs)
    db.add(employee)
    await db.commit()
    return employee


# --- Öffentliche API: /v1/punches ---------------------------------------------------------------------


async def _api_headers(client: AsyncClient, admin: dict, scopes: list[str]) -> dict:
    created = (await client.post("/api-clients", headers=admin, json={"name": "Lohn", "scopes": scopes})).json()
    token = (await client.post("/v1/auth/token", json={"client_id": created["client_id"], "client_secret": created["client_secret"]})).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


async def test_v1_punches_show_project_and_location_check(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _admin(client, db_session)
    employee = await _employee(db_session, location)
    project = Project(tenant_id=1, name="Neubau Halle", number="P-17")
    db_session.add(project)
    await db_session.commit()
    db_session.add_all([
        Punch(tenant_id=1, employee_id=employee.id, location_id=location.id, punch_type=PunchType.COME,
              timestamp_utc=datetime(2026, 10, 5, 8, 0), source=PunchSource.PORTAL, project_id=project.id,
              location_check=PunchLocationCheck.OUTSIDE),
        Punch(tenant_id=1, employee_id=employee.id, location_id=location.id, punch_type=PunchType.GO,
              timestamp_utc=datetime(2026, 10, 5, 16, 0), source=PunchSource.PORTAL,
              location_check=PunchLocationCheck.INSIDE),
        Punch(tenant_id=1, employee_id=employee.id, location_id=location.id, punch_type=PunchType.COME,
              timestamp_utc=datetime(2026, 10, 6, 8, 0), source=PunchSource.PORTAL),
    ])
    await db_session.commit()
    api = await _api_headers(client, admin, ["attendances:read"])
    page = (await client.get("/v1/punches", headers=api, params={"from": "2026-10-05", "to": "2026-10-06"})).json()
    assert page["page"]["total"] == 3
    first, second, third = page["data"]
    assert (first["project_id"], first["project_number"], first["project_name"]) == (project.id, "P-17", "Neubau Halle")
    assert first["location_check"] == "OUTSIDE"
    assert (second["project_id"], second["project_number"], second["project_name"]) == (None, None, None)
    assert second["location_check"] == "INSIDE"
    # weder Projekt noch Prüfung: alle neuen Felder sind null, nicht weggelassen
    assert {key: third[key] for key in ("project_id", "project_number", "project_name", "location_check")} == {
        "project_id": None, "project_number": None, "project_name": None, "location_check": None,
    }


async def test_v1_punches_never_expose_coordinates_or_notes(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _admin(client, db_session)
    employee = await _employee(db_session, location)
    db_session.add(Punch(tenant_id=1, employee_id=employee.id, location_id=location.id, punch_type=PunchType.COME,
                         timestamp_utc=datetime(2026, 10, 5, 8, 0), source=PunchSource.PORTAL, activity_note="intern",
                         location_check=PunchLocationCheck.UNKNOWN))
    await db_session.commit()
    api = await _api_headers(client, admin, ["attendances:read"])
    row = (await client.get("/v1/punches", headers=api, params={"from": "2026-10-05", "to": "2026-10-05"})).json()["data"][0]
    assert set(row) == {"id", "employee_id", "type", "timestamp_utc", "source", "project_id", "project_number",
                        "project_name", "location_check"}
    assert row["location_check"] == "UNKNOWN"


async def test_v1_punches_still_need_the_scope(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _admin(client, db_session)
    api = await _api_headers(client, admin, ["employees:read"])
    r = await client.get("/v1/punches", headers=api, params={"from": "2026-10-05", "to": "2026-10-05"})
    assert r.status_code == 403


# --- DATEV-LODAS: abgegoltene Überstunden ------------------------------------------------------------


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, hours: int) -> None:
    for punch_type, clock in (("COME", "08:00"), ("GO", f"{8 + hours:02d}:00")):
        r = await client.post("/punches", headers=admin, json={
            "employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z",
            "idempotency_key": str(uuid.uuid4()),
        })
        assert r.status_code == 201, r.text


async def _datev_preview(client: AsyncClient, db: AsyncSession, model: dict) -> dict:
    location, admin = await _admin(client, db)
    # Beschäftigt nur Mo 05.10. und Di 06.10.2026: der Monatssaldo dieser zwei Tage entscheidet
    employee = await _employee(db, location, hire_date=date(2026, 10, 5), termination_date=date(2026, 10, 6))
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={**model, "valid_from": "2026-01-01"})
    assert r.status_code == 200, r.text
    r = await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "10001"})
    assert r.status_code == 200, r.text
    await _work(client, admin, employee.id, "2026-10-05", 11)
    await _work(client, admin, employee.id, "2026-10-06", 11)
    preview = await client.get("/payroll-export/datev/preview", headers=admin,
                               params={"month": "2026-10", "employee_ids": [employee.id]})
    assert preview.status_code == 200, preview.text
    return preview.json()


async def test_datev_preview_mentions_settled_overtime(client: AsyncClient, db_session: AsyncSession) -> None:
    body = await _datev_preview(client, db_session, {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "settled_overtime_hours": 5})
    hints = [w for w in body["warnings"] if "abgegolten" in w]
    assert hints == ["Test, Tea: 5,00 Std. Überstunden mit dem Gehalt abgegolten – keine Buchung, nur zur Information."]
    # abgegoltene Stunden werden nie gebucht
    assert all("abgegolten" not in line["label"].lower() for line in body["lines"])


async def test_datev_preview_without_limit_has_no_settled_hint(client: AsyncClient, db_session: AsyncSession) -> None:
    body = await _datev_preview(client, db_session, {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]})
    assert not [w for w in body["warnings"] if "abgegolten" in w]


async def test_datev_preview_with_limit_but_no_overtime_has_no_hint(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _admin(client, db_session)
    employee = await _employee(db_session, location, hire_date=date(2026, 10, 5), termination_date=date(2026, 10, 6))
    model = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "settled_overtime_hours": 5, "valid_from": "2026-01-01"}
    assert (await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json=model)).status_code == 200
    await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "10001"})
    await _work(client, admin, employee.id, "2026-10-05", 8)
    await _work(client, admin, employee.id, "2026-10-06", 8)
    body = (await client.get("/payroll-export/datev/preview", headers=admin,
                             params={"month": "2026-10", "employee_ids": [employee.id]})).json()
    assert not [w for w in body["warnings"] if "abgegolten" in w]


# --- Mitarbeiter-Import: Parser (Einheit) -------------------------------------------------------------

HEAD = "vorname;nachname;personalnummer;standort"


def _parse(header: str, *lines: str) -> tuple[list[imp.ParsedEmployeeRow], list]:
    location = Location(name="Zentrale", timezone="UTC")
    location.id = 1
    return imp.parse_bulk_import_csv(f"{HEAD};{header}\n" + "\n".join(f"A;B;{i};Zentrale;{line}" for i, line in enumerate(lines, 1)) + "\n",
                                     [location], [], set(), set())


def test_parse_rotation_two_weeks() -> None:
    rows, errors = _parse("tagesstunden;tagesstunden_woche2", "Mo:8,Di:8,Mi:8;Do:8,Fr:8")
    assert errors == []
    assert rows[0].rotation_weeks == [[8, 8, 8, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0]]
    assert rows[0].daily_hours is None and rows[0].rotation_start is None


def test_parse_rotation_four_weeks_with_start_moved_to_monday() -> None:
    rows, errors = _parse(
        "tagesstunden;tagesstunden_woche2;tagesstunden_woche3;tagesstunden_woche4;turnus_beginn",
        "Mo:8;Di:8;Mi:7:30;Do:6,5;2026-10-01".replace("6,5", "6.5"),
    )
    assert errors == []
    assert len(rows[0].rotation_weeks) == 4
    assert rows[0].rotation_weeks[2][2] == 7.5 and rows[0].rotation_weeks[3][3] == 6.5
    assert rows[0].rotation_start == date(2026, 9, 28)  # Donnerstag 01.10. -> Montag der Woche


@pytest.mark.parametrize(
    "header, line, message",
    [
        ("tagesstunden;tagesstunden_woche2", ";Do:8", "Woche 1 fehlt"),
        ("tagesstunden;tagesstunden_woche2;tagesstunden_woche3", "Mo:8;;Mi:8", "Woche 2 fehlt"),
        ("tagesstunden;tagesstunden_woche2;tagesstunden_woche3;tagesstunden_woche4", "Mo:8;Di:8;;Do:8", "Woche 3 fehlt"),
        ("tagesstunden;tagesstunden_woche2", "Mo:8;Xx:8", "Ungültige Tagesstunden"),
        ("tagesstunden;tagesstunden_woche2", "Mo:11;Di:8", "über 10 Std."),
        ("tagesstunden;tagesstunden_woche2", "Mo:0;Di:0", "Arbeitszeitmodell ungültig"),
        ("tagesstunden;turnus_beginn", "Mo:8;2026-10-01", "nur beim mehrwöchigen Modell"),
        ("tagesstunden;tagesstunden_woche2;turnus_beginn", "Mo:8;Di:8;01.10.2026", "Ungültiges Datum"),
        ("arbeitstage;tagesstunden;tagesstunden_woche2", "nach Aufwand;Mo:8;Di:8", "nicht mit „nach Aufwand“"),
    ],
)
def test_parse_rotation_errors(header: str, line: str, message: str) -> None:
    rows, errors = _parse(header, line)
    assert rows == []
    assert len(errors) == 1 and message in errors[0].message, errors[0].message
    assert errors[0].row == 2


@pytest.mark.parametrize(
    "header, line, expected",
    [
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;10", 10.0),
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;7,5", 7.5),
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;0", None),
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;", None),
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;100", 100.0),
        ("wochenstunden;abgegoltene_ueberstunden", "20;5", 5.0),  # flexibel
        ("tagesstunden;abgegoltene_ueberstunden", "Mo:8,Di:8;4", 4.0),
        ("tagesstunden;tagesstunden_woche2;abgegoltene_ueberstunden", "Mo:8;Di:8;3", 3.0),
    ],
)
def test_parse_settled_overtime(header: str, line: str, expected: float | None) -> None:
    rows, errors = _parse(header, line)
    assert errors == []
    assert rows[0].settled_overtime_hours == expected


@pytest.mark.parametrize(
    "header, line, message",
    [
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;viel", "Ungültige abgegoltene Überstunden"),
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;-1", "zwischen 0 und 100"),
        ("wochenstunden;arbeitstage;abgegoltene_ueberstunden", "40;Mo-Fr;100,5", "zwischen 0 und 100"),
        ("arbeitstage;abgegoltene_ueberstunden", "nach Aufwand;5", "keine abgegoltenen Überstunden"),
        ("abgegoltene_ueberstunden", "5", "nur zusammen mit einem Arbeitszeitmodell"),
    ],
)
def test_parse_settled_overtime_errors(header: str, line: str, message: str) -> None:
    rows, errors = _parse(header, line)
    assert rows == []
    assert len(errors) == 1 and message in errors[0].message, errors[0].message


def test_one_bad_row_does_not_block_the_others() -> None:
    rows, errors = _parse("tagesstunden;tagesstunden_woche2;abgegoltene_ueberstunden", "Mo:8;Di:8;2", "Mo:8;;abc", "Mo:8;;")
    assert [r.employee_number for r in rows] == ["1", "3"]
    assert [e.row for e in errors] == [3]
    assert rows[1].rotation_weeks is None and rows[1].daily_hours == [8, 0, 0, 0, 0, 0, 0]


def test_old_files_without_new_columns_parse_as_before() -> None:
    rows, errors = _parse("wochenstunden;arbeitstage", "40;Mo-Fr")
    assert errors == []
    assert (rows[0].weekly_hours, rows[0].weekdays, rows[0].rotation_weeks, rows[0].settled_overtime_hours) == (
        40.0, [0, 1, 2, 3, 4], None, None,
    )


# --- Mitarbeiter-Import: über die API -----------------------------------------------------------------


async def _import(client: AsyncClient, admin: dict, csv_text: str) -> dict:
    r = await client.post("/employees/bulk-import", headers=admin, files={"file": ("m.csv", csv_text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


async def _model_of(client: AsyncClient, db: AsyncSession, admin: dict, number: str) -> dict:
    employee = (await db.execute(select(Employee).where(Employee.employee_number == number))).scalar_one()
    r = await client.get(f"/employees/{employee.id}/work-time-model", headers=admin, params={"date": "2026-10-05"})
    assert r.status_code == 200, r.text
    return r.json()


async def test_import_creates_rotation_model(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _admin(client, db_session)
    result = await _import(client, admin, (
        f"{HEAD};eintrittsdatum;tagesstunden;tagesstunden_woche2;turnus_beginn;abgegoltene_ueberstunden\n"
        "Tea;Turnus;R1;Zentrale;2026-09-01;Mo:8,Di:8,Mi:8;Do:8,Fr:8;2026-09-30;10\n"
    ))
    assert result == {"created": 1, "errors": []}
    model = await _model_of(client, db_session, admin, "R1")
    assert model["rotation_minutes"] == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert model["rotation_start"] == "2026-09-28"
    assert model["weekly_minutes"] == 1200  # Durchschnitt über den Turnus
    assert model["settled_overtime_minutes"] == 600


async def test_import_rotation_without_start_begins_in_the_hire_week(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _admin(client, db_session)
    result = await _import(client, admin, (
        f"{HEAD};eintrittsdatum;tagesstunden;tagesstunden_woche2\n"
        "Tea;Turnus;R2;Zentrale;2026-09-02;Mo:8;Di:8\n"
    ))
    assert result["created"] == 1, result
    model = await _model_of(client, db_session, admin, "R2")
    assert model["rotation_start"] == "2026-08-31"  # Montag der Woche des Eintritts (Mi 02.09.2026)


async def test_import_settled_overtime_on_weekly_model(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _admin(client, db_session)
    result = await _import(client, admin, (
        f"{HEAD};eintrittsdatum;wochenstunden;arbeitstage;abgegoltene_ueberstunden\n"
        "A;Mit;S1;Zentrale;2026-09-01;40;Mo-Fr;7,5\n"
        "B;Ohne;S2;Zentrale;2026-09-01;40;Mo-Fr;\n"
        "C;Falsch;S3;Zentrale;2026-09-01;40;Mo-Fr;200\n"
    ))
    assert result["created"] == 2
    assert [(e["row"], "zwischen 0 und 100" in e["message"]) for e in result["errors"]] == [(4, True)]
    assert (await _model_of(client, db_session, admin, "S1"))["settled_overtime_minutes"] == 450
    assert (await _model_of(client, db_session, admin, "S2"))["settled_overtime_minutes"] is None
    assert (await db_session.execute(select(Employee).where(Employee.employee_number == "S3"))).scalar_one_or_none() is None


# --- Mitarbeiter-Import: übrige Zweige des Parsers ---------------------------------------------------


@pytest.mark.parametrize(
    "header, line, message",
    [
        ("aktiv", "vielleicht", "für Aktiv"),
        ("wochenstunden;arbeitstage", "40;Mo-Xx", "Ungültige Arbeitstage"),
        ("wochenstunden;arbeitstage", "40;Fr-Mo", "Bereich rückwärts"),
        ("wochenstunden;arbeitstage", "40;,", "Arbeitstage fehlen"),
        ("tagesstunden", "Mo:acht", "Ungültige Stunden"),
        ("tagesstunden", "Mo:11", "über 10 Std."),
        ("tagesstunden", "Mo", "Ungültige Tagesstunden"),
        ("login_email", "keine-adresse", "keine gültige Adresse"),
        ("wochenstunden", "viel", "Ungültige Wochenstunden"),
        ("wochenstunden;arbeitstage", "viel;Mo-Fr", "Ungültige Wochenstunden"),
        ("wochenstunden;arbeitstage", "55;Mo-Fr", "mehr als 10 Std. pro Arbeitstag"),
        ("wochenstunden;arbeitstage", "70;Mo-Fr", "Arbeitszeitmodell ungültig"),
        ("arbeitstage;monatsgrenze", "nach Aufwand;viel", "Ungültige Monatsgrenze"),
        ("eintrittsdatum", "01.09.2026", "Ungültiges Datum"),
    ],
)
def test_parse_other_errors(header: str, line: str, message: str) -> None:
    rows, errors = _parse(header, line)
    assert rows == []
    assert len(errors) == 1 and message in errors[0].message, errors[0].message


def test_parse_weekdays_without_weekly_hours() -> None:
    rows, errors = _parse("wochenstunden;arbeitstage", ";Mo-Fr")
    assert rows == [] and "Arbeitstage ohne Wochenstunden" in errors[0].message


def test_parse_on_demand_with_cap_and_flags() -> None:
    rows, errors = _parse("arbeitstage;monatsgrenze;aktiv", "nach Aufwand;43,5;nein", "Aufwand;;ja")
    assert errors == []
    assert (rows[0].on_demand, rows[0].monthly_cap_hours, rows[0].active) == (True, 43.5, False)
    assert (rows[1].on_demand, rows[1].monthly_cap_hours, rows[1].active) == (True, None, True)


def test_parse_weekday_lists_and_ranges() -> None:
    rows, errors = _parse("wochenstunden;arbeitstage", "24;Mo-Mi,Fr,", "8;Sa")
    assert errors == []
    assert rows[0].weekdays == [0, 1, 2, 4] and rows[1].weekdays == [5]


def test_parse_duplicates_and_lengths() -> None:
    location = Location(name="Zentrale", timezone="UTC")
    location.id = 1
    text = (
        f"{HEAD};login_email\n"
        "A;B;1;Zentrale;a@example.com\n"
        "A;B;1;Zentrale;\n"                      # Personalnummer doppelt in der Datei
        "A;B;2;Zentrale;A@example.com\n"         # E-Mail doppelt in der Datei (Groß-/Kleinschreibung egal)
        "A;B;3;Zentrale;alt@example.com\n"       # E-Mail schon vergeben
        "A;B;X9;Zentrale;\n"                     # Personalnummer schon vergeben
        f"{'A' * 101};B;4;Zentrale;\n"           # Name zu lang
        "A;B;5;Anderswo;\n"                      # Standort unbekannt
        ";B;6;Zentrale;\n"                       # Pflichtfeld fehlt
    )
    rows, errors = imp.parse_bulk_import_csv(text, [location], [], {"X9"}, {"alt@example.com"})
    assert [r.employee_number for r in rows] == ["1"]
    assert [e.row for e in errors] == [3, 4, 5, 6, 7, 8, 9]
    messages = " | ".join(e.message for e in errors)
    for expected in ("Personalnummer '1' ist bereits vergeben", "Login-E-Mail 'a@example.com' ist bereits vergeben",
                     "Login-E-Mail 'alt@example.com' ist bereits vergeben", "Personalnummer 'X9' ist bereits vergeben",
                     "zu lang", "Standort 'Anderswo' wurde nicht gefunden", "sind Pflichtfelder"):
        assert expected in messages, expected


def test_parse_empty_file_and_missing_columns() -> None:
    assert imp.parse_bulk_import_csv("", [], [], set(), set())[1][0].message == "Die CSV-Datei ist leer."
    rows, errors = imp.parse_bulk_import_csv("vorname;nachname\nA;B\n", [], [], set(), set())
    assert rows == [] and "Fehlende Spalte(n): personalnummer, standort" in errors[0].message
