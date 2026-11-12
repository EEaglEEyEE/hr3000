"""Vorbereitende Lohnbuchhaltung: alles, was das Lohnbüro für einen Monat braucht, an einer Stelle.

Je Mitarbeiter, der im Monat beschäftigt war: Eintritt/Austritt, Änderungen im Monat (Verträge,
Vergütung, Zulagen, Standort, eigene Felder mit Wirksamkeitsdatum, persönliche Daten, Kostenstellen,
Arbeitszeitmodell), Gehalt und Gehaltsbestandteile, Abwesenheiten (Tage je Art), Stunden, Auszahlungen
und Zuschläge wie im Lohn-Export (derselbe Rechenkern payroll_period) und der Stand des
Monatsabschlusses.

Ergebnis ist ein JSON-fähiges dict: Es wird live angezeigt und bei der Freigabe als Schnappschuss
eingefroren (app/models/payroll_release.py). compare() vergleicht Schnappschuss und aktuellen Stand je
Mitarbeiter („seit der Freigabe geändert“).
"""
import calendar
import json
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (
    AbsenceType,
    AllowanceUnit,
    AttributeDefinition,
    AttributeValue,
    AuditAction,
    AuditLogEntry,
    Compensation,
    ContractType,
    Employee,
    EmployeeLocationPeriod,
    EmploymentContract,
    Location,
    PayComponent,
    PayComponentKind,
    PayType,
    PeriodClosure,
    PeriodStatus,
)
from app.services.absence_type_service import CATEGORY_LABELS
from app.services.pay_component_service import pay_component_amounts
from app.services.payroll_export_service import PayrollSummary, payroll_period
from app.services.surcharge_service import active_rules, compute_surcharges, merge_by_family
from app.services.timesheet_service import has_settled_limit, settled_between

# Höchstzahl Mitarbeiter je Monat (wie beim Lohn-Export) – Missbrauchsbremse für die Rechenzeit
MAX_EMPLOYEES = 200

CONTRACT_LABELS = {
    ContractType.PERMANENT: "unbefristet",
    ContractType.FIXED_TERM: "befristet",
    ContractType.APPRENTICESHIP: "Ausbildung",
    ContractType.MINI_JOB: "Minijob",
    ContractType.WORKING_STUDENT: "Werkstudent",
    ContractType.INTERNSHIP: "Praktikum",
    ContractType.FREELANCE: "freie Mitarbeit",
}

# Änderungen aus dem Audit-Protokoll (ohne Wirksamkeitsdatum; Zeitpunkt der Änderung zählt)
_AUDIT_CHANGES = {
    AuditAction.PERSONAL_DATA_CHANGED: "Persönliche Daten",
    AuditAction.COST_CENTERS_CHANGED: "Kostenstellen",
    AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET: "Arbeitszeitmodell",
}

CLOSURE_LABELS = {"CLOSED": "abgeschlossen", "SUBMITTED": "vorgelegt", "DISPUTED": "beanstandet", "OPEN": "offen"}


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def parse_month(value: str) -> tuple[int, int]:
    """"2026-10" → (2026, 10); die Form prüft das Schema (Pattern) vorher."""
    year, month = value.split("-")
    return int(year), int(month)


def _euro(value: Decimal | float) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"


def _euro_de(value: Decimal | float) -> str:
    """Betrag für Texte der Oberfläche: 3.500,00"""
    return f"{Decimal(str(value)).quantize(Decimal('0.01')):,}".replace(",", "X").replace(".", ",").replace("X", ".")


def _in(day: date | None, first: date, last: date) -> bool:
    return day is not None and first <= day <= last


async def employees_of_month(db: AsyncSession, tenant_id: int, year: int, month: int) -> list[Employee]:
    """Wer im Monat beschäftigt war: Eintritt spätestens am Monatsende, Austritt frühestens am
    Monatsanfang. Ohne Austrittsdatum nur aktive (deaktivierte ohne Datum sind nicht abzurechnen);
    anonymisierte nie."""
    first, last = month_bounds(year, month)
    rows = (
        await db.execute(
            select(Employee)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.anonymized_at.is_(None),
                (Employee.hire_date.is_(None)) | (Employee.hire_date <= last),
                (Employee.termination_date.is_(None)) | (Employee.termination_date >= first),
            )
            .order_by(Employee.last_name, Employee.first_name, Employee.id)
        )
    ).scalars().all()
    return [e for e in rows if e.active or e.termination_date is not None]


