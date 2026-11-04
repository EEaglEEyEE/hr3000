from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.hr_user import HrRole
from app.schemas.common import NewPassword


class HrUserCreateRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    role: HrRole = HrRole.HR


class HrUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: HrRole
