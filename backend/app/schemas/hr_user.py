from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.account import HrRole
from app.schemas.common import NewPassword
from app.schemas.role import CustomRoleRef


class HrUserCreateRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    role: HrRole = HrRole.HR
    # Berechtigung „Vergütung & Lohn-Export“ (nur Rolle HR; Admins haben sie immer)
    payroll_access: bool = False
    two_factor_enabled: bool = False
    # Eigene Rolle (nur bei Rolle HR), z. B. „Lohnbüro (nur lesen)“
    custom_role_id: int | None = Field(default=None, ge=1)


class HrUserUpdateRequest(BaseModel):
    """Weggelassene Felder bleiben unverändert; custom_role_id null = keine eigene Rolle."""

    role: HrRole | None = None
    payroll_access: bool | None = None
    custom_role_id: int | None = Field(default=None, ge=1)


class HrUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: HrRole
    payroll_access: bool = False
    custom_role: CustomRoleRef | None = None
    two_factor_enabled: bool = False
