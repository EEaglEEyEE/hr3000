"""Standort beim Stempeln im Web-Login (A18): Entfernungsrechnung, Regeln innerhalb/außerhalb/unbekannt,
Modus „nur vermerken“ / „außerhalb nicht erlauben“, Schalter, Kiosk und HR unberührt, fremde Firmen und
vor allem: Koordinaten landen weder in der Datenbank noch im Audit-Log, in Logs oder Fehlermeldungen."""
import json
import logging
import math
import uuid
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.migration import PORTABLE_SETTINGS
from app.models import (
    Account,
    AppSettings,
    AuditLogEntry,
    Base,
    Device,
    Employee,
    HrRole,
    Location,
    Punch,
    PunchLocationCheck,
    PunchSource,
    PunchType,
    Tenant,
)
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash
from app.services.period_service import build_month_report
from app.services.punch_location_service import (
    EARTH_RADIUS_M,
    REASON_INACCURATE,
    REASON_INSIDE,
    REASON_NO_POSITION,
    REASON_OUTSIDE,
    Circle,
    evaluate,
    haversine_m,
    location_remarks,
    strip_position_inputs,
)

# Mittelpunkt des Firmenkreises und ein Punkt, der garantiert nirgends sonst vorkommt
CENTER = (48.7758, 9.1829)
EMPLOYEE_LAT, EMPLOYEE_LON = 48.776123, 9.183417  # ~45 m vom Mittelpunkt
FAR_LAT, FAR_LON = 48.861234, 9.271987  # ~11 km entfernt


def _north(lat: float, lon: float, meters: float) -> tuple[float, float]:
    """Punkt `meters` genau nördlich (gleicher Längengrad)."""
    return lat + math.degrees(meters / EARTH_RADIUS_M), lon


def _pos(lat: float, lon: float, accuracy: float = 10) -> SimpleNamespace:
    return SimpleNamespace(latitude=lat, longitude=lon, accuracy_m=accuracy)


# --- Entfernung ---------------------------------------------------------------------------------------


def test_haversine_known_distances() -> None:
    assert haversine_m(0, 0, 0, 0) == 0
    # Ein Grad auf dem Äquator bzw. Meridian = R·π/180
    assert haversine_m(0, 0, 0, 1) == pytest.approx(EARTH_RADIUS_M * math.pi / 180, rel=1e-12)
    assert haversine_m(0, 0, 1, 0) == pytest.approx(EARTH_RADIUS_M * math.pi / 180, rel=1e-12)
    # Stuttgart – München ~190 km
    assert haversine_m(48.7758, 9.1829, 48.1374, 11.5755) == pytest.approx(190_500, rel=0.01)


def test_haversine_is_symmetric_and_handles_negative_longitudes() -> None:
    a = haversine_m(51.5, -0.1278, 51.5, 0.1278)
    assert a == pytest.approx(haversine_m(51.5, 0.1278, 51.5, -0.1278))
    # 0,2556° Länge auf 51,5° Breite ≈ 17,7 km – nicht 0 (Vorzeichen zählt)
    assert a == pytest.approx(17_700, rel=0.01)
    assert haversine_m(51.5, -0.1278, 51.5, -0.1278) == 0
    # West/Ost vertauscht ist ein anderer Ort
    assert haversine_m(40.0, -3.7, 40.0, 3.7) > 600_000


# --- Regeln innerhalb / außerhalb / unbekannt --------------------------------------------------------


CIRCLE = Circle(location_id=1, latitude=CENTER[0], longitude=CENTER[1], radius_m=200)


def test_no_position_is_unknown() -> None:
    result = evaluate(None, [CIRCLE])
    assert (result.result, result.reason, result.location_id) == (PunchLocationCheck.UNKNOWN, REASON_NO_POSITION, None)


def test_exactly_on_the_radius_counts_as_inside() -> None:
    lat, lon = _north(*CENTER, 200)
    assert haversine_m(lat, lon, *CENTER) == pytest.approx(200, abs=1e-6)
    result = evaluate(_pos(lat, lon), [CIRCLE])
    assert (result.result, result.reason, result.location_id) == (PunchLocationCheck.INSIDE, REASON_INSIDE, 1)


