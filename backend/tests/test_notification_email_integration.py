import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, HrRole, Account, Location
from app.services import email_service
from app.services.auth_service import hash_password


@pytest.fixture(autouse=True)
def _reset_smtp_settings():
    original = settings.smtp_host
    yield
    settings.smtp_host = original


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_absence_decision_sends_email_when_smtp_configured(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    settings.smtp_host = "smtp.example.com"
    sent_to: list[str] = []

    class _FakeServer:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, **kwargs):
            self.starttls_context = kwargs.get("context")

        def login(self, *args, **kwargs):
            pass

        def send_message(self, message):
            sent_to.append(message["To"])

    monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeServer)

    from datetime import date

    location = await _create_location(db_session)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "login_email": "erika@example.com",
        },
    )
    employee_id = create_response.json()["id"]

    db_session.add(
        Absence(
            employee_id=employee_id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 10),
            approval_status=AbsenceApprovalStatus.PENDING,
            created_by_account_id=hr_user.id,
        )
    )
    await db_session.commit()

    result = await db_session.execute(Absence.__table__.select())
    absence_id = result.first().id

    response = await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {token}"},
        json={"approve": True},
    )
    assert response.status_code == 200

    assert sent_to == ["erika@example.com"]


async def test_absence_decision_no_email_attempt_without_smtp_configured(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    settings.smtp_host = None
    called = False

    def _fake_smtp(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("smtplib darf ohne SMTP-Konfiguration nicht aufgerufen werden.")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _fake_smtp)

    from datetime import date

    location = await _create_location(db_session)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "login_email": "erika@example.com",
        },
    )
    employee_id = create_response.json()["id"]

    db_session.add(
        Absence(
            employee_id=employee_id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 10),
            approval_status=AbsenceApprovalStatus.PENDING,
            created_by_account_id=hr_user.id,
        )
    )
    await db_session.commit()

    result = await db_session.execute(Absence.__table__.select())
    absence_id = result.first().id

    response = await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {token}"},
        json={"approve": True},
    )
    assert response.status_code == 200
    assert called is False
