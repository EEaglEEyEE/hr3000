from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.absence import AbsenceApprovalStatus, AbsenceType


class AbsenceCreateRequest(BaseModel):
    employee_id: int
    # Abwesenheitsart des Mandanten; alternativ (ältere Clients) nur die Kategorie.
    absence_type_id: int | None = None
    type: AbsenceType | None = None
    date_from: date
    date_to: date
    # Nur ein halber Tag (nur möglich, wenn date_from == date_to)
    half_day: bool = False
    # Genaue Dauer in Minuten (nur einzelner Tag, nicht zusammen mit half_day), max. 16 Std.
    duration_minutes: int | None = Field(default=None, ge=1, le=960)
    note: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def _type_given(self) -> "AbsenceCreateRequest":
        if self.absence_type_id is None and self.type is None:
            raise ValueError("Bitte eine Abwesenheitsart angeben.")
        if (self.half_day or self.duration_minutes is not None) and self.date_from != self.date_to:
            raise ValueError("Halbe Tage und Stundenangaben sind nur für einen einzelnen Tag möglich.")
        if self.half_day and self.duration_minutes is not None:
            raise ValueError("Bitte entweder halber Tag oder Stunden angeben.")
        return self


class AbsenceUpdateRequest(BaseModel):
    absence_type_id: int | None = None
    type: AbsenceType | None = None
    date_from: date | None = None
    date_to: date | None = None
    half_day: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=960)
    # Stundenangabe entfernen (wieder ganzer Tag)
    clear_duration: bool = False
    note: str | None = Field(default=None, max_length=400)


class AbsenceDecideRequest(BaseModel):
    approve: bool
    note: str | None = None


class AbsenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    type: AbsenceType
    absence_type_id: int | None = None
    date_from: date
    date_to: date
    half_day: bool = False
    duration_minutes: int | None = None
    created_by: int | None
    created_by_employee_id: int | None
    note: str | None
    approval_status: AbsenceApprovalStatus
    decided_by: int | None
    decided_by_employee_id: int | None
    decided_at: datetime | None
