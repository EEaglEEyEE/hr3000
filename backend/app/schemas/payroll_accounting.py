from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

ClosureState = Literal["CLOSED", "SUBMITTED", "DISPUTED", "OPEN"]


class AccountingChange(BaseModel):
    date: date
    # ENTRY, EXIT, CONTRACT, COMPENSATION, PAY_COMPONENT, LOCATION, ATTRIBUTE, MASTER_DATA
    kind: str
    text: str


class AccountingAbsence(BaseModel):
    type: str
    label: str
    days: float


class AccountingSurcharge(BaseModel):
    name: str
    minutes: int


class AccountingHours(BaseModel):
    target_minutes: int
    actual_minutes: int
    balance_minutes: int
    payout_minutes: int
    open_days: int
    holiday_days: float = 0
    # Mit dem Gehalt abgegoltene Überstunden; fehlt in Schnappschüssen vor dieser Fassung
    settled_minutes: int = 0


class AccountingCompensation(BaseModel):
    pay_type: Literal["HOURLY", "MONTHLY"]
    # Beträge als Text mit zwei Nachkommastellen (keine Rundungsfehler im Schnappschuss)
    amount: str
    currency: str
    valid_from: date


class AccountingPayComponent(BaseModel):
    name: str
    amount: str


class AccountingEmployee(BaseModel):
    employee_id: int
    employee_number: str
    first_name: str
    last_name: str
    hire_date: date | None
    termination_date: date | None
    entry: bool
    exit: bool
    closure: ClosureState
    hours: AccountingHours
    surcharges: list[AccountingSurcharge]
    absences: list[AccountingAbsence]
    changes: list[AccountingChange]
    compensation: AccountingCompensation | None = None
    pay_components: list[AccountingPayComponent] = []


class AccountingSummary(BaseModel):
    employee_count: int
    entries: int
    exits: int
    open_closures: int


class ReleaseInfo(BaseModel):
    month: str
    released_at: datetime
    released_by: str | None
    employee_count: int
    open_closures: int
    has_datev: bool


class AccountingMonth(BaseModel):
    month: str
    # Freigabe dieses Monats; None = aktueller Stand (nur mit Bearbeiten)
    release: ReleaseInfo | None
    includes_pay: bool
    employees: list[AccountingEmployee]
    summary: AccountingSummary
    # Nur bei freigegebenen Monaten mit compare=true: Mitarbeiter, deren Daten sich seither geändert
    # haben (None = nicht verglichen)
    changed_since_release: list[int] | None = None


class ReleaseRequest(BaseModel):
    # Offene Monatsabschlüsse sind kein Verbot, aber eine Warnung: erst nach Bestätigung freigeben
    confirm_open_closures: bool = False
