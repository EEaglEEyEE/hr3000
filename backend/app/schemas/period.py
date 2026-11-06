from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.period_closure import PeriodStatus


class PeriodClosureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    year: int
    month: int
    status: PeriodStatus
    target_minutes: int
    actual_minutes: int
    delta_minutes: int
    balance_end_minutes: int
    document_id: int | None
    submitted_at: datetime
    confirmed_at: datetime | None
    disputed_at: datetime | None
    dispute_reason: str | None
    closed_at: datetime | None
    closed_without_confirmation: bool


class PeriodSubmitRequest(BaseModel):
    # Erlaubt das Vorlegen trotz offener/fehlerhafter Tage (diese sind im Nachweis rot markiert).
    ignore_open_days: bool = False
    # Erlaubt das Vorlegen trotz offener Abwesenheits- bzw. Korrekturanträge im Monat (danach sind
    # sie wegen der Sperre nicht mehr entscheidbar, bis der Monat wieder offen ist).
    ignore_open_requests: bool = False


class PeriodDisputeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PeriodCloseRequest(BaseModel):
    # Abschluss durch HR ist immer ohne Bestätigung des Mitarbeiters (die Bestätigung schließt selbst
    # ab) – wird im Audit-Log vermerkt. Feld nur noch aus Kompatibilität.
    without_confirmation: bool = True


class PeriodBulkSubmitRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    ignore_open_days: bool = False
    ignore_open_requests: bool = False


class PeriodOverviewRow(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    employee_number: str
    # None = noch nichts vorgelegt
    status: PeriodStatus | None
    closure_id: int | None
    delta_minutes: int | None
    dispute_reason: str | None = None
    open_day_count: int


class PeriodBulkResultRow(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    submitted: bool
    reason: str | None = None


class OpenDaysInfo(BaseModel):
    open_days: list[date]
