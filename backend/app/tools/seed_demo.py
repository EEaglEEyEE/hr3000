"""Demo-Firma für die Testumgebung anlegen (nie auf Produktion).

Läuft nur mit DEMO_SEED_ALLOWED=1 (steht ausschließlich in der .env der Testumgebung, siehe
docker-compose.staging.yml / scripts/staging.sh). Legt – falls noch nicht vorhanden – die Firma
"demo" mit zwei Standorten, Teams, Mitarbeitern in allen Arbeitszeitmodell-Arten, Stempelungen der
letzten Wochen (inkl. offener Tage), Abwesenheiten, Vergütung und Zuschlagsregeln an. Ein
zufälliges Passwort gilt für alle Demo-Logins; es erscheint nur im Terminal des Aufrufers:

    docker compose -p hr3000-staging -f docker-compose.staging.yml exec backend python -m app.tools.seed_demo
"""
import asyncio
import os
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Compensation,
    Employee,
    HrRole,
    HrUser,
    Location,
    PayComponent,
    PayComponentKind,
    PayComponentType,
    AllowanceUnit,
    PayType,
    Punch,
    PunchSource,
    PunchType,
    ShiftTemplate,
    SupervisorTeamAssignment,
    Team,
    Tenant,
    TenantPlan,
)
from app.services.auth_service import hash_password

SUBDOMAIN = "demo"
TZ = ZoneInfo("Europe/Berlin")


def _utc(day: date, clock: str) -> datetime:
    hour, minute = map(int, clock.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=TZ).astimezone(UTC).replace(tzinfo=None)


def _punch(employee: Employee, kind: PunchType, day: date, clock: str) -> Punch:
    return Punch(
        tenant_id=employee.tenant_id,
        employee_id=employee.id,
        location_id=employee.location_id,
        punch_type=kind,
        timestamp_utc=_utc(day, clock),
        source=PunchSource.KIOSK,
        idempotency_key=str(uuid.uuid4()),
    )


