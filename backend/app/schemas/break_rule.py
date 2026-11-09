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


MAX_BREAK_WINDOWS = 4


class BreakWindow(BaseModel):
    """Eine feste Pausenzeit (Ortszeit), z.B. 12:00–12:30."""

    start: time
    end: time

    @model_validator(mode="after")
    def _valid(self) -> "BreakWindow":
        check_window(self.start, self.end)
        return self


def check_windows(windows: list[tuple[time, time]]) -> list[tuple[time, time]]:
    """Mehrere feste Pausenzeiten: jede gültig, nach Beginn sortiert, ohne Überschneidung."""
    ordered = sorted(windows)
    for (_, end), (start, _) in zip(ordered, ordered[1:]):
        if start < end:
            raise ValueError("Feste Pausenzeiten dürfen sich nicht überschneiden.")
    return ordered


def serialize_break_windows(windows: list[tuple[time, time]]) -> str | None:
    """Text für fixed_break_windows (nur bei mehr als einer Pausenzeit, sonst NULL)."""
    if len(windows) < 2:
        return None
    return ",".join(f"{start:%H:%M}-{end:%H:%M}" for start, end in windows)


def parse_break_windows(value: str | None) -> list[tuple[time, time]]:
    if not value:
        return []
    result = []
    for part in value.split(","):
        start, end = part.split("-")
        result.append((time.fromisoformat(start), time.fromisoformat(end)))
    return result


def fixed_break_windows(source) -> list[tuple[time, time]]:
    """Feste Pausenzeiten einer Fassung bzw. Modell-Fassung: alle aus fixed_break_windows, sonst die
    eine aus fixed_break_start/-end."""
    windows = parse_break_windows(getattr(source, "fixed_break_windows", None))
    if windows:
        return windows
    if source.fixed_break_start is not None and source.fixed_break_end is not None:
        return [(source.fixed_break_start, source.fixed_break_end)]
    return []


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
