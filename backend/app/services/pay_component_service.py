"""Beträge von Zulagen und Einmalzahlungen für einen Abrechnungszeitraum (Lohn-/DATEV-Export).

- Zulage je Monat: voller Betrag für jeden Kalendermonat, in dem sie den ganzen Monat gilt;
  in Rumpfmonaten (Beginn/Ende im Monat oder Exportzeitraum kürzer als der Monat) anteilig nach
  Kalendertagen.
- Zulage je Stunde: Betrag × Ist-Stunden im gültigen Teil des Zeitraums (wie Spalte "Ist" im
  Lohn-Export).
- Einmalzahlung: voller Betrag, wenn ihr Datum im Zeitraum liegt.
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllowanceUnit, Employee, PayComponent, PayComponentKind, PayComponentType
from app.services.payroll_export_service import PayrollPeriod, payroll_period

_CENT = Decimal("0.01")


@dataclass
class PayComponentAmount:
    component: PayComponent
    amount: Decimal  # auf Cent gerundet
    hours: Decimal | None = None  # nur Zulage je Stunde: zugrunde gelegte Ist-Stunden

    @property
    def column(self) -> str:
        prefix = "Zulage" if self.component.kind == PayComponentKind.ALLOWANCE else "Einmalzahlung"
        return f"{prefix} {self.component.name}"


def _month_share(start: date, end: date) -> Decimal:
    """Anteil voller Monate von start bis end (inklusive), je Monat nach Kalendertagen."""
    share = Decimal(0)
    current = start
    while current <= end:
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        month_end = current.replace(day=days_in_month)
        last = min(end, month_end)
        share += Decimal((last - current).days + 1) / Decimal(days_in_month)
        current = month_end + timedelta(days=1)
    return share


async def pay_component_amounts(
    db: AsyncSession, employee: Employee, date_from: date, date_to: date, period: PayrollPeriod | None = None
) -> list[PayComponentAmount]:
    """period: bereits berechnete Tage des Zeitraums (Rechenkern) – sonst wird bei Bedarf gerechnet."""
    components = (
        await db.execute(
            select(PayComponent)
            .join(PayComponentType, PayComponentType.id == PayComponent.type_id)
            .where(PayComponent.employee_id == employee.id)
            .order_by(PayComponent.kind, PayComponentType.name, PayComponent.id)
        )
    ).scalars().all()
    result: list[PayComponentAmount] = []
    for component in components:
        amount = Decimal(str(component.amount))
        if component.kind == PayComponentKind.ONE_TIME:
            if component.pay_date is not None and date_from <= component.pay_date <= date_to:
                result.append(PayComponentAmount(component, amount.quantize(_CENT, ROUND_HALF_UP)))
            continue
        start = max(date_from, component.valid_from)
        end = min(date_to, component.valid_to or date_to)
        if start > end:
            continue
        if component.unit == AllowanceUnit.PER_HOUR:
            if period is None:
                period = await payroll_period(db, employee, date_from, date_to)
            minutes = period.summary(start, end).actual_minutes
            hours = Decimal(minutes) / Decimal(60)
            result.append(PayComponentAmount(component, (amount * hours).quantize(_CENT, ROUND_HALF_UP), hours))
        else:
            result.append(PayComponentAmount(component, (amount * _month_share(start, end)).quantize(_CENT, ROUND_HALF_UP)))
    return result
