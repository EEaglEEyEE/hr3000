import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.personal_data import PersonalData


class ChangeProposal(BaseModel):
    """Vorschlag: nur die geänderten Felder (persönliche Daten bzw. eigene Felder mit Freigabe „EDIT“)."""

    personal: PersonalData = PersonalData()
    # Feld-ID → neuer Wert (leer = Feld leeren)
    attributes: dict[int, str | None] = Field(default={}, max_length=50)
    note: str | None = Field(default=None, max_length=300)


class ChangeItem(BaseModel):
    field: str
    label: str
    old: str | None
    new: str | None


class ChangeRequestResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    created_at: dt.datetime
    decided_at: dt.datetime | None
    decision_note: str | None
    note: str | None = None
    contains_payroll: bool
    items: list[ChangeItem]


class ChangeDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=300)
