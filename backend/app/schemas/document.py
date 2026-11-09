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
    category_id: int | None = None


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: DocumentCategory | None = None
    # Eigene Kategorie setzen bzw. mit clear_category_id entfernen
    category_id: int | None = None
    clear_category_id: bool = False
    employee_visible: bool | None = None
    confidential: bool | None = None
    retention_until: date | None = None
    clear_retention_until: bool = False


class DocumentCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    employee_upload: bool = False
    employee_visible: bool = False
    confidential: bool = False


class DocumentCategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    employee_upload: bool | None = None
    employee_visible: bool | None = None
    confidential: bool | None = None
    archived: bool | None = None


class DocumentCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    employee_upload: bool
    employee_visible: bool
    confidential: bool
    archived: bool
