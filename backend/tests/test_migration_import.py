"""Migration aus einem Altsystem: Werte bestehender Mitarbeiter per CSV (Personalnummer) zu einem
Stichtag übernehmen – Überstunden-Übertrag, Urlaubskonto, Arbeitszeitmodell. Erst Vorschau, dann
übernehmen; fehlerhafte Zeilen werden gemeldet, gesperrte Monate und Doppelübernahmen abgelehnt."""
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BalanceAdjustment, Employee, HrRole, Account, LeaveEntitlement, Location, PeriodClosure, PeriodStatus
from app.services.auth_service import hash_password

HEADER = "personalnummer;saldo_stunden;urlaubsanspruch_tage;uebertrag_vorjahr_tage;wochenstunden;arbeitstage;monatsstunden;pause_minuten"


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[dict[str, Employee], dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employees = {
        number: Employee(location_id=location.id, first_name=first, last_name="Alt", employee_number=number)
        for number, first in (("100", "Anna"), ("101", "Ben"), ("102", "Cem"))
    }
    db_session.add_all([*employees.values(), Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    for employee in employees.values():
        await db_session.refresh(employee)
    login = await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})
    return employees, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _upload(client: AsyncClient, admin: dict, csv_text: str, apply: bool, cutover: str = "2026-10-01"):
    return await client.post(
        "/migration/employee-values",
        headers=admin,
        files={"file": ("migration.csv", ("﻿" + csv_text).encode("utf-8"), "text/csv")},
        data={"cutover": cutover, "apply": "true" if apply else "false"},
    )


CSV = "\n".join(
    [
        HEADER,
        "100;12,5;30;4,5;40;Mo-Fr;;30",
        "101;-3;28;;;Mo-Fr;108,5;",
        "102;;;;;Mo-Fr;;",  # Arbeitstage ohne Stunden
        "999;1;;;;;;",  # unbekannt
        "",
    ]
)


async def test_preview_then_apply(client: AsyncClient, db_session: AsyncSession) -> None:
    employees, admin = await _setup(db_session, client)
    r = await _upload(client, admin, CSV, apply=False)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False
    assert [row["employee_number"] for row in body["rows"]] == ["100", "101"]
    assert body["rows"][0]["changes"] == [
        "Überstunden-Übertrag +12,5 h",
        "Urlaubsanspruch 30 Tage",
        "Übertrag Vorjahr 4,5 Tage",
        "Arbeitszeitmodell: 40 h/Woche, Pause 30 Min.",
    ]
    assert body["rows"][1]["changes"][0] == "Überstunden-Übertrag −3 h"
    assert body["rows"][1]["changes"][-1] == "Arbeitszeitmodell: 108,5 h/Monat"
    assert [(e["row"], e["message"]) for e in body["errors"]] == [
        (4, "Arbeitstage ohne Wochenstunden – bitte wochenstunden ergänzen."),
        (5, "Personalnummer '999' nicht gefunden."),
    ]
    # Vorschau schreibt nichts
    assert (await db_session.execute(select(BalanceAdjustment))).first() is None

    r = await _upload(client, admin, CSV, apply=True)
    assert r.status_code == 200 and r.json()["applied"] is True
    anna = employees["100"]
    adjustments = (await db_session.execute(select(BalanceAdjustment).order_by(BalanceAdjustment.minutes))).scalars().all()
    assert [(a.minutes, a.effective_date, a.kind.value) for a in adjustments] == [
        (-180, date(2026, 10, 1), "OPENING_BALANCE"),
        (750, date(2026, 10, 1), "OPENING_BALANCE"),
    ]
    entitlement = (
        await db_session.execute(select(LeaveEntitlement).where(LeaveEntitlement.employee_id == anna.id, LeaveEntitlement.year == 2026))
    ).scalar_one()
    assert float(entitlement.entitled_days) == 30 and float(entitlement.carried_over_days) == 4.5 and entitlement.carried_over_manual
    model = (await client.get(f"/employees/{anna.id}/work-time-model/history", headers=admin)).json()[0]
    assert model["valid_from"] == "2026-10-01" and model["weekly_minutes"] == 2400 and model["break_minutes"] == 30
    ben_model = (await client.get(f"/employees/{employees['101'].id}/work-time-model/history", headers=admin)).json()[0]
    assert ben_model["monthly_minutes"] == 6510

    # Nochmal übernehmen: Übertrag zum Stichtag existiert schon -> Zeile abgelehnt
    r = await _upload(client, admin, CSV, apply=False)
    messages = {e["row"]: e["message"] for e in r.json()["errors"]}
    assert "bereits übernommen" in messages[2] and "bereits übernommen" in messages[3]

    entries = (await client.get("/audit-log", headers=admin)).json()
    assert any(e["action"] == "EMPLOYEES_BULK_IMPORTED" and "Migration zum 2026-10-01" in e["detail"] for e in entries)


async def test_header_and_value_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    r = await _upload(client, admin, "name;saldo_stunden\nx;1\n", apply=False)
    assert r.json()["errors"][0]["message"] == "Spalte personalnummer fehlt."
    r = await _upload(client, admin, "personalnummer;gehalt\n100;1\n", apply=False)
    assert "Unbekannte Spalte(n): gehalt" in r.json()["errors"][0]["message"]
    rows = "\n".join(
        [
            "personalnummer;saldo_stunden;urlaubsanspruch_tage;wochenstunden;arbeitstage;pause_minuten",
            "100;viel;;;;",
            "101;;12,3;;;",
            "102;;;;;30",
            "100;;;70;Mo-Fr;",
        ]
    )
    messages = [e["message"] for e in (await _upload(client, admin, rows, apply=False)).json()["errors"]]
    assert messages[0] == "Ungültige Zahl 'viel' für saldo_stunden."
    assert messages[1] == "Urlaubstage nur in halben Tagen (z. B. 12,5)."
    assert messages[2] == "pause_minuten nur zusammen mit einem Arbeitszeitmodell."
    assert messages[3] == "wochenstunden muss zwischen 0,01 und 60 liegen."


async def test_locked_month_and_future_cutover(client: AsyncClient, db_session: AsyncSession) -> None:
    employees, admin = await _setup(db_session, client)
    db_session.add(
        PeriodClosure(
            tenant_id=1, employee_id=employees["100"].id, year=2026, month=10, status=PeriodStatus.CLOSED,
            target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 11, 1),
        )
    )
    await db_session.commit()
    r = await _upload(client, admin, "personalnummer;saldo_stunden\n100;5\n101;5\n", apply=True)
    body = r.json()
    assert [row["employee_number"] for row in body["rows"]] == ["101"]
    assert "abgeschlossen" in body["errors"][0]["message"] or "gesperrt" in body["errors"][0]["message"].lower()
    r = await _upload(client, admin, "personalnummer;saldo_stunden\n102;5\n", apply=False, cutover="2099-01-01")
    assert r.json()["errors"][0]["message"] == "Ein Überstunden-Übertrag ist nur bis heute möglich."


async def test_balance_start_before_cutover_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    """Rechnet das Konto schon vor dem Stichtag, würde der Übertrag doppelt zählen."""
    _, admin = await _setup(db_session, client)
    assert (await client.patch("/settings", headers=admin, json={"balance_start_date": "2026-09-01"})).status_code == 200
    r = await _upload(client, admin, "personalnummer;saldo_stunden;urlaubsanspruch_tage\n100;5;\n101;;30\n", apply=False)
    body = r.json()
    assert "rechnet schon ab 01.09.2026" in body["errors"][0]["message"]
    assert [row["employee_number"] for row in body["rows"]] == ["101"]  # ohne Saldo kein Problem
    assert (await client.patch("/settings", headers=admin, json={"balance_start_date": "2026-10-01"})).status_code == 200
    body = (await _upload(client, admin, "personalnummer;saldo_stunden\n100;5\n", apply=False)).json()
    assert body["errors"] == [] and body["rows"][0]["employee_number"] == "100"