async def seed_demo(db: AsyncSession, admin_email: str, password: str, today: date | None = None) -> bool:
    """Legt die Demo-Firma an; False, wenn es sie schon gibt (dann wird nichts geändert)."""
    from app.api.deps import Actor
    from app.api.surcharges import create_default_surcharge_rules
    from app.api.work_time_model import set_work_time_model
    from app.schemas.work_time_model import WorkTimeModelSetRequest
    from app.services.settings_service import get_or_create_settings
    from app.services.tenant_provisioning import provision_tenant

    if (await db.execute(select(Tenant.id).where(Tenant.subdomain == SUBDOMAIN))).first() is not None:
        return False
    today = today or date.today()
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=14)  # ca. 6–10 Wochen

    tenant = await provision_tenant(
        db, subdomain=SUBDOMAIN, name="Demo GmbH", admin_email=admin_email, admin_password=password, plan=TenantPlan.UNLIMITED
    )
    admin = (await db.execute(select(HrUser).where(HrUser.tenant_id == tenant.id))).scalar_one()
    actor = Actor(hr_user=admin)
    settings_row = await get_or_create_settings(db, tenant.id, commit=False)
    settings_row.default_bundesland = "BW"
    settings_row.default_annual_vacation_days = 30
    settings_row.balance_start_date = start
    settings_row.kiosk_break_buttons = True

    stuttgart = Location(tenant_id=tenant.id, name="Stuttgart", timezone="Europe/Berlin", bundesland="BW")
    berlin = Location(tenant_id=tenant.id, name="Berlin", timezone="Europe/Berlin", bundesland="BE")
    sales, store = Team(tenant_id=tenant.id, name="Verkauf"), Team(tenant_id=tenant.id, name="Lager")
    db.add_all([stuttgart, berlin, sales, store])
    await db.flush()

    def person(first: str, last: str, number: str, location: Location, team: Team, **extra) -> Employee:
        return Employee(
            tenant_id=tenant.id, location_id=location.id, team_id=team.id, first_name=first, last_name=last,
            employee_number=number, hire_date=start - timedelta(days=365), **extra,
        )

    erika = person("Erika", "Muster", "1001", stuttgart, sales, login_email="erika@demo.invalid", password_hash=hash_password(password))
    tom = person("Tom", "Teamleiter", "1002", stuttgart, sales, login_email="tom@demo.invalid", password_hash=hash_password(password), hr_role=HrRole.SUPERVISOR)
    hanna = person("Hanna", "Personal", "1003", stuttgart, sales, login_email="hanna@demo.invalid", password_hash=hash_password(password), hr_role=HrRole.HR)
    max_ = person("Max", "Beispiel", "1004", stuttgart, store)
    lena = person("Lena", "Teilzeit", "1005", berlin, store)
    ali = person("Ali", "Aushilfe", "1006", berlin, store)
    fiona = person("Fiona", "Flexibel", "1007", berlin, sales)
    people = [erika, tom, hanna, max_, lena, ali, fiona]
    db.add_all(people)
    await db.flush()
    db.add(SupervisorTeamAssignment(team_id=sales.id, employee_id=tom.id))
    await db.commit()

    # Schichtvorlage liefert im Arbeitszeitmodell nur die Uhrzeiten (Soll bleibt das des Modells).
    early = ShiftTemplate(tenant_id=tenant.id, name="Frühdienst", start_time=time(7, 30), end_time=time(16, 15), target_minutes=480)
    db.add(early)
    await db.flush()
    models = {
        erika: {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]},
        tom: {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "break_minutes": 45, "shift_template_id": early.id},
        hanna: {"weekly_hours": 38.5, "weekdays": [0, 1, 2, 3, 4], "core_time_mode": "CUSTOM", "core_time_start": "09:00", "core_time_end": "15:00"},
        max_: {"daily_hours": [8, 8, 4, 0, 0, 0, 0]},
        lena: {"monthly_hours": 108.5, "weekdays": [0, 1, 2, 3, 4], "break_start": "12:00", "break_end": "12:30"},
        ali: {"on_demand": True, "monthly_cap_hours": 43},
        fiona: {"weekly_hours": 20, "flexible": True},
    }
    for employee, model in models.items():
        await set_work_time_model(employee.id, WorkTimeModelSetRequest(**model, valid_from=start), actor, db)

    # Stempelungen bis gestern; ein paar Lücken, damit "Zu klären" etwas zeigt.
    punches: list[Punch] = []
    day = start
    index = 0
    while day < today:
        weekday = day.weekday()
        if weekday < 5:
            index += 1
            if not (date(day.year, 1, 1) <= day and index % 23 == 0):  # gelegentlich ganz vergessen
                punches += [_punch(erika, PunchType.COME, day, "08:02"), _punch(erika, PunchType.BREAK_START, day, "12:00"),
                            _punch(erika, PunchType.BREAK_END, day, "12:30")]
                if index % 17 != 0:  # gelegentlich "Gehen" vergessen
                    punches.append(_punch(erika, PunchType.GO, day, "16:41"))
            punches += [_punch(tom, PunchType.COME, day, "07:31"), _punch(tom, PunchType.GO, day, "16:35")]
            punches += [_punch(hanna, PunchType.COME, day, "08:15" if index % 9 else "09:40"), _punch(hanna, PunchType.GO, day, "16:20")]
            if weekday in (0, 1):
                punches += [_punch(max_, PunchType.COME, day, "07:00"), _punch(max_, PunchType.GO, day, "15:35")]
            elif weekday == 2:
                punches += [_punch(max_, PunchType.COME, day, "07:00"), _punch(max_, PunchType.GO, day, "11:00")]
            punches += [_punch(lena, PunchType.COME, day, "08:30"), _punch(lena, PunchType.GO, day, "14:00")]
            if weekday in (1, 3):
                punches += [_punch(ali, PunchType.COME, day, "17:00"), _punch(ali, PunchType.GO, day, "22:30")]
            if weekday in (0, 2, 4):
                punches += [_punch(fiona, PunchType.COME, day, "09:00"), _punch(fiona, PunchType.GO, day, "16:00")]
        day += timedelta(days=1)
    db.add_all(punches)

    vacation_start = start + timedelta(days=21)
    db.add_all(
        [
            Absence(employee_id=hanna.id, type=AbsenceType.VACATION, date_from=vacation_start, date_to=vacation_start + timedelta(days=4),
                    approval_status=AbsenceApprovalStatus.APPROVED),
            Absence(employee_id=max_.id, type=AbsenceType.SICK, date_from=start + timedelta(days=10), date_to=start + timedelta(days=11),
                    approval_status=AbsenceApprovalStatus.APPROVED),
            Absence(employee_id=erika.id, type=AbsenceType.VACATION, date_from=today + timedelta(days=14), date_to=today + timedelta(days=18),
                    approval_status=AbsenceApprovalStatus.PENDING, note="Familienbesuch"),
            Compensation(tenant_id=tenant.id, employee_id=erika.id, valid_from=start, pay_type=PayType.MONTHLY, amount=3600, currency="EUR"),
            Compensation(tenant_id=tenant.id, employee_id=ali.id, valid_from=start, pay_type=PayType.HOURLY, amount=14.5, currency="EUR"),
            PayComponent(
                tenant_id=tenant.id, employee_id=erika.id, kind=PayComponentKind.ALLOWANCE, amount=50, unit=AllowanceUnit.PER_MONTH,
                valid_from=start,
                type=PayComponentType(tenant_id=tenant.id, kind=PayComponentKind.ALLOWANCE, name="Fahrtkostenzuschuss", wage_type="2000"),
            ),
        ]
    )
    await db.commit()
    await create_default_surcharge_rules(actor, db)
    return True


async def _main() -> int:
    from app.config import settings
    from app.db import AsyncSessionLocal

    if os.environ.get("DEMO_SEED_ALLOWED") != "1":
        print("Nur für die Testumgebung: DEMO_SEED_ALLOWED=1 fehlt.")
        return 1
    admin_email = os.environ.get("DEMO_ADMIN_EMAIL", "admin@demo.invalid")
    password = secrets.token_urlsafe(12)
    async with AsyncSessionLocal() as db:
        created = await seed_demo(db, admin_email, password)
    if not created:
        print("Demo-Firma ist schon vorhanden – nichts geändert (zurücksetzen: scripts/staging.sh reset).")
        return 0
    base = settings.tenant_base_domain or "localhost"
    print(
        "\nDemo-Firma angelegt (Passwort wird nicht erneut angezeigt):\n"
        f"  HR-Webapp: https://{SUBDOMAIN}.{base}\n"
        f"  Tablet:    https://kiosk.{SUBDOMAIN}.{base}\n"
        f"  Admin:     {admin_email}\n"
        "  HR:        hanna@demo.invalid · Teamleiter: tom@demo.invalid · Mitarbeiterin: erika@demo.invalid\n"
        f"  Passwort (für alle): {password}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
