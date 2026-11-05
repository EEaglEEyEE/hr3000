from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.pay_component import AllowanceUnit, PayComponentKind


def _cents(value: float) -> float:
    # Spalte ist Numeric(10,2) – mehr Nachkommastellen würde MySQL stillschweigend runden.
    if abs(round(value, 2) - value) > 1e-9:
        raise ValueError("Höchstens zwei Nachkommastellen (Cent).")
    return round(value, 2)


class PayComponentCreateRequest(BaseModel):
    """Zulage (wiederkehrend, je Monat oder je Ist-Stunde, gültig ab/bis) oder Einmalzahlung
    (zu einem Datum, z.B. Weihnachtsgeld)."""

    kind: PayComponentKind
    name: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, le=1_000_000)
    unit: AllowanceUnit | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    pay_date: date | None = None
    # Lohnart für den DATEV-Export (nur Ziffern)
    wage_type: str | None = Field(default=None, pattern=r"^\d{1,6}$")
    note: str | None = Field(default=None, max_length=300)

    @field_validator("amount")
    @classmethod
    def _amount_cents(cls, value: float) -> float:
        return _cents(value)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bitte eine Bezeichnung angeben.")
        return value

    @model_validator(mode="after")
    def _by_kind(self) -> "PayComponentCreateRequest":
        if self.kind == PayComponentKind.ALLOWANCE:
            if self.unit is None or self.valid_from is None:
                raise ValueError("Zulage: bitte Einheit und „Gültig ab“ angeben.")
            if self.valid_to is not None and self.valid_to < self.valid_from:
                raise ValueError("„Gültig bis“ darf nicht vor „Gültig ab“ liegen.")
            self.pay_date = None
        else:
            if self.pay_date is None:
                raise ValueError("Einmalzahlung: bitte das Datum angeben.")
            self.unit = self.valid_from = self.valid_to = None
        return self


class PayComponentUpdateRequest(BaseModel):
    """Zulage beenden/verlängern (valid_to, clear_valid_to = wieder unbefristet), Lohnart oder
    Notiz ändern. Betrag/Art ändern = beenden und neu anlegen (nachvollziehbare Historie)."""

    valid_to: date | None = None
    clear_valid_to: bool = False
    wage_type: str | None = Field(default=None, pattern=r"^\d{0,6}$")
    note: str | None = Field(default=None, max_length=300)


class PayComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    kind: PayComponentKind
    name: str
    amount: float
    unit: AllowanceUnit | None
    valid_from: date | None
    valid_to: date | None
    pay_date: date | None
    wage_type: str | None
    note: str | None
