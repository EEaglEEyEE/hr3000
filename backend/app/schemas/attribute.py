import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FieldType = Literal["TEXT", "NUMBER", "DATE", "SELECT", "BOOLEAN", "EMPLOYEE"]
EmployeeAccess = Literal["NONE", "VIEW", "EDIT"]


class AttributeSectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    employee_access: EmployeeAccess = "NONE"
    sort_order: int = Field(default=0, ge=0, le=1000)


class AttributeSectionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    employee_access: EmployeeAccess | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    archived: bool | None = None


class AttributeDefinitionRequest(BaseModel):
    section_id: int
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType
    options: list[str] = Field(default=[], max_length=50)
    dated: bool = False
    sort_order: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def _options(self) -> "AttributeDefinitionRequest":
        self.options = [o.strip() for o in self.options if o.strip()]
        if self.field_type == "SELECT" and not self.options:
            raise ValueError("Für eine Auswahl bitte mindestens einen Wert angeben.")
        if any(len(o) > 100 for o in self.options):
            raise ValueError("Auswahlwerte höchstens 100 Zeichen.")
        return self


class AttributeDefinitionUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    options: list[str] | None = Field(default=None, max_length=50)
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    archived: bool | None = None


class AttributeDefinitionResponse(BaseModel):
    id: int
    section_id: int
    label: str
    field_type: FieldType
    options: list[str]
    dated: bool
    sort_order: int
    archived: bool


class AttributeSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    employee_access: EmployeeAccess
    sort_order: int
    archived: bool
    attributes: list[AttributeDefinitionResponse] = []


class AttributeValueRequest(BaseModel):
    # null bzw. "" leert das Feld
    value: str | None = Field(default=None, max_length=1000)
    # Nur bei Feldern mit Verlauf: ab wann der Wert gilt (Standard heute)
    valid_from: dt.date | None = None


class AttributeHistoryEntry(BaseModel):
    id: int
    value: str | None
    valid_from: dt.date | None
    created_at: dt.datetime


class EmployeeAttributeValue(BaseModel):
    attribute_id: int
    # Aktueller Wert (bei Verlauf: jüngster bis heute) und Anzeige (z. B. Name statt ID)
    value: str | None
    display: str | None
    history: list[AttributeHistoryEntry] = []


class EmployeeHistoryEntry(BaseModel):
    """Mitarbeitendenhistorie: was sich wann geändert hat (Audit-Protokoll und Felder mit Gültig ab)."""

    at: dt.datetime
    valid_from: dt.date | None = None
    what: str
    by: str | None = None
