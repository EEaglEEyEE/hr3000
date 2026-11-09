from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.punch import PunchSource, PunchType


class PunchCreateRequest(BaseModel):
    employee_id: int
    punch_type: PunchType
    timestamp_utc: datetime
    idempotency_key: str
    pin: str | None = None
    # Alternative zum PIN: NFC-Karten-UID, siehe app/api/punches.py create_punch.
    nfc_uid: str | None = None


class OwnPunchRequest(BaseModel):
    """Stempeln über den Web-Login: nur die Art – Zeitpunkt ist immer die Serverzeit."""

    punch_type: PunchType


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


class PunchCorrectionRequest(BaseModel):
    punch_type: PunchType | None = None
    timestamp_utc: datetime | None = None
    correction_reason: str
