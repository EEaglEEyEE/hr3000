from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.absence import AbsenceApprovalStatus, AbsenceType


class AbsenceCreateRequest(BaseModel):
    employee_id: int
    # Abwesenheitsart des Mandanten; alternativ (ältere Clients) nur die Kategorie.
    absence_type_id: int | None = None
    type: AbsenceType | None = None
    date_from: date
    date_to: date
    # Nur ein halber Tag (nur möglich, wenn date_from == date_to)
    half_day: bool = False
    # Genaue Dauer in Minuten (nur einzelner Tag, nicht zusammen mit half_day), max. 16 Std.
    duration_minutes: int | None = Field(default=None, ge=1, le=960)
    note: str | None = Field(default=None, max_length=400)
    # Vertretung (Mitarbeiter-ID), siehe AbsenceTypeDefinition.substitute_mode
    substitute_employee_id: int | None = Field(default=None, ge=1)
    # Krankheit während eines Urlaubs (§ 9 BUrlG): die betroffenen Urlaubstage zurückgeben, d.h.
    # den Urlaub um die Krankheitstage kürzen bzw. aufteilen. Ohne diese Angabe -> 409.
    split_vacation: bool = False

    @model_validator(mode="after")
    def _type_given(self) -> "AbsenceCreateRequest":
        if self.absence_type_id is None and self.type is None:
            raise ValueError("Bitte eine Abwesenheitsart angeben.")
        if (self.half_day or self.duration_minutes is not None) and self.date_from != self.date_to:
            raise ValueError("Halbe Tage und Stundenangaben sind nur für einen einzelnen Tag möglich.")
        if self.half_day and self.duration_minutes is not None:
            raise ValueError("Bitte entweder halber Tag oder Stunden angeben.")
        return self


class AbsenceUpdateRequest(BaseModel):
    absence_type_id: int | None = None
    type: AbsenceType | None = None
    date_from: date | None = None
    date_to: date | None = None
    half_day: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=960)
    # Stundenangabe entfernen (wieder ganzer Tag)
    clear_duration: bool = False
    note: str | None = Field(default=None, max_length=400)
    substitute_employee_id: int | None = Field(default=None, ge=1)
    # Vertretung entfernen
    clear_substitute: bool = False
    split_vacation: bool = False

    @model_validator(mode="after")
    def _substitute_or_clear(self) -> "AbsenceUpdateRequest":
        if self.clear_substitute and self.substitute_employee_id is not None:
            raise ValueError("Bitte entweder eine Vertretung angeben oder sie entfernen.")
        return self


class TeamOverlap(BaseModel):
    """Abwesenheit einer anderen Person aus demselben Team im gefragten Zeitraum."""

    employee_id: int
    name: str
    date_from: date
    date_to: date
    half_day: bool = False
    pending: bool
    # Art nur für Genehmigende (Mitarbeiter sehen nur, dass jemand fehlt)
    type_name: str | None = None


class SubstituteCandidate(BaseModel):
    id: int
    first_name: str
    last_name: str


class AbsenceDecideRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=300)


class AbsenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    type: AbsenceType
    absence_type_id: int | None = None
    date_from: date
    date_to: date
    half_day: bool = False
    duration_minutes: int | None = None
    created_by_account_id: int | None
    note: str | None
    substitute_employee_id: int | None = None
    certificate_document_id: int | None = None
    # Name der Vertretung (vom Endpunkt ergänzt, damit auch Mitarbeiter ihn sehen)
    substitute_name: str | None = None
    approval_status: AbsenceApprovalStatus
    decided_by_account_id: int | None
    decided_at: datetime | None
    # Genehmigungskette: aktueller Schritt und bei wem der offene Antrag liegt
    approval_step: int = 1
    waiting_for: str | None = None


class PendingAbsenceResponse(AbsenceResponse):
    """Offener Antrag mit dem, was zur Entscheidung gebraucht wird."""

    team_overlaps: list[TeamOverlap] = Field(default_factory=list)
    # Resturlaub im Jahr des Antragsbeginns (nur bei Urlaub)
    remaining_vacation_days: float | None = None
