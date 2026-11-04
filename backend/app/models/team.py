from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Team(Base):
    """Grundlage für die Supervisor-Rollenbeschränkung, siehe
    app/services/team_scope_service.py. location_id ist optional – ein Team
    kann standortübergreifend sein (z.B. eine Abteilung, die an mehreren
    Standorten vertreten ist)."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
