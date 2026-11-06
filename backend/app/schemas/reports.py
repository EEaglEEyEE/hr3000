import enum
from datetime import date

from pydantic import BaseModel

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
