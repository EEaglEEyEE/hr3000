from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.shift_template import BreakMode, TargetPeriod
from app.schemas.core_time import CoreTimeDays


class EmployeeDefaultShiftCreateRequest(BaseModel):
    """Ältere Zuordnung "Standard-Schicht": Soll und Pause kommen aus der Schichtvorlage. Neu gibt es
    dafür das Arbeitszeitmodell (PUT /employees/{id}/work-time-model) mit optionaler Schichtvorlage."""

    shift_template_id: int
    valid_from: date
    valid_to: date | None = None
    weekdays_mask: int = Field(ge=1, le=127)
    # Soll-Minuten je Wochentag (7 Werte, Mo..So); 0 = frei. Optional.
    day_minutes: list[int] | None = Field(default=None, min_length=7, max_length=7)
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_minutes: int | None = Field(default=None, gt=0, le=24000)

    @field_validator("day_minutes")
    @classmethod
    def _valid_day_minutes(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(m < 0 or m > 600 for m in value):
            raise ValueError("Soll je Tag muss zwischen 0 und 600 Minuten (10 Std., §3 ArbZG) liegen.")
        return value


class EmployeeDefaultShiftUpdateRequest(BaseModel):
    shift_template_id: int | None = None
    weekdays_mask: int | None = Field(default=None, ge=1, le=127)
    valid_to: date | None = None
    clear_valid_to: bool = False


class EmployeeDefaultShiftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    # leer = Fassung ohne Schichtvorlage (Arbeitszeitmodell ohne feste Uhrzeiten)
    shift_template_id: int | None
    valid_from: date
    valid_to: date | None
    weekdays_mask: int
    day_minutes: str | None = None
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_minutes: int | None = None
    # Soll und Pause der Fassung (leer = aus der Schichtvorlage bzw. Pausenregeln)
    target_minutes: int | None = None
    target_period: TargetPeriod | None = None
    break_mode: BreakMode | None = None
    fixed_break_start: time | None = None
    fixed_break_end: time | None = None
    min_break_minutes: int | None = None
    min_break_after_minutes: int = 0
    core_time_mode: str | None = None
    core_time_start: time | None = None
    core_time_end: time | None = None
    core_time_days: CoreTimeDays = None
