from datetime import date

from pydantic import BaseModel, Field


class LeaveEntitlementUpdateRequest(BaseModel):
    entitled_days: float | None = Field(default=None, ge=0, le=365)
    carried_over_days: float | None = Field(default=None, ge=0, le=365)
    # True = Übertrag wieder automatisch aus dem Vorjahr berechnen (eingetragener Wert entfällt)
    carried_over_auto: bool | None = None


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
    # Anteiliger Vorschlag laut Arbeitszeitmodell (Vollzeit-Standard x Arbeitstage/5), None ohne Standard.
    suggested_entitled_days: float | None = None
    workdays_per_week: int | None = None
