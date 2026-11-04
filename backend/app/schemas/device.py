from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import normalize_card_uid


class DeviceCreateRequest(BaseModel):
    location_id: int
    name: str = Field(min_length=1, max_length=255)


class DeviceUpdateRequest(BaseModel):
    location_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    regenerate_token: bool = False
    # DEFAULT = Standard des Mandanten verwenden
    theme: Literal["DEFAULT", "DARK", "LIGHT"] | None = None
    # Bildschirmzeiten: DEFAULT = wie Einstellungen, ALWAYS = immer an, CUSTOM = eigene Zeiten
    screen_hours_mode: Literal["DEFAULT", "ALWAYS", "CUSTOM"] | None = None
    screen_on_from: time | None = None
    screen_on_until: time | None = None

    @model_validator(mode="after")
    def _valid_screen_hours(self) -> "DeviceUpdateRequest":
        if self.screen_hours_mode == "CUSTOM":
            if self.screen_on_from is None or self.screen_on_until is None:
                raise ValueError("Eigene Bildschirmzeiten: bitte „von“ und „bis“ angeben.")
            if self.screen_on_from == self.screen_on_until:
                raise ValueError("Eigene Bildschirmzeiten: „von“ und „bis“ dürfen nicht gleich sein.")
        return self


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: int
    name: str
    device_token: str
    last_seen: datetime | None
    theme: str | None = None
    screen_hours_mode: str | None = None
    screen_on_from: time | None = None
    screen_on_until: time | None = None


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    # Adresse der Kiosk-App für den QR-Code (kiosk.firma.hr3000.de bzw. altes Schema bei
    # fest eingetragenen Hosts); None = nicht ableitbar (z.B. localhost), dann nur das Token.
    kiosk_url: str | None = None


class CardRegistrationRequest(BaseModel):
    employee_id: int
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")
    nfc_uid: str = Field(min_length=4, max_length=64)

    @field_validator("nfc_uid")
    @classmethod
    def _normalize(cls, value: str) -> str:
        cleaned = normalize_card_uid(value) or ""
        if len(cleaned) < 4 or not cleaned.isalnum():
            raise ValueError("Ungültige Chipnummer.")
        return cleaned


class PinSetupRequest(BaseModel):
    employee_id: int
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class DevicePairRequest(BaseModel):
    code: str = Field(min_length=8, max_length=12)


class DevicePairResponse(BaseModel):
    device_token: str
