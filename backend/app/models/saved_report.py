"""Gespeicherte eigene Berichte (Berichts-Builder, app/services/report_builder_service.py)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SavedReport(Base):
    """Definition eines eigenen Berichts: Datenquelle, Spalten, Filter, Sortierung, Gruppierung als
    geprüftes JSON (app/schemas/report_builder.py ReportDefinition) – nie SQL. Gespeichert wird nur
    die Definition; das Ergebnis entsteht bei jedem Ausführen neu und richtet sich nach den Rechten
    dessen, der ausführt (Führungskräfte: nur der eigene Bereich, auch bei geteilten Berichten).

    owner_account_id wird NULL, wenn das Konto gelöscht wird (der Bericht bleibt, bearbeiten kann ihn
    dann nur noch ein Admin)."""

    __tablename__ = "saved_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    owner_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # JSON der ReportDefinition; wird bei jedem Lesen erneut gegen die Positivliste geprüft.
    definition: Mapped[str] = mapped_column(Text)
    # Geteilt = alle Verwaltungskonten der Firma dürfen ihn sehen und ausführen.
    shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
