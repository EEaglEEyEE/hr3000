from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmployeeDefaultShiftCreateRequest(BaseModel):
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
    shift_template_id: int
    valid_from: date
    valid_to: date | None
    weekdays_mask: int
    day_minutes: str | None = None
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_minutes: int | None = None
