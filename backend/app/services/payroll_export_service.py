"""Rechenkern für Lohn-Export (CSV), DATEV-Export und Lohnkosten: je Mitarbeiter einmal über den
Zeitraum rechnen (dieselbe Tagesauflösung calculate_day wie Kalender/Monatsbericht) und daraus
alle Summen ableiten – auch für Teilzeiträume (Stundenlohn-Abschnitte, Gültigkeit von Zulagen),
ohne die Tage erneut zu berechnen."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SEPARATE_UNPAID_CATEGORIES, AbsenceType, AdjustmentKind, BalanceAdjustment, Employee, SummaryStatus
from app.services.timesheet_service import (
    absence_day_counts,
    calculate_day,
    day_fingerprint,
    day_reviews,
    employee_timezone,
    missing_punch_reported,
    needs_review,
    pair_punches_detail,
    reports_days_without_punches,
    review_valid,
    today_in,
)


@dataclass
class PayrollDay:
    day: date
    target: int  # Tagessoll (ohne Wochenanteil flexibler Modelle)
    flexible_share: float  # flexibles Modell: Anteil des Wochensolls an diesem Kalendertag
    actual: int  # Ist inkl. Gutschriften
    worked: int  # tatsächlich gearbeitete (gestempelte) Zeit
    credits: dict[AbsenceType, int]  # Gutschrift je Zeitart (Feiertag = PUBLIC_HOLIDAY)
    absence_days: dict[AbsenceType, float]  # halbe Tage = 0,5
    holiday: bool
    open: bool  # "Tag offen" wie unter "Zu klären" (inkl. "Erledigt") – vor dem Lohnlauf klären


@dataclass
class PayrollSummary:
    """Aggregat über einen Zeitraum für einen Mitarbeiter. open_or_error_days ist bewusst ein
    eigenes Feld: HR muss diese Tage vor dem Lohnlauf klären."""

    employee: Employee
    target_minutes: int
    actual_minutes: int
    # Halbe Abwesenheitstage zählen 0,5
    vacation_days: float
    sick_days: float
    special_leave_days: float
    unpaid_days: float
    time_off_days: float
    child_sick_days: float
    # Mutterschutz/Elternzeit, Kurzarbeit, Unentschuldigt, Pflege – je Kategorie (Soll entfällt)
    separate_unpaid_days: dict[AbsenceType, float]
    # Feiertage laut Kalender + Abwesenheiten der Kategorie "Feiertag" (z.B. Feiertag GfB)
    holiday_days: float
    open_or_error_days: int
    # Tatsächlich gearbeitete (gestempelte) Zeit – Ist ohne Gutschriften (actual_minutes enthält beides).
    worked_minutes: int = 0
    # Gutschriften je Zeitart in Minuten (Urlaub, Krankheit, Feiertag, Arbeitszeit-Angaben, …)
    credit_minutes: dict[AbsenceType, int] = field(default_factory=dict)
    # Ausgezahlte Überstunden (Korrekturbuchung "Auszahlung") im Zeitraum, positiv
    payout_minutes: int = 0
    # Auszahlungen × Faktor (z. B. 10 Std. mit 1,5 = 15 Std.) und ob ein Faktor ≠ 1 vorkam
    weighted_payout_minutes: int = 0
    payout_has_factor: bool = False


@dataclass
class PayrollPeriod:
    """Alle Tage eines Mitarbeiters im Zeitraum (nur bis heute) plus Auszahlungen."""

    employee: Employee
    first: date
    last: date
    days: list[PayrollDay]
    payouts: list[tuple[date, int]]
    # Auszahlungen mit Faktor (Tag, Minuten, Faktor) – für die gewichtete Spalte im Lohn-Export
    payout_factors: list[tuple[date, int, float]] = field(default_factory=list)

    def summary(self, start: date | None = None, end: date | None = None) -> PayrollSummary:
        start, end = start or self.first, end or self.last
        days = [d for d in self.days if start <= d.day <= end]
        counts: dict[AbsenceType, float] = {category: 0.0 for category in AbsenceType}
        credits: dict[AbsenceType, int] = {}
        for d in days:
            for category, value in d.absence_days.items():
                counts[category] += value
            for category, minutes in d.credits.items():
                credits[category] = credits.get(category, 0) + minutes
        return PayrollSummary(
            employee=self.employee,
            # Flexibles Modell: Wochensoll anteilig je Kalendertag (wie im Monatsbericht).
            target_minutes=sum(d.target for d in days) + round(sum(d.flexible_share for d in days)),
            actual_minutes=sum(d.actual for d in days),
            vacation_days=counts[AbsenceType.VACATION],
            sick_days=counts[AbsenceType.SICK],
            special_leave_days=counts[AbsenceType.SPECIAL_LEAVE],
            unpaid_days=counts[AbsenceType.UNPAID],
            time_off_days=counts[AbsenceType.TIME_OFF_IN_LIEU],
            child_sick_days=counts[AbsenceType.CHILD_SICK],
            separate_unpaid_days={category: counts[category] for category in SEPARATE_UNPAID_CATEGORIES},
            holiday_days=sum(1 for d in days if d.holiday) + counts[AbsenceType.PUBLIC_HOLIDAY],
            open_or_error_days=sum(1 for d in days if d.open),
            worked_minutes=sum(d.worked for d in days),
            credit_minutes=credits,
            payout_minutes=sum(minutes for day, minutes in self.payouts if start <= day <= end),
            weighted_payout_minutes=round(sum(m * f for day, m, f in self.payout_factors if start <= day <= end)),
            payout_has_factor=any(f != 1 for day, m, f in self.payout_factors if start <= day <= end),
        )


async def payroll_period(db: AsyncSession, employee: Employee, date_from: date, date_to: date) -> PayrollPeriod:
    """Einmal je Tag rechnen. Künftige Tage haben noch kein Ist und belasten das Soll nicht – der
    Zeitraum endet daher spätestens heute (Auszahlungen zählen im ganzen Zeitraum)."""
    tz = await employee_timezone(db, employee)
    report_no_punch_days = await reports_days_without_punches(db, employee.tenant_id)
    today = today_in(tz)
    last = min(date_to, today)
    reviews = await day_reviews(db, [employee.id], date_from, last)
    days: list[PayrollDay] = []
    current = date_from
    while current <= last:
        calculation = await calculate_day(db, employee, current, tz)
        worked = 0
        if calculation.has_punches:
            worked = (await pair_punches_detail(db, employee, current, tz))[0] or 0
        holiday = calculation.status == SummaryStatus.HOLIDAY
        days.append(
            PayrollDay(
                day=current,
                target=calculation.target_minutes or 0,
                flexible_share=calculation.flexible_share,
                actual=calculation.actual_minutes or 0,
                worked=worked,
                credits=dict(calculation.credit_parts) if calculation.actual_minutes is not None else {},
                absence_days=absence_day_counts(calculation),
                holiday=holiday,
                open=needs_review(
                    calculation.status, calculation.flags, current, today,
                    missing_reported=missing_punch_reported(calculation, report_no_punch_days),
                    exempt=calculation.review_exempt,
                )
                and not review_valid(
                    reviews, employee.id, current,
                    day_fingerprint(calculation.status, calculation.target_minutes, calculation.actual_minutes, calculation.flags),
                ),
            )
        )
        current += timedelta(days=1)
    payouts = (
        await db.execute(
            select(BalanceAdjustment.effective_date, BalanceAdjustment.minutes, BalanceAdjustment.payout_factor).where(
                BalanceAdjustment.employee_id == employee.id,
                BalanceAdjustment.kind == AdjustmentKind.PAYOUT,
                BalanceAdjustment.effective_date >= date_from,
                BalanceAdjustment.effective_date <= date_to,
            )
        )
    ).all()
    return PayrollPeriod(
        employee, date_from, date_to, days,
        [(day, -minutes) for day, minutes, _ in payouts],
        [(day, -minutes, float(factor or 1)) for day, minutes, factor in payouts],
    )


async def summarize_payroll(db: AsyncSession, employee: Employee, date_from: date, date_to: date) -> PayrollSummary:
    return (await payroll_period(db, employee, date_from, date_to)).summary()
