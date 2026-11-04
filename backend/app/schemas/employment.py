from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.employment import ContractType, PayType


class ContractCreateRequest(BaseModel):
    valid_from: date
    valid_to: date | None = None
    contract_type: ContractType
    job_title: str | None = Field(default=None, max_length=150)
    probation_end: date | None = None
    fixed_term_end: date | None = None
    notice_period: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _consistent_dates(self) -> "ContractCreateRequest":
        if self.contract_type == ContractType.FIXED_TERM and self.fixed_term_end is None:
            raise ValueError("Bei einem befristeten Vertrag ist ein Befristungsende erforderlich.")
        if self.fixed_term_end is not None and self.fixed_term_end < self.valid_from:
            raise ValueError("Das Befristungsende liegt vor dem Vertragsbeginn.")
        if self.probation_end is not None and self.probation_end < self.valid_from:
            raise ValueError("Das Probezeitende liegt vor dem Vertragsbeginn.")
        return self


class ContractUpdateRequest(BaseModel):
    job_title: str | None = Field(default=None, max_length=150)
    probation_end: date | None = None
    fixed_term_end: date | None = None
    notice_period: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    valid_to: date | None = None
    clear_valid_to: bool = False
    clear_probation_end: bool = False
    clear_fixed_term_end: bool = False


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    valid_from: date
    valid_to: date | None
    contract_type: ContractType
    job_title: str | None
    probation_end: date | None
    fixed_term_end: date | None
    notice_period: str | None
    notes: str | None


class CompensationCreateRequest(BaseModel):
    valid_from: date
    valid_to: date | None = None
    pay_type: PayType
    amount: float = Field(gt=0, le=1_000_000)

    @field_validator("amount")
    @classmethod
    def _cents(cls, value: float) -> float:
        # Spalte ist Numeric(10,2) – mehr Nachkommastellen würde MySQL stillschweigend runden.
        if abs(round(value, 2) - value) > 1e-9:
            raise ValueError("Höchstens zwei Nachkommastellen (Cent).")
        return round(value, 2)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    note: str | None = Field(default=None, max_length=300)


class CompensationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    valid_from: date
    valid_to: date | None
    pay_type: PayType
    amount: float
    currency: str
    note: str | None
