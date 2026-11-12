from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.holiday_calendar import Bundesland
from app.services.punch_location_service import MAX_RADIUS_M, MIN_RADIUS_M

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


class _GeofenceFields(BaseModel):
    """Kreis für die Standortprüfung beim Stempeln (A18): Mittelpunkt und Radius nur zusammen."""

    geo_latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    geo_longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    geo_radius_m: int | None = Field(default=None, ge=MIN_RADIUS_M, le=MAX_RADIUS_M)

    @model_validator(mode="after")
    def _all_or_nothing(self):
        given = [v is not None for v in (self.geo_latitude, self.geo_longitude, self.geo_radius_m)]
        if any(given) and not all(given):
            raise ValueError("Kreis: bitte Breite, Länge und Radius angeben.")
        return self


class LocationCreateRequest(_GeofenceFields):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="Europe/Berlin", max_length=64)
    bundesland: Bundesland | None = None

    _name = field_validator("name")(_clean_name)
    _tz = field_validator("timezone")(_valid_timezone)


class LocationUpdateRequest(_GeofenceFields):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    bundesland: Bundesland | None = None
    clear_bundesland: bool = False
    # Kreis entfernen (Standort zählt dann nicht mehr für die Standortprüfung)
    clear_geofence: bool = False

    _name = field_validator("name")(_clean_name)
    _tz = field_validator("timezone")(_valid_timezone)

    @model_validator(mode="after")
    def _set_or_clear(self):
        if self.clear_geofence and self.geo_radius_m is not None:
            raise ValueError("Kreis: entweder neu setzen oder entfernen.")
        return self


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    timezone: str
    bundesland: Bundesland | None
    geo_latitude: float | None = None
    geo_longitude: float | None = None
    geo_radius_m: int | None = None
