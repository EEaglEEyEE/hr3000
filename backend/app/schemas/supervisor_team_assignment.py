from pydantic import BaseModel, ConfigDict, model_validator


class SupervisorTeamAssignmentCreateRequest(BaseModel):
    team_id: int
    hr_user_id: int | None = None
    employee_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one_actor(self) -> "SupervisorTeamAssignmentCreateRequest":
        if (self.hr_user_id is None) == (self.employee_id is None):
            raise ValueError("Genau eines von hr_user_id/employee_id muss gesetzt sein.")
        return self


class SupervisorTeamAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    hr_user_id: int | None
    employee_id: int | None
