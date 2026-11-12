import json
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.punch import PunchType
from app.models.punch_correction_request import CorrectionRequestKind, CorrectionRequestStatus


class CorrectionItem(BaseModel):
    punch_type: PunchType
    # Ortszeit des Standorts "HH:MM"
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # Für Nachtschichten: Uhrzeit gehört zum Folgetag (z.B. Gehen um 02:00)
    next_day: bool = False
    # Nur bei selbst eingetragenen Zeiten (Art TIME_ENTRY) am "Kommen": Projekt und Tätigkeit.
    # In Korrekturanträgen ohne Wirkung.
    project_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=200)


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
    # CORRECTION = Korrekturantrag, TIME_ENTRY = selbst eingetragene Zeiten (Stundenzettel)
    kind: CorrectionRequestKind = CorrectionRequestKind.CORRECTION
    items: list[CorrectionItem]
    reason: str
    status: CorrectionRequestStatus
    created_at: datetime | None
    decided_at: datetime | None
    decision_note: str | None
    # Projektnamen zu den project_id der Positionen (Anzeige)
    project_names: dict[int, str] = {}

    @field_validator("items", mode="before")
    @classmethod
    def _parse(cls, value):
        return json.loads(value) if isinstance(value, str) else value
