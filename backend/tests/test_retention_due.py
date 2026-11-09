"""Handlungsbedarf: Dokumente mit abgelaufener Aufbewahrungsfrist (nur Hinweis, keine Löschung)."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentCategory, EmployeeDocument
from tests.test_absence_types import _setup


def _doc(employee, title: str, retention: date, confidential: bool = False) -> EmployeeDocument:
    return EmployeeDocument(
        tenant_id=employee.tenant_id, employee_id=employee.id, category=DocumentCategory.OTHER, title=title,
        original_filename="x.pdf", content_type="application/pdf", size_bytes=1, sha256="0" * 64,
        storage_key=f"key-{title}", confidential=confidential, employee_visible=False, retention_until=retention,
    )


async def test_expired_retention_is_listed(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    today = date.today()
    db_session.add_all([
        _doc(employee, "Bewerbung 2019", today - timedelta(days=1)),
        _doc(employee, "Vertrag", today + timedelta(days=30)),
        _doc(employee, "Abmahnung", today - timedelta(days=2), confidential=True),
    ])
    await db_session.commit()

    items = [i for i in (await client.get("/reports/attention", headers=headers)).json() if i["kind"] == "RETENTION_DUE"]
    titles = sorted(i["detail"] for i in items)
    assert len(items) == 2  # Admin sieht auch das vertrauliche; die künftige Frist nicht
    assert any("„Bewerbung 2019“" in t for t in titles) and any("„Abmahnung“" in t for t in titles)
