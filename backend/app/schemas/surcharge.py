from datetime import time

from pydantic import BaseModel, Field, model_validator

from app.models.surcharge_rule import SurchargeKind

_GROUP = r"^[A-Za-z0-9_-]{1,50}$"


class SurchargeRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: SurchargeKind
    percent: float = Field(gt=0, le=500)
    start_time: time | None = None
    end_time: time | None = None
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6], min_length=1, max_length=7)
    exclusive_group: str | None = Field(default=None, pattern=_GROUP)
    active: bool = True

    @model_validator(mode="after")
    def _consistent(self) -> "SurchargeRuleCreateRequest":
        if any(day < 0 or day > 6 for day in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("Wochentage müssen eindeutige Werte von 0 (Montag) bis 6 (Sonntag) sein.")
        if self.kind in (SurchargeKind.NIGHT, SurchargeKind.CUSTOM):
            if self.start_time is None or self.end_time is None or self.start_time == self.end_time:
                raise ValueError("Für Nacht- und freie Zuschläge sind Beginn und Ende (verschieden) erforderlich.")
        else:
            self.start_time = None
            self.end_time = None
            self.weekdays = [0, 1, 2, 3, 4, 5, 6]
        return self


class SurchargeRuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    percent: float | None = Field(default=None, gt=0, le=500)
    start_time: time | None = None
    end_time: time | None = None
    weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    exclusive_group: str | None = Field(default=None, pattern=_GROUP)
    clear_exclusive_group: bool = False
    active: bool | None = None


class SurchargeRuleResponse(BaseModel):
    id: int
    name: str
    kind: SurchargeKind
    percent: float
    start_time: time | None
    end_time: time | None
    weekdays: list[int]
    exclusive_group: str | None
    active: bool


class SurchargeLine(BaseModel):
    rule_id: int
    name: str
    kind: SurchargeKind
    percent: float
    minutes: int
    equivalent_minutes: float
    # Nur für Administratoren und nur bei Stundenlohn: Zuschlagsbetrag in EUR brutto.
    amount: float | None = None


class SurchargeReportResponse(BaseModel):
    employee_id: int
    lines: list[SurchargeLine]
    hourly_rate: float | None = None
