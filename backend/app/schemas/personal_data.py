"""Persönliche Daten am Mitarbeiter (Adresse, Familie, Bank, Steuer, Sozialversicherung) und
Kostenstellen. Bank, Steuer und SV sehen und ändern nur Konten mit „Vergütung & Lohn-Export“."""
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PAYROLL_FIELDS = frozenset(
    {"iban", "bic", "account_holder", "tax_id", "tax_class", "church_tax", "social_security_number", "health_insurance"}
)


def _iban_ok(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


class PersonalData(BaseModel):
    private_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[0-9+()/ .\-]*$")
    street: str | None = Field(default=None, max_length=150)
    zip_code: str | None = Field(default=None, max_length=10, pattern=r"^[0-9A-Za-z \-]*$")
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=60)
    nationality: str | None = Field(default=None, max_length=60)
    birth_place: str | None = Field(default=None, max_length=100)
    birth_name: str | None = Field(default=None, max_length=100)
    children_count: int | None = Field(default=None, ge=0, le=20)
    # Kinderfreibeträge (in halben Schritten)
    child_allowance: float | None = Field(default=None, ge=0, le=20, multiple_of=0.5)
    # Lohn (nur mit „Vergütung & Lohn-Export“)
    iban: str | None = Field(default=None, max_length=42)
    bic: str | None = Field(default=None, max_length=15)
    account_holder: str | None = Field(default=None, max_length=100)
    tax_id: str | None = Field(default=None, max_length=11)
    tax_class: int | None = Field(default=None, ge=1, le=6)
    church_tax: str | None = Field(default=None, max_length=20)
    social_security_number: str | None = Field(default=None, max_length=20)
    health_insurance: str | None = Field(default=None, max_length=100)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("iban")
    @classmethod
    def _iban(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = re.sub(r"\s", "", value).upper()
        if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", value) or not _iban_ok(value):
            raise ValueError("Die IBAN ist ungültig.")
        return value

    @field_validator("bic")
    @classmethod
    def _bic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", value):
            raise ValueError("Die BIC ist ungültig.")
        return value

    @field_validator("tax_id")
    @classmethod
    def _tax_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"\d{11}", value):
            raise ValueError("Die Steuer-ID hat 11 Ziffern.")
        return value

    @field_validator("social_security_number")
    @classmethod
    def _ssn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = re.sub(r"\s", "", value).upper()
        if not re.fullmatch(r"\d{8}[A-Z]\d{3}", value):
            raise ValueError("Die Sozialversicherungsnummer hat das Format 12 345678 A 123.")
        return value


class PersonalDataResponse(PersonalData):
    # False: Bank, Steuer und SV werden ohne „Vergütung & Lohn-Export“ nicht gezeigt
    payroll_visible: bool = True


class CostCenterShare(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cost_center_id: int
    percent: int = Field(ge=1, le=100)


class CostCenterCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)


class CostCenterUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None


class CostCenterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    archived: bool
