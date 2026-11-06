from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.break_rule import check_window
from app.schemas.core_time import CoreTimeDays, CoreTimeMode, check_core_time


class WorkTimeModelInput(BaseModel):
    """Arbeitszeitmodell: entweder Wochenstunden gleichmäßig auf feste Arbeitstage verteilt
    (weekly_hours + weekdays) ODER Stunden je Wochentag (daily_hours, 7 Werte Mo..So, 0 = frei) –
    z.B. für Teilzeit Mo/Di 8 Std., Mi 4 Std. – ODER feste Monatsstunden (monthly_hours + weekdays):
    jeden Monat dasselbe Soll, gleichmäßig auf die Arbeitstage des jeweiligen Monats verteilt.
    Feiertage und genehmigte Abwesenheiten werden mit dem Soll des jeweiligen Tages
    gutgeschrieben, Urlaubstage zählen nur an Arbeitstagen."""

    weekly_hours: float | None = Field(default=None, gt=0, le=60)
    # Festes Monatssoll (z.B. 108,5 Std.), unabhängig von der Zahl der Arbeitstage im Monat.
    monthly_hours: float | None = Field(default=None, gt=0, le=260)
    # 0 = Montag … 6 = Sonntag
    weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    daily_hours: list[float] | None = Field(default=None, min_length=7, max_length=7)
    # Flexibel (Aushilfe): nur Wochenstunden, keine festen Arbeitstage.
    flexible: bool = False
    # Nach Aufwand: kein Soll, Abrechnung nach Ist-Stunden; optional Monatsgrenze als Warnung.
    on_demand: bool = False
    monthly_cap_hours: float | None = Field(default=None, gt=0, le=400)
    # Eigene Pause statt der betrieblichen Pausenregeln des Mandanten (die gesetzliche Staffel gilt
    # immer zusätzlich als Untergrenze): feste Minuten je Arbeitstag ODER feste Pausenzeit.
    break_minutes: int | None = Field(default=None, gt=0, le=240)
    # Feste Minuten erst ab dieser Arbeitszeit (Std.); leer = ab der ersten Minute
    break_after_hours: float | None = Field(default=None, ge=0, le=16)
    break_start: time | None = None
    break_end: time | None = None
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

    @model_validator(mode="after")
    def _core_time(self) -> "WorkTimeModelInput":
        check_core_time(self.core_time_mode, self.core_time_start, self.core_time_end, self.core_time_days)
        return self

    @model_validator(mode="after")
    def _break(self) -> "WorkTimeModelInput":
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
    def break_label(self) -> str:
        """Namenszusatz der Vorlage bzw. Audit-Text, z.B. ", Pause 30 Min. ab 6 Std." / ", Pause 12:00–12:30"."""
        if self.break_minutes is not None:
            after = f" ab {self.break_after_hours:g} Std." if self.break_after_hours else ""
            return f", Pause {self.break_minutes} Min.{after}"
        if self.break_start is not None and self.break_end is not None:
            return f", Pause {self.break_start:%H:%M}–{self.break_end:%H:%M}"
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

    @model_validator(mode="after")
    def _derive(self) -> "WorkTimeModelInput":
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
    def monthly_cap_minutes(self) -> int | None:
        return round(self.monthly_cap_hours * 60) if self.monthly_cap_hours is not None else None

    @property
    def monthly_minutes(self) -> int | None:
        return round(self.monthly_hours * 60) if self.monthly_hours is not None else None

    @property
    def day_minutes(self) -> list[int] | None:
        return [round(h * 60) for h in self.daily_hours] if self.daily_hours is not None else None

    @property
    def exceeds_daily_maximum(self) -> bool:
        """§3 ArbZG: mehr als 10 Std. je Arbeitstag (geprüft mit fachlicher Meldung, siehe API)."""
        if self.flexible or self.on_demand:
            return False  # keine festen Tage – Tagesgrenze wird erst beim Stempeln geprüft
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
