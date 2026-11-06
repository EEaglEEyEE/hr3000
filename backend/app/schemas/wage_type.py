import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.pay_component import PayComponentKind
from app.models.wage_type import WageTypeItem

# Bezeichnungen wie auf der Seite „Lohnarten“ (auch für Hinweise im DATEV-Export)
WAGE_TYPE_LABELS: dict[WageTypeItem, str] = {
    WageTypeItem.WORKED: "Gearbeitete Stunden",
    WageTypeItem.VACATION: "Urlaub",
    WageTypeItem.SICK: "Krankheit",
    WageTypeItem.CHILD_SICK: "Kind krank",
    WageTypeItem.SPECIAL_LEAVE: "Sonderurlaub",
    WageTypeItem.PUBLIC_HOLIDAY: "Feiertag",
    WageTypeItem.WORK_TIME: "Arbeitszeit-Angaben (z. B. Homeoffice)",
    WageTypeItem.OVERTIME_PAYOUT: "Ausgezahlte Überstunden",
}

_WAGE_TYPE = r"^[0-9]{1,6}$"


class WageTypeItemResponse(BaseModel):
    item: WageTypeItem
    label: str
    wage_type: str | None


class WageTypesResponse(BaseModel):
    items: list[WageTypeItemResponse]


class WageTypesUpdateRequest(BaseModel):
    """Lohnart je Zeitart (nur Ziffern); leer bzw. null = keine Lohnart (nicht übertragen)."""

    items: dict[WageTypeItem, str | None] = Field(max_length=len(WageTypeItem))

    @field_validator("items")
    @classmethod
    def _digits(cls, value: dict[WageTypeItem, str | None]) -> dict[WageTypeItem, str | None]:
        cleaned: dict[WageTypeItem, str | None] = {}
        for item, wage_type in value.items():
            wage_type = (wage_type or "").strip() or None
            if wage_type is not None and not re.fullmatch(r"[0-9]{1,6}", wage_type):
                raise ValueError("Lohnarten bestehen aus 1–6 Ziffern.")
            cleaned[item] = wage_type
        return cleaned


class PayComponentTypeCreateRequest(BaseModel):
    kind: PayComponentKind
    name: str = Field(min_length=1, max_length=100)
    wage_type: str | None = Field(default=None, pattern=_WAGE_TYPE)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bitte eine Bezeichnung angeben.")
        return value


class PayComponentTypeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # "" = Lohnart entfernen
    wage_type: str | None = Field(default=None, pattern=r"^[0-9]{0,6}$")
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Bitte eine Bezeichnung angeben.")
        return value


class PayComponentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: PayComponentKind
    name: str
    wage_type: str | None
    active: bool
    # Anzahl Zulagen/Einmalzahlungen mit dieser Art (Löschen nur, wenn 0)
    in_use: int = 0
