from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry


def log_action(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor_hr_user_id: int | None,
    actor_employee_id: int | None,
    action: AuditAction,
    entity_type: str,
    entity_id: int,
    detail: str | None = None,
) -> None:
    """Fügt einen Audit-Log-Eintrag zur Session hinzu, ohne selbst zu
    committen – reitet auf der ohnehin folgenden db.commit() des Aufrufers
    mit, damit Audit-Eintrag und die eigentliche Änderung immer in derselben
    Transaktion landen."""
    db.add(
        AuditLogEntry(
            tenant_id=tenant_id,
            actor_hr_user_id=actor_hr_user_id,
            actor_employee_id=actor_employee_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )
