from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.db import get_db
from app.errors import AppError
from app.models import Notification
from app.schemas.notification import NotificationResponse

router = APIRouter(tags=["notifications"])

_MAX_LIMIT = 100


def _require_non_device(actor: Actor) -> None:
    if actor.device is not None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")


def _recipient_clause(actor: Actor):
    if actor.hr_user is not None:
        return Notification.recipient_hr_user_id == actor.hr_user.id
    return Notification.recipient_employee_id == actor.employee.id


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    limit: int = Query(default=30, le=_MAX_LIMIT),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    """Eigene Benachrichtigungen (HrUser ODER Employee-Login, siehe
    app/services/notification_service.py) – neueste zuerst."""
    _require_non_device(actor)

    stmt = (
        select(Notification)
        .where(Notification.tenant_id == actor.tenant_id, _recipient_clause(actor))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [NotificationResponse.model_validate(n) for n in result.scalars().all()]


@router.patch("/notifications/read-all", status_code=204)
async def mark_all_notifications_read(
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_non_device(actor)

    await db.execute(
        update(Notification)
        .where(
            Notification.tenant_id == actor.tenant_id,
            _recipient_clause(actor),
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    _require_non_device(actor)

    notification = await db.get(Notification, notification_id)
    is_owner = notification is not None and (
        (actor.hr_user is not None and notification.recipient_hr_user_id == actor.hr_user.id)
        or (actor.employee is not None and notification.recipient_employee_id == actor.employee.id)
    )
    if notification is None or notification.tenant_id != actor.tenant_id or not is_owner:
        raise AppError(404, "NOTIFICATION_NOT_FOUND", "Benachrichtigung nicht gefunden.")

    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notification)

    return NotificationResponse.model_validate(notification)
