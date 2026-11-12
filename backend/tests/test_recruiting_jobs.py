"""Recruiting: Schalter, Zugriff und Stellen (Anlegen, Ändern, Hiring Team, Löschen)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditAction, AuditLogEntry, RecruitingJob, RecruitingJobMember, RecruitingStat
from tests.recruiting_helpers import company, create_application, create_job, job_payload, other_company


async def test_switch_off_returns_404_for_all_endpoints(client, db_session) -> None:
    ctx = await company(db_session, client, enabled=False)
    for method, url in (
        ("get", "/recruiting/jobs"),
        ("post", "/recruiting/jobs"),
        ("get", "/recruiting/jobs/1"),
        ("get", "/recruiting/applications"),
        ("get", "/recruiting/applications/1"),
        ("get", "/recruiting/applications/due-for-deletion"),
        ("get", "/recruiting/team-candidates"),
    ):
        kwargs = {"json": job_payload()} if method == "post" else {}
        response = await getattr(client, method)(url, headers=ctx.headers["admin"], **kwargs)
        assert response.status_code == 404, url
        assert response.json()["code"] == "RECRUITING_DISABLED"


async def test_access_reports_switch_and_rights(client, db_session) -> None:
    ctx = await company(db_session, client, enabled=False)
    off = (await client.get("/recruiting/access", headers=ctx.headers["admin"])).json()
    assert off == {"enabled": False, "can_manage": False, "member": False, "can_see_salary": False}

    from tests.recruiting_helpers import enable

    await enable(db_session)
    admin = (await client.get("/recruiting/access", headers=ctx.headers["admin"])).json()
    assert admin == {"enabled": True, "can_manage": True, "member": False, "can_see_salary": True}
    hr = (await client.get("/recruiting/access", headers=ctx.headers["hr"])).json()
    assert hr["can_manage"] and not hr["can_see_salary"]
    assert (await client.get("/recruiting/access", headers=ctx.headers["payroll"])).json()["can_see_salary"]

    staff = (await client.get("/recruiting/access", headers=ctx.headers["staff"])).json()
    assert staff == {"enabled": True, "can_manage": False, "member": False, "can_see_salary": False}
    await create_job(client, ctx.headers["admin"], member_account_ids=[ctx.accounts["staff"].id])
    assert (await client.get("/recruiting/access", headers=ctx.headers["staff"])).json()["member"] is True


async def test_access_requires_login(client, db_session) -> None:
    await company(db_session, client)
    assert (await client.get("/recruiting/access")).status_code in (401, 403)


async def test_admin_creates_job_with_team_and_audit(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(
        client, ctx.headers["hr"],
        department_id=ctx.department.id, location_id=ctx.location.id,
        application_deadline=str(date.today() + timedelta(days=10)),
        member_account_ids=[ctx.accounts["lead"].id, ctx.accounts["staff"].id],
    )
    assert job["status"] == "PUBLISHED" and job["public"] is True
    assert job["slug"] == "sachbearbeiter-m-w-d-buchhaltung"
    assert job["department_name"] == "Vertrieb" and job["location_name"] == "Zentrale"
    assert job["published_at"] is not None
    assert {m["account_id"] for m in job["members"]} == {ctx.accounts["lead"].id, ctx.accounts["staff"].id}
    assert {m["name"] for m in job["members"]} == {"Lead Muster", "Staff Muster"}
    audit = (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.RECRUITING_JOB_CHANGED)
    )).scalars().all()
    assert len(audit) == 1 and audit[0].entity_id == job["id"]


async def test_draft_job_is_not_public_and_has_no_published_at(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], status="DRAFT")
    assert job["public"] is False and job["published_at"] is None


async def test_past_deadline_is_not_public(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], application_deadline=str(date.today() - timedelta(days=1)))
    assert job["public"] is False
    today = await create_job(client, ctx.headers["admin"], application_deadline=str(date.today()))
    assert today["public"] is True


@pytest.mark.parametrize("role", ["lead", "staff"])
async def test_only_full_hr_can_create_jobs(client, db_session, role) -> None:
    ctx = await company(db_session, client)
    response = await client.post("/recruiting/jobs", json=job_payload(), headers=ctx.headers[role])
    assert response.status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"status": "ARCHIVED"},
        {"employment_type": "SLAVE"},
        {"description": "x" * 20001},
        {"application_deadline": "1999-12-31"},
        {"member_account_ids": [1, 1]},
        {"member_account_ids": [0]},
        {"department_id": 0},
    ],
)
async def test_job_validation(client, db_session, overrides) -> None:
    ctx = await company(db_session, client)
    response = await client.post("/recruiting/jobs", json=job_payload(**overrides), headers=ctx.headers["admin"])
    assert response.status_code == 422


async def test_job_references_must_belong_to_company(client, db_session) -> None:
    ctx = await company(db_session, client)
    assert (await client.post("/recruiting/jobs", json=job_payload(department_id=999), headers=ctx.headers["admin"])).status_code == 404
    assert (await client.post("/recruiting/jobs", json=job_payload(location_id=999), headers=ctx.headers["admin"])).status_code == 404


async def test_team_member_must_be_account_of_company(client, db_session) -> None:
    ctx = await company(db_session, client)
    await other_company(db_session, client)
    from app.models import Account

    foreign = (await db_session.execute(select(Account).where(Account.tenant_id == 2))).scalar_one()
    response = await client.post("/recruiting/jobs", json=job_payload(member_account_ids=[foreign.id]), headers=ctx.headers["admin"])
    assert response.status_code == 400 and response.json()["code"] == "RECRUITING_MEMBER_INVALID"
    response = await client.post("/recruiting/jobs", json=job_payload(member_account_ids=[9999]), headers=ctx.headers["admin"])
    assert response.status_code == 400


async def test_update_job_changes_fields_team_and_logs_changed_fields(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], status="DRAFT", member_account_ids=[ctx.accounts["lead"].id])
    response = await client.put(
        f"/recruiting/jobs/{job['id']}",
        json=job_payload(title="Lagerist", status="PUBLISHED", member_account_ids=[ctx.accounts["staff"].id]),
        headers=ctx.headers["admin"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Lagerist" and body["slug"] == "lagerist" and body["published_at"] is not None
    assert [m["account_id"] for m in body["members"]] == [ctx.accounts["staff"].id]
    entries = (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.RECRUITING_JOB_CHANGED).order_by(AuditLogEntry.id)
    )).scalars().all()
    assert "title" in entries[-1].detail and "hiring_team" in entries[-1].detail and "Lagerist" not in entries[-1].detail


async def test_update_without_changes_writes_no_audit(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    await client.put(f"/recruiting/jobs/{job['id']}", json=job_payload(), headers=ctx.headers["admin"])
    count = len((await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.RECRUITING_JOB_CHANGED)
    )).scalars().all())
    assert count == 1


async def test_closing_keeps_published_at(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    closed = (await client.put(f"/recruiting/jobs/{job['id']}", json=job_payload(status="CLOSED"), headers=ctx.headers["admin"])).json()
    assert closed["status"] == "CLOSED" and closed["public"] is False and closed["published_at"] == job["published_at"]


async def test_visibility_of_jobs_by_role(client, db_session) -> None:
    ctx = await company(db_session, client)
    mine = await create_job(client, ctx.headers["admin"], title="Mit Team", member_account_ids=[ctx.accounts["lead"].id, ctx.accounts["staff"].id])
    other = await create_job(client, ctx.headers["admin"], title="Ohne Team")
    for role in ("admin", "hr"):
        titles = {j["title"] for j in (await client.get("/recruiting/jobs", headers=ctx.headers[role])).json()}
        assert titles == {"Mit Team", "Ohne Team"}
    for role in ("lead", "staff"):
        titles = [j["title"] for j in (await client.get("/recruiting/jobs", headers=ctx.headers[role])).json()]
        assert titles == ["Mit Team"]
        assert (await client.get(f"/recruiting/jobs/{mine['id']}", headers=ctx.headers[role])).status_code == 200
        hidden = await client.get(f"/recruiting/jobs/{other['id']}", headers=ctx.headers[role])
        assert hidden.status_code == 404 and hidden.json()["code"] == "RECRUITING_JOB_NOT_FOUND"
    assert (await client.get("/recruiting/jobs", headers=ctx.headers["other"])).json() == []


@pytest.mark.parametrize("role", ["lead", "staff"])
async def test_members_cannot_edit_or_delete_jobs(client, db_session, role) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], member_account_ids=[ctx.accounts[role].id])
    assert (await client.put(f"/recruiting/jobs/{job['id']}", json=job_payload(), headers=ctx.headers[role])).status_code == 403
    assert (await client.delete(f"/recruiting/jobs/{job['id']}", headers=ctx.headers[role])).status_code == 403
    assert (await client.get("/recruiting/team-candidates", headers=ctx.headers[role])).status_code == 403


async def test_foreign_company_sees_nothing(client, db_session) -> None:
    ctx = await company(db_session, client)
    acme = await other_company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    assert (await client.get("/recruiting/jobs", headers=acme)).json() == []
    assert (await client.get(f"/recruiting/jobs/{job['id']}", headers=acme)).status_code == 404
    assert (await client.put(f"/recruiting/jobs/{job['id']}", json=job_payload(), headers=acme)).status_code == 404
    assert (await client.delete(f"/recruiting/jobs/{job['id']}", headers=acme)).status_code == 404


async def test_foreign_company_with_recruiting_off_gets_404(client, db_session) -> None:
    await company(db_session, client)
    acme = await other_company(db_session, client, enabled=False)
    assert (await client.get("/recruiting/jobs", headers=acme)).status_code == 404


async def test_delete_job_without_applications(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], member_account_ids=[ctx.accounts["lead"].id])
    assert (await client.delete(f"/recruiting/jobs/{job['id']}", headers=ctx.headers["admin"])).status_code == 204
    assert (await db_session.execute(select(RecruitingJob))).scalars().all() == []
    assert (await db_session.execute(select(RecruitingJobMember))).scalars().all() == []


async def test_delete_job_with_applications_or_stats_is_refused(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    await create_application(client, ctx.headers["admin"], job["id"])
    response = await client.delete(f"/recruiting/jobs/{job['id']}", headers=ctx.headers["admin"])
    assert response.status_code == 409 and response.json()["code"] == "RECRUITING_JOB_IN_USE"

    second = await create_job(client, ctx.headers["admin"], title="Zweite")
    db_session.add(RecruitingStat(tenant_id=1, job_id=second["id"], stage="REJECTED", count=1))
    await db_session.commit()
    assert (await client.delete(f"/recruiting/jobs/{second['id']}", headers=ctx.headers["admin"])).status_code == 409


async def test_job_counts(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    first = await create_application(client, ctx.headers["admin"], job["id"])
    await create_application(client, ctx.headers["admin"], job["id"], email="b2@example.com")
    await client.post(f"/recruiting/applications/{first['id']}/stage", json={"stage": "REJECTED", "rejection_reason": "OTHER"}, headers=ctx.headers["admin"])
    db_session.add(RecruitingStat(tenant_id=1, job_id=job["id"], stage="WITHDRAWN", count=3))
    await db_session.commit()
    body = (await client.get(f"/recruiting/jobs/{job['id']}", headers=ctx.headers["admin"])).json()
    assert body["application_count"] == 2 and body["open_count"] == 1
    assert body["deleted_counts"] == {"WITHDRAWN": 3}


async def test_team_candidates_lists_accounts_with_login(client, db_session) -> None:
    ctx = await company(db_session, client)
    candidates = (await client.get("/recruiting/team-candidates", headers=ctx.headers["hr"])).json()
    emails = {c["email"] for c in candidates}
    assert {"admin@example.com", "lead@example.com", "staff@example.com"} <= emails
    staff = next(c for c in candidates if c["email"] == "staff@example.com")
    assert staff["role"] is None and staff["name"] == "Staff Muster"


async def test_tablet_and_super_admin_have_no_access(client, db_session) -> None:
    from app.api.deps import Actor
    from app.api.recruiting import _require_account
    from app.errors import AppError
    from app.models import Account, Device, HrRole

    with pytest.raises(AppError) as tablet:
        _require_account(Actor(device=Device(tenant_id=1)))
    assert tablet.value.status_code == 403
    with pytest.raises(AppError) as super_admin:
        _require_account(Actor(account=Account(tenant_id=None, role=HrRole.SUPER_ADMIN)))
    assert super_admin.value.code == "TENANT_CONTEXT_REQUIRED"
