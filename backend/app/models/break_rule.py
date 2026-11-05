import enum
from datetime import date, time

from sqlalchemy import Date, Enum, ForeignKey, Index, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BreakRuleKind(str, enum.Enum):
    # Gesetzliche Staffel (§4 ArbZG): Mindestpause ab einer Arbeitszeit; gestempelte Pausen zählen mit.
    LEGAL = "LEGAL"
    # Betriebliche feste Pause: ab einer Arbeitszeit mindestens so viele Minuten (auch ohne Stempelung).
    FIXED_MINUTES = "FIXED_MINUTES"
    # Feste Pausenzeit (z.B. 12:00–12:30): wird abgezogen, soweit der Mitarbeiter in dem Fenster anwesend war.
    FIXED_WINDOW = "FIXED_WINDOW"


class BreakRule(Base):
    """Pausenregel eines Mandanten.

    LEGAL: mehrere Zeilen bilden die gesetzliche Staffel, z.B. (360, 30) und (540, 45) für
    >6 Std. -> 30 Min. und >9 Std. -> 45 Min. Pausenabzug; wird bei Mandanten-Anlage aus den
    gesetzlichen Mindestwerten vorbefüllt, siehe app/services/settings_service.py
    seed_default_break_rules. FIXED_MINUTES/FIXED_WINDOW sind betriebliche Regeln obendrauf –
    die gesetzliche Staffel bleibt immer die Untergrenze. Ein Arbeitszeitmodell bzw. eine
    Schichtvorlage mit eigener Pause ersetzt die betrieblichen Regeln des Mandanten, siehe
    app/services/timesheet_service.py break_policy.
    """

    __tablename__ = "break_rules"
    # Effektiv-datiert: Änderungen gelten ab einem Stichtag, frühere Tage rechnen mit der alten
    # Staffel weiter (keine rückwirkende Änderung abgeschlossener Monate). Eindeutigkeit der
    # Schwelle bzw. Überschneidungsfreiheit der Fenster je Zeitraum prüft app/api/break_rules.py.
    __table_args__ = (Index("ix_break_rules_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    kind: Mapped[BreakRuleKind] = mapped_column(Enum(BreakRuleKind), default=BreakRuleKind.LEGAL)
    # LEGAL/FIXED_MINUTES: Schwelle (Arbeitsminuten) und Pausenminuten. FIXED_WINDOW: 0 und Fensterlänge.
    min_work_minutes: Mapped[int] = mapped_column()
    deduct_minutes: Mapped[int] = mapped_column()
    # Nur FIXED_WINDOW: Pausenzeit in Ortszeit des Standorts (Beginn vor Ende, nicht über Mitternacht).
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, default=date(2000, 1, 1))
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
