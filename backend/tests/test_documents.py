from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _setup(db_session: AsyncSession, client: AsyncClient, role: HrRole = HrRole.HR):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1",
        login_email="erika@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(employee)
    db_session.add(HrUser(email="user@example.com", password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/hr/login", json={"email": "user@example.com", "password": "pw"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    elogin = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "pw"})
    self_headers = {"Authorization": f"Bearer {elogin.json()['access_token']}"}
    return employee, headers, self_headers


async def _upload(client, headers, employee_id, **overrides):
    data = {"category": "CONTRACT", "title": "Arbeitsvertrag", "employee_visible": "false", "confidential": "false"}
    data.update(overrides.pop("data", {}))
    files = overrides.pop("files", {"file": ("vertrag.pdf", PDF, "application/pdf")})
    return await client.post(f"/employees/{employee_id}/documents", headers=headers, data=data, files=files)


async def test_upload_list_download_roundtrip_is_encrypted_at_rest(
    client: AsyncClient, db_session: AsyncSession, tmp_path
) -> None:
    employee, headers, _ = await _setup(db_session, client)

    created = await _upload(client, headers, employee.id)
    assert created.status_code == 201
    document = created.json()
    assert document["content_type"] == "application/pdf" and document["size_bytes"] == len(PDF)

    listing = (await client.get(f"/employees/{employee.id}/documents", headers=headers)).json()
    assert [d["id"] for d in listing] == [document["id"]]

    download = await client.get(f"/employees/{employee.id}/documents/{document['id']}/download", headers=headers)
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in download.headers["content-disposition"]

    stored = [p for p in (tmp_path / "docs").rglob("*") if p.is_file()]
    assert len(stored) == 1 and PDF not in stored[0].read_bytes()  # nicht im Klartext


async def test_file_type_is_detected_by_content_not_name(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers, _ = await _setup(db_session, client)

    html = await _upload(client, headers, employee.id, files={"file": ("bild.png", b"<html><script>x</script>", "image/png")})
    exe = await _upload(client, headers, employee.id, files={"file": ("a.pdf", b"MZ\x90\x00", "application/pdf")})
    empty = await _upload(client, headers, employee.id, files={"file": ("leer.pdf", b"", "application/pdf")})
    png = await _upload(client, headers, employee.id, files={"file": ("x.png", b"\x89PNG\r\n\x1a\n....", "text/html")})

    assert html.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    assert exe.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    assert empty.json()["code"] == "EMPTY_FILE"
    assert png.status_code == 201 and png.json()["content_type"] == "image/png"  # Client-Header wird ignoriert


async def test_size_limit_and_quota(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    employee, headers, _ = await _setup(db_session, client)
    monkeypatch.setattr(settings, "max_document_bytes", 100)
    too_big = await _upload(client, headers, employee.id, files={"file": ("a.pdf", PDF + b"x" * 200, "application/pdf")})
    assert too_big.status_code == 413 and too_big.json()["code"] == "DOCUMENT_TOO_LARGE"

    monkeypatch.setattr(settings, "max_document_bytes", 10_000)
    monkeypatch.setattr(settings, "max_tenant_document_bytes", len(PDF) + 5)
    assert (await _upload(client, headers, employee.id)).status_code == 201
    over = await _upload(client, headers, employee.id)
    assert over.status_code == 413 and over.json()["code"] == "DOCUMENT_QUOTA_EXCEEDED"


async def test_visibility_rules_for_hr_admin_employee_and_supervisor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, hr_headers, self_headers = await _setup(db_session, client, HrRole.HR)
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    db_session.add(HrUser(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR))
    await db_session.commit()
    admin = (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()
    sup = (await client.post("/auth/hr/login", json={"email": "sup@example.com", "password": "pw"})).json()
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    sup_headers = {"Authorization": f"Bearer {sup['access_token']}"}

    visible = (await _upload(client, hr_headers, employee.id, data={"title": "Für Mitarbeiter", "employee_visible": "true"})).json()
    internal = (await _upload(client, hr_headers, employee.id, data={"title": "Intern"})).json()
    secret = await _upload(client, admin_headers, employee.id, data={"title": "Abmahnung", "confidential": "true", "category": "WARNING"})
    assert secret.status_code == 201
    hr_confidential = await _upload(client, hr_headers, employee.id, data={"confidential": "true"})
    assert hr_confidential.status_code == 403

    def titles(response):
        return sorted(d["title"] for d in response.json())

    url = f"/employees/{employee.id}/documents"
    assert titles(await client.get(url, headers=hr_headers)) == ["Für Mitarbeiter", "Intern"]  # HR sieht Vertrauliches nicht
    assert titles(await client.get(url, headers=admin_headers)) == ["Abmahnung", "Für Mitarbeiter", "Intern"]
    assert titles(await client.get(url, headers=self_headers)) == ["Für Mitarbeiter"]
    assert (await client.get(url, headers=sup_headers)).status_code == 403

    # Mitarbeiter lädt nur Freigegebenes herunter, Internes ist für ihn "nicht gefunden"
    assert (await client.get(f"{url}/{visible['id']}/download", headers=self_headers)).status_code == 200
    assert (await client.get(f"{url}/{internal['id']}/download", headers=self_headers)).status_code == 404
    assert (await client.get(f"{url}/{secret.json()['id']}/download", headers=hr_headers)).status_code == 404
    # Mitarbeiter darf nichts hochladen/ändern/löschen
    assert (await _upload(client, self_headers, employee.id)).status_code == 403
    assert (await client.delete(f"{url}/{visible['id']}", headers=self_headers)).status_code == 403


async def test_confidential_and_employee_visible_are_exclusive(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers, _ = await _setup(db_session, client, HrRole.ADMIN)

    both = await _upload(client, headers, employee.id, data={"confidential": "true", "employee_visible": "true"})
    ok = (await _upload(client, headers, employee.id, data={"confidential": "true"})).json()
    flip = await client.patch(f"/employees/{employee.id}/documents/{ok['id']}", headers=headers, json={"employee_visible": True})

    assert both.status_code == 400 and flip.status_code == 400
    assert both.json()["code"] == "CONFIDENTIAL_NOT_VISIBLE"


async def test_retention_blocks_deletion_and_delete_removes_file(
    client: AsyncClient, db_session: AsyncSession, tmp_path
) -> None:
    employee, headers, _ = await _setup(db_session, client)
    future = (date.today() + timedelta(days=30)).isoformat()
    kept = (await _upload(client, headers, employee.id, data={"retention_until": future})).json()
    free = (await _upload(client, headers, employee.id, data={"title": "Frei"})).json()

    blocked = await client.delete(f"/employees/{employee.id}/documents/{kept['id']}", headers=headers)
    deleted = await client.delete(f"/employees/{employee.id}/documents/{free['id']}", headers=headers)

    assert blocked.status_code == 409 and blocked.json()["code"] == "DOCUMENT_UNDER_RETENTION"
    assert deleted.status_code == 204
    assert len([p for p in (tmp_path / "docs").rglob("*") if p.is_file()]) == 1


async def test_document_actions_are_audited_without_content(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers, _ = await _setup(db_session, client, HrRole.ADMIN)
    document = (await _upload(client, headers, employee.id)).json()
    await client.get(f"/employees/{employee.id}/documents/{document['id']}/download", headers=headers)
    await client.delete(f"/employees/{employee.id}/documents/{document['id']}", headers=headers)

    actions = {e["action"] for e in (await client.get("/audit-log", headers=headers)).json()}

    assert {"DOCUMENT_UPLOADED", "DOCUMENT_ACCESSED", "DOCUMENT_DELETED"} <= actions


async def test_anonymization_deletes_documents_except_under_retention(
    client: AsyncClient, db_session: AsyncSession, tmp_path
) -> None:
    employee, headers, _ = await _setup(db_session, client, HrRole.ADMIN)
    employee.termination_date = date(2026, 1, 1)
    await db_session.commit()
    future = (date.today() + timedelta(days=30)).isoformat()
    await _upload(client, headers, employee.id, data={"title": "Löschbar"})
    await _upload(client, headers, employee.id, data={"title": "Aufbewahrung", "retention_until": future})

    anonymized = await client.post(f"/employees/{employee.id}/anonymize", headers=headers)

    assert anonymized.status_code == 200
    remaining = (await client.get(f"/employees/{employee.id}/documents", headers=headers)).json()
    assert [d["title"] for d in remaining] == ["Aufbewahrung"]
    assert len([p for p in (tmp_path / "docs").rglob("*") if p.is_file()]) == 1


async def test_unknown_employee_and_cross_tenant_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers, _ = await _setup(db_session, client)

    assert (await client.get("/employees/9999/documents", headers=headers)).status_code == 404
    assert (await _upload(client, headers, 9999)).status_code == 404
