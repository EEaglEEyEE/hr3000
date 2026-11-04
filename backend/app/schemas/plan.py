from pydantic import BaseModel

from app.models.tenant import TenantPlan


class PlanResponse(BaseModel):
    plan: TenantPlan
    active_employees: int
    # None = keine Grenze (bezahlt bzw. unbegrenzt)
    limit: int | None
    remaining: int | None
