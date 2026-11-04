from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import ChecklistKind, ChecklistRole


class TemplateItemInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    responsible: ChecklistRole = ChecklistRole.HR
    due_offset_days: int = Field(default=0, ge=-365, le=365)


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
    # Standard: Eintrittsdatum (Onboarding) bzw. Austrittsdatum (Offboarding), sonst heute.
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