@pytest.mark.parametrize(
    ("meters", "expected"),
    [(0, PunchLocationCheck.INSIDE), (199.9, PunchLocationCheck.INSIDE), (200.1, PunchLocationCheck.OUTSIDE), (5000, PunchLocationCheck.OUTSIDE)],
)
def test_just_inside_and_just_outside(meters: float, expected: PunchLocationCheck) -> None:
    assert evaluate(_pos(*_north(*CENTER, meters)), [CIRCLE]).result == expected


def test_longitude_sign_matters() -> None:
    london = Circle(location_id=7, latitude=51.5074, longitude=-0.1278, radius_m=500)
    assert evaluate(_pos(51.5074, -0.1278), [london]).result == PunchLocationCheck.INSIDE
    assert evaluate(_pos(51.5074, 0.1278), [london]).result == PunchLocationCheck.OUTSIDE
    stuttgart_west = Circle(location_id=8, latitude=48.7758, longitude=-9.1829, radius_m=500)
    assert evaluate(_pos(*CENTER), [stuttgart_west]).result == PunchLocationCheck.OUTSIDE


def test_accuracy_equal_to_radius_still_counts() -> None:
    assert evaluate(_pos(*_north(*CENTER, 150), accuracy=200), [CIRCLE]).result == PunchLocationCheck.INSIDE
    assert evaluate(_pos(*_north(*CENTER, 250), accuracy=200), [CIRCLE]).result == PunchLocationCheck.OUTSIDE


def test_inaccurate_position_near_the_circle_is_unknown() -> None:
    # Ungenauigkeit größer als der Radius – auch mitten im Kreis lässt sich nichts sagen
    for meters in (0, 150, 600):
        result = evaluate(_pos(*_north(*CENTER, meters), accuracy=500), [CIRCLE])
        assert (result.result, result.reason) == (PunchLocationCheck.UNKNOWN, REASON_INACCURATE), meters


def test_inaccurate_but_clearly_far_away_is_outside() -> None:
    # 11 km entfernt, Ungenauigkeit 2 km: selbst der nächstmögliche Punkt liegt außerhalb
    result = evaluate(_pos(FAR_LAT, FAR_LON, accuracy=2000), [CIRCLE])
    assert (result.result, result.reason) == (PunchLocationCheck.OUTSIDE, REASON_OUTSIDE)
    # Grenzfall: Entfernung − Ungenauigkeit genau gleich dem Radius → noch unbekannt
    lat, lon = _north(*CENTER, 1200)
    assert evaluate(_pos(lat, lon, accuracy=1000), [CIRCLE]).result == PunchLocationCheck.UNKNOWN
    assert evaluate(_pos(*_north(*CENTER, 1201), accuracy=1000), [CIRCLE]).result == PunchLocationCheck.OUTSIDE


def test_several_circles_pick_the_nearest_inside() -> None:
    second = Circle(location_id=2, latitude=_north(*CENTER, 100)[0], longitude=CENTER[1], radius_m=300)
    result = evaluate(_pos(*_north(*CENTER, 90)), [CIRCLE, second])
    assert (result.result, result.location_id) == (PunchLocationCheck.INSIDE, 2)
    result = evaluate(_pos(*_north(*CENTER, 5)), [CIRCLE, second])
    assert (result.result, result.location_id) == (PunchLocationCheck.INSIDE, 1)
    # Nur im zweiten Kreis
    result = evaluate(_pos(*_north(*CENTER, 350)), [CIRCLE, second])
    assert (result.result, result.location_id) == (PunchLocationCheck.INSIDE, 2)


def test_inside_one_circle_wins_over_an_undecided_other() -> None:
    big = Circle(location_id=3, latitude=CENTER[0], longitude=CENTER[1], radius_m=5000)
    small = Circle(location_id=4, latitude=_north(*CENTER, 400)[0], longitude=CENTER[1], radius_m=50)
    result = evaluate(_pos(*_north(*CENTER, 400), accuracy=80), [small, big])
    assert (result.result, result.location_id) == (PunchLocationCheck.INSIDE, 3)


