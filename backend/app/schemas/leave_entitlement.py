from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    # beim mehrwöchigen Arbeitszeitmodell der Durchschnitt über den Turnus (z.B. 2.5)
    workdays_per_week: float | None = None
    # Summe der Korrekturen am Urlaubskonto (± Tage) im Jahr
    adjustment_days: float = 0


class LeaveAdjustmentCreateRequest(BaseModel):
    """Korrektur am Urlaubskonto: ± Tage (halbe Tage erlaubt), optional mit Verfallsdatum."""

    year: int = Field(ge=2000, le=2100)
    days: float = Field(ge=-100, le=100, multiple_of=0.5)
    expires_on: date | None = None
    note: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def _valid(self) -> "LeaveAdjustmentCreateRequest":
        if self.days == 0:
            raise ValueError("Eine Korrektur über 0 Tage ist nicht sinnvoll.")
        if self.expires_on is not None:
            if self.days < 0:
                raise ValueError("Ein Verfallsdatum gibt es nur bei zusätzlichen Tagen.")
            if not date(self.year, 1, 1) <= self.expires_on <= date(self.year + 1, 12, 31):
                raise ValueError("Das Verfallsdatum muss im Jahr der Korrektur oder im Folgejahr liegen.")
        self.note = self.note.strip()
        if len(self.note) < 3:
            raise ValueError("Bitte eine Begründung angeben.")
        return self


class LeaveAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    year: int
    days: float
    expires_on: date | None
    note: str
    created_at: datetime
