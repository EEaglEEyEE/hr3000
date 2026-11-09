from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    parent_id: int | None = None


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    parent_id: int | None = None
    clear_parent_id: bool = False


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    # Aktive Mitarbeiter direkt in dieser Abteilung
    employee_count: int = 0


class OrgChartPerson(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    position: str | None
    department_id: int | None
    department: str | None
    # Führungskraft (nur, wenn sie ebenfalls im Organigramm steht)
    supervisor_id: int | None
