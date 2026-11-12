from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.punch import PunchSource, PunchType
from app.models.punch_location import PunchLocationCheck
from app.services.punch_location_service import MAX_ACCURACY_M


class PunchCreateRequest(BaseModel):
    employee_id: int
    punch_type: PunchType
    timestamp_utc: datetime
    idempotency_key: str
    pin: str | None = None
    # Alternative zum PIN: NFC-Karten-UID, siehe app/api/punches.py create_punch.
    nfc_uid: str | None = None


class PunchPosition(BaseModel):
    """Position des Browsers im Moment des Stempelns (navigator.geolocation). Wird nur ausgewertet,
    nie gespeichert oder protokolliert – siehe app/services/punch_location_service.py."""

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    # Ungenauigkeit in Metern, wie sie der Browser meldet (coords.accuracy)
    accuracy_m: float = Field(ge=0, le=MAX_ACCURACY_M, allow_inf_nan=False)


class OwnPunchRequest(BaseModel):
    """Stempeln über den Web-Login: nur die Art – Zeitpunkt ist immer die Serverzeit."""

    punch_type: PunchType
    # Nur bei eingeschalteter Standortprüfung nötig; sonst wird sie ignoriert.
    position: PunchPosition | None = None


class PunchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    location_id: int
    punch_type: PunchType
    timestamp_utc: datetime
    source: PunchSource
    device_id: int | None
    created_by_account_id: int | None
    corrected: bool
    correction_reason: str | None
    # Standortprüfung beim Stempeln im Web-Login (None = nicht geprüft)
    location_check: PunchLocationCheck | None = None
    location_check_location_id: int | None = None
    # Projektzeiten (am "Kommen")
    project_id: int | None = None
    activity_note: str | None = None


class PunchCorrectionRequest(BaseModel):
    punch_type: PunchType | None = None
    timestamp_utc: datetime | None = None
    correction_reason: str
    # Projektzeiten: nur am "Kommen"; null (mitgeschickt) = kein Projekt
    project_id: int | None = Field(default=None, ge=1)
    activity_note: str | None = Field(default=None, max_length=200)