def test_outside_one_but_undecided_for_another_is_unknown() -> None:
    near_small = Circle(location_id=5, latitude=CENTER[0], longitude=CENTER[1], radius_m=50)
    far = Circle(location_id=6, latitude=FAR_LAT, longitude=FAR_LON, radius_m=5000)
    result = evaluate(_pos(*_north(*CENTER, 60), accuracy=100), [far, near_small])
    assert (result.result, result.reason) == (PunchLocationCheck.UNKNOWN, REASON_INACCURATE)


def test_no_circles_means_outside_for_the_pure_function() -> None:
    # Die API prüft ohne Kreise gar nicht erst (check_own_punch → None); die reine Funktion bleibt eindeutig.
    assert evaluate(_pos(*CENTER), []).result == PunchLocationCheck.OUTSIDE


# --- Monatsnachweis und Fehlerausgabe ----------------------------------------------------------------


def _punch(kind: PunchType, hour: int, minute: int, check: PunchLocationCheck | None) -> Punch:
    return Punch(punch_type=kind, timestamp_utc=datetime(2026, 10, 5, hour, minute), location_check=check)


def test_location_remarks() -> None:
    tz = ZoneInfo("Europe/Berlin")
    assert location_remarks([], tz) == ""
    assert location_remarks([_punch(PunchType.COME, 6, 0, PunchLocationCheck.INSIDE), _punch(PunchType.GO, 14, 0, None)], tz) == ""
    punches = [
        _punch(PunchType.COME, 6, 2, PunchLocationCheck.UNKNOWN),
        _punch(PunchType.BREAK_START, 10, 0, PunchLocationCheck.OUTSIDE),
        _punch(PunchType.BREAK_END, 10, 30, PunchLocationCheck.INSIDE),
        _punch(PunchType.GO, 15, 1, PunchLocationCheck.OUTSIDE),
    ]
    # Berlin im Oktober: UTC+2; „außerhalb“ zuerst
    assert location_remarks(punches, tz) == "außerhalb: Pause Start 12:00, Gehen 17:01 · Standort unbekannt: Kommen 08:02"


def test_strip_position_inputs_only_touches_position_errors() -> None:
    errors = [
        {"type": "less_than_equal", "loc": ("body", "position", "latitude"), "msg": "x", "input": 123.4, "ctx": {"le": 90}},
        {"type": "enum", "loc": ("body", "punch_type"), "msg": "y", "input": "KAFFEE"},
        {"type": "missing", "loc": ("body",), "msg": "z"},
    ]
    cleaned = strip_position_inputs(errors)
    assert "input" not in cleaned[0] and cleaned[0]["ctx"] == {"le": 90}
    assert cleaned[1]["input"] == "KAFFEE"
    assert cleaned[2] == errors[2]


# --- API ---------------------------------------------------------------------------------------------


