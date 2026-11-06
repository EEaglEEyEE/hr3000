from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.holiday_calendar import Bundesland

_TIMEZONES = available_timezones()


def _valid_timezone(value: str | None) -> str | None:
    if value is not None and value not in _TIMEZONES:
        raise ValueError("Unbekannte Zeitzone – bitte z. B. Europe/Berlin angeben.")
    return value


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    if not value:
        raise ValueError("Bitte einen Namen angeben.")
    return value


class LocationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="Europe/Berlin", max_length=64)
    bundesland: Bundesland | None = None

    _name = field_validator("name")(_clean_name)
    _tz = field_validator("timezone")(_valid_timezone)


class LocationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    bundesland: Bundesland | None = None
    clear_bundesland: bool = False

    _name = field_validator("name")(_clean_name)
    _tz = field_validator("timezone")(_valid_timezone)


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    timezone: str
    bundesland: Bundesland | None
