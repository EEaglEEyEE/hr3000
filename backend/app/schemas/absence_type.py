from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.absence import AbsenceType

_COLOR = r"^#[0-9a-fA-F]{6}$"


class AbsenceTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    category: AbsenceType
    requires_approval: bool
    employee_can_request: bool
    certificate_from_day: int | None
    active: bool
    sort_order: int


class AbsenceTypeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#64748b", pattern=_COLOR)
    category: AbsenceType
    requires_approval: bool = False
    employee_can_request: bool = True
    certificate_from_day: int | None = Field(default=None, ge=1, le=365)
    sort_order: int = Field(default=0, ge=0, le=1000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name darf nicht leer sein.")
        return value


class AbsenceTypeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    # Kategorie ändern: bestehende Einträge dieser Art werden neu berechnet (nicht in gesperrten Monaten)
    category: AbsenceType | None = None
    color: str | None = Field(default=None, pattern=_COLOR)
    requires_approval: bool | None = None
    employee_can_request: bool | None = None
    certificate_from_day: int | None = Field(default=None, ge=1, le=365)
    clear_certificate_from_day: bool = False
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Name darf nicht leer sein.")
        return value
