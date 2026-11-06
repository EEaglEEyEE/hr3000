from datetime import date

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # Art aus dem Katalog („Lohnarten“) – oder type_name: Art mit diesem Namen finden bzw. anlegen
    type_id: int | None = Field(default=None, ge=1)
    type_name: str | None = Field(
        default=None, min_length=1, max_length=100, validation_alias=AliasChoices("type_name", "name")
    )
    amount: float = Field(gt=0, le=1_000_000)
    unit: AllowanceUnit | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    pay_date: date | None = None
    # Lohnart einer neu angelegten Art (type_name); sonst gilt die Lohnart der Art
    wage_type: str | None = Field(default=None, pattern=r"^[0-9]{1,6}$")
    note: str | None = Field(default=None, max_length=300)

    @field_validator("amount")
    @classmethod
    def _amount_cents(cls, value: float) -> float:
        return _cents(value)

    @field_validator("type_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Bitte eine Bezeichnung angeben.")
        return value

    @model_validator(mode="after")
    def _by_kind(self) -> "PayComponentCreateRequest":
        if (self.type_id is None) == (self.type_name is None):
            raise ValueError("Bitte eine Art wählen oder eine neue Art angeben.")
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
    """Zulage beenden/verlängern (valid_to, clear_valid_to = wieder unbefristet) oder Notiz ändern.
    Betrag/Art ändern = beenden und neu anlegen (nachvollziehbare Historie); die Lohnart steht an
    der Art (Seite „Lohnarten“)."""

    valid_to: date | None = None
    clear_valid_to: bool = False
    note: str | None = Field(default=None, max_length=300)


class PayComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    kind: PayComponentKind
    type_id: int
    # Name und Lohnart der Art
    name: str
    amount: float
    unit: AllowanceUnit | None
    valid_from: date | None
    valid_to: date | None
    pay_date: date | None
    wage_type: str | None
    note: str | None
