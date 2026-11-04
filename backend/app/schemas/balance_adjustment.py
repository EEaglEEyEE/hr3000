from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.balance_adjustment import AdjustmentKind


class BalanceAdjustmentCreateRequest(BaseModel):
    effective_date: date
    # Vorzeichenbehaftet in Minuten: +600 = 10 Std. gutschreiben, -600 = abziehen/auszahlen.
    minutes: int = Field(ge=-60_000, le=60_000)
    kind: AdjustmentKind
    note: str = Field(min_length=3, max_length=300)

    @field_validator("minutes")
    @classmethod
    def _not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Eine Buchung über 0 Minuten ist nicht sinnvoll.")
        return value

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Bitte eine Begründung angeben.")
        return value


class BalanceAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    effective_date: date
    minutes: int
    kind: AdjustmentKind
    note: str
    created_at: datetime
