from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Verschlüsselte Inhalte (Fernet, app/services/secret_box.py) können groß werden – MySQL-TEXT reicht
# nur bis 64 KB.
_LARGE_TEXT = Text().with_variant(MEDIUMTEXT(), "mysql")


class PayrollRelease(Base):
    """Freigegebener Monat der vorbereitenden Lohnbuchhaltung (app/services/payroll_accounting_service.py):
    eingefrorener Schnappschuss (JSON) und die Exportdateien von damals (generisches CSV, DATEV LODAS
    wenn eingerichtet) – alles verschlüsselt. Danach unverändert abrufbar; „Freigabe zurücknehmen“
    (nur Admin) löscht die Zeile, das Audit-Protokoll behält den Vorgang."""

    __tablename__ = "payroll_releases"
    __table_args__ = (UniqueConstraint("tenant_id", "year", "month", name="uq_payroll_releases_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    released_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    released_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    # Mitarbeiter, deren Monatsabschluss bei der Freigabe noch nicht abgeschlossen war (Warnung)
    open_closures: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[str] = mapped_column(_LARGE_TEXT)
    csv_file: Mapped[str] = mapped_column(_LARGE_TEXT)
    # NULL = DATEV war bei der Freigabe nicht eingerichtet
    datev_file: Mapped[str | None] = mapped_column(_LARGE_TEXT, nullable=True)
