"""Öffentliche API (Zugänge mit Client-ID/Secret) und Webhooks samt Ausgangswarteschlange."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

API_SCOPES = ("employees:read", "absences:read", "attendances:read")
WEBHOOK_EVENTS = ("employee.created", "employee.updated", "absence.created", "absence.decided")


class ApiClient(Base):
    __tablename__ = "api_clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    client_id: Mapped[str] = mapped_column(String(40), unique=True)
    # SHA-256 des Secrets – das Secret selbst wird nur beim Anlegen einmal angezeigt
    secret_hash: Mapped[str] = mapped_column(String(64))
    # Kommagetrennt, siehe API_SCOPES
    scopes: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    url: Mapped[str] = mapped_column(String(500))
    # Signatur-Secret verschlüsselt (secret_box) – wird zum Signieren gebraucht
    secret: Mapped[str] = mapped_column(String(300))
    events: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(200), nullable=True)


class WebhookDelivery(Base):
    """Ausgangswarteschlange: wird in derselben Transaktion wie die Änderung geschrieben und von
    app/services/webhook_service.run_deliveries zugestellt (übersteht Neustarts)."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[str] = mapped_column(Text)
    # PENDING, SENT, FAILED
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
