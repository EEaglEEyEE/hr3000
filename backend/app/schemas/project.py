"""Projektzeiterfassung: Kunden, Projekte und die Auswertung „Projektzeiten“."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NAME_MAX = 120
NUMBER_MAX = 40


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    active: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bitte einen Namen angeben.")
        return value


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Bitte einen Namen angeben.")
        return value.strip() if value is not None else None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    active: bool
    project_count: int = 0


class _ProjectFields(BaseModel):
    @field_validator("number", "name", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _period(self):
        valid_from = getattr(self, "valid_from", None)
        valid_to = getattr(self, "valid_to", None)
        if valid_from is not None and valid_to is not None and valid_from > valid_to:
            raise ValueError("„Gültig von“ muss vor „Gültig bis“ liegen.")
        return self


class ProjectCreate(_ProjectFields):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    number: str | None = Field(default=None, max_length=NUMBER_MAX)
    customer_id: int | None = Field(default=None, ge=1)
    cost_center_id: int | None = Field(default=None, ge=1)
    billable: bool = True
    active: bool = True
    valid_from: date | None = None
    valid_to: date | None = None

    @field_validator("number")
    @classmethod
    def _number(cls, value: str | None) -> str | None:
        return _clean(value)


class ProjectUpdate(_ProjectFields):
    """Nur mitgeschickte Felder ändern sich; number, customer_id, cost_center_id, valid_from und
    valid_to lassen sich mit null leeren."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    number: str | None = Field(default=None, max_length=NUMBER_MAX)
    customer_id: int | None = Field(default=None, ge=1)
    cost_center_id: int | None = Field(default=None, ge=1)
    billable: bool | None = None
    active: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @field_validator("number")
    @classmethod
    def _number(cls, value: str | None) -> str | None:
        return _clean(value)


class ProjectResponse(BaseModel):
    id: int
    name: str
    number: str | None
    customer_id: int | None
    customer_name: str | None = None
    cost_center_id: int | None
    cost_center_label: str | None = None
    billable: bool
    active: bool
    valid_from: date | None
    valid_to: date | None
    # Zeiten zugeordnet → nur deaktivierbar
    in_use: bool = False


class ProjectOption(BaseModel):
    """Auswahl im Stundenzettel: nur aktive Projekte (Kunde aktiv); Zeitraum je Tag beachten."""

    id: int
    label: str
    valid_from: date | None = None
    valid_to: date | None = None


class ProjectTimeRow(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    employee_number: str | None = None
    project_id: int
    project_name: str
    project_number: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    cost_center: str | None = None
    billable: bool
    minutes: int


class ProjectTimesResponse(BaseModel):
    date_from: date
    date_to: date
    rows: list[ProjectTimeRow]
    total_minutes: int
    billable_minutes: int
    non_billable_minutes: int
