"""Schemas für das Recruiting (Stellen, Bewerbungen, Karriereseite)."""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.document import DocumentCategory

JobStatus = Literal["DRAFT", "PUBLISHED", "CLOSED"]
EmploymentType = Literal[
    "FULL_TIME", "PART_TIME", "MINI_JOB", "FIXED_TERM", "APPRENTICESHIP", "INTERNSHIP", "WORKING_STUDENT", "FREELANCE"
]
Stage = Literal["NEW", "SCREENING", "INTERVIEW", "OFFER", "HIRED", "REJECTED", "WITHDRAWN"]
Source = Literal["CAREER_PAGE", "MANUAL"]
RejectionReason = Literal["QUALIFICATION", "EXPERIENCE", "SALARY", "POSITION_FILLED", "NO_RESPONSE", "OTHER"]
AttachmentKind = Literal["CV", "OTHER"]

PHONE_PATTERN = r"^[0-9+()/ .\-]*$"
_MIN_DATE = dt.date(2000, 1, 1)
_MAX_DATE = dt.date(2100, 12, 31)


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _valid_date(value: dt.date | None, label: str) -> None:
    if value is not None and not _MIN_DATE <= value <= _MAX_DATE:
        raise ValueError(f"{label}: bitte ein Datum zwischen 2000 und 2100 angeben.")


# --- Stellen ---------------------------------------------------------------------------------


class JobWriteRequest(BaseModel):
    """Anlegen und Ändern einer Stelle (immer der vollständige Stand)."""

    title: str = Field(min_length=1, max_length=200)
    department_id: int | None = Field(default=None, ge=1)
    location_id: int | None = Field(default=None, ge=1)
    employment_type: EmploymentType = "FULL_TIME"
    # Einfacher Text: Absätze durch Leerzeilen, Listen mit „- “ am Zeilenanfang
    description: str = Field(default="", max_length=20000)
    status: JobStatus = "DRAFT"
    application_deadline: dt.date | None = None
    # Hiring Team: Konten, die die Bewerbungen dieser Stelle sehen dürfen (zusätzlich zu Admin/HR)
    member_account_ids: list[int] = Field(default_factory=list, max_length=50)

    _strip_title = field_validator("title", mode="before")(_strip)

    @model_validator(mode="after")
    def _check(self) -> "JobWriteRequest":
        _valid_date(self.application_deadline, "Bewerbungsschluss")
        if any(account_id < 1 for account_id in self.member_account_ids):
            raise ValueError("Hiring Team: ungültiges Konto.")
        if len(set(self.member_account_ids)) != len(self.member_account_ids):
            raise ValueError("Hiring Team: jedes Konto nur einmal angeben.")
        return self


class JobMemberResponse(BaseModel):
    account_id: int
    name: str
    email: str | None = None


class TeamCandidateResponse(BaseModel):
    """Konto, das ins Hiring Team aufgenommen werden kann."""

    account_id: int
    name: str
    email: str | None = None
    role: str | None = None


class JobResponse(BaseModel):
    id: int
    title: str
    slug: str
    department_id: int | None = None
    department_name: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    employment_type: EmploymentType
    description: str
    status: JobStatus
    application_deadline: dt.date | None = None
    published_at: dt.datetime | None = None
    created_at: dt.datetime
    # auf der Karriereseite sichtbar (veröffentlicht und Bewerbungsschluss nicht überschritten)
    public: bool
    members: list[JobMemberResponse] = []
    application_count: int = 0
    # Bewerbungen in laufenden Phasen (Neu bis Angebot)
    open_count: int = 0
    # Anonyme Zählung gelöschter Bewerbungen je (letzter) Phase
    deleted_counts: dict[str, int] = {}


# --- Bewerbungen -----------------------------------------------------------------------------


class ApplicationCreateRequest(BaseModel):
    """Manuell erfasste Bewerbung (z. B. per Post oder E-Mail eingegangen)."""

    job_id: int = Field(ge=1)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40, pattern=PHONE_PATTERN)
    cover_letter: str | None = Field(default=None, max_length=20000)
    # Freitext (z. B. „52.000 € brutto/Jahr“); nur mit Berechtigung „Vergütung & Lohn-Export“
    salary_expectation: str | None = Field(default=None, max_length=200)
    talent_pool: bool = False

    _strip_names = field_validator("first_name", "last_name", "phone", "salary_expectation", mode="before")(_strip)


