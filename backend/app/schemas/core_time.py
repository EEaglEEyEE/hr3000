"""Kernzeit je Wochentag: 7 Einträge (Mo..So), je Tag Beginn/Ende oder None (an diesem Tag keine
Kernzeit). Gespeichert kompakt als Text in AppSettings.core_time_days bzw. in der Fassung der
Arbeitszeit (EmployeeDefaultShift.core_time_days),
z.B. "09:00-15:00,09:00-15:00,09:00-15:00,09:00-15:00,09:00-12:00,," (NULL = jeden Tag dieselbe
Kernzeit aus core_time_start/-end)."""
from datetime import time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator


class CoreTimeDay(BaseModel):
    start: time
    end: time

    @model_validator(mode="after")
    def _order(self) -> "CoreTimeDay":
        if self.start >= self.end:
            raise ValueError("Kernzeit: der Beginn muss vor dem Ende liegen.")
        return self


def parse_core_time_days(value: str | None) -> list[tuple[time, time] | None] | None:
    if not value:
        return None
    days: list[tuple[time, time] | None] = []
    for part in value.split(",")[:7]:
        if not part:
            days.append(None)
            continue
        start, end = part.split("-")
        days.append((time.fromisoformat(start), time.fromisoformat(end)))
    return days + [None] * (7 - len(days))


def serialize_core_time_days(days: list[CoreTimeDay | None] | None) -> str | None:
    if days is None:
        return None
    return ",".join(f"{d.start:%H:%M}-{d.end:%H:%M}" if d is not None else "" for d in days)


def _from_storage(value: Any) -> Any:
    """Aus der Datenbank (Text) für Antworten lesen; Listen (Requests) unverändert durchreichen."""
    if isinstance(value, str) or value is None:
        parsed = parse_core_time_days(value)
        return None if parsed is None else [None if d is None else {"start": d[0], "end": d[1]} for d in parsed]
    return value


_SevenDays = Annotated[list[CoreTimeDay | None], Field(min_length=7, max_length=7)]
CoreTimeDays = Annotated[_SevenDays | None, BeforeValidator(_from_storage)]


# Kernzeit einer Fassung der Arbeitszeit: TENANT = wie in den Einstellungen, CUSTOM = eigene
# (Beginn/Ende oder je Wochentag), NONE = keine Pünktlichkeitsprüfung (z.B. Außendienst).
CoreTimeMode = Literal["TENANT", "CUSTOM", "NONE"]


def check_core_time(mode: str | None, start: time | None, end: time | None, days: list | None = None) -> None:
    if mode == "CUSTOM":
        if days is not None:
            return  # Kernzeit je Wochentag (je Tag geprüft, siehe CoreTimeDay)
        if start is None or end is None:
            raise ValueError("Eigene Kernzeit: bitte Beginn und Ende angeben.")
        if start >= end:
            raise ValueError("Eigene Kernzeit: der Beginn muss vor dem Ende liegen.")
