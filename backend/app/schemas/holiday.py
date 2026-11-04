import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.services.holiday_calendar import Bundesland


class HolidayCreateRequest(BaseModel):
    date: dt.date
    name: str = Field(min_length=1, max_length=200)
    # Leer = für alle Standorte gültig, sonst nur für die genannten.
    location_ids: list[int] = Field(default_factory=list, max_length=200)


class HolidayUpdateRequest(BaseModel):
    date: dt.date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    # None = Standorte unverändert, [] = ab sofort für alle Standorte.
    location_ids: list[int] | None = Field(default=None, max_length=200)


class HolidayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    name: str
    # Leer = gilt für alle Standorte.
    location_ids: list[int]


class HolidayImportRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    # None = für alle Standorte importieren (firmenweite Feiertage).
    location_id: int | None = None
    # None -> Bundesland des Standorts, sonst AppSettings.default_bundesland verwenden.
    bundesland: Bundesland | None = None


class HolidayImportResponse(BaseModel):
    imported: list[HolidayResponse]
    skipped_existing: int
