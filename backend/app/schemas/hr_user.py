from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.hr_user import HrRole
from app.schemas.common import NewPassword


class HrUserCreateRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    role: HrRole = HrRole.HR
    # Berechtigung „Vergütung & Lohn-Export“ (nur Rolle HR; Admins haben sie immer)
    payroll_access: bool = False


class HrUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: HrRole
    payroll_access: bool = False
