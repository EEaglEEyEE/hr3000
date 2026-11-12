"""Hinweisgebersystem (interne Meldestelle nach HinSchG), siehe app/services/whistle_service.py.

Grundsätze, die sich im Schema zeigen:
- Zur meldenden Person wird nichts gespeichert, was sie nicht selbst angegeben hat: keine IP-Adresse,
  kein Konto, kein Mitarbeiter. Es gibt dafür bewusst keine Spalte.
- Alle Inhalte (Beschreibung, Zeitpunkt/Ort, Kontaktangaben, Nachrichten, Abschlussvermerk, Dateinamen)
  liegen verschlüsselt (secret_box), die Anhänge verschlüsselt im Dokumentenspeicher.
- Der Zugangscode der meldenden Person steht nur als SHA-256 in der Tabelle.
- Wer Meldungen sehen darf, steht ausschließlich in whistle_officers (nicht aus der Rolle abgeleitet).
"""
import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WhistleCategory(str, enum.Enum):
    CRIME = "CRIME"  # Straftat / Ordnungswidrigkeit
    SAFETY = "SAFETY"  # Arbeitsschutz
    PRIVACY = "PRIVACY"  # Datenschutz
    CORRUPTION = "CORRUPTION"  # Korruption / Betrug
    DISCRIMINATION = "DISCRIMINATION"  # Diskriminierung / Belästigung
    OTHER = "OTHER"


class WhistleStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"  # Eingegangen
    IN_REVIEW = "IN_REVIEW"  # In Prüfung
    FEEDBACK_GIVEN = "FEEDBACK_GIVEN"  # Rückmeldung erteilt
    CLOSED = "CLOSED"  # Abgeschlossen


class WhistleMessageKind(str, enum.Enum):
    REPORTER = "REPORTER"  # Nachricht der meldenden Person (nie mit Konto)
    OFFICE = "OFFICE"  # Nachricht der Meldestelle an die meldende Person
    NOTE = "NOTE"  # interne Notiz, für die meldende Person unsichtbar


class WhistleOfficer(Base):
    """Meldestellen-Beauftragte:r: nur diese Konten sehen Meldungen (§ 8 HinSchG). Benennt der Admin."""

    __tablename__ = "whistle_officers"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", name="uq_whistle_officers_account"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    created_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WhistleCase(Base):
    __tablename__ = "whistle_cases"
    __table_args__ = (UniqueConstraint("tenant_id", "case_number", name="uq_whistle_cases_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    # Zufällig (nicht fortlaufend), damit die Nummer nichts über Anzahl und Reihenfolge verrät.
    case_number: Mapped[str] = mapped_column(String(12))
    # SHA-256 über Firma, Vorgangsnummer und Zugangscode (whistle_service.hash_access_code)
    access_code_hash: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=WhistleStatus.RECEIVED.value)
    description_encrypted: Mapped[str] = mapped_column(Text)
    # JSON, verschlüsselt: occurred_when, occurred_where, contact_name, contact_email (nur Angegebenes)
    details_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ohne Kontaktangabe – nur dieses Merkmal steht im Klartext (für die Liste)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closing_note_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Drei Jahre nach Abschluss (§ 11 Abs. 5 HinSchG); ab dann „zur Löschung fällig“
    delete_after: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Neue Nachricht/neuer Anhang der meldenden Person seit dem letzten Öffnen durch die Meldestelle
    unread_for_office: Mapped[bool] = mapped_column(Boolean, default=True)
    # Erinnerungen: 0 = keine, 1 = Vorwarnung verschickt, 2 = „überfällig“ verschickt
    ack_reminder_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    feedback_reminder_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    deletion_reminded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class WhistleMessage(Base):
    __tablename__ = "whistle_messages"
    __table_args__ = (Index("ix_whistle_messages_case", "case_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    case_id: Mapped[int] = mapped_column(ForeignKey("whistle_cases.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    body_encrypted: Mapped[str] = mapped_column(Text)
    # ACKNOWLEDGEMENT | FEEDBACK – diese Nachricht war die Eingangsbestätigung bzw. die Rückmeldung
    mark: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Nur bei OFFICE/NOTE; bei REPORTER immer NULL (keine Verknüpfung zur meldenden Person).
    author_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WhistleAttachment(Base):
    """Anhang der meldenden Person. Inhalt verschlüsselt im Dokumentenspeicher (storage_key), der –
    bereinigte – Dateiname verschlüsselt in der Tabelle."""

    __tablename__ = "whistle_attachments"
    __table_args__ = (Index("ix_whistle_attachments_case", "case_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    case_id: Mapped[int] = mapped_column(ForeignKey("whistle_cases.id", ondelete="CASCADE"))
    filename_encrypted: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
