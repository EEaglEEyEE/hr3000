from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentCategory


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    category: DocumentCategory
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    confidential: bool
    employee_visible: bool
    retention_until: date | None
    created_at: datetime


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: DocumentCategory | None = None
    employee_visible: bool | None = None
    confidential: bool | None = None
    retention_until: date | None = None
    clear_retention_until: bool = False
