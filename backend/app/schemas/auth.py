from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class DeviceLoginRequest(BaseModel):
    device_token: str = Field(max_length=200)
    # Zufällige ID der Tablet-Installation (vom Tablet einmal erzeugt) – bindet den Zugang an ein Gerät
    installation_id: str | None = Field(default=None, min_length=16, max_length=100)


class KioskConfigResponse(BaseModel):
    """Anzeige-/Verhaltenseinstellungen des Tablets (Einstellungen → Kiosk)."""

    require_pin: bool
    rfid_required: bool = False
    # Chip-Funktion am Tablet (Terminalmodus, Mitarbeiter per Chip öffnen)
    rfid_enabled: bool = True
    # Mitarbeiter dürfen ihren Chip am Tablet selbst registrieren (nur mit PIN)
    card_self_registration: bool = True
    # Ohne PIN: beim ersten Stempeln am Tablet selbst festlegen (nur bei PIN-Pflicht relevant)
    pin_self_setup: bool = True
    show_balance: bool = True
    show_vacation: bool = True
    break_buttons: bool = True
    errand_buttons: bool = False
    greeting: str | None = None
    sort: str = "LAST_NAME"
    theme: str = "DARK"
    # Bildschirm nur in diesem Fenster wach halten ("HH:MM", Gerät vor Mandant aufgelöst);
    # beide None = immer an. von > bis = über Mitternacht.
    screen_on_from: str | None = None
    screen_on_until: str | None = None
    # IANA-Zeitzone des Standorts des Tablets (maßgeblich für die Bildschirmzeiten)
    timezone: str = "Europe/Berlin"


class DeviceLoginResponse(KioskConfigResponse):
    access_token: str
    token_type: str = "bearer"
    location_id: int
    device_name: str
    # Salz für die Chip-Hashes in der Mitarbeiterliste (card_hash = SHA-256(card_salt + UID))
    card_salt: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Ohne Zwei-Faktor-Anmeldung die Tokens; sonst two_factor = "required" (Code eingeben) bzw.
    "setup" (Pflicht, noch einzurichten) mit einem kurzen challenge_token für den nächsten Schritt."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    two_factor: Literal["required", "setup"] | None = None
    challenge_token: str | None = None


class TwoFactorLoginRequest(BaseModel):
    challenge_token: str = Field(max_length=4096)
    # 6 Ziffern aus der App oder ein Wiederherstellungscode (abcd-efgh)
    code: str = Field(min_length=6, max_length=20)


class TwoFactorChallenge(BaseModel):
    """Für das Einrichten direkt beim Login (Pflicht): statt eines Zugriffs-Tokens das Challenge-Token."""

    challenge_token: str | None = Field(default=None, max_length=4096)


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TwoFactorEnableRequest(TwoFactorChallenge):
    code: str = Field(min_length=6, max_length=10)


class TwoFactorEnableResponse(BaseModel):
    recovery_codes: list[str]
    # Neue Sitzung (bisherige Sitzungen enden beim Einschalten)
    access_token: str
    refresh_token: str


class TwoFactorDisableRequest(BaseModel):
    password: str = Field(max_length=256)


class TwoFactorStatus(BaseModel):
    enabled: bool
    required: bool
    recovery_codes_left: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=4096)


def _check_new_password(value: str) -> str:
    """Selbst gewählte Passwörter: mind. 10 Zeichen, höchstens 72 Byte (bcrypt-Grenze)."""
    if len(value) < 10:
        raise ValueError("Das Passwort muss mindestens 10 Zeichen haben.")
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Das Passwort ist zu lang (höchstens 72 Byte).")
    return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(max_length=128)

    @field_validator("new_password")
    @classmethod
    def _new_password(cls, value: str) -> str:
        return _check_new_password(value)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(max_length=128)

    @field_validator("new_password")
    @classmethod
    def _new_password(cls, value: str) -> str:
        return _check_new_password(value)
