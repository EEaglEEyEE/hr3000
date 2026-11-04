from datetime import date

from sqlalchemy import Date, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BreakRule(Base):
    """Staffel für gesetzlichen automatischen Pausenabzug nach §4 ArbZG.

    Mehrere Zeilen bilden die Staffel, z.B. (360, 30) und (540, 45) für
    >6 Std. -> 30 Min. und >9 Std. -> 45 Min. Pausenabzug. Pro Mandant, wird
    bei Mandanten-Anlage aus den gesetzlichen Mindestwerten vorbefüllt, siehe
    app/services/settings_service.py seed_default_break_rules.
    """

    __tablename__ = "break_rules"
    # Effektiv-datiert: Änderungen gelten ab einem Stichtag, frühere Tage rechnen mit der alten
    # Staffel weiter (keine rückwirkende Änderung abgeschlossener Monate). Eindeutigkeit der
    # Schwelle je Zeitraum prüft app/api/break_rules.py.
    __table_args__ = (Index("ix_break_rules_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    min_work_minutes: Mapped[int] = mapped_column()
    deduct_minutes: Mapped[int] = mapped_column()
    valid_from: Mapped[date] = mapped_column(Date, default=date(2000, 1, 1))
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
