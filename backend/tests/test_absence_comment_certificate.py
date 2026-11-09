"""Pflichtkommentar je Abwesenheitsart und Nachweis-Upload (z. B. AU-Bescheinigung) am Eintrag."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Employee
from tests.test_absence_types import _setup, _types

@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    """Nachweise nicht ins Repo schreiben (wie in test_documents.py)."""
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


async def _me(client: AsyncClient) -> dict:
    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_comment_required(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    types = await _types(client, headers)
    special = types["Sonderurlaub"]
    assert (await client.patch(f"/absence-types/{special['id']}", headers=headers, json={"comment_required": True})).json()["comment_required"]

    body = {"employee_id": employee.id, "absence_type_id": special["id"], "date_from": "2025-03-10", "date_to": "2025-03-10"}
    missing = await client.post("/absences", headers=headers, json={**body, "note": "  "})
    assert missing.status_code == 400 and missing.json()["code"] == "COMMENT_REQUIRED"
    assert (await client.post("/absences", headers=headers, json={**body, "note": "Umzug"})).status_code == 201

    sick = await client.patch(f"/absence-types/{types['Krank']['id']}", headers=headers, json={"comment_required": True})
    assert sick.status_code == 400 and sick.json()["code"] == "COMMENT_NOT_FOR_SICKNESS"
    new = await client.post("/absence-types", headers=headers, json={"name": "Krank 2", "category": "SICK", "comment_required": True})
    assert new.status_code == 400


async def test_employee_uploads_certificate(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    sick = (await _types(client, headers))["Krank"]
    created = await client.post(
        "/absences", headers=headers,
        json={"employee_id": employee.id, "absence_type_id": sick["id"], "date_from": "2025-03-10", "date_to": "2025-03-14"},
    )
    absence_id = created.json()["id"]
    me = await _me(client)

    r = await client.post(f"/absences/{absence_id}/certificate", headers=me, files={"file": ("au.pdf", PDF, "application/pdf")})
    assert r.status_code == 200, r.text
    document_id = r.json()["certificate_document_id"]
    assert document_id

    docs = (await client.get(f"/employees/{employee.id}/documents", headers=me)).json()
    doc = next(d for d in docs if d["id"] == document_id)
    assert doc["category"] == "SICK_NOTE" and doc["title"].startswith("Nachweis Krank 10.03.2025")

    # Andere Mitarbeiter dürfen nicht hochladen
    other = Employee(location_id=employee.location_id, first_name="Max", last_name="Fremd", employee_number="A9",
                     login_email="max@example.com", password_hash=employee.password_hash)
    db_session.add(other)
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "max@example.com", "password": "pw123456"})).json()["access_token"]
    forbidden = await client.post(
        f"/absences/{absence_id}/certificate", headers={"Authorization": f"Bearer {token}"},
        files={"file": ("au.pdf", PDF, "application/pdf")},
    )
    assert forbidden.status_code == 403
