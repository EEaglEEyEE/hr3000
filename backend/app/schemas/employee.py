import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.daily_summary import SummaryStatus
from app.models.hr_user import HrRole
from app.schemas.common import NewPassword, normalize_card_uid
from app.schemas.work_time_model import WorkTimeModelInput


class EmployeeCreateRequest(BaseModel):
    location_id: int
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    employee_number: str = Field(min_length=1, max_length=50)
    active: bool = True
    login_email: EmailStr | None = None
    password: NewPassword | None = None
    # None = Standard des Mandanten (Einstellungen)
    auto_break_enabled: bool | None = None
    # Stempel-PIN: 4–8 Ziffern (Tablet-Tastatur), "" = entfernen
    pin: str | None = Field(default=None, pattern=r"^(\d{4,8})?$")
    nfc_uid: str | None = Field(default=None, max_length=64)

    @field_validator("nfc_uid")
    @classmethod
    def _normalize_uid(cls, value: str | None) -> str | None:
        return normalize_card_uid(value)
    hire_date: dt.date | None = None
    termination_date: dt.date | None = None
    birth_date: dt.date | None = None
    show_birthday_in_calendar: bool | None = None
    team_id: int | None = None
    # Optional direkt beim Anlegen: gilt ab Eintritt (bzw. heute, ohne Eintrittsdatum) – inkl.
    # Kernzeit/Pünktlichkeit (die gehört zur Fassung der Arbeitszeit).
    work_time_model: WorkTimeModelInput | None = None
    # True = bewusst ohne Arbeitszeitmodell anlegen (z. B. reines HR-Konto), auch wenn in den
    # Einstellungen ein Standardmodell steht. Ohne Modell gibt es kein Soll.
    no_work_time_model: bool = False

    @model_validator(mode="after")
    def _model_or_none(self) -> "EmployeeCreateRequest":
        if self.no_work_time_model and self.work_time_model is not None:
            raise ValueError("Entweder ein Arbeitszeitmodell angeben oder „ohne Arbeitszeitmodell“, nicht beides.")
        return self


class EmployeeUpdateRequest(BaseModel):
    location_id: int | None = None
    # Ab wann ein Standortwechsel gilt (Standard: heute) – frühere Tage behalten Feiertage des alten Standorts.
    location_valid_from: dt.date | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    employee_number: str | None = Field(default=None, min_length=1, max_length=50)
    active: bool | None = None
    login_email: EmailStr | None = None
    password: NewPassword | None = None
    auto_break_enabled: bool | None = None
    # Stempel-PIN: 4–8 Ziffern (Tablet-Tastatur), "" = entfernen
    pin: str | None = Field(default=None, pattern=r"^(\d{4,8})?$")
    # None = unverändert, "" = Karte entfernen (wie bei pin).
    nfc_uid: str | None = Field(default=None, max_length=64)

    @field_validator("nfc_uid")
    @classmethod
    def _normalize_uid(cls, value: str | None) -> str | None:
        return normalize_card_uid(value)
    # Datumsfelder rein informativ, wirken nicht auf `active` zurück.
    hire_date: dt.date | None = None
    termination_date: dt.date | None = None
    clear_hire_date: bool = False
    clear_termination_date: bool = False
    birth_date: dt.date | None = None
    clear_birth_date: bool = False
    show_birthday_in_calendar: bool | None = None
    team_id: int | None = None
    clear_team_id: bool = False


class EmployeeHrRoleUpdateRequest(BaseModel):
    hr_role: HrRole | None
    # Berechtigung „Vergütung & Lohn-Export“ (nur bei HR; Admins haben sie immer); None = unverändert
    payroll_access: bool | None = None


class BulkImportRowError(BaseModel):
    row: int
    message: str


class BulkImportResult(BaseModel):
    created: int
    errors: list[BulkImportRowError]


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: int
    first_name: str
    last_name: str
    employee_number: str
    active: bool
    login_email: str | None
    hr_role: HrRole | None
    hr_payroll_access: bool = False
    auto_break_enabled: bool
    has_pin: bool
    nfc_uid: str | None
    hire_date: dt.date | None
    termination_date: dt.date | None
    birth_date: dt.date | None
    show_birthday_in_calendar: bool
    team_id: int | None
    anonymized_at: dt.datetime | None


class LocationEmployeeResponse(BaseModel):
    """Für den Kiosk: reduzierte Mitarbeiterliste eines Standorts inkl. des
    aktuellen Anwesenheitsstatus (für die Farbcodierung der Kachel), ob ein PIN
    hinterlegt ist (für die PIN-Pflicht beim Stempeln) und der NFC-Karten-UID
    (damit das Tablet einen Scan lokal einem Mitarbeiter zuordnen kann, ohne
    dafür online sein zu müssen – die Autorisierung selbst prüft der Server
    trotzdem erneut beim Stempeln, siehe app/api/punches.py)."""

    id: int
    first_name: str
    last_name: str
    employee_number: str
    has_pin: bool
    nfc_uid: str | None
    today_status: SummaryStatus
    # Sonderfälle heute, z.B. außerplanmäßig anwesend (UNPLANNED_WORK) – Anzeige "zu klären".
    today_flags: list[str] = []


class EmployeePasswordResetRequest(BaseModel):
    send_email: bool = False


class EmployeePasswordResetResponse(BaseModel):
    emailed: bool
    # Nur gesetzt, wenn NICHT per E-Mail versendet wurde (einmalige Anzeige).
    new_password: str | None
