from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# HEAD = Leitung (Führungskraft der Abteilung), DEPUTY = Stellvertretung
LeaderRole = Literal["HEAD", "DEPUTY"]
# Rechte einer Stellvertretung, siehe app/services/scope_service.py:
# STANDBY = sieht immer, entscheidet bei Abwesenheit · FULL = wie Leitung · ABSENCE = nur bei Abwesenheit
DeputyRights = Literal["STANDBY", "FULL", "ABSENCE"]

MAX_LEADERS = 50


class DepartmentLeaderInput(BaseModel):
    employee_id: int = Field(ge=1)
    role: LeaderRole = "HEAD"
    # Nur bei Stellvertretungen von Bedeutung
    deputy_rights: DeputyRights = "STANDBY"


def _unique_people(leaders: list[DepartmentLeaderInput] | None) -> list[DepartmentLeaderInput] | None:
    if leaders is not None:
        ids = [leader.employee_id for leader in leaders]
        if len(ids) != len(set(ids)):
            raise ValueError("Jede Person nur einmal als Leitung oder Stellvertretung eintragen.")
    return leaders


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    parent_id: int | None = Field(default=None, ge=1)
    # Leitungen und Stellvertretungen (Reihenfolge = Anzeige)
    leaders: list[DepartmentLeaderInput] = Field(default_factory=list, max_length=MAX_LEADERS)

    _unique = field_validator("leaders")(_unique_people)


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    parent_id: int | None = Field(default=None, ge=1)
    clear_parent_id: bool = False
    # None = unverändert, [] = keine Leitung und keine Stellvertretung mehr; sonst ersetzt die Liste alle
    leaders: list[DepartmentLeaderInput] | None = Field(default=None, max_length=MAX_LEADERS)

    _unique = field_validator("leaders")(_unique_people)


MAX_MEMBERS_PER_REQUEST = 500


class DepartmentMembersRequest(BaseModel):
    """Mitarbeiter in diese Abteilung aufnehmen (z. B. aus dem Organigramm). Wer in einer anderen
    Abteilung ist, wechselt hierher; wer schon darin ist, bleibt unverändert."""

    employee_ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1, max_length=MAX_MEMBERS_PER_REQUEST)

    @field_validator("employee_ids")
    @classmethod
    def _unique(cls, ids: list[int]) -> list[int]:
        if len(ids) != len(set(ids)):
            raise ValueError("Jede Person nur einmal angeben.")
        return ids


class DepartmentLeaderResponse(BaseModel):
    employee_id: int
    # „Vorname Nachname“
    name: str
    role: LeaderRole
    deputy_rights: DeputyRights
    # Inaktive Personen bleiben eingetragen, zählen aber nicht
    active: bool


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    leaders: list[DepartmentLeaderResponse] = []
    # Aktive Mitarbeiter direkt in dieser Abteilung
    employee_count: int = 0


class DepartmentMembersResponse(BaseModel):
    department: DepartmentResponse
    # Personen, die tatsächlich in die Abteilung gekommen sind (ohne die, die schon darin waren)
    added: int


class OrgChartPerson(BaseModel):
    employee_id: int
    first_name: str
    last_name: str
    position: str | None
    department_id: int | None
    department: str | None
    # Wirksame Führungskräfte (Leitungen bzw. Ausnahme; nur, wer ebenfalls im Organigramm steht)
    supervisor_ids: list[int]


class OrgChartLeader(BaseModel):
    employee_id: int
    role: LeaderRole
    deputy_rights: DeputyRights


class OrgChartDepartment(BaseModel):
    id: int
    name: str
    parent_id: int | None
    # Aktive Leitungen und Stellvertretungen
    leaders: list[OrgChartLeader]


class OrgChartResponse(BaseModel):
    """Abteilungsbaum mit Leitungen und Stellvertretungen; people enthält alle aktiven Mitarbeiter
    (department_id = wo sie stehen, ohne Abteilung = None)."""

    departments: list[OrgChartDepartment]
    people: list[OrgChartPerson]
