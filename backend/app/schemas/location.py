from pydantic import BaseModel, ConfigDict

from app.services.holiday_calendar import Bundesland


class LocationCreateRequest(BaseModel):
    name: str
    timezone: str
    bundesland: Bundesland | None = None


class LocationUpdateRequest(BaseModel):
    name: str | None = None
    timezone: str | None = None
    bundesland: Bundesland | None = None
    clear_bundesland: bool = False


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    timezone: str
    bundesland: Bundesland | None
