"""Öffentliche API: Zugänge mit Rechten, Token, Lese-Endpunkte, Sperren. Webhooks: SSRF-Schutz,
Ausgangswarteschlange, Signatur, Wiederholung."""
import hashlib
import hmac
import json

import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, HrRole, Location, WebhookDelivery
from app.services import webhook_service
from app.services.auth_service import hash_password

PW = "pw123456"


async def _admin(client: AsyncClient, db_session: AsyncSession) -> tuple[Location, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    r = await client.post("/auth/login", json={"email": "chefin@example.com", "password": PW})
    return location, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_api_clients_tokens_and_reads(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _admin(client, db_session)
    await client.post("/employees", headers=admin, json={"location_id": location.id, "first_name": "Erika", "last_name": "M", "employee_number": "1", "position": "Lager"})
    assert (await client.post("/api-clients", headers=admin, json={"name": "X", "scopes": ["root"]})).status_code == 422
    created = (await client.post("/api-clients", headers=admin, json={"name": "Lohnsoftware", "scopes": ["employees:read"]})).json()
    assert created["client_secret"] and created["client_id"].startswith("hr3000_")
    assert "client_secret" not in (await client.get("/api-clients", headers=admin)).json()[0]

    wrong = await client.post("/v1/auth/token", json={"client_id": created["client_id"], "client_secret": "falsch"})
    assert wrong.status_code == 401
    token = (await client.post("/v1/auth/token", json={"client_id": created["client_id"], "client_secret": created["client_secret"]})).json()
    api = {"Authorization": f"Bearer {token['access_token']}"}
    page = (await client.get("/v1/employees", headers=api)).json()
    assert page["page"]["total"] == 1
    assert (page["data"][0]["first_name"], page["data"][0]["position"], page["data"][0]["status"]) == ("Erika", "Lager", "ACTIVE")
    # fehlendes Recht, Webapp-Token taugt nicht, API-Token nicht für die Webapp
    assert (await client.get("/v1/absences", headers=api, params={"from": "2026-01-01", "to": "2026-01-31"})).status_code == 403
    assert (await client.get("/v1/employees", headers=admin)).status_code == 401
    assert (await client.get("/employees", headers=api)).status_code == 401
    # Sperren beendet auch ausgegebene Tokens
    assert (await client.delete(f"/api-clients/{created['id']}", headers=admin)).status_code == 204
    assert (await client.get("/v1/employees", headers=api)).status_code == 401
    assert (await client.post("/v1/auth/token", json={"client_id": created["client_id"], "client_secret": created["client_secret"]})).status_code == 401



async def test_api_employees_show_department_and_effective_supervisor(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _admin(client, db_session)

    async def employee(number: str, first: str, **extra) -> int:
        r = await client.post(
            "/employees", headers=admin,
            json={"location_id": location.id, "first_name": first, "last_name": "M", "employee_number": number, **extra},
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    sales = (await client.post("/departments", headers=admin, json={"name": "Vertrieb"})).json()["id"]
    bea = await employee("1", "Bea", department_id=sales)
    assert (await client.patch(f"/departments/{sales}", headers=admin, json={"leaders": [{"employee_id": bea}]})).status_code == 200
    erika = await employee("2", "Erika", department_id=sales)  # Führungskraft: Leitung Bea
    xenia = await employee("3", "Xenia")
    otto = await employee("4", "Otto", department_id=sales, supervisor_id=xenia)  # abweichend: Xenia

    created = (await client.post("/api-clients", headers=admin, json={"name": "Lohnsoftware", "scopes": ["employees:read"]})).json()
    token = (await client.post("/v1/auth/token", json={"client_id": created["client_id"], "client_secret": created["client_secret"]})).json()
    page = (await client.get("/v1/employees", headers={"Authorization": f"Bearer {token['access_token']}"})).json()
    assert all("team_id" not in row for row in page["data"])
    assert {row["id"]: row["supervisor_ids"] for row in page["data"]} == {bea: [], erika: [bea], xenia: [], otto: [xenia]}
    rows = {row["id"]: (row["department_id"], row["department"], row["supervisor_id"]) for row in page["data"]}
    assert rows == {
        bea: (sales, "Vertrieb", None),
        erika: (sales, "Vertrieb", bea),
        xenia: (None, None, None),
        otto: (sales, "Vertrieb", xenia),
    }

async def test_webhooks_queue_sign_and_retry(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    location, admin = await _admin(client, db_session)
    for url in ("http://example.com/hook", "https://10.0.0.5/hook", "https://localhost/hook", "https://user:pw@example.com/x"):
        assert (await client.post("/webhooks", headers=admin, json={"url": url, "events": ["employee.created"]})).status_code == 400
    hook = (await client.post("/webhooks", headers=admin, json={"url": "https://example.com/hook", "events": ["employee.created"]})).json()
    secret = hook["secret"]

    await client.post("/employees", headers=admin, json={"location_id": location.id, "first_name": "Nina", "last_name": "N", "employee_number": "2"})
    queued = (await db_session.execute(select(WebhookDelivery))).scalars().all()
    assert [(d.event, d.status) for d in queued] == [("employee.created", "PENDING")]
    assert json.loads(queued[0].payload)["data"]["employee_id"] > 0

    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(204 if len(received) == 1 else 500)

    async def public(host, port):
        return True

    monkeypatch.setattr(webhook_service, "_resolves_publicly", public)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await webhook_service.deliver_due(db_session, http) == 1
        request = received[0]
        expected = "sha256=" + hmac.new(
            secret.encode(), request.headers["X-HR3000-Timestamp"].encode() + b"." + request.content, hashlib.sha256
        ).hexdigest()
        assert request.headers["X-HR3000-Signature"] == expected
        assert request.headers["X-HR3000-Event"] == "employee.created"
        await db_session.refresh(queued[0])
        assert queued[0].status == "SENT"

        # Fehler: nächster Versuch später, noch offen
        test = (await client.post(f"/webhooks/{hook['id']}/test", headers=admin)).json()
        await webhook_service.deliver_due(db_session, http)
        delivery = await db_session.get(WebhookDelivery, test["id"])
        await db_session.refresh(delivery)
        assert (delivery.status, delivery.attempts, delivery.last_error) == ("PENDING", 1, "Antwort 500")
        assert await webhook_service.deliver_due(db_session, http) == 0  # noch nicht fällig

    # interne Auflösung wird nicht angefragt
    async def private(host, port):
        return False

    monkeypatch.setattr(webhook_service, "_resolves_publicly", private)
    delivery.next_attempt_at = delivery.created_at
    await db_session.commit()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await webhook_service.deliver_due(db_session, http)
    await db_session.refresh(delivery)
    assert delivery.last_error == "Adresse nicht öffentlich erreichbar" and len(received) == 2
    listed = (await client.get("/webhooks", headers=admin)).json()[0]
    assert listed["last_status"].startswith("Fehler") and "secret" not in listed