class ApplicationUpdateRequest(BaseModel):
    """Nur die angegebenen Felder ändern; "" leert Telefon, Anschreiben und Gehaltsvorstellung."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40, pattern=PHONE_PATTERN)
    cover_letter: str | None = Field(default=None, max_length=20000)
    salary_expectation: str | None = Field(default=None, max_length=200)
    talent_pool: bool | None = None

    _strip_names = field_validator("first_name", "last_name", "phone", "salary_expectation", mode="before")(_strip)


class StageChangeRequest(BaseModel):
    stage: Stage
    # Absagegrund: Pflicht bei „Abgelehnt“, sonst nicht erlaubt
    rejection_reason: RejectionReason | None = None
    # Freitext zur Absage bzw. zum Rückzug
    rejection_note: str | None = Field(default=None, max_length=500)

    _strip_note = field_validator("rejection_note", mode="before")(_strip)

    @model_validator(mode="after")
    def _check(self) -> "StageChangeRequest":
        if self.stage == "REJECTED" and self.rejection_reason is None:
            raise ValueError("Bitte einen Absagegrund wählen.")
        if self.stage != "REJECTED" and self.rejection_reason is not None:
            raise ValueError("Ein Absagegrund gehört nur zur Phase „Abgelehnt“.")
        if self.stage not in ("REJECTED", "WITHDRAWN") and self.rejection_note:
            raise ValueError("Eine Begründung gehört nur zu „Abgelehnt“ oder „Zurückgezogen“.")
        return self


class NoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    _strip_body = field_validator("body", mode="before")(_strip)


class RatingRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)

    _strip_comment = field_validator("comment", mode="before")(_strip)


class HireRequest(BaseModel):
    """„Als Mitarbeiter übernehmen“: Angaben für die Anlage des Mitarbeiters."""

    employee_number: str = Field(min_length=1, max_length=50)
    # Vorbelegt aus der Bewerbung
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    # Private E-Mail-Adresse (Personalakte, „Persönliche Daten“); ohne Angabe die der Bewerbung
    private_email: EmailStr | None = None
    location_id: int = Field(ge=1)
    department_id: int | None = Field(default=None, ge=1)
    hire_date: dt.date
    position: str | None = Field(default=None, max_length=150)
    # Anhänge der Bewerbung, die in die Personalakte übernommen werden
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)
    document_category: DocumentCategory = DocumentCategory.OTHER
    # Onboarding-Checkliste starten (Vorlage)
    checklist_template_id: int | None = Field(default=None, ge=1)

    _strip_fields = field_validator("employee_number", "first_name", "last_name", "position", mode="before")(_strip)

    @model_validator(mode="after")
    def _check(self) -> "HireRequest":
        _valid_date(self.hire_date, "Eintrittsdatum")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("Jeden Anhang nur einmal angeben.")
        if any(attachment_id < 1 for attachment_id in self.attachment_ids):
            raise ValueError("Ungültiger Anhang.")
        return self


class HireResponse(BaseModel):
    employee_id: int
    documents_copied: int
    checklist_started: bool


class AttachmentResponse(BaseModel):
    id: int
    kind: AttachmentKind
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: dt.datetime


class NoteResponse(BaseModel):
    id: int
    author_account_id: int | None = None
    author_name: str | None = None
    body: str
    created_at: dt.datetime
    # eigene Notiz bzw. Admin/HR
    can_delete: bool = False


class RatingResponse(BaseModel):
    account_id: int
    name: str | None = None
    score: int
    comment: str | None = None
    updated_at: dt.datetime
    mine: bool = False


class StageEventResponse(BaseModel):
    from_stage: Stage | None = None
    to_stage: Stage
    account_name: str | None = None
    created_at: dt.datetime


class ApplicationListItem(BaseModel):
    id: int
    job_id: int
    job_title: str
    first_name: str
    last_name: str
    email: str
    stage: Stage
    source: Source
    talent_pool: bool
    created_at: dt.datetime
    closed_at: dt.datetime | None = None
    # Tag, ab dem der Hintergrundlauf die Bewerbung löscht (nur abgelehnt/zurückgezogen)
    delete_on: dt.date | None = None
    average_rating: float | None = None
    rating_count: int = 0
    attachment_count: int = 0
    employee_id: int | None = None


class ApplicationDetailResponse(ApplicationListItem):
    phone: str | None = None
    cover_letter: str | None = None
    # nur mit Berechtigung „Vergütung & Lohn-Export“ gefüllt (salary_visible)
    salary_expectation: str | None = None
    salary_visible: bool = False
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = None
    privacy_acknowledged_at: dt.datetime | None = None
    hired_at: dt.datetime | None = None
    attachments: list[AttachmentResponse] = []
    notes: list[NoteResponse] = []
    ratings: list[RatingResponse] = []
    events: list[StageEventResponse] = []
    # Admin/HR: löschen, übernehmen, Stelle verwalten
    can_manage: bool = False


class RecruitingAccessResponse(BaseModel):
    """Für Menü und Reiter: Ist Recruiting eingeschaltet und was darf das Konto?"""

    enabled: bool
    # Admin/HR: Stellen verwalten, alle Bewerbungen
    can_manage: bool
    # im Hiring Team mindestens einer Stelle
    member: bool
    can_see_salary: bool


# --- Karriereseite (öffentlich) ---------------------------------------------------------------


class PublicJobResponse(BaseModel):
    id: int
    slug: str
    title: str
    department: str | None = None
    location: str | None = None
    employment_type: EmploymentType
    application_deadline: dt.date | None = None


class PublicJobDetailResponse(PublicJobResponse):
    description: str
    company_name: str
    privacy_text: str | None = None
    privacy_url: str | None = None
    max_files: int
    max_file_mb: int


class CareersResponse(BaseModel):
    company_name: str
    privacy_text: str | None = None
    privacy_url: str | None = None
    jobs: list[PublicJobResponse]


class PublicApplicationForm(BaseModel):
    """Formularfelder der Bewerbung über die Karriereseite (Multipart, hier geprüft)."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40, pattern=PHONE_PATTERN)
    cover_letter: str | None = Field(default=None, max_length=20000)
    salary_expectation: str | None = Field(default=None, max_length=200)
    # Pflicht: Kenntnisnahme der Datenschutzhinweise
    privacy_acknowledged: bool
    talent_pool: bool = False
    # Honeypot (für Menschen unsichtbar)
    website: str | None = Field(default=None, max_length=500)

    _strip_fields = field_validator(
        "first_name", "last_name", "email", "phone", "cover_letter", "salary_expectation", mode="before"
    )(_strip)

    @model_validator(mode="after")
    def _check(self) -> "PublicApplicationForm":
        if not self.privacy_acknowledged:
            raise ValueError("Bitte die Kenntnisnahme der Datenschutzhinweise bestätigen.")
        return self


class PublicApplicationResponse(BaseModel):
    received: bool = True
