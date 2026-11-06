from datetime import date

from pydantic import BaseModel, Field, model_validator


class LeaveEntitlementUpdateRequest(BaseModel):
    # Anspruch für dieses Jahr fest eintragen
    entitled_days: float | None = Field(default=None, ge=0, le=365)
    # True = Anspruch wieder berechnen (fest eingetragener Wert entfällt)
    entitled_auto: bool | None = None
    carried_over_days: float | None = Field(default=None, ge=0, le=365)
    # True = Übertrag wieder automatisch aus dem Vorjahr berechnen (eingetragener Wert entfällt)
    carried_over_auto: bool | None = None

    @model_validator(mode="after")
    def _either_value_or_auto(self) -> "LeaveEntitlementUpdateRequest":
        if self.entitled_auto and self.entitled_days is not None:
            raise ValueError("Anspruch entweder eintragen oder wieder berechnen lassen, nicht beides.")
        if self.carried_over_auto and self.carried_over_days is not None:
            raise ValueError("Übertrag entweder eintragen oder wieder berechnen lassen, nicht beides.")
        return self


class LeaveEntitlementResponse(BaseModel):
    employee_id: int
    year: int
    entitled_days: float
    carried_over_days: float
    used_days: float
    remaining_days: float
    carried_over_auto: bool = False
    expired_days: float = 0
    expiring_days: float = 0
    expiry_date: date | None = None
    # Berechneter Anspruch (Jahresurlaub laut Vertrag bzw. Standard, Teilzeit, Teilurlaub); None =
    # nach Aufwand (HR trägt ein)
    suggested_entitled_days: float | None = None
    # True = Anspruch für dieses Jahr fest eingetragen (sonst berechnet)
    entitled_manual: bool = False
    # Jahresurlaub heute laut Vertrag bzw. Standard (bezogen auf die 5-Tage-Woche)
    annual_vacation_days: float = 0
    workdays_per_week: int | None = None
