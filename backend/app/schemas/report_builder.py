"""Schemas des Berichts-Builders. Die Definition eines Berichts ist ausschließlich das hier geprüfte
JSON – jede Spalte, jeder Operator und jeder Wert wird gegen die Positivliste
(app/services/report_catalog.py) geprüft; eigene Felder (``attr_<id>``) zusätzlich im Dienst gegen
den Attribut-Katalog der Firma."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from app.services import report_catalog as catalog

ColumnKey = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")]
Operator = Literal["eq", "ne", "contains", "starts_with", "gt", "gte", "lt", "lte", "in", "is_empty", "is_not_empty"]
SourceKey = Literal["employees", "absences", "time_months", "project_times"]
FilterValue = StrictBool | StrictInt | StrictFloat | StrictStr | list[StrictStr] | None

MAX_RANGE_DAYS = 366
MAX_PAGE_SIZE = 200


class ReportFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: ColumnKey
    operator: Operator
    value: FilterValue = None


class ReportSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: ColumnKey
    direction: Literal["asc", "desc"] = "asc"


class ReportDefinition(BaseModel):
    """Datenquelle + Spalten + Filter + Sortierung + optionale Gruppierung (mit Summen)."""

    model_config = ConfigDict(extra="forbid")

    source: SourceKey
    columns: list[ColumnKey] = Field(min_length=1, max_length=catalog.MAX_COLUMNS)
    filters: list[ReportFilter] = Field(default_factory=list, max_length=catalog.MAX_FILTERS)
    sort: list[ReportSort] = Field(default_factory=list, max_length=catalog.MAX_SORTS)
    group_by: ColumnKey | None = None

    @model_validator(mode="after")
    def _check_against_catalog(self) -> "ReportDefinition":
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("Jede Spalte darf nur einmal gewählt werden.")
        if len({s.column for s in self.sort}) != len(self.sort):
            raise ValueError("Nach jeder Spalte kann nur einmal sortiert werden.")
        referenced = [*self.columns, *(f.column for f in self.filters), *(s.column for s in self.sort)]
        if self.group_by is not None:
            referenced.append(self.group_by)
        for key in referenced:
            if not catalog.is_known_key(self.source, key):
                raise ValueError(f"Die Spalte „{key}“ gibt es in dieser Datenquelle nicht.")
        static = catalog.STATIC_COLUMNS[self.source]
        for item in self.filters:
            spec = static.get(item.column)
            if spec is not None:  # eigene Felder prüft der Dienst (Typ steht im Attribut-Katalog)
                catalog.normalize_filter_value(spec, item.operator, item.value)
        return self


class ReportPeriod(BaseModel):
    """Zeitraum und Seite eines Laufs. Zeitbezogene Quellen verlangen den Zeitraum (höchstens
    366 Tage) – geprüft im Dienst, weil die Quelle bei gespeicherten Berichten aus der Datenbank kommt."""

    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=MAX_PAGE_SIZE)

    @model_validator(mode="after")
    def _check_range(self) -> "ReportPeriod":
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("Bitte Beginn und Ende des Zeitraums angeben.")
        if self.date_from is not None and self.date_to is not None:
            if self.date_to < self.date_from:
                raise ValueError("Das Ende darf nicht vor dem Beginn liegen.")
            if (self.date_to - self.date_from).days > MAX_RANGE_DAYS:
                raise ValueError(f"Der Zeitraum darf höchstens {MAX_RANGE_DAYS} Tage umfassen.")
            if self.date_from.year < 2000 or self.date_to.year > 2100:
                raise ValueError("Der Zeitraum liegt außerhalb des erlaubten Bereichs.")
        return self


class ReportPreviewRequest(ReportPeriod):
    definition: ReportDefinition


class _SavedReportFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    definition: ReportDefinition
    shared: bool = False

    @field_validator("name", "description", mode="before")
    @classmethod
    def _strip(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class SavedReportRequest(_SavedReportFields):
    pass


class SavedReportResponse(BaseModel):
    id: int
    name: str
    description: str | None
    definition: ReportDefinition
    shared: bool
    owner_account_id: int | None
    owner_name: str | None
    # eigener Bericht des Anfragenden
    mine: bool
    # darf bearbeiten/löschen (Besitzer oder Admin)
    can_edit: bool
    created_at: datetime
    updated_at: datetime


class CatalogOption(BaseModel):
    value: str
    label: str


class CatalogColumn(BaseModel):
    key: str
    label: str
    type: Literal["text", "number", "date", "bool", "enum"]
    group: str
    operators: list[Operator]
    options: list[CatalogOption] = Field(default_factory=list)
    summable: bool = False


class CatalogSource(BaseModel):
    key: SourceKey
    label: str
    requires_period: bool
    columns: list[CatalogColumn]


class CatalogOperator(BaseModel):
    key: Operator
    label: str


class CatalogResponse(BaseModel):
    sources: list[CatalogSource]
    operators: list[CatalogOperator]
    max_columns: int
    max_filters: int
    max_sorts: int
    max_range_days: int
    max_page_size: int


Cell = str | float | bool | None


class ReportResultColumn(BaseModel):
    key: str
    label: str
    type: Literal["text", "number", "date", "bool", "enum"]
    summable: bool = False


class ReportGroup(BaseModel):
    # Anzeige des Gruppenwerts ("" = ohne Wert)
    label: str
    count: int
    # Summe je summierbarer Spalte (Spaltenschlüssel -> Summe)
    sums: dict[str, float]


class ReportResult(BaseModel):
    columns: list[ReportResultColumn]
    # eine Seite, Zellen in der Reihenfolge von columns (Datum als JJJJ-MM-TT, Auswahlwerte als Anzeige)
    rows: list[list[Cell]]
    total_rows: int
    page: int
    page_size: int
    # Summen über alle Zeilen (nicht nur die Seite)
    totals: dict[str, float]
    group_by: str | None = None
    # Anzeigename der Gruppierungsspalte (sie muss nicht unter den Ausgabespalten sein)
    group_by_label: str | None = None
    groups: list[ReportGroup] = Field(default_factory=list)
    # Spalten des gespeicherten Berichts, die für den Ausführenden nicht sichtbar sind (Anzeigenamen)
    omitted_columns: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