async def _setup(db_session: AsyncSession, client: AsyncClient, *, circle: bool = True):
    location = Location(name="Zentrale", timezone="Europe/Berlin")
    if circle:
        location.geo_latitude, location.geo_longitude, location.geo_radius_m = CENTER[0], CENTER[1], 200
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id, first_name="Gina", last_name="Geo", employee_number="G1",
        login_email="gina@example.com", password_hash=hash_password("pw123456"),
    )
    device = Device(name="Tablet", location_id=location.id, token_hash=token_hash("tok-geo"))
    db_session.add_all([employee, device, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()

    async def token(path: str, body: dict) -> dict:
        return {"Authorization": "Bearer " + (await client.post(path, json=body)).json()["access_token"]}

    admin = await token("/auth/login", {"email": "admin@example.com", "password": "pw"})
    me = await token("/auth/login", {"email": "gina@example.com", "password": "pw123456"})
    device_headers = await token("/auth/device/login", {"device_token": "tok-geo"})
    r = await client.patch("/settings", headers=admin, json={"portal_punching_enabled": True, "kiosk_errand_buttons": True})
    assert r.status_code == 200, r.text
    return SimpleNamespace(location=location, employee=employee, admin=admin, me=me, device=device_headers)


def _position(lat: float = EMPLOYEE_LAT, lon: float = EMPLOYEE_LON, accuracy: float = 15) -> dict:
    return {"latitude": lat, "longitude": lon, "accuracy_m": accuracy}


async def _enable(client: AsyncClient, admin: dict, mode: str = "RECORD") -> None:
    r = await client.patch("/settings", headers=admin, json={"punch_location_check_enabled": True, "punch_location_mode": mode})
    assert r.status_code == 200, r.text
    assert (r.json()["punch_location_check_enabled"], r.json()["punch_location_mode"]) == (True, mode)


async def _own(client: AsyncClient, w, kind: str, position: dict | None = None):
    body: dict = {"punch_type": kind}
    if position is not None:
        body["position"] = position
    return await client.post("/me/punches", headers=w.me, json=body)


async def test_settings_default_off_and_switchable(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    settings = (await client.get("/settings", headers=w.admin)).json()
    assert (settings["punch_location_check_enabled"], settings["punch_location_mode"]) == (False, "RECORD")
    await _enable(client, w.admin, "BLOCK")
    assert (await client.patch("/settings", headers=w.admin, json={"punch_location_mode": "SOMETIMES"})).status_code == 422
    entries = (await db_session.execute(select(AuditLogEntry.detail))).scalars().all()
    assert any("punch_location_mode=BLOCK" in (d or "") for d in entries)
    assert {"punch_location_check_enabled", "punch_location_mode"} <= set(PORTABLE_SETTINGS)
    # Mitarbeiter dürfen die Einstellungen nicht ändern
    assert (await client.patch("/settings", headers=w.me, json={"punch_location_check_enabled": False})).status_code == 403


async def test_switch_off_ignores_position_and_stores_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    r = await _own(client, w, "COME", _position(FAR_LAT, FAR_LON))
    assert r.status_code == 201, r.text
    assert (r.json()["location_check"], r.json()["location_check_location_id"]) == (None, None)
    me = (await client.get("/dashboard", headers=w.me)).json()["me"]
    assert (me["location_check"], me["location_check_required"]) == (False, False)
    # Auch der Modus „außerhalb nicht erlauben“ wirkt bei ausgeschaltetem Schalter nicht
    await client.patch("/settings", headers=w.admin, json={"punch_location_mode": "BLOCK"})
    r = await _own(client, w, "GO")
    assert r.status_code == 201 and r.json()["location_check"] is None


async def test_without_any_circle_nothing_is_checked(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client, circle=False)
    await _enable(client, w.admin, "BLOCK")
    assert (await client.get("/dashboard", headers=w.me)).json()["me"]["location_check"] is False
    r = await _own(client, w, "COME")  # ohne Position – trotzdem erlaubt, weil kein Kreis eingerichtet ist
    assert r.status_code == 201 and r.json()["location_check"] is None


async def test_record_mode_marks_each_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    await _enable(client, w.admin)
    me = (await client.get("/dashboard", headers=w.me)).json()["me"]
    assert (me["location_check"], me["location_check_required"]) == (True, False)

    cases = (
        ("COME", _position(), "INSIDE", w.location.id),
        ("BREAK_START", _position(FAR_LAT, FAR_LON), "OUTSIDE", None),
        ("BREAK_END", None, "UNKNOWN", None),
        ("ERRAND_START", _position(accuracy=900), "UNKNOWN", None),
        ("ERRAND_END", _position(*_north(*CENTER, 200), accuracy=0), "INSIDE", w.location.id),
        ("GO", _position(*_north(*CENTER, 201)), "OUTSIDE", None),
    )
    for kind, position, expected, location_id in cases:
        r = await _own(client, w, kind, position)
        assert r.status_code == 201, (kind, r.text)
        assert (r.json()["location_check"], r.json()["location_check_location_id"]) == (expected, location_id), kind

    # Mitarbeiter sehen das Kennzeichen an ihren eigenen Buchungen, HR ebenso
    for headers in (w.me, w.admin):
        punches = (await client.get(f"/employees/{w.employee.id}/punches", headers=headers)).json()
        assert [p["location_check"] for p in punches] == [c[2] for c in cases]


async def test_block_mode_rejects_outside_unknown_and_missing_position(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    await _enable(client, w.admin, "BLOCK")
    assert (await client.get("/dashboard", headers=w.me)).json()["me"]["location_check_required"] is True

    for position, code in (
        (_position(FAR_LAT, FAR_LON), "PUNCH_LOCATION_OUTSIDE"),
        (None, "PUNCH_LOCATION_REQUIRED"),
        (_position(accuracy=1500), "PUNCH_LOCATION_INACCURATE"),
    ):
        r = await _own(client, w, "COME", position)
        assert r.status_code == 403 and r.json()["code"] == code, r.text
        assert r.json()["detail"]  # klare Meldung
        for value in (FAR_LAT, FAR_LON, EMPLOYEE_LAT, EMPLOYEE_LON):
            assert str(value) not in r.text
    assert (await db_session.execute(select(Punch))).scalars().all() == []

    r = await _own(client, w, "COME", _position())
    assert r.status_code == 201 and r.json()["location_check"] == "INSIDE"


async def test_kiosk_and_hr_punches_are_never_checked(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    await _enable(client, w.admin, "BLOCK")
    for headers, kind, ts in ((w.device, "COME", "2026-10-05T06:00:00Z"), (w.admin, "GO", "2026-10-05T14:00:00Z")):
        r = await client.post("/punches", headers=headers, json={
            "employee_id": w.employee.id, "punch_type": kind, "timestamp_utc": ts,
            "idempotency_key": str(uuid.uuid4()), "position": _position(FAR_LAT, FAR_LON),
        })
        assert r.status_code == 201, r.text
        assert r.json()["location_check"] is None
    sources = {p.source: p.location_check for p in (await db_session.execute(select(Punch))).scalars()}
    assert sources == {PunchSource.KIOSK: None, PunchSource.MANUAL_HR: None}


async def test_circles_of_other_tenants_never_count(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client, circle=False)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()
    foreign = Location(tenant_id=2, name="Fremd", timezone="UTC", geo_latitude=EMPLOYEE_LAT, geo_longitude=EMPLOYEE_LON, geo_radius_m=5000)
    db_session.add_all([foreign, AppSettings(tenant_id=2)])
    await db_session.commit()
    await _enable(client, w.admin)
    # Nur die fremde Firma hat einen Kreis → bei uns keine Prüfung
    r = await _own(client, w, "COME", _position())
    assert r.status_code == 201 and r.json()["location_check"] is None

    # Eigener Kreis weit weg: außerhalb, obwohl der fremde Kreis passen würde
    r = await client.patch(f"/locations/{w.location.id}", headers=w.admin,
                           json={"geo_latitude": FAR_LAT, "geo_longitude": FAR_LON, "geo_radius_m": 100})
    assert r.status_code == 200, r.text
    r = await _own(client, w, "GO", _position())
    assert r.status_code == 201 and r.json()["location_check"] == "OUTSIDE"

    # Fremden Standort weder sehen noch ändern
    assert foreign.id not in {loc["id"] for loc in (await client.get("/locations", headers=w.admin)).json()}
    r = await client.patch(f"/locations/{foreign.id}", headers=w.admin, json={"clear_geofence": True})
    assert r.status_code == 404
    await db_session.refresh(foreign)
    assert foreign.geo_radius_m == 5000


async def test_coordinates_are_never_stored_logged_or_audited(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    w = await _setup(db_session, client)
    await _enable(client, w.admin)
    caplog.set_level(logging.DEBUG)
    for kind, position in (("COME", _position()), ("GO", _position(FAR_LAT, FAR_LON, accuracy=12.5))):
        assert (await _own(client, w, kind, position)).status_code == 201
    # HR korrigiert eine Buchung: das Ergebnis bleibt, Koordinaten tauchen auch im Audit nicht auf
    punch_id = (await db_session.execute(select(Punch.id).where(Punch.punch_type == PunchType.GO))).scalar_one()
    r = await client.patch(f"/punches/{punch_id}", headers=w.admin, json={"correction_reason": "Uhr ging vor"})
    assert r.status_code == 200 and r.json()["location_check"] == "OUTSIDE"
    export = await client.get(f"/employees/{w.employee.id}/data-export", headers=w.admin)
    assert export.status_code == 200, export.text  # Datenauskunft: Ergebnis ja, Koordinaten nein (unten)
    assert "OUTSIDE" in export.text
    assert not any(s in export.text for s in (str(EMPLOYEE_LAT), str(FAR_LAT)))

    secrets = {f"{v}" for v in (EMPLOYEE_LAT, EMPLOYEE_LON, FAR_LAT, FAR_LON)} | {"48.77612", "9.18341", "48.86123", "9.27198"}
    floats = {EMPLOYEE_LAT, EMPLOYEE_LON, FAR_LAT, FAR_LON}
    conn = await db_session.connection()
    checked_rows = 0
    for table in Base.metadata.sorted_tables:
        for row in (await conn.execute(text(f'SELECT * FROM "{table.name}"'))).all():
            checked_rows += 1
            for value in row:
                if isinstance(value, float):
                    assert value not in floats, table.name
                assert not any(s in str(value) for s in secrets), (table.name, value)
    assert checked_rows > 5
    assert not any(s in caplog.text for s in secrets)
    audit = " ".join(str(d) for d in (await db_session.execute(select(AuditLogEntry.detail))).scalars())
    assert not any(s in audit for s in secrets)


async def test_invalid_positions_are_rejected_without_echoing_them(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    await _enable(client, w.admin)
    for position in (
        _position(lat=123.456789),
        _position(lat=-90.000001),
        _position(lon=-180.123456),
        _position(lon=187.654321),
        _position(accuracy=-1),
        _position(accuracy=100_000.5),
        {"latitude": 48.1, "longitude": 9.2},  # Genauigkeit fehlt
        {"latitude": "Nord", "longitude": 9.2, "accuracy_m": 5},
    ):
        r = await _own(client, w, "COME", position)
        assert r.status_code == 422, position
        for value in ("123.456789", "-90.000001", "-180.123456", "187.654321", "100000.5", "Nord"):
            assert value not in r.text
    # NaN/Unendlich (in JSON nicht standardkonform, Python würde es aber parsen)
    raw = '{"punch_type": "COME", "position": {"latitude": NaN, "longitude": 9.2, "accuracy_m": 5}}'
    r = await client.post("/me/punches", headers={**w.me, "Content-Type": "application/json"}, content=raw)
    assert r.status_code == 422
    # Grenzen selbst sind erlaubt
    r = await _own(client, w, "COME", _position(lat=-90, lon=180, accuracy=100_000))
    assert r.status_code == 201 and r.json()["location_check"] == "OUTSIDE"
    # Andere Validierungsfehler behalten das Standardformat inkl. Eingabe
    r = await client.post("/me/punches", headers=w.me, json={"punch_type": "KAFFEE"})
    assert r.status_code == 422 and r.json()["detail"][0]["input"] == "KAFFEE"


async def test_location_circle_crud_and_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client, circle=False)
    r = await client.post("/locations", headers=w.admin, json={"name": "Lager", "geo_latitude": 48.5, "geo_longitude": -9.25, "geo_radius_m": 50})
    assert r.status_code == 201, r.text
    assert (r.json()["geo_latitude"], r.json()["geo_longitude"], r.json()["geo_radius_m"]) == (48.5, -9.25, 50)
    created = r.json()["id"]
    r = await client.post("/locations", headers=w.admin, json={"name": "Ohne Kreis"})
    assert r.status_code == 201 and r.json()["geo_radius_m"] is None

    url = f"/locations/{w.location.id}"
    for body in (
        {"geo_latitude": 48.5, "geo_longitude": 9.2},  # Radius fehlt
        {"geo_radius_m": 100},
        {"geo_latitude": 48.5, "geo_longitude": 9.2, "geo_radius_m": 49},
        {"geo_latitude": 48.5, "geo_longitude": 9.2, "geo_radius_m": 5001},
        {"geo_latitude": 90.5, "geo_longitude": 9.2, "geo_radius_m": 100},
        {"geo_latitude": 48.5, "geo_longitude": -180.5, "geo_radius_m": 100},
        {"geo_latitude": 48.5, "geo_longitude": 9.2, "geo_radius_m": 100, "clear_geofence": True},
    ):
        assert (await client.patch(url, headers=w.admin, json=body)).status_code == 422, body
    r = await client.patch(url, headers=w.admin, json={"geo_latitude": -33.8688, "geo_longitude": 151.2093, "geo_radius_m": 5000})
    assert r.status_code == 200 and r.json()["geo_radius_m"] == 5000
    # Name ändern lässt den Kreis stehen
    r = await client.patch(url, headers=w.admin, json={"name": "Hauptsitz"})
    assert (r.json()["name"], r.json()["geo_latitude"]) == ("Hauptsitz", -33.8688)
    r = await client.patch(url, headers=w.admin, json={"clear_geofence": True})
    assert (r.json()["geo_latitude"], r.json()["geo_longitude"], r.json()["geo_radius_m"]) == (None, None, None)
    # Mitarbeiter dürfen keine Kreise pflegen
    assert (await client.patch(f"/locations/{created}", headers=w.me, json={"clear_geofence": True})).status_code == 403


async def test_month_report_shows_outside_and_unknown(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    for kind, hour, check in (
        (PunchType.COME, 6, PunchLocationCheck.OUTSIDE),
        (PunchType.GO, 14, PunchLocationCheck.UNKNOWN),
    ):
        db_session.add(Punch(employee_id=w.employee.id, location_id=w.location.id, punch_type=kind,
                             timestamp_utc=datetime(2026, 10, 6, hour, 0), source=PunchSource.PORTAL, location_check=check))
    db_session.add(Punch(employee_id=w.employee.id, location_id=w.location.id, punch_type=PunchType.COME,
                         timestamp_utc=datetime(2026, 10, 7, 6, 0), source=PunchSource.PORTAL, location_check=PunchLocationCheck.INSIDE,
                         location_check_location_id=w.location.id))
    db_session.add(Punch(employee_id=w.employee.id, location_id=w.location.id, punch_type=PunchType.GO,
                         timestamp_utc=datetime(2026, 10, 7, 14, 0), source=PunchSource.PORTAL))
    await db_session.commit()
    report = await build_month_report(db_session, await db_session.get(Employee, w.employee.id), 2026, 10)
    by_day = {d.day: d for d in report.days}
    assert "außerhalb: Kommen 08:00" in by_day[date(2026, 10, 6)].label
    assert "Standort unbekannt: Gehen 16:00" in by_day[date(2026, 10, 6)].label
    assert "außerhalb" not in by_day[date(2026, 10, 7)].label and "unbekannt" not in by_day[date(2026, 10, 7)].label


async def test_dashboard_needs_portal_punching(client: AsyncClient, db_session: AsyncSession) -> None:
    w = await _setup(db_session, client)
    await _enable(client, w.admin, "BLOCK")
    await client.patch("/settings", headers=w.admin, json={"portal_punching_enabled": False})
    me = (await client.get("/dashboard", headers=w.me)).json()["me"]
    assert (me["portal_punching"], me["location_check"], me["location_check_required"]) == (False, False, False)


def test_response_never_carries_coordinates() -> None:
    from app.schemas.punch import PunchResponse

    fields = set(PunchResponse.model_fields)
    assert {"location_check", "location_check_location_id"} <= fields
    assert not fields & {"latitude", "longitude", "accuracy_m", "position"}
    assert not {c.name for c in Punch.__table__.columns} & {"latitude", "longitude", "accuracy_m", "position"}
    assert json.dumps([c.value for c in PunchLocationCheck]) == '["INSIDE", "OUTSIDE", "UNKNOWN"]'
