"""Einstellungen eines Mandanten als Datei exportieren und in einem anderen Mandanten importieren
(Migration, z.B. aus einer Testfirma). Firmenbezogenes (Mailserver, Admin-PIN, DATEV-Nummern,
Kontobeginn) bleibt außen vor; Pausenregeln, Abwesenheitsarten und Zuschläge werden nur ergänzt."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, HrRole, HrUser
from app.services.auth_service import hash_password


async def _admin(db_session: AsyncSession, client: AsyncClient, tenant_id: int, email: str) -> dict:
    db_session.add(HrUser(tenant_id=tenant_id, email=email, password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    login = await client.post("/auth/hr/login", json={"email": email, "password": "pw"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _source(db_session: AsyncSession, client: AsyncClient) -> tuple[dict, dict]:
    admin = await _admin(db_session, client, 1, "admin@example.com")
    r = await client.patch(
        "/settings",
        headers=admin,
        json={
            "core_time_start": "09:00", "core_time_end": "15:00", "disabled_day_flags": [],
            "report_days_without_punches": False, "kiosk_greeting": "Moin",
            "datev_consultant_number": "1234567", "datev_client_number": "10001",
        },
    )
    assert r.status_code == 200, r.text
    assert (await client.put("/wage-types", headers=admin, json={"items": {"WORKED": "1000", "VACATION": "1100"}})).status_code == 200
    assert (await client.post("/pay-component-types", headers=admin, json={"kind": "ALLOWANCE", "name": "Fahrtkosten", "wage_type": "2000"})).status_code == 201
    db_session.add_all([BreakRule(tenant_id=1, min_work_minutes=360, deduct_minutes=30), BreakRule(tenant_id=1, min_work_minutes=540, deduct_minutes=45)])
    await db_session.commit()
    assert (await client.post("/break-rules", headers=admin, json={"kind": "FIXED_WINDOW", "start_time": "12:00", "end_time": "12:30", "valid_from": "2026-01-01"})).status_code == 201
    assert (await client.post("/absence-types", headers=admin, json={"name": "Berufsschule", "category": "WORK_TIME", "color": "#123456"})).status_code == 201
    assert (await client.post("/surcharge-rules", headers=admin, json={"name": "Nacht", "kind": "NIGHT", "percent": 25, "start_time": "22:00", "end_time": "06:00", "wage_type": "1200"})).status_code == 201
    r = await client.get("/migration/settings-export", headers=admin)
    assert r.status_code == 200, r.text
    return admin, r.json()


async def test_export_contains_portable_parts_only(client: AsyncClient, db_session: AsyncSession) -> None:
    _, exported = await _source(db_session, client)
    assert exported["format"] == "hr3000-settings" and exported["version"] == 1
    settings = exported["settings"]
    assert settings["core_time_start"] == "09:00:00" and settings["report_days_without_punches"] is False
    assert exported["wage_types"] == {"WORKED": "1000", "VACATION": "1100"}
    assert exported["pay_component_types"] == [{"kind": "ALLOWANCE", "name": "Fahrtkosten", "wage_type": "2000", "active": True}]
    for private in ("smtp_host", "smtp_password_set", "datev_consultant_number", "datev_client_number", "balance_start_date", "kiosk_admin_pin_set"):
        assert private not in settings
    assert {r["kind"] for r in exported["break_rules"]} == {"LEGAL", "FIXED_WINDOW"}
    assert "Berufsschule" in [t["name"] for t in exported["absence_types"]]
    assert exported["surcharge_rules"][0]["wage_type"] == "1200"


async def test_import_preview_then_apply(client: AsyncClient, db_session: AsyncSession) -> None:
    """Simuliert die Ziel-Firma, indem nach dem Export alles abweichend eingestellt wird."""
    admin, exported = await _source(db_session, client)
    await client.patch("/settings", headers=admin, json={"clear_core_time": True, "disabled_day_flags": ["EARLY_LEAVE", "LATE_ARRIVAL"], "kiosk_greeting": ""})
    await client.put("/wage-types", headers=admin, json={"items": {"WORKED": None, "VACATION": "1199"}})
    fahrtkosten = (await client.get("/pay-component-types", headers=admin)).json()[0]
    assert (await client.delete(f"/pay-component-types/{fahrtkosten['id']}", headers=admin)).status_code == 204
    for rule in (await db_session.execute(select(BreakRule))).scalars().all():
        if rule.start_time is not None:
            await db_session.delete(rule)  # feste Pausenzeit fehlt im Ziel
        elif rule.min_work_minutes == 540:
            rule.deduct_minutes = 60  # gleiche Schwelle, anderer Wert
    await db_session.commit()
    surcharge_id = (await client.get("/surcharge-rules", headers=admin)).json()[0]["id"]
    assert (await client.delete(f"/surcharge-rules/{surcharge_id}", headers=admin)).status_code == 204
    berufsschule = next(t for t in (await client.get("/absence-types", headers=admin)).json() if t["name"] == "Berufsschule")
    assert (await client.patch(f"/absence-types/{berufsschule['id']}", headers=admin, json={"name": "Schule alt"})).status_code == 200
    await db_session.commit()

    r = await client.post("/migration/settings-import", headers=admin, json=exported)
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["applied"] is False
    assert "Einstellung core_time_start" in preview["changes"]
    assert "Feste Pausenzeit 12:00–12:30" in preview["changes"]
    assert not any(c.startswith("Pausenregel ab 360") for c in preview["changes"])  # identisch vorhanden
    assert any("ab 540 Min." in s and "kollidiert" in s for s in preview["skipped"])
    assert "Abwesenheitsart Berufsschule" in preview["changes"] and "Zuschlag Nacht" in preview["changes"]
    assert "Lohnart Gearbeitete Stunden: 1000" in preview["changes"] and "Lohnart Urlaub: 1100" in preview["changes"]
    assert "Zulagenart Fahrtkosten" in preview["changes"]
    assert (await client.get("/settings", headers=admin)).json()["core_time_start"] is None  # Vorschau schreibt nichts

    r = await client.post("/migration/settings-import?apply=true", headers=admin, json=exported)
    assert r.status_code == 200 and r.json()["applied"] is True
    settings = (await client.get("/settings", headers=admin)).json()
    assert settings["core_time_start"] == "09:00:00" and settings["disabled_day_flags"] == []
    assert settings["kiosk_greeting"] == "Moin"
    wage_types = {i["item"]: i["wage_type"] for i in (await client.get("/wage-types", headers=admin)).json()["items"]}
    assert wage_types["WORKED"] == "1000" and wage_types["VACATION"] == "1100"
    assert [(t["name"], t["wage_type"]) for t in (await client.get("/pay-component-types", headers=admin)).json()] == [("Fahrtkosten", "2000")]
    assert settings["datev_consultant_number"] == "1234567"  # firmenbezogen, bleibt
    db_session.expire_all()
    windows = (await db_session.execute(select(BreakRule).where(BreakRule.start_time.is_not(None)))).scalars().all()
    assert len(windows) == 1
    assert "Berufsschule" in [t["name"] for t in (await client.get("/absence-types", headers=admin)).json()]
    assert [r["name"] for r in (await client.get("/surcharge-rules", headers=admin)).json()] == ["Nacht"]

    # zweiter Import: nichts mehr zu ergänzen
    again = (await client.post("/migration/settings-import", headers=admin, json=exported)).json()
    assert not any(c.startswith(("Feste", "Abwesenheitsart", "Zuschlag", "Einstellung", "Lohnart", "Zulagenart")) for c in again["changes"])


async def test_import_old_file_with_hours_wage_type(client: AsyncClient, db_session: AsyncSession) -> None:
    """Dateien von vor den Lohnarten trugen die Lohnart gearbeitete Stunden in den Einstellungen."""
    admin = await _admin(db_session, client, 1, "admin@example.com")
    old = {"format": "hr3000-settings", "version": 1, "settings": {"datev_hours_wage_type": "1000", "kiosk_greeting": "Hallo"}}
    r = await client.post("/migration/settings-import?apply=true", headers=admin, json=old)
    assert r.status_code == 200, r.text
    wage_types = {i["item"]: i["wage_type"] for i in (await client.get("/wage-types", headers=admin)).json()["items"]}
    assert wage_types["WORKED"] == "1000"


async def test_import_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, exported = await _source(db_session, client)
    assert (await client.post("/migration/settings-import", headers=admin, json={**exported, "format": "anderes"})).status_code == 422
    bad = {**exported, "settings": {**exported["settings"], "late_tolerance_minutes": 999}}
    r = await client.post("/migration/settings-import", headers=admin, json=bad)
    assert r.status_code == 422 and r.json()["code"] == "INVALID_SETTINGS_FILE"
    bad_rule = {**exported, "break_rules": [{"kind": "LEGAL", "min_work_minutes": -1, "deduct_minutes": 30}]}
    assert (await client.post("/migration/settings-import", headers=admin, json=bad_rule)).status_code == 422
    hr_user = HrUser(tenant_id=1, email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(hr_user)
    await db_session.commit()
    login = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    hr = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/migration/settings-export", headers=hr)).status_code == 403
