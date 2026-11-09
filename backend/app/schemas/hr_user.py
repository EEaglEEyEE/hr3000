from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.account import HrRole
from app.schemas.common import NewPassword


class HrUserCreateRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    role: HrRole = HrRole.HR
    # Berechtigung „Vergütung & Lohn-Export“ (nur Rolle HR; Admins haben sie immer)
    payroll_access: bool = False
    two_factor_enabled: bool = False


class HrUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: HrRole
    payroll_access: bool = False
