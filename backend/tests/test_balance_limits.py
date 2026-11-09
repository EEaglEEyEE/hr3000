"""Grenzen fürs Überstundenkonto: Hinweis ab 90 % der Obergrenze bzw. unter der Untergrenze."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_absence_types import _setup


async def test_balance_limits(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    assert (await client.get("/timesheet/balance-limits", headers=headers)).json() == []  # keine Grenzen

    r = await client.patch("/settings", headers=headers, json={"overtime_limit_max_hours": 20, "overtime_limit_min_hours": -10})
    assert r.status_code == 200, r.text
    assert (r.json()["overtime_limit_max_hours"], r.json()["overtime_limit_min_hours"]) == (20, -10)
    assert (await client.patch("/settings", headers=headers, json={"overtime_limit_min_hours": 5})).status_code == 422

    # Kontostand auf +19 Std. setzen (ab 90 % von 20 Std. -> Hinweis, noch nicht überschritten)
    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments/set-balance", headers=headers,
        json={"effective_date": "2025-01-01", "balance_minutes": 19 * 60, "note": "Test"},
    )
    assert r.status_code == 201, r.text
    # Ohne Stempelung beginnt das Konto nicht – der Stand ist genau die Buchung (+19 Std.).
    rows = (await client.get("/timesheet/balance-limits", headers=headers)).json()
    assert [(r["kind"], r["balance_minutes"], r["limit_minutes"], r["exceeded"]) for r in rows] == [("MAX", 1140, 1200, False)]

    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments/set-balance", headers=headers,
        json={"effective_date": "2025-01-02", "balance_minutes": -12 * 60, "note": "Test"},
    )
    rows = (await client.get("/timesheet/balance-limits", headers=headers)).json()
    assert [(r["kind"], r["balance_minutes"], r["exceeded"]) for r in rows] == [("MIN", -720, True)]

    r = await client.patch("/settings", headers=headers, json={"clear_overtime_limit_max": True, "clear_overtime_limit_min": True})
    assert (r.json()["overtime_limit_max_hours"], r.json()["overtime_limit_min_hours"]) == (None, None)
    assert (await client.get("/timesheet/balance-limits", headers=headers)).json() == []
