"""Eigene Berichte (Berichts-Builder): Positivliste, Vorschau, CSV, gespeicherte Berichte.

Nur mit eingeschaltetem Schalter „Eigene Berichte“ (AppSettings.custom_reports_enabled), sonst 403.
Zugriff: alle Verwaltungskonten; Führungskräfte sehen in jedem Bericht nur ihren Bereich. Geteilte
Berichte darf jedes Verwaltungskonto der Firma lesen und ausführen, ändern und löschen nur Besitzer
und Admin. Ausführen und Export werden ohne Inhalte protokolliert. Rechte je Spalte und Ablauf:
app/services/report_builder_service.py.
"""
from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, SavedReport
from app.schemas.report_builder import (
    CatalogResponse,
    ReportDefinition,
    ReportPeriod,
    ReportPreviewRequest,
    ReportResult,
    SavedReportRequest,
    SavedReportResponse,
)
from app.services import report_builder_service as builder
from app.services.audit_service import log_action

router = APIRouter(prefix="/report-builder", tags=["report-builder"])

ENTITY = "saved_report"


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, entity_id: int, detail: str) -> None:
    log_action(db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=action, entity_type=ENTITY, entity_id=entity_id, detail=detail)


def _definition(report: SavedReport) -> ReportDefinition:
    try:
        return ReportDefinition.model_validate_json(report.definition)
    except ValidationError as exc:
        raise AppError(409, "REPORT_DEFINITION_OUTDATED", "Die Definition dieses Berichts ist nicht mehr gültig – bitte neu anlegen.") from exc


def _can_edit(actor: Actor, report: SavedReport) -> bool:
    return report.owner_account_id == actor.account_id or actor.is_admin_level


def _visible(actor: Actor):
    """Eigene, geteilte und (für Admins) verwaiste Berichte, deren Besitzer-Konto gelöscht wurde."""
    conditions = [SavedReport.owner_account_id == actor.account_id, SavedReport.shared.is_(True)]
    if actor.is_admin_level:
        conditions.append(SavedReport.owner_account_id.is_(None))
    return or_(*conditions)


async def _owner_names(db: AsyncSession, reports: list[SavedReport]) -> dict[int, str]:
    ids = {r.owner_account_id for r in reports if r.owner_account_id is not None}
    if not ids:
        return {}
    accounts = (await db.execute(select(Account).where(Account.id.in_(ids)))).scalars().all()
    return {
        a.id: f"{a.employee.first_name} {a.employee.last_name}" if a.employee is not None else (a.email or "Konto")
        for a in accounts
    }


def _response(actor: Actor, report: SavedReport, definition: ReportDefinition, names: dict[int, str]) -> SavedReportResponse:
    return SavedReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        definition=definition,
        shared=report.shared,
        owner_account_id=report.owner_account_id,
        owner_name=names.get(report.owner_account_id) if report.owner_account_id is not None else None,
        mine=report.owner_account_id == actor.account_id,
        can_edit=_can_edit(actor, report),
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


async def _get_report(db: AsyncSession, actor: Actor, report_id: int) -> SavedReport:
    report = (
        await db.execute(select(SavedReport).where(SavedReport.id == report_id, SavedReport.tenant_id == actor.tenant_id, _visible(actor)))
    ).scalar_one_or_none()
    if report is None:
        raise AppError(404, "REPORT_NOT_FOUND", "Bericht nicht gefunden.")
    return report


def _csv_response(content: str, name: str) -> Response:
    safe = "".join(ch if (ch.isascii() and ch.isalnum()) or ch in "-_" else "_" for ch in name)[:60] or "bericht"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'},
    )


async def _run(
    db: AsyncSession, actor: Actor, definition: ReportDefinition, period: ReportPeriod, *, lenient: bool
) -> builder.Outcome:
    settings_row = await builder.ensure_enabled(db, actor.tenant_id)
    plan = await builder.resolve(db, actor, definition, lenient=lenient)
    return await builder.execute(db, actor, settings_row, plan, period)


async def _log_run(db: AsyncSession, actor: Actor, action: AuditAction, outcome: builder.Outcome, report: SavedReport | None) -> None:
    entity_id = report.id if report is not None else 0
    _audit(db, actor, action, entity_id, builder.audit_detail(outcome, report.name if report is not None else None))
    if outcome.plan.shows_compensation:
        _audit(db, actor, AuditAction.COMPENSATION_VIEWED, entity_id, f"Vergütung in eigenem Bericht ausgegeben ({len(outcome.rows)} Zeilen)")
    await db.commit()


# --- Positivliste und Ad-hoc-Läufe ----------------------------------------------------------------


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> CatalogResponse:
    await builder.ensure_enabled(db, actor.tenant_id)
    return await builder.build_catalog(db, actor)