async def _changes(db: AsyncSession, employee: Employee, first: date, last: date, include_pay: bool) -> list[dict]:
    changes: list[dict] = []
    if _in(employee.hire_date, first, last):
        changes.append({"date": employee.hire_date.isoformat(), "kind": "ENTRY", "text": "Eintritt"})
    if _in(employee.termination_date, first, last):
        changes.append({"date": employee.termination_date.isoformat(), "kind": "EXIT", "text": "Austritt"})

    contracts = (
        await db.execute(select(EmploymentContract).where(EmploymentContract.employee_id == employee.id))
    ).scalars().all()
    for contract in contracts:
        if _in(contract.valid_from, first, last):
            label = CONTRACT_LABELS.get(contract.contract_type, contract.contract_type.value)
            title = f", {contract.job_title}" if contract.job_title else ""
            changes.append({"date": contract.valid_from.isoformat(), "kind": "CONTRACT", "text": f"Vertrag ab: {label}{title}"})
        if _in(contract.valid_to, first, last):
            changes.append({"date": contract.valid_to.isoformat(), "kind": "CONTRACT", "text": "Vertrag endet"})

    if include_pay:
        compensations = (
            await db.execute(select(Compensation).where(Compensation.employee_id == employee.id))
        ).scalars().all()
        for compensation in compensations:
            if _in(compensation.valid_from, first, last):
                unit = "je Stunde" if compensation.pay_type == PayType.HOURLY else "je Monat"
                changes.append(
                    {
                        "date": compensation.valid_from.isoformat(),
                        "kind": "COMPENSATION",
                        "text": f"Vergütung ab: {_euro_de(compensation.amount)} {'€' if compensation.currency == 'EUR' else compensation.currency} {unit}",
                    }
                )
        components = (
            await db.execute(
                select(PayComponent).where(
                    PayComponent.employee_id == employee.id, PayComponent.kind == PayComponentKind.ALLOWANCE
                )
            )
        ).scalars().all()
        for component in components:
            unit = "je Stunde" if component.unit == AllowanceUnit.PER_HOUR else "je Monat"
            if _in(component.valid_from, first, last):
                changes.append(
                    {
                        "date": component.valid_from.isoformat(),
                        "kind": "PAY_COMPONENT",
                        "text": f"Zulage {component.name} ab: {_euro_de(component.amount)} € {unit}",
                    }
                )
            if _in(component.valid_to, first, last):
                changes.append(
                    {"date": component.valid_to.isoformat(), "kind": "PAY_COMPONENT", "text": f"Zulage {component.name} endet"}
                )

    locations = (
        await db.execute(
            select(EmployeeLocationPeriod, Location.name)
            .join(Location, Location.id == EmployeeLocationPeriod.location_id)
            .where(EmployeeLocationPeriod.employee_id == employee.id)
        )
    ).all()
    for period, name in locations:
        if _in(period.valid_from, first, last):
            changes.append({"date": period.valid_from.isoformat(), "kind": "LOCATION", "text": f"Standort ab: {name}"})

    values = (
        await db.execute(
            select(AttributeValue, AttributeDefinition.label)
            .join(AttributeDefinition, AttributeDefinition.id == AttributeValue.attribute_id)
            .where(AttributeValue.employee_id == employee.id, AttributeValue.valid_from.is_not(None))
        )
    ).all()
    for value, label in values:
        if _in(value.valid_from, first, last):
            changes.append(
                {"date": value.valid_from.isoformat(), "kind": "ATTRIBUTE", "text": f"{label} ab: {value.value or '–'}"}
            )

    entries = (
        await db.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.tenant_id == employee.tenant_id,
                AuditLogEntry.entity_type == "employee",
                AuditLogEntry.entity_id == employee.id,
                AuditLogEntry.action.in_(list(_AUDIT_CHANGES)),
                AuditLogEntry.created_at >= datetime.combine(first, time.min),
                AuditLogEntry.created_at <= datetime.combine(last, time.max),
            )
        )
    ).scalars().all()
    for entry in entries:
        text = _AUDIT_CHANGES[entry.action] + " geändert"
        # Detail ohne Namensvorsatz („Erika Muster: IBAN, …“) – Werte stehen dort nie
        detail = (entry.detail or "").split(": ", 1)[-1]
        changes.append(
            {"date": entry.created_at.date().isoformat(), "kind": "MASTER_DATA", "text": f"{text}: {detail}" if detail else text}
        )
    return sorted(changes, key=lambda change: (change["date"], change["kind"], change["text"]))


