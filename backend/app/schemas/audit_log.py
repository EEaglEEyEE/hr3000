from datetime import datetime

from pydantic import BaseModel

from app.models.audit_log_entry import AuditAction


class AuditLogEntryResponse(BaseModel):
    id: int
    actor_label: str
    action: AuditAction
    entity_type: str
    entity_id: int
    detail: str | None
    created_at: datetime
