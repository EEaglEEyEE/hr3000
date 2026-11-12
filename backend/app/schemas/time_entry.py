"""Zeiten selbst eintragen (Stundenzettel in „Mein Bereich“), siehe services/time_entry_service.py."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.punch import PunchSource
from app.schemas.project import ProjectOption

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
MAX_SPANS = 10
NOTE_MAX_LENGTH = 200


def minutes_of(value: str) -> int:
    hour, minute = (int(v) for v in value.split(":"))
    return hour * 60 + minute


class TimeSpanIn(BaseModel):
    """Eine Zeitspanne eines Tages in Ortszeit des Standorts. WORK = Arbeit (Kommen/Gehen),
    BREAK = Pause innerhalb einer Arbeitsspanne (Pause Start/Ende) – wie beim Stempeln."""

    kind: Literal["WORK", "BREAK"] = "WORK"
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    # Ende am Folgetag (Nachtschicht, z. B. 22:00–06:00)
    end_next_day: bool = False
    # Projektzeiten (nur Arbeitszeiten, nur wenn eingeschaltet): Projekt und Tätigkeitsnotiz
    project_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    def start_minutes(self) -> int:
        return minutes_of(self.start)

    def end_minutes(self) -> int:
        return minutes_of(self.end) + (1440 if self.end_next_day else 0)

    @model_validator(mode="after")
    def _end_after_start(self) -> "TimeSpanIn":
        if self.end_minutes() <= self.start_minutes():
            raise ValueError("Das Ende muss nach dem Beginn liegen (über Mitternacht: „Folgetag“ ankreuzen).")
        if self.kind == "BREAK" and (self.project_id is not None or self.note is not None):
            raise ValueError("Projekt und Tätigkeit gibt es nur bei Arbeitszeiten, nicht bei Pausen.")
        return self


class TimeEntryCreate(BaseModel):
    work_date: date
    spans: list[TimeSpanIn] = Field(min_length=1, max_length=MAX_SPANS)
    # Optionaler Hinweis für die Genehmigung
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @model_validator(mode="after")
    def _consistent(self) -> "TimeEntryCreate":
        work = sorted((s for s in self.spans if s.kind == "WORK"), key=lambda s: s.start_minutes())
        breaks = sorted((s for s in self.spans if s.kind == "BREAK"), key=lambda s: s.start_minutes())
        if not work:
            raise ValueError("Bitte mindestens eine Arbeitszeit eintragen (eine Pause allein geht nicht).")
        for earlier, later in zip(work, work[1:]):
            if later.start_minutes() < earlier.end_minutes():
                raise ValueError("Die eingetragenen Zeiten überschneiden sich.")
        for earlier, later in zip(breaks, breaks[1:]):
            if later.start_minutes() < earlier.end_minutes():
                raise ValueError("Die eingetragenen Pausen überschneiden sich.")
        for pause in breaks:
            # Eine Pause liegt ganz innerhalb einer Arbeitszeit, nicht an deren Rand (sonst wäre es keine).
            if not any(w.start_minutes() < pause.start_minutes() and pause.end_minutes() < w.end_minutes() for w in work):
                raise ValueError("Eine Pause muss innerhalb einer Arbeitszeit liegen.")
        return self


class TimeSpanOut(BaseModel):
    """Wirksame Spanne (aus Stempelungen) oder beantragte Spanne (aus einem offenen Antrag)."""

    kind: Literal["WORK", "BREAK"]
    start: datetime
    # None = noch offen ("Kommen" ohne "Gehen")
    end: datetime | None
    source: PunchSource | None = None
    # Stempelung "Kommen" bzw. "Pause Start" (zum Löschen eigener Einträge)
    punch_id: int | None = None
    # Selbst löschbar (eigener Eintrag ohne Genehmigungspflicht, im erlaubten Zeitraum)
    deletable: bool = False
    # Projektzeiten (nur Arbeitszeiten)
    project_id: int | None = None
    note: str | None = None


class PendingTimeEntry(BaseModel):
    request_id: int
    spans: list[TimeSpanOut]
    comment: str | None = None
    created_at: datetime | None = None


class TimeEntryDay(BaseModel):
    work_date: date
    # Darf an diesem Tag eingetragen werden (Zeitraum, Beschäftigung, Monat nicht abgeschlossen)?
    can_enter: bool
    spans: list[TimeSpanOut] = []
    pending: list[PendingTimeEntry] = []
    # Ist-Zeit des Tages (nach Pausenregeln) – None, solange offen oder ohne Zeiten
    actual_minutes: int | None = None


class TimeEntryWeek(BaseModel):
    enabled: bool
    approval_required: bool
    backdate_days: int
    # Frühester Tag, der eingetragen werden darf (heute − backdate_days)
    earliest_date: date
    today: date
    timezone: str
    days: list[TimeEntryDay]
    # Projektzeiten: Auswahl (aktive Projekte mit Zeitraum), Pflicht und Namen für die Anzeige
    projects_enabled: bool = False
    project_required: bool = False
    projects: list[ProjectOption] = []
    project_names: dict[int, str] = {}


class TimeEntryResult(BaseModel):
    # APPLIED = sofort wirksam, PENDING = als Antrag unter „Zu klären“
    status: Literal["APPLIED", "PENDING"]
    request_id: int | None = None
    punch_ids: list[int] = []
