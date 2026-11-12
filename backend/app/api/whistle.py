"""Hinweisgebersystem – Meldestelle und Benennung der Beauftragten (app/services/whistle_service.py).

Wer nicht benannt ist, bekommt für alles unter ``/whistle/cases`` 404 – gleich ob Admin, HR,
Führungskraft, Mitarbeiter, Tablet oder Super-Admin, und auch wenn das Hinweisgebersystem aus ist.
Die Benennung selbst (``/whistle/officers``) ist Sache der Admins und wird auditiert.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_admin_principal
from app.db import get_db
from app.models import WhistleCase
from app.schemas.whistle import (
    WhistleCaseDetail,
    WhistleCaseSummary,
    WhistleCaseUpdate,
    WhistleOfficeMessageCreate,
    WhistleOfficerCreate,
    WhistleOfficersResponse,
    WhistleStatusResponse,
)
from app.services import whistle_service as service

router = APIRouter(prefix="/whistle", tags=["whistle"])

_MAX_ID = 2_147_483_647
# Für jeden Parameter ein eigenes Path(): ein gemeinsames Objekt übernimmt FastAPI mit dem Namen des
# ersten Parameters – /cases/{case_id}/attachments/{attachment_id} läse dann zweimal case_id.


async def get_whistle_officer(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> Actor:
    if actor.account is None or actor.tenant_id is None:
        raise service.not_found()
    if not await service.is_enabled(db, actor.tenant_id) or not await service.is_officer(db, actor.tenant_id, actor.account.id):
        raise service.not_found()
    return actor


async def _case(case_id: int = Path(ge=1, le=_MAX_ID), actor: Actor = Depends(get_whistle_officer), db: AsyncSession = Depends(get_db)) -> WhistleCase:
    return await service.get_case(db, actor.tenant_id, case_id)


@router.get("/status", response_model=WhistleStatusResponse)
async def whistle_status(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> WhistleStatusResponse:
    """Für Menü und „Mein Bereich“ – verrät nichts über Meldungen."""
    if actor.account is None or actor.tenant_id is None:
        return WhistleStatusResponse(enabled=False, officer=False)
    enabled = await service.is_enabled(db, actor.tenant_id)
    officer = enabled and await service.is_officer(db, actor.tenant_id, actor.account.id)
    return WhistleStatusResponse(enabled=enabled, officer=officer)


@router.get("/cases", response_model=list[WhistleCaseSummary])
async def list_cases(actor: Actor = Depends(get_whistle_officer), db: AsyncSession = Depends(get_db)) -> list[WhistleCaseSummary]:
    return await service.list_cases(db, actor.tenant_id)


@router.get("/cases/{case_id}", response_model=WhistleCaseDetail)
async def get_case(
    case: WhistleCase = Depends(_case), actor: Actor = Depends(get_whistle_officer), db: AsyncSession = Depends(get_db)
) -> WhistleCaseDetail:
    return await service.open_case(db, case, actor.account.id)


@router.post("/cases/{case_id}/messages", response_model=WhistleCaseDetail, status_code=201)
async def add_message(
    payload: WhistleOfficeMessageCreate,
    case: WhistleCase = Depends(_case),
    actor: Actor = Depends(get_whistle_officer),
    db: AsyncSession = Depends(get_db),
) -> WhistleCaseDetail:
    return await service.add_office_message(db, case, actor.account.id, payload)


@router.patch("/cases/{case_id}", response_model=WhistleCaseDetail)
async def update_case(
    payload: WhistleCaseUpdate,
    case: WhistleCase = Depends(_case),
    actor: Actor = Depends(get_whistle_officer),
    db: AsyncSession = Depends(get_db),
) -> WhistleCaseDetail:
    return await service.update_case(db, case, actor.account.id, payload)


@router.get("/cases/{case_id}/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: int = Path(ge=1, le=_MAX_ID),
    case: WhistleCase = Depends(_case),
    actor: Actor = Depends(get_whistle_officer),
    db: AsyncSession = Depends(get_db),
) -> Response:
    filename, content_type, data = await service.read_attachment(db, case, attachment_id, actor.account.id)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(
    case: WhistleCase = Depends(_case), actor: Actor = Depends(get_whistle_officer), db: AsyncSession = Depends(get_db)
) -> Response:
    await service.delete_case(db, case, actor.account.id)
    return Response(status_code=204)


# --- Beauftragte benennen (Admin) ------------------------------------------------------------


@router.get("/officers", response_model=WhistleOfficersResponse)
async def list_officers(
    actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> WhistleOfficersResponse:
    officers, candidates = await service.list_officers(db, actor.tenant_id)
    return WhistleOfficersResponse(officers=officers, candidates=candidates)


@router.post("/officers", response_model=WhistleOfficersResponse, status_code=201)
async def appoint_officer(
    payload: WhistleOfficerCreate,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> WhistleOfficersResponse:
    await service.appoint_officer(db, actor.tenant_id, payload.account_id, actor.account_id)
    officers, candidates = await service.list_officers(db, actor.tenant_id)
    return WhistleOfficersResponse(officers=officers, candidates=candidates)


@router.delete("/officers/{account_id}", response_model=WhistleOfficersResponse)
async def dismiss_officer(
    account_id: int = Path(ge=1, le=_MAX_ID),
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> WhistleOfficersResponse:
    await service.dismiss_officer(db, actor.tenant_id, account_id, actor.account_id)
    officers, candidates = await service.list_officers(db, actor.tenant_id)
    return WhistleOfficersResponse(officers=officers, candidates=candidates)
