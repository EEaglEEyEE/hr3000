from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.tenant import TenantPlan


class PlanResponse(BaseModel):
    plan: TenantPlan
    active_employees: int
    # None = keine Grenze (bezahlt bzw. unbegrenzt)
    limit: int | None
    remaining: int | None
    # Kündigung (services/tenant_lifecycle.py): None = nicht gekündigt
    cancelled_at: datetime | None = None
    contract_end: date | None = None
    deletion_due_on: date | None = None


class CancellationRequest(BaseModel):
    """Kündigen nur mit Bestätigung: die Adresse der Firma (Subdomain) muss eingetippt werden."""

    model_config = ConfigDict(str_strip_whitespace=True)

    confirm_subdomain: str = Field(min_length=1, max_length=63)