async def build_month(db: AsyncSession, tenant_id: int, year: int, month: int, include_pay: bool) -> dict:
    """Aktueller Stand des Monats (JSON-fähig). include_pay: Gehalt, Zulagen und Vergütungsänderungen
    (nur mit Berechtigung „Vergütung & Lohn“)."""
    first, last = month_bounds(year, month)
    employees = await employees_of_month(db, tenant_id, year, month)
    if len(employees) > MAX_EMPLOYEES:
        raise AppError(400, "TOO_MANY_EMPLOYEES", f"Mehr als {MAX_EMPLOYEES} Mitarbeiter im Monat – bitte den Lohn-Export nutzen.")
    rules = await active_rules(db, tenant_id)
    families: dict[int, str] = {}
    for rule in sorted(rules, key=lambda r: (r.family, r.valid_from or date.min)):
        families[rule.family] = rule.name
    statuses = {
        employee_id: status
        for employee_id, status in (
            await db.execute(
                select(PeriodClosure.employee_id, PeriodClosure.status).where(
                    PeriodClosure.tenant_id == tenant_id,
                    PeriodClosure.year == year,
                    PeriodClosure.month == month,
                )
            )
        ).all()
    }

    rows = []
    for employee in employees:
        period = await payroll_period(db, employee, first, last)
        summary = period.summary()
        absences = [
            {"type": category.value, "label": CATEGORY_LABELS[category], "days": days}
            for category, days in _absence_days(summary).items()
            if days
        ]
        by_family = {
            rule.family: minutes
            for rule, minutes in merge_by_family(await compute_surcharges(db, employee, first, last, rules))
        }
        status = statuses.get(employee.id)
        row = {
            "employee_id": employee.id,
            "employee_number": employee.employee_number,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
            "termination_date": employee.termination_date.isoformat() if employee.termination_date else None,
            "entry": _in(employee.hire_date, first, last),
            "exit": _in(employee.termination_date, first, last),
            "closure": status.value if status is not None else "OPEN",
            "hours": {
                "target_minutes": summary.target_minutes,
                "actual_minutes": summary.actual_minutes,
                "balance_minutes": summary.actual_minutes - summary.target_minutes,
                "payout_minutes": summary.payout_minutes,
                "open_days": summary.open_or_error_days,
                "holiday_days": summary.holiday_days,
                # Mit dem Gehalt abgegoltene Überstunden des Monats (0 = keine Grenze im Modell)
                "settled_minutes": (
                    await settled_between(db, employee, first, last)
                    if await has_settled_limit(db, employee, first, last)
                    else 0
                ),
            },
            "surcharges": [
                {"name": name, "minutes": by_family.get(family, 0)} for family, name in families.items() if by_family.get(family)
            ],
            "absences": absences,
            "changes": await _changes(db, employee, first, last, include_pay),
        }
        if include_pay:
            compensation = (
                await db.execute(
                    select(Compensation)
                    .where(
                        Compensation.employee_id == employee.id,
                        Compensation.valid_from <= last,
                        (Compensation.valid_to.is_(None)) | (Compensation.valid_to >= first),
                    )
                    .order_by(Compensation.valid_from.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            row["compensation"] = (
                {
                    "pay_type": compensation.pay_type.value,
                    "amount": _euro(compensation.amount),
                    "currency": compensation.currency,
                    "valid_from": compensation.valid_from.isoformat(),
                }
                if compensation is not None
                else None
            )
            amounts: dict[str, Decimal] = {}
            for amount in await pay_component_amounts(db, employee, first, last, period):
                amounts[amount.column] = amounts.get(amount.column, Decimal(0)) + amount.amount
            row["pay_components"] = [{"name": name, "amount": _euro(value)} for name, value in sorted(amounts.items())]
        rows.append(row)

    open_closures = sum(1 for row in rows if row["closure"] != PeriodStatus.CLOSED.value)
    return {
        "month": f"{year:04d}-{month:02d}",
        "includes_pay": include_pay,
        "employees": rows,
        "summary": {
            "employee_count": len(rows),
            "entries": sum(1 for row in rows if row["entry"]),
            "exits": sum(1 for row in rows if row["exit"]),
            "open_closures": open_closures,
        },
    }


def _absence_days(summary: PayrollSummary) -> dict[AbsenceType, float]:
    """Tage je Art aus der Lohnperiode, in der Reihenfolge der Oberfläche."""
    days = {
        AbsenceType.VACATION: summary.vacation_days,
        AbsenceType.SICK: summary.sick_days,
        AbsenceType.CHILD_SICK: summary.child_sick_days,
        AbsenceType.SPECIAL_LEAVE: summary.special_leave_days,
        AbsenceType.UNPAID: summary.unpaid_days,
        AbsenceType.TIME_OFF_IN_LIEU: summary.time_off_days,
    }
    days.update(summary.separate_unpaid_days)
    return days


def changed_employees(snapshot: dict, current: dict) -> list[int]:
    """Mitarbeiter, deren Zeile sich seit der Freigabe geändert hat (auch neu hinzugekommene oder
    weggefallene)."""
    before = {row["employee_id"]: json.dumps(row, sort_keys=True) for row in snapshot.get("employees", [])}
    after = {row["employee_id"]: json.dumps(row, sort_keys=True) for row in current.get("employees", [])}
    return sorted(employee_id for employee_id in before.keys() | after.keys() if before.get(employee_id) != after.get(employee_id))
