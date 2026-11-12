"""Eigene Rollen in den Modulen aus Phase 7–10: Recruiting (Bereich „Recruiting“, sonst nur Hiring Team),
Auswertungen/eigene Berichte (Bereich „Auswertungen“, Vorschau/Export sind lesende POSTs) und
Hinweisgebersystem (Benennung entscheidet, nicht die Rolle)."""
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, HrRole, Role
from app.services import role_permissions as rp
from app.services.auth_service import hash_password
from app.services.role_permissions import Area, Level, dump_permissions
from app.services.settings_service import get_or_create_settings
from tests import recruiting_helpers as rh
from tests import whistle_helpers as wh


async def _role(db: AsyncSession, name: str, **perms: str) -> Role:
    role = Role(tenant_id=1, name=name, permissions=dump_permissions({Area(k): v for k, v in perms.items()}))
    db.add(role)
    await db.commit()
    return role


async def _limited_account(db: AsyncSession, email: str, role: Role) -> Account:
    account = Account(email=email, password_hash=hash_password("pw"), role=HrRole.HR, custom_role=role)
    db.add(account)
    await db.commit()
    return account


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": "pw"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- Regeltabelle (Einheit) -------------------------------------------------------------------------


def test_recruiting_area_exists_and_is_labelled() -> None:
    assert Area.RECRUITING in rp.AREA_INFO
    assert rp.AREA_INFO[Area.RECRUITING][0] == "Recruiting"


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/recruiting/jobs"),
        ("POST", "/recruiting/jobs"),
        ("POST", "/recruiting/applications/{application_id}/stage"),
        ("POST", "/recruiting/applications/{application_id}/hire"),
    ],
)
def test_recruiting_routes_fall_back_to_self_without_area(method: str, path: str) -> None:
    only_time = rp.normalize({"TIME": "EDIT"})
    assert rp.decide(method, path, only_time, has_employee=False) == rp.Decision.SELF
    with_area = rp.normalize({"RECRUITING": "EDIT"})
    assert rp.decide(method, path, with_area, has_employee=False) == rp.Decision.ALLOW


def test_recruiting_view_is_not_enough_for_writes() -> None:
    view = rp.normalize({"RECRUITING": "VIEW"})
    assert rp.decide("GET", "/recruiting/jobs", view, has_employee=True) == rp.Decision.ALLOW
    assert rp.decide("POST", "/recruiting/jobs", view, has_employee=True) == rp.Decision.SELF


@pytest.mark.parametrize(
    "path",
    ["/report-builder/preview", "/report-builder/export", "/report-builder/reports/{report_id}/run",
     "/report-builder/reports/{report_id}/export"],
)
def test_report_builder_read_posts_need_only_view(path: str) -> None:
    view = rp.normalize({"REPORTS": "VIEW"})
    assert rp.decide("POST", path, view, has_employee=False) == rp.Decision.ALLOW
    assert rp.decide("POST", path, rp.normalize({"TIME": "EDIT"}), has_employee=False) == rp.Decision.DENY


@pytest.mark.parametrize(
    "method, path",
    [("POST", "/report-builder/reports"), ("PUT", "/report-builder/reports/{report_id}"),
     ("DELETE", "/report-builder/reports/{report_id}")],
)
def test_saving_reports_needs_edit(method: str, path: str) -> None:
    assert rp.decide(method, path, rp.normalize({"REPORTS": "VIEW"}), has_employee=False) == rp.Decision.DENY
    assert rp.decide(method, path, rp.normalize({"REPORTS": "EDIT"}), has_employee=False) == rp.Decision.ALLOW


def test_whistle_rules() -> None:
    nothing = rp.normalize({"TIME": "VIEW"})
    assert rp.decide("GET", "/whistle/cases", nothing, has_employee=False) == rp.Decision.ALLOW
    assert rp.decide("POST", "/whistle/officers", rp.normalize({a.value: "EDIT" for a in Area}), has_employee=False) == rp.Decision.DENY
    assert rp.ROUTE_RULES["POST /public/whistle/reports"].kind == rp.RuleKind.PUBLIC


# --- Recruiting ---------------------------------------------------------------------------------------


async def test_custom_role_with_recruiting_area_manages_jobs(client: AsyncClient, db_session: AsyncSession) -> None:
    await rh.company(db_session, client)
    await _limited_account(db_session, "recruiter@example.com", await _role(db_session, "Recruiting", RECRUITING="EDIT"))
    headers = await _login(client, "recruiter@example.com")
    access = (await client.get("/recruiting/access", headers=headers)).json()
    assert access["enabled"] is True and access["can_manage"] is True
    job = await rh.create_job(client, headers)
    assert (await client.get(f"/recruiting/jobs/{job['id']}", headers=headers)).status_code == 200


async def test_custom_role_with_view_cannot_create_jobs(client: AsyncClient, db_session: AsyncSession) -> None:
    await rh.company(db_session, client)
    await _limited_account(db_session, "viewer@example.com", await _role(db_session, "Nur sehen", RECRUITING="VIEW"))
    headers = await _login(client, "viewer@example.com")
    response = await client.post("/recruiting/jobs", json=rh.job_payload(), headers=headers)
    assert response.status_code in (403, 404)