@router.post("/preview", response_model=ReportResult)
async def preview(payload: ReportPreviewRequest, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> ReportResult:
    outcome = await _run(db, actor, payload.definition, payload, lenient=False)
    await _log_run(db, actor, AuditAction.REPORT_RUN, outcome, None)
    return builder.to_result(outcome, payload)


@router.post("/export")
async def export(payload: ReportPreviewRequest, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> Response:
    outcome = await _run(db, actor, payload.definition, payload, lenient=False)
    await _log_run(db, actor, AuditAction.REPORT_EXPORTED, outcome, None)
    return _csv_response(builder.to_csv(outcome), "bericht")


# --- Gespeicherte Berichte ------------------------------------------------------------------------


@router.get("/reports", response_model=list[SavedReportResponse])
async def list_reports(actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> list[SavedReportResponse]:
    await builder.ensure_enabled(db, actor.tenant_id)
    reports = (
        await db.execute(
            select(SavedReport).where(SavedReport.tenant_id == actor.tenant_id, _visible(actor)).order_by(SavedReport.name, SavedReport.id)
        )
    ).scalars().all()
    names = await _owner_names(db, list(reports))
    result = []
    for report in reports:
        try:
            definition = _definition(report)
        except AppError:
            continue  # nicht mehr lesbare Definition: in der Liste nicht anbieten
        result.append(_response(actor, report, definition, names))
    return result


@router.post("/reports", response_model=SavedReportResponse, status_code=201)
async def create_report(payload: SavedReportRequest, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> SavedReportResponse:
    await builder.ensure_enabled(db, actor.tenant_id)
    await builder.resolve(db, actor, payload.definition)
    report = SavedReport(
        tenant_id=actor.tenant_id,
        owner_account_id=actor.account_id,
        name=payload.name,
        description=payload.description,
        definition=payload.definition.model_dump_json(),
        shared=payload.shared,
    )
    db.add(report)
    await db.flush()
    _audit(db, actor, AuditAction.REPORT_CHANGED, report.id, f"Bericht „{report.name}“ angelegt{' (geteilt)' if report.shared else ''}")
    await db.commit()
    await db.refresh(report)
    return _response(actor, report, payload.definition, await _owner_names(db, [report]))


@router.get("/reports/{report_id}", response_model=SavedReportResponse)
async def get_report(report_id: int, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> SavedReportResponse:
    await builder.ensure_enabled(db, actor.tenant_id)
    report = await _get_report(db, actor, report_id)
    return _response(actor, report, _definition(report), await _owner_names(db, [report]))


@router.put("/reports/{report_id}", response_model=SavedReportResponse)
async def update_report(
    report_id: int, payload: SavedReportRequest, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)
) -> SavedReportResponse:
    await builder.ensure_enabled(db, actor.tenant_id)
    report = await _get_report(db, actor, report_id)
    if not _can_edit(actor, report):
        raise AppError(403, "REPORT_NOT_EDITABLE", "Nur Besitzer und Admins dürfen diesen Bericht ändern.")
    await builder.resolve(db, actor, payload.definition)
    report.name = payload.name
    report.description = payload.description
    report.definition = payload.definition.model_dump_json()
    report.shared = payload.shared
    _audit(db, actor, AuditAction.REPORT_CHANGED, report.id, f"Bericht „{report.name}“ geändert{' (geteilt)' if report.shared else ''}")
    await db.commit()
    await db.refresh(report)
    return _response(actor, report, payload.definition, await _owner_names(db, [report]))


@router.delete("/reports/{report_id}", status_code=204)
async def delete_report(report_id: int, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)) -> Response:
    await builder.ensure_enabled(db, actor.tenant_id)
    report = await _get_report(db, actor, report_id)
    if not _can_edit(actor, report):
        raise AppError(403, "REPORT_NOT_EDITABLE", "Nur Besitzer und Admins dürfen diesen Bericht löschen.")
    _audit(db, actor, AuditAction.REPORT_CHANGED, report.id, f"Bericht „{report.name}“ gelöscht")
    await db.delete(report)
    await db.commit()
    return Response(status_code=204)


@router.post("/reports/{report_id}/run", response_model=ReportResult)
async def run_report(
    report_id: int, payload: ReportPeriod, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)
) -> ReportResult:
    await builder.ensure_enabled(db, actor.tenant_id)
    report = await _get_report(db, actor, report_id)
    outcome = await _run(db, actor, _definition(report), payload, lenient=True)
    await _log_run(db, actor, AuditAction.REPORT_RUN, outcome, report)
    return builder.to_result(outcome, payload)


@router.post("/reports/{report_id}/export")
async def export_report(
    report_id: int, payload: ReportPeriod, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)
) -> Response:
    await builder.ensure_enabled(db, actor.tenant_id)
    report = await _get_report(db, actor, report_id)
    outcome = await _run(db, actor, _definition(report), payload, lenient=True)
    await _log_run(db, actor, AuditAction.REPORT_EXPORTED, outcome, report)
    return _csv_response(builder.to_csv(outcome), report.name)
