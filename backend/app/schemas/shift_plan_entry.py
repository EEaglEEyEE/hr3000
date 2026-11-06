from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ShiftPlanEntryUpsertRequest(BaseModel):
    is_workday: bool
    shift_template_id: int | None = None
    target_minutes: int | None = Field(default=None, ge=0)


class ShiftPlanEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    date: date
    shift_template_id: int | None
    is_workday: bool
    target_minutes: int | None
    planned_by_hr_user_id: int | None
    planned_by_employee_id: int | None


class EffectiveShiftDayResponse(BaseModel):
    """Aufgelöste Tagesplanung (ShiftPlanEntry-Ausnahme ODER
    EmployeeDefaultShift ODER unkonfiguriert) für Kalenderansicht,
    Druckansicht und PDF-Export – siehe
    app/services/shift_planning_service.py resolve_effective_shift."""

    date: date
    is_workday: bool
    plan_exists: bool
    from_entry: bool
    shift_template_id: int | None
    target_minutes: int | None
    # Arbeitszeitmodell ohne Tagessoll: flexibel (Wochensoll) bzw. nach Aufwand (ohne Soll)
    flexible: bool = False
    on_demand: bool = False
