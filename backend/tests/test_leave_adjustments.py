"""Korrekturen am Urlaubskonto: ± Tage, ablaufende Tage verfallen, wenn sie bis dahin nicht genommen sind."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_absence_types import _setup, _types


async def test_adjustments_with_expiry(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await client.patch("/settings", headers=headers, json={"default_annual_vacation_days": 30})
    url = f"/employees/{employee.id}/leave-adjustments"

    assert (await client.post(url, headers=headers, json={"year": 2025, "days": 0.3, "note": "falsch"})).status_code == 422
    assert (await client.post(url, headers=headers, json={"year": 2025, "days": -1, "expires_on": "2025-03-31", "note": "x y z"})).status_code == 422

    bonus = await client.post(url, headers=headers, json={"year": 2025, "days": 2, "expires_on": "2025-03-31", "note": "Sonderurlaub Umzug"})
    assert bonus.status_code == 201, bonus.text
    assert (await client.post(url, headers=headers, json={"year": 2025, "days": -1, "note": "Korrektur Altsystem"})).status_code == 201

    vacation = (await _types(client, headers))["Urlaub"]
    r = await client.post(
        "/absences", headers=headers,
        json={"employee_id": employee.id, "absence_type_id": vacation["id"], "date_from": "2025-03-10", "date_to": "2025-03-10"},
    )
    assert r.status_code == 201, r.text

    balance = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025})).json()
    # 30 + (2 − 1) Korrektur; vom +2 bis 31.03. nur 1 Tag genommen → 1 verfallen; 1 genommen
    assert (balance["adjustment_days"], balance["expired_days"], balance["used_days"], balance["remaining_days"]) == (1, 1, 1, 29)

    listed = (await client.get(url, headers=headers, params={"year": 2025})).json()
    assert [a["days"] for a in listed] == [2, -1]
    assert (await client.delete(f"{url}/{bonus.json()['id']}", headers=headers)).status_code == 204
    balance = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025})).json()
    assert balance["remaining_days"] == 28  # 30 − 1 − 1
