from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SupervisorTeamAssignment(Base):
    """Ordnet ein Konto mit Rolle SUPERVISOR (Teamleiter/in) einem Team zu."""

    __tablename__ = "supervisor_team_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    account: Mapped["Account"] = relationship(lazy="selectin")

    @property
    def employee_id(self) -> int | None:
        """Mitarbeiter des Kontos (die Webapp ordnet Teamleitungen über Mitarbeiter zu)."""
        return self.account.employee_id if self.account is not None else None
