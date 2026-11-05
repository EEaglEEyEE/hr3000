from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


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


class WorkTimeModelResponse(BaseModel):
    employee_id: int
    # False = für heute ist gar keine Standard-Zuordnung hinterlegt.
    configured: bool
    # False = es gilt eine echte Schichtvorlage (siehe Schichtplanung), kein einfaches Modell.
    is_work_time_model: bool
    template_name: str | None
    weekly_minutes: int | None
    daily_minutes: int | None
    weekdays: list[int]
    # Soll-Minuten je Wochentag (Mo..So) – bei ungleich verteilten Stunden maßgeblich.
    day_minutes: list[int] | None = None
    uneven: bool = False
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_minutes: int | None = None
    # Festes Monatssoll (Tagessoll schwankt dann je nach Zahl der Arbeitstage im Monat).
    monthly_minutes: int | None = None
    valid_from: date | None


class WorkTimeModelVersion(BaseModel):
    """Eine Fassung des Arbeitszeitmodells mit Gültigkeitszeitraum (Historie)."""

    id: int
    valid_from: date
    valid_to: date | None
    template_name: str
    # False = echte Schichtvorlage (Schichtplanung) – dort bearbeiten, nicht hier.
    is_work_time_model: bool
    weekly_minutes: int | None
    daily_minutes: int | None
    weekdays: list[int]
    day_minutes: list[int] | None = None
    uneven: bool = False
    flexible: bool = False
    on_demand: bool = False
    monthly_cap_minutes: int | None = None
    monthly_minutes: int | None = None
