"""Hinweisgebersystem – Seite der meldenden Person, ohne Anmeldung (app/services/whistle_service.py).

Die Pfade liegen bewusst unter ``/public/``: Aufrufe dort stehen nicht im Zugriffsprotokoll
(main.SkipPublicAccessLog). Die Firma ergibt sich aus der Subdomain (anders als bei den Website-Pfaden
in api/public.py stehen diese hier nicht in middleware/tenant._NO_TENANT_PATHS).

- Kein Endpoint wertet einen Anmelde-Header aus: Auch wer angemeldet ist, meldet ohne Bezug zum Konto.
- Die IP-Adresse dient nur der flüchtigen Begrenzung im Speicher und wird nirgends gespeichert.
- Vorgangsnummer und Zugangscode stehen immer im Rumpf der Anfrage, nie in der Adresse.
- Hinweisgebersystem aus (oder keine Firma, z. B. Super-Admin-Adresse): alles 404.
"""
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public import _client_ip
from app.db import get_db
from app.models import Tenant
from app.schemas.whistle import (
    WhistleAccess,
    WhistleInfoResponse,
    WhistlePublicCase,
    WhistleReportCreate,
    WhistleReportCreated,
    WhistleReporterMessageCreate,
)
from app.services import whistle_service as service


def _no_store(response: Response) -> None:
    """Antworten mit Meldungsinhalten gehören in keinen Zwischenspeicher."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/public/whistle", tags=["whistle_public"], dependencies=[Depends(_no_store)])


async def _tenant(request: Request, db: AsyncSession = Depends(get_db)) -> Tenant:
    tenant = getattr(request.state, "tenant", None)
    if tenant is None or not await service.is_enabled(db, tenant.id):
        raise service.not_found()
    return tenant


@router.get("/info", response_model=WhistleInfoResponse)
async def whistle_info(tenant: Tenant = Depends(_tenant), db: AsyncSession = Depends(get_db)) -> WhistleInfoResponse:
    return WhistleInfoResponse(
        company_name=tenant.name,
        accepting_reports=await service.accepting_reports(db, tenant.id),
        max_attachment_bytes=service.MAX_ATTACHMENT_BYTES,
        max_attachments=service.MAX_ATTACHMENTS_PER_CASE,
    )


@router.post("/reports", response_model=WhistleReportCreated, status_code=201)
async def create_report(
    payload: WhistleReportCreate,
    request: Request,
    tenant: Tenant = Depends(_tenant),
    db: AsyncSession = Depends(get_db),
) -> WhistleReportCreated:
    if not await service.accepting_reports(db, tenant.id):
        raise service.not_found()
    ip = _client_ip(request)
    service.check_report_limits(tenant.id, ip)
    service.count_report(tenant.id, ip)
    case, code = await service.create_report(db, tenant.id, payload)
    return WhistleReportCreated(case_number=case.case_number, access_code=service.format_access_code(code))


@router.post("/status", response_model=WhistlePublicCase)
async def report_status(
    payload: WhistleAccess,
    request: Request,
    tenant: Tenant = Depends(_tenant),
    db: AsyncSession = Depends(get_db),
) -> WhistlePublicCase:
    case = await service.verify_access(db, tenant.id, _client_ip(request), payload.case_number, payload.access_code)
    return await service.public_view(db, case)


@router.post("/messages", response_model=WhistlePublicCase, status_code=201)
async def reporter_message(
    payload: WhistleReporterMessageCreate,
    request: Request,
    tenant: Tenant = Depends(_tenant),
    db: AsyncSession = Depends(get_db),
) -> WhistlePublicCase:
    case = await service.verify_access(db, tenant.id, _client_ip(request), payload.case_number, payload.access_code)
    await service.add_reporter_message(db, case, payload.body)
    return await service.public_view(db, case)


@router.post("/attachments", response_model=WhistlePublicCase, status_code=201)
async def reporter_attachment(
    request: Request,
    case_number: str = Form(min_length=1, max_length=20),
    access_code: str = Form(min_length=1, max_length=60),
    file: UploadFile = File(...),
    tenant: Tenant = Depends(_tenant),
    db: AsyncSession = Depends(get_db),
) -> WhistlePublicCase:
    try:
        access = WhistleAccess(case_number=case_number, access_code=access_code)
    except ValidationError:  # pragma: no cover - die Formularfelder sind oben schon begrenzt
        raise service.invalid_access() from None
    case = await service.verify_access(db, tenant.id, _client_ip(request), access.case_number, access.access_code)
    data = await file.read(service.MAX_ATTACHMENT_BYTES + 1)
    await service.add_attachment(db, case, file.filename, data)
    return await service.public_view(db, case)
