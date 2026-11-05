from datetime import date, time
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, field_validator, model_validator

from app.services.holiday_calendar import Bundesland


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    require_pin_for_punch: bool
    vacation_approval_required: bool
    default_bundesland: Bundesland | None
    default_annual_vacation_days: float
    show_birthdays_in_calendar: bool
    shift_planning_enabled: bool
    balance_start_date: date | None = None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_from: str | None
    smtp_security: Literal["NONE", "STARTTLS", "SSL"]
    # Das Passwort selbst wird nie ausgegeben, nur ob eines hinterlegt ist.
    smtp_password_set: bool
    email_notifications_enabled: bool
    default_auto_break: bool = True
    default_show_birthday: bool = True
    default_day_minutes: list[int] | None = None
    prorate_part_time_vacation: bool = True
    vacation_carry_over_auto: bool = False
    vacation_carry_over_max_days: float | None = None
    vacation_carry_over_expiry: str | None = None
    disabled_day_flags: list[str] = []
    report_days_without_punches: bool = True
    core_time_start: time | None = None
    core_time_end: time | None = None
    punctuality_check: bool = False
    late_tolerance_minutes: int = 5
    flex_frame_start: time | None = None
    flex_frame_end: time | None = None
    max_shift_span_hours: int = 16
    kiosk_admin_pin_set: bool = False
    rfid_required: bool = False
    kiosk_rfid_enabled: bool = True
    kiosk_card_self_registration: bool = True
    kiosk_pin_self_setup: bool = True
    kiosk_show_balance: bool = True
    kiosk_show_vacation: bool = True
    kiosk_break_buttons: bool = True
    kiosk_errand_buttons: bool = False
    portal_punching_enabled: bool = False
    absence_requests_enabled: bool = True
    kiosk_greeting: str | None = None
    kiosk_sort: Literal["LAST_NAME", "FIRST_NAME"] = "LAST_NAME"
    kiosk_theme: Literal["DARK", "LIGHT"] = "DARK"
    kiosk_screen_on_from: time | None = None
    kiosk_screen_on_until: time | None = None

    @field_validator("default_day_minutes", mode="before")
    @classmethod
    def _split_minutes(cls, value):
        if isinstance(value, str):
            return [int(v) for v in value.split(",")] if value else None
        return value

    @field_validator("disabled_day_flags", mode="before")
    @classmethod
    def _split_flags(cls, value):
        if isinstance(value, str):
            return [v for v in value.split(",") if v]
        return value or []


_EMAIL = TypeAdapter(EmailStr)
_HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")