async def test_custom_role_without_recruiting_sees_only_hiring_team_jobs(client: AsyncClient, db_session: AsyncSession) -> None:
    company = await rh.company(db_session, client)
    account = await _limited_account(db_session, "zeiten@example.com", await _role(db_session, "Zeiten", TIME="EDIT"))
    headers = await _login(client, "zeiten@example.com")
    foreign = await rh.create_job(client, company.headers["admin"], title="Ohne mich")
    mine = await rh.create_job(client, company.headers["admin"], title="Mit mir", member_account_ids=[account.id])
    await rh.create_application(client, company.headers["admin"], mine["id"])

    access = (await client.get("/recruiting/access", headers=headers)).json()
    assert access["can_manage"] is False and access["member"] is True
    assert (await client.get(f"/recruiting/jobs/{foreign['id']}", headers=headers)).status_code == 404
    listed = (await client.get("/recruiting/applications", headers=headers)).json()
    rows = listed["items"] if isinstance(listed, dict) else listed
    assert rows and all(row["job_id"] == mine["id"] for row in rows)
    assert (await client.post("/recruiting/jobs", json=rh.job_payload(), headers=headers)).status_code in (403, 404)


async def test_custom_role_without_recruiting_and_no_team_sees_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    company = await rh.company(db_session, client)
    await _limited_account(db_session, "zeiten@example.com", await _role(db_session, "Zeiten", TIME="EDIT"))
    headers = await _login(client, "zeiten@example.com")
    job = await rh.create_job(client, company.headers["admin"])
    access = (await client.get("/recruiting/access", headers=headers)).json()
    assert access["can_manage"] is False and access["member"] is False
    assert (await client.get(f"/recruiting/jobs/{job['id']}", headers=headers)).status_code == 404


# --- Auswertungen und eigene Berichte ----------------------------------------------------------------


async def _reports_setup(db: AsyncSession) -> None:
    (await get_or_create_settings(db, 1)).custom_reports_enabled = True
    await db.commit()


async def test_reports_view_can_preview_but_not_save(client: AsyncClient, db_session: AsyncSession) -> None:
    await _reports_setup(db_session)
    await _limited_account(db_session, "analyst@example.com", await _role(db_session, "Analyse", REPORTS="VIEW"))
    headers = await _login(client, "analyst@example.com")
    definition = {"source": "employees", "columns": ["last_name"]}
    assert (await client.post("/report-builder/preview", headers=headers, json={"definition": definition})).status_code == 200
    assert (await client.post("/report-builder/export", headers=headers, json={"definition": definition})).status_code == 200
    saved = await client.post("/report-builder/reports", headers=headers, json={"name": "x", "definition": definition})
    assert saved.status_code == 403
    assert "ROLE_PERMISSION_REQUIRED" in saved.text


async def test_reports_edit_can_save(client: AsyncClient, db_session: AsyncSession) -> None:
    await _reports_setup(db_session)
    await _limited_account(db_session, "analyst@example.com", await _role(db_session, "Analyse", REPORTS="EDIT"))
    headers = await _login(client, "analyst@example.com")
    definition = {"source": "employees", "columns": ["last_name"]}
    saved = await client.post("/report-builder/reports", headers=headers, json={"name": "Liste", "definition": definition})
    assert saved.status_code == 201, saved.text


async def test_fixed_analyses_follow_reports_area(client: AsyncClient, db_session: AsyncSession) -> None:
    await _limited_account(db_session, "analyst@example.com", await _role(db_session, "Analyse", REPORTS="VIEW"))
    await _limited_account(db_session, "zeiten@example.com", await _role(db_session, "Zeiten", TIME="EDIT"))
    period = {"date_from": date(2026, 1, 1).isoformat(), "date_to": date(2026, 3, 31).isoformat()}
    for path in ("/reports/absence-rate", "/reports/headcount"):
        allowed = await client.get(path, params=period, headers=await _login(client, "analyst@example.com"))
        assert allowed.status_code == 200, allowed.text
        denied = await client.get(path, params=period, headers=await _login(client, "zeiten@example.com"))
        assert denied.status_code == 403


async def test_reports_area_none_blocks_builder(client: AsyncClient, db_session: AsyncSession) -> None:
    await _reports_setup(db_session)
    await _limited_account(db_session, "zeiten@example.com", await _role(db_session, "Zeiten", TIME="EDIT"))
    headers = await _login(client, "zeiten@example.com")
    assert (await client.get("/report-builder/catalog", headers=headers)).status_code == 403
    response = await client.post("/report-builder/preview", headers=headers,
                                 json={"definition": {"source": "employees", "columns": ["last_name"]}})
    assert response.status_code == 403


# --- Hinweisgebersystem -------------------------------------------------------------------------------


async def test_appointed_officer_with_custom_role_sees_cases(client: AsyncClient, db_session: AsyncSession) -> None:
    await wh.company(db_session, client, with_officer=False)
    officer = await _limited_account(db_session, "meldestelle@example.com", await _role(db_session, "Zeiten", TIME="VIEW"))
    await wh.appoint(db_session, officer.id)
    headers = await _login(client, "meldestelle@example.com")
    assert (await client.get("/whistle/status", headers=headers)).json()["officer"] is True
    assert (await client.get("/whistle/cases", headers=headers)).status_code == 200


async def test_not_appointed_custom_role_sees_no_cases(client: AsyncClient, db_session: AsyncSession) -> None:
    await wh.company(db_session, client)
    await _limited_account(db_session, "alles@example.com", await _role(db_session, "Alles", **{a.value: "EDIT" for a in Area}))
    headers = await _login(client, "alles@example.com")
    assert (await client.get("/whistle/status", headers=headers)).json()["officer"] is False
    assert (await client.get("/whistle/cases", headers=headers)).status_code == 404
    assert (await client.get("/whistle/officers", headers=headers)).status_code == 403


def test_level_enum_unchanged() -> None:
    assert [level.value for level in Level] == ["NONE", "VIEW", "EDIT"]
