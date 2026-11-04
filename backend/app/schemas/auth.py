from pydantic import BaseModel, EmailStr, Field


class DeviceLoginRequest(BaseModel):
    device_token: str = Field(max_length=200)


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


class HrLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class EmployeeLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=4096)