class SettingsUpdateRequest(BaseModel):
    require_pin_for_punch: bool | None = None
    vacation_approval_required: bool | None = None
    default_bundesland: Bundesland | None = None
    default_annual_vacation_days: float | None = None
    show_birthdays_in_calendar: bool | None = None
    shift_planning_enabled: bool | None = None
    default_auto_break: bool | None = None
    default_show_birthday: bool | None = None
    # 7 Werte Mo..So in Minuten (0 = frei); leere Liste = kein Standardmodell
    default_day_minutes: list[int] | None = Field(default=None, max_length=7)
    prorate_part_time_vacation: bool | None = None
    vacation_carry_over_auto: bool | None = None
    vacation_carry_over_max_days: float | None = Field(default=None, ge=0, le=365)
    clear_vacation_carry_over_max_days: bool = False
    # "MM-TT" (z.B. "03-31"); leerer String = kein Verfall
    vacation_carry_over_expiry: str | None = Field(default=None, pattern=r"^((0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))?$")
    disabled_day_flags: list[str] | None = Field(default=None, max_length=10)
    report_days_without_punches: bool | None = None
    max_shift_span_hours: int | None = Field(default=None, ge=8, le=24)
    # Kernzeit und Gleitzeit-Rahmen: jeweils beide Zeiten zusammen; clear_* = entfernen
    core_time_start: time | None = None
    core_time_end: time | None = None
    clear_core_time: bool = False
    punctuality_check: bool | None = None
    late_tolerance_minutes: int | None = Field(default=None, ge=0, le=120)
    flex_frame_start: time | None = None
    flex_frame_end: time | None = None
    clear_flex_frame: bool = False
    # 4–8 Ziffern; leerer String = PIN entfernen
    kiosk_admin_pin: str | None = Field(default=None, pattern=r"^(\d{4,8})?$")
    rfid_required: bool | None = None
    kiosk_rfid_enabled: bool | None = None
    kiosk_card_self_registration: bool | None = None
    kiosk_pin_self_setup: bool | None = None
    kiosk_show_balance: bool | None = None
    kiosk_show_vacation: bool | None = None
    kiosk_break_buttons: bool | None = None
    kiosk_errand_buttons: bool | None = None
    portal_punching_enabled: bool | None = None
    absence_requests_enabled: bool | None = None
    # Leerer String = Text entfernen
    kiosk_greeting: str | None = Field(default=None, max_length=120)
    kiosk_sort: Literal["LAST_NAME", "FIRST_NAME"] | None = None
    kiosk_theme: Literal["DARK", "LIGHT"] | None = None
    # Bildschirmzeiten am Tablet: beide zusammen; clear_kiosk_screen_hours = wieder immer an
    kiosk_screen_on_from: time | None = None
    kiosk_screen_on_until: time | None = None
    clear_kiosk_screen_hours: bool = False
    balance_start_date: date | None = None
    clear_balance_start_date: bool = False
    # Leerer String bei host/user/password = zurücksetzen (Host leer → Plattform-SMTP).
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_user: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    # Leerer String = Absender entfernen.
    smtp_from: str | None = Field(default=None, max_length=255)
    smtp_security: Literal["NONE", "STARTTLS", "SSL"] | None = None
    email_notifications_enabled: bool | None = None

    @model_validator(mode="after")
    def _valid_time_ranges(self) -> "SettingsUpdateRequest":
        for start, end, label in (
            (self.core_time_start, self.core_time_end, "Kernzeit"),
            (self.flex_frame_start, self.flex_frame_end, "Gleitzeit-Rahmen"),
        ):
            if (start is None) != (end is None):
                raise ValueError(f"{label}: bitte Beginn und Ende angeben.")
            if start is not None and end is not None and start >= end:
                raise ValueError(f"{label}: der Beginn muss vor dem Ende liegen.")
        if (self.kiosk_screen_on_from is None) != (self.kiosk_screen_on_until is None):
            raise ValueError("Bildschirmzeiten: bitte „von“ und „bis“ angeben.")
        if self.kiosk_screen_on_from is not None and self.kiosk_screen_on_from == self.kiosk_screen_on_until:
            raise ValueError("Bildschirmzeiten: „von“ und „bis“ dürfen nicht gleich sein.")
        if (
            self.core_time_start is not None
            and self.flex_frame_start is not None
            and not (self.flex_frame_start <= self.core_time_start and self.core_time_end <= self.flex_frame_end)
        ):
            raise ValueError("Die Kernzeit muss innerhalb des Gleitzeit-Rahmens liegen.")
        return self

    @field_validator("smtp_from")
    @classmethod
    def _valid_from(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        return str(_EMAIL.validate_python(value))

    @field_validator("smtp_host")
    @classmethod
    def _valid_host(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if not _HOSTNAME_PATTERN.match(value):
            raise ValueError("Ungültiger Hostname.")
        return value.lower()


class FeaturesResponse(BaseModel):
    shift_planning_enabled: bool
    absence_requests_enabled: bool = True
    # Vorbelegung für "Neuer Mitarbeiter"
    default_auto_break: bool = True
    default_show_birthday: bool = True
    default_day_minutes: list[int] | None = None


class SmtpTestRequest(BaseModel):
    # Standard: die eigene Adresse des angemeldeten Admins.
    to: EmailStr | None = None


class SmtpTestResponse(BaseModel):
    sent_to: str
