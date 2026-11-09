"""Eigene Dokumentkategorien mit Rechten; Mitarbeiter laden in freigegebene Kategorien selbst hoch."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account, Employee, HrRole, Location, Notification, NotificationType
from app.services.auth_service import hash_password

PW = "pw123456"
PDF = b"%PDF-1.4\n%test\n"


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _setup(client: AsyncClient, db_session: AsyncSession):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    erika = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="1",
        login_email="erika@example.com", password_hash=hash_password(PW),
    )
    db_session.add(erika)
    await db_session.commit()
    tokens = {}
    for name in ("chefin", "erika"):
        r = await client.post("/auth/login", json={"email": f"{name}@example.com", "password": PW})
        tokens[name] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return erika, tokens


async def test_categories_and_employee_upload(client: AsyncClient, db_session: AsyncSession) -> None:
    erika, t = await _setup(client, db_session)
    certificates = (await client.post("/document-categories", headers=t["chefin"], json={"name": "Bescheinigungen", "employee_upload": True, "employee_visible": True})).json()
    internal = (await client.post("/document-categories", headers=t["chefin"], json={"name": "Intern", "confidential": True})).json()
    bad = await client.post("/document-categories", headers=t["chefin"], json={"name": "X", "confidential": True, "employee_upload": True})
    assert bad.status_code == 400

    # Mitarbeiter sieht nur hochladbare Kategorien
    assert [c["name"] for c in (await client.get("/document-categories", headers=t["erika"])).json()] == ["Bescheinigungen"]
    denied = await client.post("/me/documents", headers=t["erika"], data={"category_id": internal["id"], "title": "X"}, files={"file": ("x.pdf", PDF, "application/pdf")})
    assert denied.status_code == 403
    uploaded = await client.post(
        "/me/documents", headers=t["erika"], data={"category_id": certificates["id"], "title": "Erste-Hilfe-Kurs"},
        files={"file": ("kurs.pdf", PDF, "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert (uploaded.json()["category_id"], uploaded.json()["employee_visible"]) == (certificates["id"], True)
    mine = (await client.get(f"/employees/{erika.id}/documents", headers=t["erika"])).json()
    assert [d["title"] for d in mine] == ["Erste-Hilfe-Kurs"]
    notes = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.DOCUMENT_UPLOADED))).scalars().all()
    assert len(notes) == 1

    # HR legt in eine eigene Kategorie ab und ändert sie
    hr_doc = await client.post(
        f"/employees/{erika.id}/documents", headers=t["chefin"],
        data={"category": "OTHER", "category_id": internal["id"], "title": "Notiz", "confidential": "true"},
        files={"file": ("n.pdf", PDF, "application/pdf")},
    )
    assert hr_doc.status_code == 201 and hr_doc.json()["category_id"] == internal["id"]
    moved = await client.patch(f"/employees/{erika.id}/documents/{hr_doc.json()['id']}", headers=t["chefin"], json={"category": "CONTRACT"})
    assert (moved.json()["category"], moved.json()["category_id"]) == ("CONTRACT", None)
