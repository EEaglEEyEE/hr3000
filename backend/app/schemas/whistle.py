"""Schemas des Hinweisgebersystems. Öffentliche Eingaben (Meldung, Zugangsdaten, Nachricht) sind eng
begrenzt, weil die Endpoints ohne Anmeldung erreichbar sind."""
import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.audit_log_entry import AuditAction
from app.models.whistle import WhistleCategory, WhistleStatus

DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 10000
MESSAGE_MAX = 5000
NOTE_MAX = 4000
SHORT_MAX = 200

CASE_NUMBER_PATTERN = r"^H-[A-Z2-9]{8}$"
_ACCESS_CODE = re.compile(r"^[A-Z2-9]{20}$")
# Steuerzeichen außer Zeilenumbruch und Tabulator haben in Freitext nichts verloren.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(value: str | None) -> str | None:
    """Trimmt, entfernt Steuerzeichen, leer -> None."""
    if value is None:
        return None
    cleaned = _CONTROL.sub("", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
    return cleaned or None


def _clean_line(value: str | None) -> str | None:
    cleaned = _clean(value)
    return " ".join(cleaned.split()) if cleaned else None


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- öffentlich ------------------------------------------------------------------------------


class WhistleInfoResponse(BaseModel):
    company_name: str
    # False = Hinweisgebersystem ist an, aber niemand als Beauftragte:r benannt: keine neuen Meldungen
    accepting_reports: bool
    max_attachment_bytes: int
    max_attachments: int


class WhistleReportCreate(_Strict):
    category: WhistleCategory
    description: str = Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)
    occurred_when: str | None = Field(default=None, max_length=SHORT_MAX)
    occurred_where: str | None = Field(default=None, max_length=SHORT_MAX)
    anonymous: bool = True
    contact_name: str | None = Field(default=None, max_length=SHORT_MAX)
    contact_email: EmailStr | None = Field(default=None, max_length=255)

    @field_validator("contact_email", mode="before")
    @classmethod
    def _blank_email(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("occurred_when", "occurred_where", "contact_name")
    @classmethod
    def _line(cls, value: str | None) -> str | None:
        return _clean_line(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        cleaned = _clean(value)
        if cleaned is None or len(cleaned) < DESCRIPTION_MIN:
            raise ValueError(f"Bitte beschreiben Sie den Sachverhalt mit mindestens {DESCRIPTION_MIN} Zeichen.")
        return cleaned

    @model_validator(mode="after")
    def _contact(self) -> "WhistleReportCreate":
        has_contact = self.contact_name is not None or self.contact_email is not None
        if self.anonymous and has_contact:
            raise ValueError("Eine anonyme Meldung enthält keine Kontaktangaben.")
        if not self.anonymous and not has_contact:
            raise ValueError("Bitte Name oder E-Mail-Adresse angeben – oder die Meldung anonym abgeben.")
        return self


class WhistleReportCreated(BaseModel):
    """Vorgangsnummer und Zugangscode – der Code wird nur dieses eine Mal ausgegeben."""

    case_number: str
    access_code: str


class WhistleAccess(_Strict):
    case_number: str = Field(min_length=1, max_length=20)
    access_code: str = Field(min_length=1, max_length=60)

    @field_validator("case_number")
    @classmethod
    def _number(cls, value: str) -> str:
        normalized = re.sub(r"\s", "", value).upper()
        if not re.match(CASE_NUMBER_PATTERN, normalized):
            # Kein eigener Fehlertext: ein falsch geschriebener Vorgang wird wie ein falscher Code behandelt.
            return "H-INVALID"
        return normalized

    @field_validator("access_code")
    @classmethod
    def _code(cls, value: str) -> str:
        normalized = re.sub(r"[\s-]", "", value).upper()
        return normalized if _ACCESS_CODE.match(normalized) else "INVALID"


class WhistleReporterMessageCreate(WhistleAccess):
    body: str = Field(min_length=1, max_length=MESSAGE_MAX)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = _clean(value)
        if cleaned is None:
            raise ValueError("Die Nachricht ist leer.")
        return cleaned


class WhistlePublicMessage(BaseModel):
    from_office: bool
    body: str
    created_at: datetime
    mark: Literal["ACKNOWLEDGEMENT", "FEEDBACK"] | None = None


class WhistlePublicAttachment(BaseModel):
    filename: str
    size_bytes: int
    created_at: datetime


class WhistlePublicCase(BaseModel):
    """Was die meldende Person mit Vorgangsnummer und Zugangscode sieht – ohne interne Notizen,
    Verlauf und Abschlussvermerk."""

    case_number: str
    category: WhistleCategory
    status: WhistleStatus
    description: str
    received_at: datetime
    acknowledged_at: datetime | None
    messages: list[WhistlePublicMessage]
    attachments: list[WhistlePublicAttachment]


# --- Meldestelle -----------------------------------------------------------------------------


class WhistleStatusResponse(BaseModel):
    """Für Menü und „Mein Bereich“: ist das Hinweisgebersystem an, bin ich Beauftragte:r?"""

    enabled: bool
    officer: bool


class WhistleCaseSummary(BaseModel):
    id: int
    case_number: str
    category: WhistleCategory
    status: WhistleStatus
    anonymous: bool
    unread: bool
    received_at: datetime
    acknowledged_at: datetime | None
    feedback_at: datetime | None
    closed_at: datetime | None
    ack_due: date
    ack_overdue: bool
    feedback_due: date
    feedback_overdue: bool
    delete_after: date | None
    deletion_due: bool


class WhistleMessageResponse(BaseModel):
    id: int
    kind: Literal["REPORTER", "OFFICE", "NOTE"]
    body: str
    mark: Literal["ACKNOWLEDGEMENT", "FEEDBACK"] | None
    author_label: str | None
    created_at: datetime


class WhistleAttachmentResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class WhistleProtocolEntry(BaseModel):
    action: AuditAction
    actor_label: str
    detail: str | None
    created_at: datetime


class WhistleCaseDetail(WhistleCaseSummary):
    description: str
    occurred_when: str | None
    occurred_where: str | None
    contact_name: str | None
    contact_email: str | None
    closing_note: str | None
    messages: list[WhistleMessageResponse]
    attachments: list[WhistleAttachmentResponse]
    protocol: list[WhistleProtocolEntry]


class WhistleOfficeMessageCreate(_Strict):
    kind: Literal["MESSAGE", "NOTE"]
    body: str = Field(min_length=1, max_length=MESSAGE_MAX)
    # Nur bei MESSAGE: diese Nachricht ist die Eingangsbestätigung bzw. die Rückmeldung
    mark: Literal["ACKNOWLEDGEMENT", "FEEDBACK"] | None = None

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = _clean(value)
        if cleaned is None:
            raise ValueError("Der Text ist leer.")
        return cleaned

    @model_validator(mode="after")
    def _mark_only_for_messages(self) -> "WhistleOfficeMessageCreate":
        if self.kind == "NOTE" and self.mark is not None:
            raise ValueError("Eine interne Notiz kann keine Eingangsbestätigung oder Rückmeldung sein.")
        return self


class WhistleCaseUpdate(_Strict):
    status: WhistleStatus
    closing_note: str | None = Field(default=None, max_length=NOTE_MAX)

    @field_validator("closing_note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return _clean(value)

    @model_validator(mode="after")
    def _closing_note(self) -> "WhistleCaseUpdate":
        if self.status == WhistleStatus.CLOSED and self.closing_note is None:
            raise ValueError("Zum Abschließen ist ein Abschlussvermerk nötig.")
        if self.status != WhistleStatus.CLOSED and self.closing_note is not None:
            raise ValueError("Ein Abschlussvermerk gehört nur zum Status „Abgeschlossen“.")
        return self


# --- Beauftragte (Admin) ---------------------------------------------------------------------


class WhistleOfficerAccount(BaseModel):
    account_id: int
    name: str
    email: str | None


class WhistleOfficersResponse(BaseModel):
    officers: list[WhistleOfficerAccount]
    # Konten der Firma mit Zugang, die noch nicht benannt sind
    candidates: list[WhistleOfficerAccount]


class WhistleOfficerCreate(_Strict):
    account_id: int = Field(ge=1)
