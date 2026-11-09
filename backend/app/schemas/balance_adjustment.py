from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.balance_adjustment import AdjustmentKind


class BalanceAdjustmentCreateRequest(BaseModel):
    effective_date: date
    # Vorzeichenbehaftet in Minuten: +600 = 10 Std. gutschreiben, -600 = abziehen/auszahlen.
    minutes: int = Field(ge=-60_000, le=60_000)
    kind: AdjustmentKind
    note: str = Field(min_length=3, max_length=300)
    # Nur bei Auszahlung: Vergütungsfaktor 1–3 (z. B. 1,5), leer = 1
    payout_factor: Decimal | None = Field(default=None, ge=1, le=3, max_digits=4, decimal_places=2)

    @field_validator("minutes")
    @classmethod
    def _not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Eine Buchung über 0 Minuten ist nicht sinnvoll.")
        return value

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Bitte eine Begründung angeben.")
        return value

    @model_validator(mode="after")
    def _payout_reduces(self) -> "BalanceAdjustmentCreateRequest":
        if self.kind == AdjustmentKind.PAYOUT and self.minutes > 0:
            raise ValueError("Eine Auszahlung verringert das Konto – bitte einen negativen Wert angeben.")
        if self.payout_factor is not None and self.kind != AdjustmentKind.PAYOUT:
            raise ValueError("Ein Faktor gibt es nur bei einer Auszahlung.")
        if self.effective_date < date(2000, 1, 1):
            raise ValueError("Das Datum ist zu weit in der Vergangenheit.")
        return self


class BalanceAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    effective_date: date
    minutes: int
    kind: AdjustmentKind
    note: str
    payout_factor: Decimal | None = None
    created_at: datetime


class SetBalanceRequest(BaseModel):
    """„Neuen Kontostand festlegen“: Stand am Ende des Tages auf diesen Wert setzen – gebucht wird
    die Differenz als Anpassung (spätere rückwirkende Änderungen davor verschieben den Stand weiter)."""

    effective_date: date
    balance_minutes: int = Field(ge=-60_000, le=60_000)
    note: str = Field(min_length=3, max_length=250)

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Bitte eine Begründung angeben.")
        return value
