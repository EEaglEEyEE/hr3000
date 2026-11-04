import base64

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction
from app.services.audit_service import log_action
from app.services.settings_service import get_or_create_settings

router = APIRouter(tags=["branding"])

_MAX_LOGO_BYTES = 256 * 1024


class BrandingResponse(BaseModel):
    tenant_name: str | None
    # data:-URL des Firmenlogos oder None (dann nur das HR3000-Logo).
    logo_data_url: str | None


def _sniff_image(data: bytes) -> str | None:
    """Nur Rastergrafiken – kein SVG (könnte Skripte enthalten)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.get("/branding", response_model=BrandingResponse)
async def get_branding(request: Request, db: AsyncSession = Depends(get_db)) -> BrandingResponse:
    """Öffentlich (auch vor dem Login, z.B. Login-Seite und Kiosk): Name und Logo des Mandanten,
    der über den Hostnamen bestimmt wird."""
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        return BrandingResponse(tenant_name=None, logo_data_url=None)
    settings_row = await get_or_create_settings(db, tenant.id)
    logo = (
        f"data:{settings_row.logo_content_type};base64,{settings_row.logo_data}"
        if settings_row.logo_data and settings_row.logo_content_type
        else None
    )
    return BrandingResponse(tenant_name=tenant.name, logo_data_url=logo)


@router.put("/settings/logo", response_model=BrandingResponse)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> BrandingResponse:
    data = await file.read(_MAX_LOGO_BYTES + 1)
    if not data:
        raise AppError(400, "EMPTY_FILE", "Die Datei ist leer.")
    if len(data) > _MAX_LOGO_BYTES:
        raise AppError(413, "LOGO_TOO_LARGE", "Das Logo darf höchstens 256 KB groß sein.")
    content_type = _sniff_image(data)
    if content_type is None:
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", "Erlaubt sind PNG, JPEG oder WebP.")
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    settings_row.logo_content_type = content_type
    settings_row.logo_data = base64.b64encode(data).decode("ascii")
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.SETTINGS_CHANGED,
        entity_type="app_settings",
        entity_id=settings_row.id,
        detail=f"Firmenlogo hochgeladen ({content_type}, {len(data) // 1024} KB)",
    )
    await db.commit()
    return await get_branding(request, db)


@router.delete("/settings/logo", status_code=204)
async def delete_logo(
    actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> None:
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    settings_row.logo_content_type = None
    settings_row.logo_data = None
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.SETTINGS_CHANGED,
        entity_type="app_settings",
        entity_id=settings_row.id,
        detail="Firmenlogo entfernt",
    )
    await db.commit()
