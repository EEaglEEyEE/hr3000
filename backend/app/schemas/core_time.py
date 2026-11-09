"""Zeitfenster je Wochentag – Kernzeit und Gleitzeit-Rahmen: 7 Einträge (Mo..So), je Tag Beginn/Ende
oder None (an diesem Tag keine Kernzeit bzw. kein Rahmen). Gespeichert kompakt als Text in
AppSettings.core_time_days bzw. in der Fassung der Arbeitszeit (EmployeeDefaultShift.core_time_days,
.flex_frame_days und dasselbe an der Modell-Fassung),
z.B. "09:00-15:00,09:00-15:00,09:00-15:00,09:00-15:00,09:00-12:00,," (NULL = jeden Tag dasselbe
Fenster aus *_start/-end)."""
from datetime import time
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator

WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

Window = tuple[time, time]


class _DayWindow(BaseModel):
    window_label: ClassVar[str] = "Zeitfenster"

    start: time
    end: time

    @model_validator(mode="after")
    def _order(self) -> "_DayWindow":
        if self.start >= self.end:
            raise ValueError(f"{self.window_label}: der Beginn muss vor dem Ende liegen.")
        return self


class CoreTimeDay(_DayWindow):
    window_label: ClassVar[str] = "Kernzeit"


class FlexFrameDay(_DayWindow):
    window_label: ClassVar[str] = "Gleitzeit-Rahmen"


def parse_day_windows(value: str | None) -> list[Window | None] | None:
    if not value:
        return None
    days: list[Window | None] = []
    for part in value.split(",")[:7]:
        if not part:
            days.append(None)
            continue
        start, end = part.split("-")
        days.append((time.fromisoformat(start), time.fromisoformat(end)))
    return days + [None] * (7 - len(days))


def serialize_day_windows(days: list[_DayWindow | None] | None) -> str | None:
    if days is None:
        return None
    return ",".join(f"{d.start:%H:%M}-{d.end:%H:%M}" if d is not None else "" for d in days)


# Bisherige Namen (Kernzeit), weiter genutzt in Einstellungen und Tagesberechnung
parse_core_time_days = parse_day_windows
serialize_core_time_days = serialize_day_windows


def day_windows(days: list | None, start: time | None, end: time | None) -> list[Window | None]:
    """Fenster je Wochentag (7 Einträge): aus den Tageswerten (Modelle oder Tupel) oder jeden Tag
    start–end; ohne Angaben an keinem Tag."""
    if days is not None:
        return [None if d is None else (d if isinstance(d, tuple) else (d.start, d.end)) for d in days]
    if start is not None and end is not None:
        return [(start, end)] * 7
    return [None] * 7


def describe_day_windows(days: list[Window | None], empty: str = "ohne") -> str:
    """Kurzform fürs Audit-Protokoll: aufeinanderfolgende gleiche Tage zusammengefasst, z.B.
    "Mo–Do 07:00–19:00, Fr 07:00–15:00, Sa–So ohne"."""
    parts: list[str] = []
    index = 0
    while index < len(days):
        last = index
        while last + 1 < len(days) and days[last + 1] == days[index]:
            last += 1
        span = WEEKDAY_LABELS[index] if last == index else f"{WEEKDAY_LABELS[index]}–{WEEKDAY_LABELS[last]}"
        window = days[index]
        parts.append(f"{span} {empty}" if window is None else f"{span} {window[0]:%H:%M}–{window[1]:%H:%M}")
        index = last + 1
    return ", ".join(parts)


def _from_storage(value: Any) -> Any:
    """Aus der Datenbank (Text) für Antworten lesen; Listen (Requests) unverändert durchreichen."""
    if isinstance(value, str) or value is None:
        parsed = parse_day_windows(value)
        return None if parsed is None else [None if d is None else {"start": d[0], "end": d[1]} for d in parsed]
    return value


_SevenDays = Annotated[list[CoreTimeDay | None], Field(min_length=7, max_length=7)]
CoreTimeDays = Annotated[_SevenDays | None, BeforeValidator(_from_storage)]
_SevenFrames = Annotated[list[FlexFrameDay | None], Field(min_length=7, max_length=7)]
FlexFrameDays = Annotated[_SevenFrames | None, BeforeValidator(_from_storage)]


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
