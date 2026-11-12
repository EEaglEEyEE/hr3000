"""Recruiting: Stellen, Bewerbungen und der Bewerbungsprozess (Migrationen 0154–0156).

- Stelle (``RecruitingJob``) mit Status Entwurf/Veröffentlicht/Geschlossen und „Hiring Team“
  (``RecruitingJobMember``: Konten, die die Bewerbungen dieser Stelle sehen – zusätzlich zu Admin/HR).
- Bewerbung (``RecruitingApplication``) mit Phase, Quelle, Anhängen (verschlüsselt abgelegt wie
  Dokumente der Personalakte), Notizen, Bewertungen je Konto und Verlauf der Phasenwechsel.
- Anschreiben, Gehaltsvorstellung, Notizen und Bewertungskommentare stehen verschlüsselt in der
  Datenbank (``secret_box``).
- Nach dem Löschen einer Bewerbung bleibt nur eine anonyme Zählung je Stelle und Phase
  (``RecruitingStat``).

Alle Tabellen tragen ``tenant_id`` (Mandantentrennung in jeder Abfrage, Löschung einer Firma über
``tenant_lifecycle.purge_plan``). Regeln und Abläufe: app/services/recruiting_service.py.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JOB_DRAFT = "DRAFT"
JOB_PUBLISHED = "PUBLISHED"
JOB_CLOSED = "CLOSED"
JOB_STATUSES = (JOB_DRAFT, JOB_PUBLISHED, JOB_CLOSED)

EMPLOYMENT_TYPES = (
    "FULL_TIME",
    "PART_TIME",
    "MINI_JOB",
    "FIXED_TERM",
    "APPRENTICESHIP",
    "INTERNSHIP",
    "WORKING_STUDENT",
    "FREELANCE",
)

# Phasen einer Bewerbung (fest). REJECTED und WITHDRAWN schließen die Bewerbung ab – ab dann läuft
# die Löschfrist.
STAGE_NEW = "NEW"
STAGE_SCREENING = "SCREENING"
STAGE_INTERVIEW = "INTERVIEW"
STAGE_OFFER = "OFFER"
STAGE_HIRED = "HIRED"
STAGE_REJECTED = "REJECTED"
STAGE_WITHDRAWN = "WITHDRAWN"
STAGES = (STAGE_NEW, STAGE_SCREENING, STAGE_INTERVIEW, STAGE_OFFER, STAGE_HIRED, STAGE_REJECTED, STAGE_WITHDRAWN)
CLOSED_STAGES = (STAGE_REJECTED, STAGE_WITHDRAWN)

SOURCE_CAREER_PAGE = "CAREER_PAGE"
SOURCE_MANUAL = "MANUAL"
SOURCES = (SOURCE_CAREER_PAGE, SOURCE_MANUAL)

REJECTION_REASONS = (
    "QUALIFICATION",
    "EXPERIENCE",
    "SALARY",
    "POSITION_FILLED",
    "NO_RESPONSE",
    "OTHER",
)

ATTACHMENT_CV = "CV"
ATTACHMENT_OTHER = "OTHER"
ATTACHMENT_KINDS = (ATTACHMENT_CV, ATTACHMENT_OTHER)


class RecruitingJob(Base):
    __tablename__ = "recruiting_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(20), default="FULL_TIME")
    # Einfacher Text (Absätze, Listen mit „- “); nie als HTML ausgegeben
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default=JOB_DRAFT)
    # Letzter Tag, an dem Bewerbungen über die Karriereseite möglich sind (leer = ohne Frist)
    application_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecruitingJobMember(Base):
    """Hiring Team: Konto, das die Bewerbungen der Stelle sehen, bewerten und weiterführen darf."""

    __tablename__ = "recruiting_job_members"
    __table_args__ = (UniqueConstraint("job_id", "account_id", name="uq_recruiting_job_members"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)


class RecruitingApplication(Base):
    __tablename__ = "recruiting_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # verschlüsselt (secret_box)
    cover_letter_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # verschlüsselt; nur mit Berechtigung „Vergütung & Lohn-Export“ lesbar
    salary_expectation_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(12), default=STAGE_NEW, index=True)
    source: Mapped[str] = mapped_column(String(12), default=SOURCE_MANUAL)
    rejection_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # „Bewerbung für künftige Stellen aufbewahren“ – verlängerte Löschfrist
    talent_pool: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Kenntnisnahme der Datenschutzhinweise (Karriereseite)
    privacy_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Abschluss (Abgelehnt/Zurückgezogen) – Beginn der Löschfrist
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # „Als Mitarbeiter übernehmen“: der angelegte Mitarbeiter (verhindert doppelte Übernahme)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    hired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecruitingAttachment(Base):
    """Anhang einer Bewerbung (PDF/Bild), verschlüsselt abgelegt wie Dokumente der Personalakte."""

    __tablename__ = "recruiting_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("recruiting_applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default=ATTACHMENT_OTHER)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecruitingNote(Base):
    __tablename__ = "recruiting_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    application_id: Mapped[int] = mapped_column(ForeignKey("recruiting_applications.id", ondelete="CASCADE"), index=True)
    author_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    body_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecruitingRating(Base):
    """Bewertung 1–5 je Konto und Bewerbung, mit Kommentar."""

    __tablename__ = "recruiting_ratings"
    __table_args__ = (UniqueConstraint("application_id", "account_id", name="uq_recruiting_ratings"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    application_id: Mapped[int] = mapped_column(ForeignKey("recruiting_applications.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(Integer)
    comment_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecruitingStageEvent(Base):
    """Verlauf: Eingang und jeder Phasenwechsel."""

    __tablename__ = "recruiting_stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    application_id: Mapped[int] = mapped_column(ForeignKey("recruiting_applications.id", ondelete="CASCADE"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(12), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(12))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecruitingStat(Base):
    """Anonyme Zählung gelöschter Bewerbungen je Stelle und (letzter) Phase – das Einzige, was nach
    dem Löschen einer Bewerbung bleibt."""

    __tablename__ = "recruiting_stats"
    __table_args__ = (UniqueConstraint("job_id", "stage", name="uq_recruiting_stats"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(12))
    count: Mapped[int] = mapped_column(Integer, default=0)
