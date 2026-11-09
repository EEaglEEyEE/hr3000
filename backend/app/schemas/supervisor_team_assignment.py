from pydantic import BaseModel, ConfigDict, model_validator


class SupervisorTeamAssignmentCreateRequest(BaseModel):
    """Teamleitung zuordnen: über den Mitarbeiter (mit Zugang) oder direkt über das Konto."""

    team_id: int
    employee_id: int | None = None
    account_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "SupervisorTeamAssignmentCreateRequest":
        if (self.employee_id is None) == (self.account_id is None):
            raise ValueError("Genau eines von employee_id/account_id muss gesetzt sein.")
        return self


class SupervisorTeamAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    account_id: int
    employee_id: int | None
