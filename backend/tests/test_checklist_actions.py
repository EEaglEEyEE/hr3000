"""On-/Offboarding mit Aktionen: die neue Person lädt selbst hoch und schlägt Daten vor; E-Mail-Schritt
beim Start (ohne Mailversand bleibt er offen)."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account, Employee, HrRole, Location
from app.services import email_service
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
    neu = Employee(
        location_id=location.id, first_name="Nina", last_name="Neu", employee_number="1",
        login_email="nina@example.com", password_hash=hash_password(PW),
    )
    db_session.add(neu)
    await db_session.commit()
    tokens = {}
    for name in ("chefin", "nina"):
        r = await client.post("/auth/login", json={"email": f"{name}@example.com", "password": PW})
        tokens[name] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return neu, tokens


async def test_onboarding_tasks_for_the_new_person(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    neu, t = await _setup(client, db_session)
    sent = []

    async def fake_send(to, subject, body, config=None):
        sent.append((to, subject, body))
        return True

    async def fake_config(db, tenant_id):
        return object()

    monkeypatch.setattr("app.services.email_service.send_email", fake_send)
    monkeypatch.setattr("app.services.email_service.resolve_smtp_config", fake_config)

    category = (await client.post("/document-categories", headers=t["chefin"], json={"name": "Nachweise"})).json()
    bad = await client.post("/checklist-templates", headers=t["chefin"], json={
        "kind": "ONBOARDING", "name": "X", "items": [{"title": "Upload", "responsible": "HR", "action": "UPLOAD_DOCUMENT", "action_category_id": category["id"]}],
    })
    assert bad.status_code == 422
    template = (await client.post("/checklist-templates", headers=t["chefin"], json={
        "kind": "ONBOARDING", "name": "Start", "items": [
            {"title": "Willkommen", "responsible": "EMPLOYEE", "action": "SEND_EMAIL", "description": "Hallo {{vorname}}, willkommen bei {{firma}}!"},
            {"title": "Führerschein hochladen", "responsible": "EMPLOYEE", "action": "UPLOAD_DOCUMENT", "action_category_id": category["id"]},
            {"title": "Bankdaten eintragen", "responsible": "EMPLOYEE", "action": "FILL_DATA"},
            {"title": "Laptop bestellen", "responsible": "IT"},
        ],
    })).json()
    started = (await client.post(f"/employees/{neu.id}/checklists", headers=t["chefin"], json={"template_id": template["id"]})).json()
    assert sent == [("nina@example.com", "Willkommen", "Hallo Nina, willkommen bei Musterfirma!")]
    welcome = next(i for i in started["items"] if i["title"] == "Willkommen")
    assert welcome["done"] is True and "nina@example.com" in welcome["note"]

    mine = (await client.get("/me/checklist-items", headers=t["nina"])).json()
    assert [i["title"] for i in mine] == ["Führerschein hochladen", "Bankdaten eintragen"]
    upload_item = mine[0]
    # Abhaken geht bei Upload-Aufgaben nicht, Hochladen erledigt sie (auch ohne „Mitarbeiter dürfen hochladen“)
    assert (await client.post(f"/me/checklist-items/{upload_item['id']}/done", headers=t["nina"])).status_code == 400
    r = await client.post(
        "/me/documents", headers=t["nina"],
        data={"category_id": category["id"], "title": "Führerschein", "checklist_item_id": upload_item["id"]},
        files={"file": ("f.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 201
    await client.post("/me/change-requests", headers=t["nina"], json={"personal": {"iban": "DE89 3704 0044 0532 0130 00"}})
    assert (await client.post(f"/me/checklist-items/{mine[1]['id']}/done", headers=t["nina"])).status_code == 200
    assert (await client.get("/me/checklist-items", headers=t["nina"])).json() == []


async def test_email_step_without_mail_setup_stays_open(client: AsyncClient, db_session: AsyncSession) -> None:
    neu, t = await _setup(client, db_session)
    template = (await client.post("/checklist-templates", headers=t["chefin"], json={
        "kind": "ONBOARDING", "name": "Start", "items": [{"title": "Willkommen", "responsible": "HR", "action": "SEND_EMAIL", "description": "Neu: {{vorname}}"}],
    })).json()
    started = (await client.post(f"/employees/{neu.id}/checklists", headers=t["chefin"], json={"template_id": template["id"]})).json()
    item = started["items"][0]
    assert item["done"] is False and "kein Mailversand" in item["note"]


async def test_email_step_for_supervisor_goes_to_all_heads(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    from org_helpers import department

    neu, t = await _setup(client, db_session)
    heads = [
        Employee(location_id=neu.location_id, first_name=first, last_name="Leitung", employee_number=number, login_email=email)
        for first, number, email in (("Ada", "2", "ada@example.com"), ("Bo", "3", "bo@example.com"), ("Cy", "4", None))
    ]
    db_session.add_all(heads)
    await db_session.commit()
    await department(db_session, "Vertrieb", neu, heads=tuple(heads))  # Cy ohne E-Mail-Adresse
    sent = []

    async def fake_send(to, subject, body, config=None):
        sent.append(to)
        return True

    async def fake_config(db, tenant_id):
        return object()

    monkeypatch.setattr("app.services.email_service.send_email", fake_send)
    monkeypatch.setattr("app.services.email_service.resolve_smtp_config", fake_config)
    template = (await client.post("/checklist-templates", headers=t["chefin"], json={
        "kind": "ONBOARDING", "name": "Start",
        "items": [{"title": "Einarbeitung planen", "responsible": "SUPERVISOR", "action": "SEND_EMAIL", "description": "{{vorname}} fängt an"}],
    })).json()
    started = (await client.post(f"/employees/{neu.id}/checklists", headers=t["chefin"], json={"template_id": template["id"]})).json()
    assert sorted(sent) == ["ada@example.com", "bo@example.com"]
    assert started["items"][0]["done"] is True
