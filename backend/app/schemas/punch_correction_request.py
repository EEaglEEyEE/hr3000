import json
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.punch import PunchType
from app.models.punch_correction_request import CorrectionRequestStatus


class CorrectionItem(BaseModel):
    punch_type: PunchType
    # Ortszeit des Standorts "HH:MM"
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # Für Nachtschichten: Uhrzeit gehört zum Folgetag (z.B. Gehen um 02:00)
    next_day: bool = False


class CorrectionRequestCreate(BaseModel):
    work_date: date
    items: list[CorrectionItem] = Field(min_length=1, max_length=6)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Bitte kurz begründen.")
        return value


class CorrectionRequestDecide(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class CorrectionRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    employee_name: str | None = None
    work_date: date
    items: list[CorrectionItem]
    reason: str
    status: CorrectionRequestStatus
    created_at: datetime | None
    decided_at: datetime | None
    decision_note: str | None

    @field_validator("items", mode="before")
    @classmethod
    def _parse(cls, value):
        return json.loads(value) if isinstance(value, str) else value
