from typing import Literal
import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.daily_summary import SummaryStatus
from app.models.account import HrRole
from app.schemas.personal_data import CostCenterShare
from app.schemas.role import CustomRoleRef
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
    department_id: int | None = None
    position: str | None = Field(default=None, max_length=150)
    # Abweichende Führungskraft (Ausnahme, ein anderer Mitarbeiter derselben Firma); ohne Angabe gilt
    # die Leitung der Abteilung (app/services/org_service.py)
    supervisor_id: int | None = None
    # Optional direkt beim Anlegen: gilt ab Eintritt (bzw. heute, ohne Anstelldatum) – inkl.
    # Kernzeit/Pünktlichkeit (die gehört zur Fassung der Arbeitszeit).
    work_time_model: WorkTimeModelInput | None = None
    # True = bewusst ohne Arbeitszeitmodell anlegen (z. B. reines HR-Konto), auch wenn in den
    # Einstellungen ein Standardmodell steht. Ohne Modell gibt es kein Soll.
    no_work_time_model: bool = False
    # Stattdessen ein Arbeitszeitmodell zuweisen (ab Eintritt bzw. heute); folgt dessen Änderungen.
    work_time_profile_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _model_or_none(self) -> "EmployeeCreateRequest":
        chosen = [self.work_time_model is not None, self.no_work_time_model, self.work_time_profile_id is not None]
        if sum(chosen) > 1:
            raise ValueError(
                "Entweder individuelle Angaben, ein zugewiesenes Arbeitszeitmodell oder „ohne Arbeitszeitmodell“ angeben, nicht mehreres."
            )
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
    department_id: int | None = None
    clear_department_id: bool = False
    # "" entfernt die Position
    position: str | None = Field(default=None, max_length=150)
    supervisor_id: int | None = None
    clear_supervisor_id: bool = False


class EmployeeHrRoleUpdateRequest(BaseModel):
    hr_role: HrRole | None
    # Berechtigung „Vergütung & Lohn-Export“ (nur bei HR; Admins haben sie immer); None = unverändert
    payroll_access: bool | None = None
    # Eigene Rolle (nur bei HR): weggelassen = unverändert, null = keine (voller HR-Zugriff)
    custom_role_id: int | None = Field(default=None, ge=1)


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
    # Zwei-Faktor-Anmeldung eingerichtet (Admins können sie zurücksetzen)
    two_factor_enabled: bool = False
    hr_role: HrRole | None
    hr_payroll_access: bool = False
    hr_custom_role: CustomRoleRef | None = None
    auto_break_enabled: bool
    has_pin: bool
    nfc_uid: str | None
    hire_date: dt.date | None
    termination_date: dt.date | None
    birth_date: dt.date | None
    show_birthday_in_calendar: bool
    department_id: int | None = None
    position: str | None = None
    # Abweichende Führungskraft (Ausnahme je Person)
    supervisor_id: int | None = None
    # Wirksame Führungskräfte: die Ausnahme oder die Leitungen der Abteilung (OVERRIDE / DEPARTMENT)
    effective_supervisor_ids: list[int] = []
    supervisor_source: Literal["OVERRIDE", "DEPARTMENT"] | None = None
    # ONBOARDING, ACTIVE, LEAVE (Auszeit), INACTIVE
    employment_status: str = "ACTIVE"
    cost_centers: list[CostCenterShare] = []
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
    # Für Tablets: SHA-256(card_salt + normalisierte UID) statt der UID
    card_hash: str | None = None
    today_status: SummaryStatus
    # Sonderfälle heute, z.B. außerplanmäßig anwesend (UNPLANNED_WORK) – Anzeige "zu klären".
    today_flags: list[str] = []


class EmployeePasswordResetRequest(BaseModel):
    send_email: bool = False


class EmployeePasswordResetResponse(BaseModel):
    emailed: bool
    # Nur gesetzt, wenn NICHT per E-Mail versendet wurde (einmalige Anzeige).
    new_password: str | None
