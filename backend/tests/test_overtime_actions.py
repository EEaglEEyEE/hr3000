"""Überstundenkonto: „Neuen Kontostand festlegen“ und Auszahlung mit Faktor."""
import csv
import io

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_absence_types import _setup


async def _balance(client: AsyncClient, headers: dict, employee_id: int) -> int:
    r = await client.get(f"/employees/{employee_id}/overtime-balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["running_balance_minutes"]


async def test_set_balance_books_the_difference(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    before = await _balance(client, headers, employee.id)
    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments/set-balance", headers=headers,
        json={"effective_date": "2025-03-31", "balance_minutes": 600, "note": "Stand aus Altsystem"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "CORRECTION"
    assert "Neuer Kontostand +10:00 Std." in r.json()["note"]
    # heute = Stand zum 31.03. + alles danach; die Buchung ist genau die Differenz
    assert await _balance(client, headers, employee.id) == before + r.json()["minutes"]

    again = await client.post(
        f"/employees/{employee.id}/balance-adjustments/set-balance", headers=headers,
        json={"effective_date": "2025-03-31", "balance_minutes": 600, "note": "nochmal"},
    )
    assert again.status_code == 400 and again.json()["code"] == "BALANCE_UNCHANGED"


async def test_payout_with_factor_in_payroll_export(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    bad = await client.post(
        f"/employees/{employee.id}/balance-adjustments", headers=headers,
        json={"effective_date": "2025-03-10", "minutes": 120, "kind": "CORRECTION", "note": "Test", "payout_factor": 1.5},
    )
    assert bad.status_code == 422
    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments", headers=headers,
        json={"effective_date": "2025-03-10", "minutes": -600, "kind": "PAYOUT", "note": "Auszahlung März", "payout_factor": 1.5},
    )
    assert r.status_code == 201, r.text
    assert float(r.json()["payout_factor"]) == 1.5

    export = await client.get(
        "/payroll-export", headers=headers, params={"employee_ids": [employee.id], "from": "2025-03-01", "to": "2025-03-31"}
    )
    row = list(csv.DictReader(io.StringIO(export.text.lstrip("﻿")), delimiter=";"))[0]
    assert row["Ausgezahlte Überstunden (Std.)"] == "10,00"
    assert row["Ausgezahlte Überstunden gewichtet (Std.)"] == "15,00"
