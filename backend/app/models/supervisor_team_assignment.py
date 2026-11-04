from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SupervisorTeamAssignment(Base):
    """Ordnet einen Supervisor (HrUser ODER Employee mit hr_role=SUPERVISOR,
    genau eines von beiden – dasselbe Dual-Actor-Muster wie z.B. bei
    Absence.created_by/created_by_employee_id) einem Team zu."""

    __tablename__ = "supervisor_team_assignments"
    __table_args__ = (
        CheckConstraint(
            "(hr_user_id IS NOT NULL) <> (employee_id IS NOT NULL)",
            name="ck_supervisor_team_assignment_exactly_one_actor",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("hr_users.id"), nullable=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
