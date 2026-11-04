from pydantic import BaseModel, ConfigDict


class TeamCreateRequest(BaseModel):
    name: str
    location_id: int | None = None


class TeamUpdateRequest(BaseModel):
    name: str | None = None
    location_id: int | None = None
    clear_location_id: bool = False


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location_id: int | None
