from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.break_rule import check_window

from app.models.shift_template import BreakMode, TargetPeriod


class ShiftTemplateCreateRequest(BaseModel):
    name: str
    start_time: time | None = None
    end_time: time | None = None
    break_mode: BreakMode = BreakMode.FLEXIBLE
    fixed_break_start: time | None = None
    fixed_break_end: time | None = None
    # Feste Minuten Pause (ab der ersten Arbeitsminute), nur bei FLEXIBLE; 0/leer = Pausenregeln des Mandanten.
    min_break_minutes: int | None = Field(default=None, ge=0, le=240)
    target_minutes: int = Field(default=0, ge=0)
    target_period: TargetPeriod = TargetPeriod.DAILY
    location_id: int | None = None

    @model_validator(mode="after")
    def _break(self) -> "ShiftTemplateCreateRequest":
        if self.break_mode == BreakMode.FIXED:
            check_window(self.fixed_break_start, self.fixed_break_end)
        return self


class ShiftTemplateUpdateRequest(BaseModel):
    name: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    break_mode: BreakMode | None = None
    fixed_break_start: time | None = None
    fixed_break_end: time | None = None
    min_break_minutes: int | None = Field(default=None, ge=0, le=240)
    target_minutes: int | None = Field(default=None, ge=0)
    target_period: TargetPeriod | None = None
    location_id: int | None = None
    clear_location_id: bool = False
    # Ab wann ein geändertes Soll gilt (Standard: heute). Tage davor rechnen mit dem alten Soll.
    valid_from: date | None = None


class ShiftTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    start_time: time | None
    end_time: time | None
    break_mode: BreakMode
    fixed_break_start: time | None
    fixed_break_end: time | None
    min_break_minutes: int | None
    target_minutes: int
    target_period: TargetPeriod
    location_id: int | None
    is_work_time_model: bool
    archived: bool = False
