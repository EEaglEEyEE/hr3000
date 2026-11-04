from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class BreakRuleCreateRequest(BaseModel):
    min_work_minutes: int = Field(ge=0, le=24 * 60)
    deduct_minutes: int = Field(ge=0, le=240)
    # Ab wann die Regel gilt (Standard: heute). Frühere Tage bleiben unverändert.
    valid_from: date | None = None


class BreakRuleUpdateRequest(BaseModel):
    min_work_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    deduct_minutes: int | None = Field(default=None, ge=0, le=240)
    valid_from: date | None = None


class BreakRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    min_work_minutes: int
    deduct_minutes: int
    valid_from: date
    valid_to: date | None
