from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Absence, AbsenceType, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, employee_number: str = "EMP-1", **fields) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number=employee_number,
        active=True,
        **fields,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_leave_entitlement_defaults_to_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "employee_id": employee.id,
        "year": 2026,
        "entitled_days": 0,
        "carried_over_days": 0,
        "used_days": 0,
        "remaining_days": 0,
        "carried_over_auto": False,
        "expired_days": 0,
        "expiring_days": 0,
        "expiry_date": None,
        # ohne Standard-Jahresurlaub (0) wird nichts berechnet – HR trägt den Anspruch ein
        "suggested_entitled_days": 0.0,
        "entitled_manual": False,
        "annual_vacation_days": 0.0,
        "workdays_per_week": None,
        "adjustment_days": 0,
    }


async def test_new_entitlement_uses_global_default_annual_vacation_days(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    # HR-Rolle darf /settings nicht ändern (siehe test_settings.py) – für
    # diesen Test direkt in der DB vorbelegen, kein zweiter Admin-User nötig.
    settings_row = await get_or_create_settings(db_session, employee.tenant_id)
    settings_row.default_annual_vacation_days = 30
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["entitled_days"] == 30


async def test_hr_can_set_entitlement_and_carry_over(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.patch(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
        json={"entitled_days": 28, "carried_over_days": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entitled_days"] == 28
    assert body["carried_over_days"] == 3
    assert body["remaining_days"] == 31


async def test_remaining_days_accounts_for_used_vacation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.patch(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
        json={"entitled_days": 28},
    )

    # Mo 10.8. - Fr 14.8.2026: 5 Werktage Urlaub (kein Sonntag dabei).
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 14),
            created_by_account_id=hr_user.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["used_days"] == 5
    assert body["remaining_days"] == 23


async def test_sick_leave_does_not_count_as_vacation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.SICK,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 12),
            created_by_account_id=hr_user.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.json()["used_days"] == 0


async def test_vacation_over_weekend_counts_only_weekdays_without_model(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    # Sa 8.8. - Mo 10.8.2026 ohne Arbeitszeitmodell: nur der Montag zählt (Mo–Fr, wie der Anspruch
    # auf Basis der 5-Tage-Woche; wer samstags arbeitet, bekommt ein Modell mit Samstag).
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 8),
            date_to=date(2026, 8, 10),
            created_by_account_id=hr_user.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.json()["used_days"] == 1


async def test_entitlement_from_contract_with_part_time_and_partial_year(client: AsyncClient, db_session: AsyncSession) -> None:
    """Jahresurlaub dauerhaft im Vertrag; das Jahr wird berechnet (Teilzeit, Eintritt/Austritt) und
    lässt sich je Jahr fest eintragen."""
    from datetime import date as _date

    from app.services.leave_service import round_vacation

    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    employee_id = employee.id
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}
    url = f"/employees/{employee_id}/leave-entitlement"
    r = await client.post(
        f"/employees/{employee_id}/contracts", headers=headers,
        json={"valid_from": "2020-01-01", "contract_type": "PERMANENT", "annual_vacation_days": 30},
    )
    assert r.status_code == 201, r.text
    full = (await client.get(url, headers=headers, params={"year": 2026})).json()
    assert (full["entitled_days"], full["entitled_manual"], full["annual_vacation_days"]) == (30, False, 30)

    # Teilzeit 3 Tage ab 01.07.: halbes Jahr 30, halbes Jahr 18 -> 24
    r = await client.put(
        f"/employees/{employee_id}/work-time-model", headers=headers,
        json={"weekly_hours": 24, "weekdays": [0, 1, 2], "valid_from": "2026-07-01"},
    )
    assert r.status_code == 200
    assert (await client.get(url, headers=headers, params={"year": 2026})).json()["entitled_days"] == 24

    # fest eintragen und zurück auf berechnet
    r = await client.patch(url, headers=headers, params={"year": 2026}, json={"entitled_days": 26})
    assert r.json()["entitled_days"] == 26 and r.json()["entitled_manual"] is True and r.json()["suggested_entitled_days"] == 24
    r = await client.patch(url, headers=headers, params={"year": 2026}, json={"entitled_auto": True})
    assert r.json()["entitled_days"] == 24 and r.json()["entitled_manual"] is False

    # Eintritt am 01.10.2027 (Wartezeit im Jahr nicht erfüllt): anteilig, aufgerundet
    other = await _create_employee(db_session, location, employee_number="EMP-2", hire_date=_date(2027, 10, 1))
    late = (await client.get(f"/employees/{other.id}/leave-entitlement", headers=headers, params={"year": 2027})).json()
    assert late["entitled_days"] == 0  # Standard der Firma ist 0 -> nichts berechnet
    assert round_vacation(7.4) == 7.5 and round_vacation(7.5) == 8 and round_vacation(7.0) == 7 and round_vacation(7.6) == 8


async def test_partial_year_keeps_statutory_minimum(db_session: AsyncSession) -> None:
    from datetime import date as _date

    from app.services.leave_service import computed_entitlement

    settings_row = await get_or_create_settings(db_session, 1)
    settings_row.default_annual_vacation_days = 30
    await db_session.commit()
    location = await _create_location(db_session)
    march = await _create_employee(db_session, location, employee_number="M1", hire_date=_date(2026, 3, 1))
    october = await _create_employee(db_session, location, employee_number="O1", hire_date=_date(2026, 10, 1))
    leaves_may = await _create_employee(db_session, location, employee_number="L1", termination_date=_date(2026, 5, 31))
    # Eintritt 01.03.: anteilig 30 x 306/365 = 25,15 -> 25,5 (Bruchteile nie abrunden)
    assert await computed_entitlement(db_session, march, 2026) == 25.5
    # Eintritt 01.06., Wartezeit im Jahr erfüllt: anteilig 17,6 -> gesetzlich mindestens 20
    june = await _create_employee(db_session, location, employee_number="J1", hire_date=_date(2026, 6, 1))
    assert await computed_entitlement(db_session, june, 2026) == 20
    # Eintritt 01.10.: anteilig 30 x 92/365 = 7,56 -> 8
    assert await computed_entitlement(db_session, october, 2026) == 8
    # Austritt 31.05. (erstes Halbjahr): anteilig 30 x 151/365 = 12,4 -> 12,5
    assert await computed_entitlement(db_session, leaves_may, 2026) == 12.5


async def test_waiting_period_decides_statutory_minimum(db_session: AsyncSession) -> None:
    from datetime import date as _date

    from app.services.leave_service import computed_entitlement, waiting_period_end

    assert waiting_period_end(_date(2026, 1, 1)) == _date(2026, 6, 30)
    assert waiting_period_end(_date(2026, 7, 1)) == _date(2026, 12, 31)
    assert waiting_period_end(_date(2026, 8, 31)) == _date(2027, 2, 28)  # § 188 Abs. 3 BGB

    settings_row = await get_or_create_settings(db_session, 1)
    settings_row.default_annual_vacation_days = 30
    await db_session.commit()
    location = await _create_location(db_session)
    # 01.04.–30.09.: Wartezeit erfüllt, Austritt im zweiten Halbjahr -> voller gesetzlicher Urlaub
    fulfilled = await _create_employee(
        db_session, location, employee_number="W1", hire_date=_date(2026, 4, 1), termination_date=_date(2026, 9, 30)
    )
    assert await computed_entitlement(db_session, fulfilled, 2026) == 20
    # 01.04.–31.08.: vor Ende der Wartezeit ausgeschieden -> nur anteilig 30 x 153/365 = 12,6 -> 13
    early = await _create_employee(
        db_session, location, employee_number="W2", hire_date=_date(2026, 4, 1), termination_date=_date(2026, 8, 31)
    )
    assert await computed_entitlement(db_session, early, 2026) == 13
    # Austritt im Folgejahr betrifft das laufende Jahr nicht
    later = await _create_employee(db_session, location, employee_number="W3", termination_date=_date(2027, 3, 31))
    assert await computed_entitlement(db_session, later, 2026) == 30
    assert await computed_entitlement(db_session, later, 2027) == 7.5  # 30 x 90/365 = 7,4 -> 7,5
    assert await computed_entitlement(db_session, later, 2028) == 0


async def test_without_partial_year_switch_the_whole_year_counts(client: AsyncClient, db_session: AsyncSession) -> None:
    """Bestehende Mandanten (Teilurlaub aus): voller Jahresurlaub auch bei Eintritt im Jahr, Teilzeit
    weiter anteilig – wie bisher."""
    from datetime import date as _date

    from app.services.leave_service import computed_entitlement

    settings_row = await get_or_create_settings(db_session, 1)
    settings_row.default_annual_vacation_days = 30
    settings_row.prorate_partial_year_vacation = False
    await db_session.commit()
    location = await _create_location(db_session)
    october = await _create_employee(db_session, location, employee_number="O2", hire_date=_date(2026, 10, 1))
    await _create_hr_user(db_session)
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}
    october_id = october.id
    assert await computed_entitlement(db_session, october, 2026) == 30
    r = await client.put(
        f"/employees/{october_id}/work-time-model", headers=headers,
        json={"weekly_hours": 24, "weekdays": [0, 1, 2], "valid_from": "2026-01-01"},
    )
    assert r.status_code == 200, r.text
    entitlement = (await client.get(f"/employees/{october_id}/leave-entitlement", headers=headers, params={"year": 2026})).json()
    assert entitlement["entitled_days"] == 18 and entitlement["entitled_manual"] is False


async def test_on_demand_gets_full_entitlement_without_part_time_rule(db_session: AsyncSession) -> None:
    """Aushilfe nach Aufwand: mit Teilzeit-Anteil kein berechneter Anspruch (HR trägt ein), ohne
    Teilzeit-Anteil wie bisher der volle Jahresurlaub."""
    from datetime import date as _date

    from app.models import EmployeeDefaultShift
    from app.services.leave_service import computed_entitlement

    settings_row = await get_or_create_settings(db_session, 1)
    settings_row.default_annual_vacation_days = 30
    await db_session.commit()
    location = await _create_location(db_session)
    helper = await _create_employee(db_session, location, employee_number="A1")
    db_session.add(EmployeeDefaultShift(employee_id=helper.id, valid_from=_date(2026, 1, 1), weekdays_mask=0b11111, on_demand=True))
    await db_session.commit()
    assert await computed_entitlement(db_session, helper, 2026) is None
    settings_row.prorate_part_time_vacation = False
    await db_session.commit()
    assert await computed_entitlement(db_session, helper, 2026) == 30
