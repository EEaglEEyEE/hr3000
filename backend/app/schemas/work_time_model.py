from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.rotation import ROTATION_MAX_WEEKS, ROTATION_MIN_WEEKS, monday_of
from app.schemas.break_rule import MAX_BREAK_WINDOWS, BreakWindow, check_window, check_windows
from app.schemas.core_time import CoreTimeDays, CoreTimeMode, FlexFrameDays, check_core_time, day_windows

# Gleitzeit-Rahmen eines Arbeitszeitmodells: TENANT = wie in den Einstellungen, CUSTOM = eigener,
# NONE = kein Rahmen.
FlexFrameMode = Literal["TENANT", "CUSTOM", "NONE"]


class WorkTimeModelInput(BaseModel):
    """Arbeitszeitmodell: entweder Wochenstunden gleichmäßig auf feste Arbeitstage verteilt
    (weekly_hours + weekdays) ODER Stunden je Wochentag (daily_hours, 7 Werte Mo..So, 0 = frei) –
    z.B. für Teilzeit Mo/Di 8 Std., Mi 4 Std. – ODER feste Monatsstunden (monthly_hours + weekdays):
    jeden Monat dasselbe Soll, gleichmäßig auf die Arbeitstage des jeweiligen Monats verteilt.
    ODER ein mehrwöchiger Turnus (rotation_weeks: 2–4 Wochen mit je 7 Werten Mo..So), der sich
    fortlaufend wiederholt. Feiertage und genehmigte Abwesenheiten werden mit dem Soll des jeweiligen
    Tages gutgeschrieben, Urlaubstage zählen nur an Arbeitstagen."""

    weekly_hours: float | None = Field(default=None, gt=0, le=60)
    # Festes Monatssoll (z.B. 108,5 Std.), unabhängig von der Zahl der Arbeitstage im Monat.
    monthly_hours: float | None = Field(default=None, gt=0, le=260)
    # 0 = Montag … 6 = Sonntag
    weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    daily_hours: list[float] | None = Field(default=None, min_length=7, max_length=7)
    # Mehrwöchiges Modell: Stunden je Wochentag für jede Woche des Turnus (2–4 Wochen, je 7 Werte
    # Mo..So, 0 = frei). Woche 1 beginnt am Montag der Woche von rotation_start, ohne Angabe am
    # Montag der Woche des Gültig-ab-Datums.
    rotation_weeks: list[list[float]] | None = Field(
        default=None, min_length=ROTATION_MIN_WEEKS, max_length=ROTATION_MAX_WEEKS
    )
    # "Turnus beginnt am": beliebiger Tag der Woche 1 (wird auf deren Montag gelegt).
    rotation_start: date | None = None
    # Flexibel (Aushilfe): nur Wochenstunden, keine festen Arbeitstage.
    flexible: bool = False
    # Nach Aufwand: kein Soll, Abrechnung nach Ist-Stunden; optional Monatsgrenze als Warnung.
    on_demand: bool = False
    monthly_cap_hours: float | None = Field(default=None, gt=0, le=400)
    # Mit dem Gehalt abgegoltene Überstunden je Kalendermonat (Stunden, 0/leer = keine): Mehrarbeit
    # eines Monats bis zu dieser Grenze wird dem Gleitzeitkonto nicht gutgeschrieben. Nicht bei
    # "nach Aufwand" (kein Konto).
    settled_overtime_hours: float | None = Field(default=None, ge=0, le=100)
    # Eigene Pause statt der betrieblichen Pausenregeln des Mandanten (die gesetzliche Staffel gilt
    # immer zusätzlich als Untergrenze): feste Minuten je Arbeitstag ODER feste Pausenzeit.
    break_minutes: int | None = Field(default=None, gt=0, le=240)
    # Feste Minuten erst ab dieser Arbeitszeit (Std.); leer = ab der ersten Minute
    break_after_hours: float | None = Field(default=None, ge=0, le=16)
    break_start: time | None = None
    break_end: time | None = None
    # Mehrere feste Pausenzeiten (z.B. 09:00–09:15 und 12:00–12:30) statt break_start/break_end;
    # eine einzelne wird zu break_start/break_end.
    break_windows: list[BreakWindow] | None = Field(default=None, min_length=1, max_length=MAX_BREAK_WINDOWS)
    # Uhrzeiten aus einer Schichtvorlage (optional): Beginn/Ende für Schichtplan, Pünktlichkeit und
    # Ruhezeit-Prüfung. Das Soll bleibt das des Modells; ohne eigene Pause gilt die der Vorlage.
    shift_template_id: int | None = Field(default=None, ge=1)
    # Kernzeit/Pünktlichkeit dieser Fassung; leer = unverändert (wie die bisherige Fassung, sonst wie
    # in den Einstellungen).
    core_time_mode: CoreTimeMode | None = None
    core_time_start: time | None = None
    core_time_end: time | None = None
    # Eigene Kernzeit je Wochentag (nur bei CUSTOM); null = jeden Tag dieselbe.
    core_time_days: CoreTimeDays = None
    # Gleitzeit-Rahmen dieser Fassung; leer = unverändert (wie die bisherige Fassung, sonst wie in den
    # Einstellungen). Arbeitszeitmodelle setzen ihn immer (Standard: wie in den Einstellungen).
    flex_frame_mode: FlexFrameMode | None = None
    flex_frame_start: time | None = None
    flex_frame_end: time | None = None
    # Eigener Rahmen je Wochentag (nur bei CUSTOM, Tag ohne Eintrag = an diesem Tag kein Rahmen);
    # null = jeden Tag derselbe.
    flex_frame_days: FlexFrameDays = None

    @model_validator(mode="after")
    def _core_time(self) -> "WorkTimeModelInput":
        check_core_time(self.core_time_mode, self.core_time_start, self.core_time_end, self.core_time_days)
        return self

    @model_validator(mode="after")
    def _flex_frame(self) -> "WorkTimeModelInput":
        if self.flex_frame_mode != "CUSTOM":
            self.flex_frame_start = self.flex_frame_end = None
            self.flex_frame_days = None
            return self
        if self.flex_frame_days is not None:
            self.flex_frame_start = self.flex_frame_end = None  # je Tag geprüft, siehe FlexFrameDay
        elif self.flex_frame_start is None or self.flex_frame_end is None:
            raise ValueError("Für einen eigenen Gleitzeit-Rahmen bitte Beginn und Ende angeben.")
        elif self.flex_frame_start >= self.flex_frame_end:
            raise ValueError("Gleitzeit-Rahmen: der Beginn muss vor dem Ende liegen.")
        if self.core_time_mode == "CUSTOM":
            core = day_windows(self.core_time_days, self.core_time_start, self.core_time_end)
            frame = day_windows(self.flex_frame_days, self.flex_frame_start, self.flex_frame_end)
            if any(c and f and not (f[0] <= c[0] and c[1] <= f[1]) for c, f in zip(core, frame)):
                per_day = self.core_time_days is not None or self.flex_frame_days is not None
                raise ValueError(
                    "Die Kernzeit muss an jedem Tag innerhalb des Gleitzeit-Rahmens liegen."
                    if per_day
                    else "Die Kernzeit muss innerhalb des Gleitzeit-Rahmens liegen."
                )
        return self

    @model_validator(mode="after")
    def _break(self) -> "WorkTimeModelInput":
        if self.break_windows is not None:
            if self.break_start is not None or self.break_end is not None:
                raise ValueError("Feste Pausenzeiten entweder als Liste oder als eine Pausenzeit angeben.")
            if self.break_minutes is not None:
                raise ValueError("Pause entweder als feste Minuten oder als feste Uhrzeit angeben.")
            ordered = check_windows([(w.start, w.end) for w in self.break_windows])
            if len(ordered) == 1:
                (self.break_start, self.break_end), self.break_windows = ordered[0], None
            else:
                self.break_windows = [BreakWindow(start=start, end=end) for start, end in ordered]
        if self.break_start is not None or self.break_end is not None:
            if self.break_minutes is not None:
                raise ValueError("Pause entweder als feste Minuten oder als feste Uhrzeit angeben.")
            check_window(self.break_start, self.break_end)
        if self.break_after_hours is not None and self.break_minutes is None:
            raise ValueError("„ab … Std.“ gibt es nur zusammen mit festen Pausenminuten.")
        if self.break_after_hours == 0:
            self.break_after_hours = None
        return self

    @property
    def break_after_minutes(self) -> int:
        return round(self.break_after_hours * 60) if self.break_after_hours else 0

    @property
    def break_window_list(self) -> list[tuple[time, time]]:
        """Alle festen Pausenzeiten (leer = keine feste Uhrzeit)."""
        if self.break_windows is not None:
            return [(w.start, w.end) for w in self.break_windows]
        if self.break_start is not None and self.break_end is not None:
            return [(self.break_start, self.break_end)]
        return []

    @property
    def break_label(self) -> str:
        """Namenszusatz der Vorlage bzw. Audit-Text, z.B. ", Pause 30 Min. ab 6 Std." / ", Pause 12:00–12:30"."""
        if self.break_minutes is not None:
            after = f" ab {self.break_after_hours:g} Std." if self.break_after_hours else ""
            return f", Pause {self.break_minutes} Min.{after}"
        windows = self.break_window_list
        if windows:
            return ", Pause " + ", ".join(f"{start:%H:%M}–{end:%H:%M}" for start, end in windows)
        return ""

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Wochentage müssen zwischen 0 (Montag) und 6 (Sonntag) liegen.")
        if len(set(value)) != len(value):
            raise ValueError("Wochentage dürfen nicht doppelt vorkommen.")
        return sorted(value)

    @field_validator("daily_hours")
    @classmethod
    def _valid_daily(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if any(h < 0 or h > 24 for h in value):
            raise ValueError("Stunden je Tag müssen zwischen 0 und 24 liegen.")
        if not any(round(h * 60) > 0 for h in value):
            raise ValueError("Mindestens ein Tag braucht Stunden.")
        return value

    @field_validator("rotation_weeks")
    @classmethod
    def _valid_rotation(cls, value: list[list[float]] | None) -> list[list[float]] | None:
        if value is None:
            return value
        if any(len(week) != 7 for week in value):
            raise ValueError("Jede Woche des Turnus braucht sieben Werte (Montag bis Sonntag).")
        if any(h < 0 or h > 24 for week in value for h in week):
            raise ValueError("Stunden je Tag müssen zwischen 0 und 24 liegen.")
        if not any(round(h * 60) > 0 for week in value for h in week):
            raise ValueError("Mindestens ein Tag braucht Stunden.")
        if any(round(sum(week), 4) > 60 for week in value):
            raise ValueError("Mehr als 60 Wochenstunden sind nicht möglich.")
        return value

    @field_validator("rotation_start")
    @classmethod
    def _valid_rotation_start(cls, value: date | None) -> date | None:
        if value is None:
            return value
        if not (2000 <= value.year <= 2100):
            raise ValueError("„Turnus beginnt am“ muss zwischen 2000 und 2100 liegen.")
        return monday_of(value)

    @model_validator(mode="after")
    def _settled_overtime(self) -> "WorkTimeModelInput":
        if self.on_demand and self.settled_overtime_minutes:
            raise ValueError("Bei „Nach Aufwand“ gibt es kein Überstundenkonto und keine abgegoltenen Überstunden.")
        return self

    @model_validator(mode="after")
    def _derive(self) -> "WorkTimeModelInput":
        if self.rotation_weeks is not None:
            if self.flexible or self.on_demand or self.monthly_hours is not None:
                raise ValueError(
                    "Ein mehrwöchiges Modell lässt sich nicht mit flexibel, nach Aufwand oder Monatsstunden verbinden."
                )
            self.monthly_cap_hours = None
            self.daily_hours = None
            # Arbeitstage = alle Tage, die in irgendeiner Woche Stunden haben; Wochenstunden = Durchschnitt.
            self.weekdays = [
                day for day in range(7) if any(round(week[day] * 60) > 0 for week in self.rotation_weeks)
            ]
            self.weekly_hours = round(sum(sum(week) for week in self.rotation_weeks) / len(self.rotation_weeks), 4)
            return self
        if self.rotation_start is not None:
            raise ValueError("„Turnus beginnt am“ gibt es nur beim mehrwöchigen Modell.")
        if self.on_demand:
            if self.flexible:
                raise ValueError("Ein Modell ist entweder flexibel oder nach Aufwand.")
            self.weekly_hours = None
            self.monthly_hours = None
            self.weekdays = []
            self.daily_hours = None
            return self
        self.monthly_cap_hours = None
        if self.monthly_hours is not None:
            if self.flexible:
                raise ValueError("Monatsstunden gibt es nur mit festen Arbeitstagen.")
            if not self.weekdays:
                raise ValueError("Bitte Monatsstunden und Arbeitstage angeben.")
            if round(self.monthly_hours * 60) < 1:
                raise ValueError("Monatsstunden sind zu klein.")
            self.weekly_hours = None
            self.daily_hours = None
            return self
        if self.flexible:
            if self.weekly_hours is None:
                raise ValueError("Für ein flexibles Modell sind Wochenstunden nötig.")
            self.weekdays = [0, 1, 2, 3, 4]
            self.daily_hours = None
            return self
        if self.daily_hours is not None:
            self.weekdays = [day for day, h in enumerate(self.daily_hours) if round(h * 60) > 0]
            self.weekly_hours = round(sum(self.daily_hours), 4)
            if self.weekly_hours > 60:
                raise ValueError("Mehr als 60 Wochenstunden sind nicht möglich.")
        elif self.weekly_hours is None or not self.weekdays:
            raise ValueError("Bitte Wochenstunden und Arbeitstage oder Stunden je Wochentag angeben.")
        elif round(self.weekly_hours * 60) < 1:
            raise ValueError("Wochenstunden sind zu klein.")
        return self

    @property
    def settled_overtime_minutes(self) -> int | None:
        """Abgegoltene Überstunden je Monat in Minuten (None = keine, auch bei 0)."""
        if self.settled_overtime_hours is None:
            return None
        return round(self.settled_overtime_hours * 60) or None

    @property
    def monthly_cap_minutes(self) -> int | None:
        return round(self.monthly_cap_hours * 60) if self.monthly_cap_hours is not None else None

    @property
    def monthly_minutes(self) -> int | None:
        return round(self.monthly_hours * 60) if self.monthly_hours is not None else None

    @property
    def day_minutes(self) -> list[int] | None:
        return [round(h * 60) for h in self.daily_hours] if self.daily_hours is not None else None

    @property
    def rotation_minutes(self) -> list[list[int]] | None:
        """Soll-Minuten je Turnus-Woche und Wochentag (None = kein mehrwöchiges Modell)."""
        if self.rotation_weeks is None:
            return None
        return [[round(h * 60) for h in week] for week in self.rotation_weeks]

    @property
    def exceeds_daily_maximum(self) -> bool:
        """§3 ArbZG: mehr als 10 Std. je Arbeitstag (geprüft mit fachlicher Meldung, siehe API)."""
        if self.flexible or self.on_demand:
            return False  # keine festen Tage – Tagesgrenze wird erst beim Stempeln geprüft
        if self.rotation_weeks is not None:
            return any(m > 600 for week in self.rotation_minutes for m in week)
        if self.daily_hours is not None:
            return any(m > 600 for m in self.day_minutes)
        if self.monthly_hours is not None:
            # Jeder Wochentag kommt in einem Monat mindestens viermal vor (ungünstigster Monat).
            return self.monthly_minutes / (4 * len(self.weekdays)) > 600
        return round(self.weekly_hours * 60) / len(self.weekdays) > 600


class WorkTimeModelSetRequest(WorkTimeModelInput):
    valid_from: date

    @classmethod
    def from_input(cls, model: WorkTimeModelInput, valid_from: date) -> "WorkTimeModelSetRequest":
        """Ein bereits geprüftes Modell (z.B. aus Anlegen-Dialog oder Import) ab Stichtag setzen –
        mit allen Feldern (Monatsstunden, Pause, …)."""
        data = model.model_dump(exclude_none=True)
        if not data.get("weekdays"):
            data.pop("weekdays", None)  # "nach Aufwand" hat keine Arbeitstage
        return cls(**data, valid_from=valid_from)


class WorkTimeModelFields(BaseModel):
    """Beschreibung einer Fassung: Soll, Pause, Uhrzeiten (Schichtvorlage) und Kernzeit."""

    # In der Antwort sind alle Felder immer vorhanden (OpenAPI: required) – auch die mit Standardwert.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    weekly_minutes: int | None = None
    daily_minutes: int | None = None
    weekdays: list[int] = []
    # Soll-Minuten je Wochentag (Mo..So) – bei ungleich verteilten Stunden maßgeblich.
    day_minutes: list[int] | None = None
    uneven: bool = False
    # Mehrwöchiges Modell: Soll-Minuten je Turnus-Woche (je 7 Werte Mo..So) und der Montag der
    # Woche 1; weekly_minutes ist dann der Durchschnitt, weekdays alle Tage mit Soll in irgendeiner Woche.
    rotation_minutes: list[list[int]] | None = None
    rotation_start: date | None = None
    # Mit dem Gehalt abgegoltene Überstunden je Kalendermonat (Minuten, None = keine)
    settled_overtime_minutes: int | None = None
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_minutes: int | None = None
    # Festes Monatssoll (Tagessoll schwankt dann je nach Zahl der Arbeitstage im Monat).
    monthly_minutes: int | None = None
    # True = ältere Standard-Schicht: das Soll kommt (noch) aus der Schichtvorlage; beim nächsten
    # Speichern im Arbeitszeitmodell wird es fest übernommen.
    target_from_template: bool = False
    # Pause dieser Fassung (leer = Pausenregeln); break_from_template = Pause der Schichtvorlage.
    break_minutes: int | None = None
    break_after_minutes: int = 0
    break_start: time | None = None
    break_end: time | None = None
    # Alle festen Pausenzeiten (auch eine einzelne); leer = keine feste Uhrzeit
    break_windows: list[BreakWindow] | None = None
    break_from_template: bool = False
    # Schichtvorlage für die Uhrzeiten (optional)
    shift_template_id: int | None = None
    shift_template_name: str | None = None
    shift_start: time | None = None
    shift_end: time | None = None
    # Kernzeit/Pünktlichkeit: TENANT = wie Einstellungen, CUSTOM = eigene, NONE = keine Prüfung
    core_time_mode: CoreTimeMode = "TENANT"
    core_time_start: time | None = None
    core_time_end: time | None = None
    core_time_days: CoreTimeDays = None
    # Gleitzeit-Rahmen (auch je Wochentag) und Toleranz (eigene Toleranz nur aus einem
    # Arbeitszeitmodell; leer = wie Einstellungen)
    flex_frame_mode: FlexFrameMode = "TENANT"
    flex_frame_start: time | None = None
    flex_frame_end: time | None = None
    flex_frame_days: FlexFrameDays = None
    late_tolerance_minutes: int | None = None
    # Zugewiesenes Arbeitszeitmodell (leer = individuell eingetragen)
    profile_id: int | None = None
    profile_name: str | None = None


class WorkTimeModelResponse(WorkTimeModelFields):
    employee_id: int
    # False = für heute ist gar keine Fassung hinterlegt.
    configured: bool
    valid_from: date | None


class WorkTimeModelVersion(WorkTimeModelFields):
    """Eine Fassung des Arbeitszeitmodells mit Gültigkeitszeitraum (Historie)."""

    id: int
    valid_from: date
    valid_to: date | None


class WorkTimeProfileInput(WorkTimeModelInput):
    """Angaben eines Arbeitszeitmodells: wie ein Arbeitszeitmodell, dazu die Pünktlichkeits-Toleranz
    (leer = wie in den Einstellungen). Der Gleitzeit-Rahmen ist hier immer gesetzt (Standard: wie in
    den Einstellungen)."""

    flex_frame_mode: FlexFrameMode = "TENANT"
    late_tolerance_minutes: int | None = Field(default=None, ge=0, le=120)


class WorkTimeProfileCreateRequest(WorkTimeProfileInput):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bitte einen Namen angeben.")
        return value


class WorkTimeProfileSetRequest(WorkTimeProfileInput):
    """Neue Fassung des Modells ab Stichtag – gilt für alle zugewiesenen Mitarbeiter."""

    valid_from: date


class WorkTimeProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Bitte einen Namen angeben.")
        return value


class WorkTimeProfileResponse(WorkTimeModelFields):
    """Modell mit der heute gültigen Fassung und den aktuell zugewiesenen Mitarbeitern."""

    id: int
    name: str
    archived: bool
    valid_from: date
    employee_count: int
    employees: list[str] = []


class WorkTimeProfileVersionResponse(WorkTimeModelFields):
    id: int
    valid_from: date
    valid_to: date | None


class WorkTimeProfileAssignRequest(BaseModel):
    """Modell einem Mitarbeiter ab Stichtag zuweisen (ersetzt alles ab diesem Tag)."""

    profile_id: int = Field(ge=1)
    valid_from: date
