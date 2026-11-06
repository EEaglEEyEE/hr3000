from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.break_rule import BreakRuleKind


def window_length(start: time, end: time) -> int:
    return round((datetime.combine(date.min, end) - datetime.combine(date.min, start)).total_seconds() / 60)


def check_window(start: time | None, end: time | None) -> None:
    """Feste Pausenzeit: beide Uhrzeiten, Beginn vor Ende (nicht über Mitternacht), höchstens 4 Std."""
    if start is None or end is None:
        raise ValueError("Bitte Beginn und Ende der Pausenzeit angeben.")
    if start >= end:
        raise ValueError("Die Pausenzeit muss vor ihrem Ende beginnen (nicht über Mitternacht).")
    if window_length(start, end) > 240:
        raise ValueError("Eine feste Pausenzeit darf höchstens 4 Stunden lang sein.")


class BreakRuleCreateRequest(BaseModel):
    kind: BreakRuleKind = BreakRuleKind.LEGAL
    # LEGAL/FIXED_MINUTES: ab wie vielen Arbeitsminuten wie viel Pause.
    min_work_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    deduct_minutes: int | None = Field(default=None, ge=0, le=240)
    # FIXED_WINDOW: Pausenzeit (Ortszeit).
    start_time: time | None = None
    end_time: time | None = None
    # Ab wann die Regel gilt (Standard: heute). Frühere Tage bleiben unverändert.
    valid_from: date | None = None

    @model_validator(mode="after")
    def _by_kind(self) -> "BreakRuleCreateRequest":
        if self.kind == BreakRuleKind.FIXED_WINDOW:
            check_window(self.start_time, self.end_time)
            self.min_work_minutes = 0
            self.deduct_minutes = window_length(self.start_time, self.end_time)
        else:
            # "Feste Minuten" ist eine Zeile der Pausenstaffel (rechnerisch identisch).
            self.kind = BreakRuleKind.LEGAL
            if self.min_work_minutes is None or self.deduct_minutes is None:
                raise ValueError("Bitte Arbeitsminuten und Pausenminuten angeben.")
            self.start_time = self.end_time = None
        return self


class BreakRuleUpdateRequest(BaseModel):
    min_work_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    deduct_minutes: int | None = Field(default=None, ge=0, le=240)
    start_time: time | None = None
    end_time: time | None = None
    valid_from: date | None = None


class BreakRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: BreakRuleKind
    min_work_minutes: int
    deduct_minutes: int
    start_time: time | None
    end_time: time | None
    valid_from: date
    valid_to: date | None
