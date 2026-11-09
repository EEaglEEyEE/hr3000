from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.checklist import ChecklistKind, ChecklistRole


ChecklistAction = Literal["TASK", "UPLOAD_DOCUMENT", "FILL_DATA", "SEND_EMAIL"]


class TemplateItemInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # Bei SEND_EMAIL der Text der E-Mail (Platzhalter wie in Dokumentvorlagen)
    description: str | None = Field(default=None, max_length=500)
    responsible: ChecklistRole = ChecklistRole.HR
    due_offset_days: int = Field(default=0, ge=-365, le=365)
    action: ChecklistAction = "TASK"
    action_category_id: int | None = None

    @model_validator(mode="after")
    def _action(self) -> "TemplateItemInput":
        if self.action in ("UPLOAD_DOCUMENT", "FILL_DATA") and self.responsible != ChecklistRole.EMPLOYEE:
            raise ValueError("Hochladen und Daten ausfüllen erledigt die Person selbst (zuständig: Mitarbeiter).")
        if self.action == "UPLOAD_DOCUMENT" and self.action_category_id is None:
            raise ValueError("Für „Dokument hochladen“ bitte eine Kategorie wählen.")
        if self.action == "SEND_EMAIL" and not (self.description or "").strip():
            raise ValueError("Für „E-Mail senden“ bitte den Text angeben.")
        return self


class TemplateItemResponse(TemplateItemInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int


class TemplateCreateRequest(BaseModel):
    kind: ChecklistKind
    name: str = Field(min_length=1, max_length=100)
    items: list[TemplateItemInput] = Field(min_length=1, max_length=100)


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # Ersetzt die komplette Aufgabenliste (bestehende Mitarbeiter-Checklisten bleiben unberührt).
    items: list[TemplateItemInput] | None = Field(default=None, min_length=1, max_length=100)


class TemplateResponse(BaseModel):
    id: int
    kind: ChecklistKind
    name: str
    items: list[TemplateItemResponse]


class ChecklistStartRequest(BaseModel):
    template_id: int
    # Standard: Anstelldatum (Onboarding) bzw. Austrittsdatum (Offboarding), sonst heute.
    anchor_date: date | None = None


class ChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    title: str
    description: str | None
    responsible: ChecklistRole
    due_date: date
    done: bool
    done_at: datetime | None
    note: str | None
    action: str = "TASK"
    action_category_id: int | None = None


class ChecklistResponse(BaseModel):
    id: int
    employee_id: int
    kind: ChecklistKind
    name: str
    anchor_date: date
    items: list[ChecklistItemResponse]


class ChecklistItemUpdateRequest(BaseModel):
    done: bool | None = None
    note: str | None = Field(default=None, max_length=300)


class OpenChecklistItem(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    checklist_id: int
    checklist_name: str
    kind: ChecklistKind
    item_id: int
    title: str
    responsible: ChecklistRole
    due_date: date
    overdue: bool
