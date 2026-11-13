from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import normalize_card_uid


def clean_mdm_name(value: str | None) -> str | None:
    """Gerätename aus dem MDM: getrimmt, leer = keiner. Nicht ersetzte Platzhalter ({{devicename}},
    %DeviceName%, $env:COMPUTERNAME) zählen als „kein Name“ statt als Name."""
    if value is None:
        return None
    value = value.strip()
    if not value or (value.startswith("{{") and value.endswith("}}")) or (
        len(value) > 1 and value.startswith("%") and value.endswith("%")
    ) or value.startswith("$"):
        return None
    if any(ord(ch) < 32 or ch in "<>" for ch in value):
        raise ValueError("Der Gerätename enthält unzulässige Zeichen.")
    return value


class DeviceCreateRequest(BaseModel):
    location_id: int
    name: str = Field(min_length=1, max_length=255)
    # Gerätename im MDM (optional): bindet ein per Registrierungsschlüssel startendes Gerät ohne Freigabe
    mdm_name: str | None = Field(default=None, max_length=100)

    @field_validator("mdm_name")
    @classmethod
    def _clean_mdm_name(cls, value: str | None) -> str | None:
        return clean_mdm_name(value)


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
    # Nur wenn mitgeschickt: neuer Gerätename im MDM, leer = entfernen
    mdm_name: str | None = Field(default=None, max_length=100)

    @field_validator("mdm_name")
    @classmethod
    def _clean_mdm_name(cls, value: str | None) -> str | None:
        return clean_mdm_name(value)

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
    last_seen: datetime | None
    # Gebunden an ein Tablet seit (None = noch kein Tablet angemeldet)
    bound_at: datetime | None = None
    # Letzter abgewiesener Versuch eines anderen Geräts
    rejected_at: datetime | None = None
    theme: str | None = None
    screen_hours_mode: str | None = None
    screen_on_from: time | None = None
    screen_on_until: time | None = None
    mdm_name: str | None = None


class PairingCodeRequest(BaseModel):
    """QR-Code für ein Tablet, das schon mit einem Gerät verbunden ist, nur mit ausdrücklichem
    replace_bound: Koppeln meldet das bisherige Gerät ab (Tablet-Tausch)."""

    model_config = ConfigDict(extra="forbid")

    replace_bound: bool = False


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
    installation_id: str = Field(min_length=16, max_length=100)


class DevicePairResponse(BaseModel):
    device_token: str


class DeviceEnrollRequest(BaseModel):
    """Selbstregistrierung eines Tablets mit dem Registrierungsschlüssel aus der MDM-Start-URL."""

    key: str = Field(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    installation_id: str = Field(min_length=16, max_length=100)
    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        return clean_mdm_name(value)


class DeviceEnrollResponse(BaseModel):
    # BOUND = an einen Tablet-Eintrag gebunden, PENDING = wartet auf Freigabe in der Webapp
    status: Literal["BOUND", "PENDING"]
    device_token: str
    # Prüfcode für den Abgleich bei der Freigabe (nur PENDING)
    verify_code: str | None = None


class EnrollmentKeyCreateRequest(BaseModel):
    location_id: int
    # None = unbefristet
    valid_days: int | None = Field(default=30, ge=1, le=365)


class EnrollmentKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    location_id: int
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class EnrollmentKeyCreatedResponse(EnrollmentKeyResponse):
    # Nur jetzt sichtbar – gespeichert wird nur der Hash
    key: str
    # Start-URL für das MDM (ohne Gerätenamen); None, wenn sich die Kiosk-Adresse nicht ableiten lässt
    enroll_url: str | None = None


class DeviceEnrollmentResponse(BaseModel):
    id: int
    location_id: int
    reported_name: str | None
    verify_code: str
    created_at: datetime
    last_seen_at: datetime | None
    # Es gibt schon einen benutzten Tablet-Eintrag mit diesem Gerätenamen (möglicher Doppelgänger)
    conflict_device_name: str | None = None
    # Das Gerät wartet gerade (meldet sich jede Minute); False = meldet sich nicht mehr
    active: bool = True
    # Herkunft der Anfrage: Browser und System (aus der Browser-Kennung) und IP-Adresse – ungeprüft
    client: str | None = None
    client_ip: str | None = None


class EnrollmentCleanupResponse(BaseModel):
    removed: int


class EnrollmentApproveRequest(BaseModel):
    # Vorhandenen Tablet-Eintrag (gleicher Standort) übernehmen; None = neuen Eintrag anlegen
    device_id: int | None = None
    # Name eines neuen Eintrags (Standard: gemeldeter Gerätename)
    name: str | None = Field(default=None, min_length=1, max_length=255)
