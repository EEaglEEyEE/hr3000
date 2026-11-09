"""Dokumentvorlagen: Platzhalter füllen, PDF in die Personalakte, unbekannte Platzhalter abweisen."""
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account, Employee, HrRole, Location
from app.services import document_template_service
from app.services.auth_service import hash_password

PW = "pw123456"


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _setup(client: AsyncClient, db_session: AsyncSession):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    erika = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="1001",
        hire_date=date(2020, 2, 1), position="Buchhaltung",
    )
    db_session.add(erika)
    await db_session.commit()
    r = await client.post("/auth/login", json={"email": "chefin@example.com", "password": PW})
    return erika, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_values_and_fill(client: AsyncClient, db_session: AsyncSession) -> None:
    erika, _ = await _setup(client, db_session)
    data = await document_template_service.values(db_session, erika)
    text, unknown = document_template_service.fill(
        "{{ Vorname }} {{nachname}} ({{personalnummer}}), {{position}} seit {{eintrittsdatum}} am {{standort}}", data
    )
    assert text == "Erika Muster (1001), Buchhaltung seit 01.02.2020 am Zentrale"
    assert unknown == []


async def test_generate_pdf_into_file(client: AsyncClient, db_session: AsyncSession) -> None:
    erika, admin = await _setup(client, db_session)
    template = (await client.post("/document-templates", headers=admin, json={
        "name": "Arbeitsbescheinigung", "category": "CERTIFICATE", "employee_visible": True,
        "body": "# Arbeitsbescheinigung\n\n{{vorname}} {{nachname}} arbeitet seit {{eintrittsdatum}} bei {{firma}}.",
    })).json()
    preview = await client.get(f"/employees/{erika.id}/document-templates/{template['id']}/preview", headers=admin)
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")

    created = await client.post(f"/employees/{erika.id}/documents/from-template", headers=admin, json={"template_id": template["id"]})
    assert created.status_code == 201
    body = created.json()
    assert (body["category"], body["employee_visible"], body["content_type"]) == ("CERTIFICATE", True, "application/pdf")
    assert body["title"].startswith("Arbeitsbescheinigung ")

    broken = (await client.post("/document-templates", headers=admin, json={"name": "Kaputt", "body": "Hallo {{spitzname}}"})).json()
    r = await client.post(f"/employees/{erika.id}/documents/from-template", headers=admin, json={"template_id": broken["id"]})
    assert r.status_code == 400 and "spitzname" in r.json()["detail"]
    placeholders = (await client.get("/document-templates/placeholders", headers=admin)).json()
    assert {"key": "vorname", "label": "Vorname"} in placeholders
