import enum
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.absence import AbsenceType
from app.models.employment import PayType


class EmployeeRef(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    employee_number: str


class AbsenceStatsMonth(BaseModel):
    month: int
    # Halbe Abwesenheitstage zählen 0,5
    vacation_days: float
    sick_days: float
    special_leave_days: float
    unpaid_days: float = 0
    time_off_days: float = 0
    child_sick_days: float = 0


class AbsenceStatsEmployee(EmployeeRef):
    # Halbe Abwesenheitstage zählen 0,5
    vacation_days: float
    sick_days: float
    special_leave_days: float
    unpaid_days: float = 0
    time_off_days: float = 0
    child_sick_days: float = 0


class AbsenceStatsResponse(BaseModel):
    year: int
    months: list[AbsenceStatsMonth]
    employees: list[AbsenceStatsEmployee]
    active_employee_count: int
    # Krankenquote = Krankheitstage / (aktive Mitarbeiter x Arbeitstage bis heute/Jahresende);
    # Näherung (Arbeitstage laut Arbeitszeitmodell, ohne Modell Mo–Fr, jeweils ohne Feiertage),
    # None ohne Mitarbeiter/Arbeitstage.
    sick_rate_percent: float | None


class VacationRow(EmployeeRef):
    entitled_days: float
    carried_over_days: float
    used_days: float
    expired_days: float = 0
    remaining_days: float


class OvertimeRow(EmployeeRef):
    balance_minutes: int
    as_of: date | None


class AttentionKind(str, enum.Enum):
    BEM = "BEM"
    PROBATION_ENDING = "PROBATION_ENDING"
    FIXED_TERM_ENDING = "FIXED_TERM_ENDING"
    TERMINATION = "TERMINATION"
    # Aufbewahrungsfrist eines Dokuments abgelaufen – prüfen, ggf. löschen (keine Automatik)
    RETENTION_DUE = "RETENTION_DUE"


class AttentionItem(EmployeeRef):
    kind: AttentionKind
    due_date: date | None
    detail: str


class LaborCostRow(EmployeeRef):
    pay_type: PayType | None
    rate: float | None
    actual_minutes: int
    base_cost: float | None
    surcharge_cost: float | None
    # Zulagen und Einmalzahlungen im Zeitraum (wie im Lohn-Export eines Admins)
    allowance_cost: float = 0.0
    total_cost: float | None
    note: str | None = None


class LaborCostResponse(BaseModel):
    date_from: date
    date_to: date
    rows: list[LaborCostRow]
    total_cost: float


# --- Abwesenheitsquote und Köpfe/FTE (app/services/workforce_stats_service.py) -------------------

MAX_RATE_MONTHS = 24
MAX_HEADCOUNT_MONTHS = 36
# Kategorien ohne Fehlzeit-Charakter: Arbeitszeit (z. B. Dienstreise) und Feiertag
RATE_EXCLUDED_CATEGORIES = frozenset({AbsenceType.WORK_TIME, AbsenceType.PUBLIC_HOLIDAY})


def _months_in(first: date, last: date) -> int:
    return (last.year - first.year) * 12 + last.month - first.month + 1


class _MonthRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date

    def _check(self, max_months: int) -> None:
        if self.date_to < self.date_from:
            raise ValueError("Das Ende darf nicht vor dem Beginn liegen.")
        if self.date_from.year < 2000 or self.date_to.year > 2100:
            raise ValueError("Der Zeitraum liegt außerhalb des erlaubten Bereichs.")
        if _months_in(self.date_from, self.date_to) > max_months:
            raise ValueError(f"Der Zeitraum darf höchstens {max_months} Monate umfassen.")


class AbsenceRateQuery(_MonthRange):
    # Standard: Krankheit und Kind krank
    categories: list[AbsenceType] = Field(default_factory=lambda: [AbsenceType.SICK, AbsenceType.CHILD_SICK], min_length=1, max_length=12)

    @model_validator(mode="after")
    def _validate(self) -> "AbsenceRateQuery":
        self._check(MAX_RATE_MONTHS)
        if RATE_EXCLUDED_CATEGORIES & set(self.categories):
            raise ValueError("Arbeitszeit und Feiertag sind keine Abwesenheiten im Sinne der Quote.")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Jede Kategorie nur einmal angeben.")
        return self


class HeadcountQuery(_MonthRange):
    @model_validator(mode="after")
    def _validate(self) -> "HeadcountQuery":
        self._check(MAX_HEADCOUNT_MONTHS)
        return self


class RateValue(BaseModel):
    absence_days: float
    workdays: int
    # None ohne Soll-Arbeitstage
    rate_percent: float | None


class AbsenceRateMonth(RateValue):
    month: str  # JJJJ-MM


class AbsenceRateDepartment(BaseModel):
    department_id: int | None
    name: str
    months: list[AbsenceRateMonth]
    total: RateValue


class AbsenceRateResponse(BaseModel):
    date_from: date
    date_to: date
    # gerechnet bis einschließlich (heute, wenn der Zeitraum in die Zukunft reicht); None = Zeitraum liegt in der Zukunft
    through: date | None
    categories: list[AbsenceType]
    months: list[AbsenceRateMonth]
    total: RateValue
    departments: list[AbsenceRateDepartment]


class HeadcountValue(BaseModel):
    headcount: int
    fte: float


class HeadcountDepartmentValue(HeadcountValue):
    department_id: int | None


class HeadcountMonthRow(HeadcountValue):
    month: str  # JJJJ-MM
    as_of: date
    joiners: int
    leavers: int
    departments: list[HeadcountDepartmentValue]


class HeadcountDepartment(BaseModel):
    department_id: int | None
    name: str


class HeadcountResponse(BaseModel):
    date_from: date
    date_to: date
    full_time_weekly_hours: float
    # False: keine Standard-Arbeitszeit in den Einstellungen, Vollzeit = 40 Stunden
    full_time_from_settings: bool
    months: list[HeadcountMonthRow]
    departments: list[HeadcountDepartment]
