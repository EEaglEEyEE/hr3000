from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.services.role_permissions import Area, Level

RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
RoleDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


def _check_permissions(permissions: dict[Area, Level] | None) -> None:
    if permissions is not None and all(level == Level.NONE for level in permissions.values()):
        raise ValueError("Die Rolle braucht mindestens einen Bereich mit „Ansehen“ oder „Bearbeiten“.")


class RoleCreateRequest(BaseModel):
    name: RoleName
    description: RoleDescription | None = None
    # Fehlende Bereiche = kein Zugriff; unbekannte Bereiche/Stufen lehnt Pydantic ab (422)
    permissions: dict[Area, Level]

    @model_validator(mode="after")
    def _at_least_one_area(self) -> "RoleCreateRequest":
        _check_permissions(self.permissions)
        return self


class RoleUpdateRequest(BaseModel):
    name: RoleName | None = None
    description: RoleDescription | None = None
    permissions: dict[Area, Level] | None = None

    @model_validator(mode="after")
    def _at_least_one_area(self) -> "RoleUpdateRequest":
        _check_permissions(self.permissions)
        return self


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None
    # Immer alle Bereiche (fehlende = NONE)
    permissions: dict[Area, Level]
    # Wie vielen Konten die Rolle zugewiesen ist (Löschen nur bei 0)
    account_count: int = Field(ge=0)


class RoleAreaInfo(BaseModel):
    key: Area
    label: str
    description: str


class RoleTemplate(BaseModel):
    key: str
    name: str
    description: str
    permissions: dict[Area, Level]


class RoleMetaResponse(BaseModel):
    areas: list[RoleAreaInfo]
    templates: list[RoleTemplate]


class CustomRoleRef(BaseModel):
    """Kurzform der eigenen Rolle an Konten (Mitarbeiter-Zugang, Verwaltungskonto)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
