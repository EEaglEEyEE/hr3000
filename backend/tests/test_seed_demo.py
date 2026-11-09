"""Demo-Firma der Testumgebung (app/tools/seed_demo.py): läuft durch, ist idempotent und setzt
überall die richtige Firma (in den Tests würde ein Hook fehlende tenant_id mit 1 füllen). Tom leitet den
Verkauf und ist dort Führungskraft."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department, Employee, HrRole, Location, Punch, Tenant
from app.services.org_service import load_org
from app.services.timesheet_service import calculate_day, employee_timezone
from app.tools.seed_demo import SUBDOMAIN, seed_demo


async def test_seed_demo_creates_consistent_tenant(db_session: AsyncSession) -> None:
    assert await seed_demo(db_session, "admin@example.com", "geheim-123", today=date(2026, 11, 5)) is True
    tenant_id = (await db_session.execute(select(Tenant.id).where(Tenant.subdomain == SUBDOMAIN))).scalar_one()
    assert tenant_id != 1
    for model in (Employee, Location, Department, Punch):
        wrong = (await db_session.execute(select(func.count()).select_from(model).where(model.tenant_id == 1))).scalar_one()
        assert wrong == 0, model.__name__
    assert (await db_session.execute(select(func.count()).select_from(Punch))).scalar_one() > 200
    erika = (await db_session.execute(select(Employee).where(Employee.employee_number == "1001"))).scalar_one()
    day = await calculate_day(db_session, erika, date(2026, 10, 6), await employee_timezone(db_session, erika))
    assert day.target_minutes == 480
    # Tom (Führungskraft) leitet den Verkauf: zuständig für alle anderen dort, nicht für das Lager
    departments = {d.name: d for d in (await db_session.execute(select(Department).where(Department.tenant_id == tenant_id))).scalars()}
    tom = (await db_session.execute(select(Employee).where(Employee.employee_number == "1002"))).scalar_one()
    assert tom.hr_role == HrRole.SUPERVISOR
    org = await load_org(db_session, tenant_id)
    fiona = (await db_session.execute(select(Employee).where(Employee.employee_number == "1007"))).scalar_one()
    assert org.heads(departments["Verkauf"].id) == [tom.id] and org.heads(departments["Lager"].id) == []
    assert org.deputies(departments["Verkauf"].id) == [(fiona.id, "STANDBY")]  # Fiona vertritt Tom
    sales_ids = set(
        (await db_session.execute(select(Employee.id).where(Employee.department_id == departments["Verkauf"].id))).scalars()
    )
    assert len(sales_ids) > 1 and org.reports(tom.id) == sales_ids - {tom.id}
    # zweiter Aufruf ändert nichts
    assert await seed_demo(db_session, "admin@example.com", "geheim-123", today=date(2026, 11, 5)) is False
