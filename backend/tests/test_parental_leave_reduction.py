"""§ 17 BEEG: je vollem Kalendermonat Elternzeit 1/12 weniger Urlaub – nur mit Einstellung."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_absence_types import _setup


async def _entitled(client: AsyncClient, headers: dict, employee_id: int) -> float:
    r = await client.get(f"/employees/{employee_id}/leave-entitlement", headers=headers, params={"year": 2025})
    assert r.status_code == 200, r.text
    return r.json()["entitled_days"]


async def test_parental_leave_reduces_vacation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    assert (await client.patch("/settings", headers=headers, json={"default_annual_vacation_days": 30})).status_code == 200
    r = await client.post("/absence-types", headers=headers, json={"name": "Elternzeit", "category": "PARENTAL_LEAVE"})
    type_id = r.json()["id"]
    r = await client.post(
        "/absences", headers=headers,
        json={"employee_id": employee.id, "absence_type_id": type_id, "date_from": "2025-03-01", "date_to": "2025-05-31"},
    )
    assert r.status_code == 201, r.text

    assert await _entitled(client, headers, employee.id) == 30  # Standard: keine Kürzung
    assert (await client.patch("/settings", headers=headers, json={"reduce_vacation_parental_leave": True})).status_code == 200
    assert await _entitled(client, headers, employee.id) == 23  # 30 − 3 × 2,5 = 22,5 → aufgerundet
