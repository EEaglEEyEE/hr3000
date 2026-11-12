"""Vorbereitende Lohnbuchhaltung (Seite „Lohnbuchhaltung“, Schalter AppSettings.payroll_accounting_enabled).

- Ansehen: Berechtigung „Vergütung & Lohn“ (get_current_payroll_principal). Wer nur ansehen darf
  (eigene Rolle mit „Vergütung & Lohn: Ansehen“, z. B. das Lohnbüro), sieht ausschließlich freigegebene
  Monate samt Dateien; den aktuellen Stand und das Freigeben gibt es nur mit Actor.can_edit_payroll.
- Freigeben friert den Monat ein: Schnappschuss (JSON) und die Exportdateien (generisches CSV wie im
  Lohn-Export, DATEV LODAS wenn eingerichtet) verschlüsselt (secret_box), protokolliert in
  PayrollExportLog wie ein Export.
- „Freigabe zurücknehmen“ nur Admin. Jeder Abruf und Download steht im Audit-Protokoll.
"""
import json
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import load_only
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal, get_current_payroll_principal
from app.api.payroll_export import _log_export, render_payroll_csv
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, PayrollRelease
from app.schemas.payroll_accounting import AccountingMonth, ReleaseInfo, ReleaseRequest
from app.services.audit_service import log_action
from app.services.datev_export_service import build_datev_export
from app.services.payroll_accounting_service import (
    build_month,
    changed_employees,
    employees_of_month,
    month_bounds,
    parse_month,
)
from app.services.secret_box import decrypt_secret, encrypt_secret
from app.services.settings_service import get_or_create_settings

router = APIRouter(tags=["payroll_accounting"])

_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
MonthPath = Annotated[str, Path(pattern=_MONTH, description="Monat als JJJJ-MM")]


async def _ensure_enabled(db: AsyncSession, tenant_id: int):
    settings_row = await get_or_create_settings(db, tenant_id)
    if not settings_row.payroll_accounting_enabled:
        raise AppError(404, "PAYROLL_ACCOUNTING_DISABLED", "Die Lohnbuchhaltung ist nicht eingeschaltet.")
    return settings_row


def _require_edit(actor: Actor) -> None:
    if not actor.can_edit_payroll:
        raise AppError(403, "PAYROLL_PERMISSION_REQUIRED", "Nur mit Berechtigung „Vergütung & Lohn: Bearbeiten“.")


async def _release(db: AsyncSession, tenant_id: int, year: int, month: int) -> PayrollRelease | None:
    return await db.scalar(
        select(PayrollRelease).where(
            PayrollRelease.tenant_id == tenant_id, PayrollRelease.year == year, PayrollRelease.month == month
        )
    )


async def _info(db: AsyncSession, release: PayrollRelease, has_datev: bool | None = None) -> ReleaseInfo:
    account = await db.get(Account, release.released_by_account_id) if release.released_by_account_id else None
    return ReleaseInfo(
        month=f"{release.year:04d}-{release.month:02d}",
        released_at=release.released_at,
        released_by=account.display_name if account else None,
        employee_count=release.employee_count,
        open_closures=release.open_closures,
        has_datev=release.datev_file is not None if has_datev is None else has_datev,
    )


def _decrypt(token: str | None) -> str:
    plain = decrypt_secret(token) if token else None
    if plain is None:
        raise AppError(500, "RELEASE_UNREADABLE", "Die freigegebenen Daten lassen sich nicht entschlüsseln.")
    return plain


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, year: int, month: int, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=action,
        entity_type="payroll_month",
        entity_id=year * 100 + month,
        detail=detail,
    )


@router.get("/payroll-accounting/releases", response_model=list[ReleaseInfo])
async def list_releases(
    limit: int = Query(default=36, ge=1, le=120),
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ReleaseInfo]:
    """Freigegebene Monate, neueste zuerst."""
    await _ensure_enabled(db, actor.tenant_id)
    # Ohne die (großen, verschlüsselten) Inhalte laden
    rows = (
        await db.execute(
            select(PayrollRelease, PayrollRelease.datev_file.is_not(None))
            .options(
                load_only(
                    PayrollRelease.id, PayrollRelease.tenant_id, PayrollRelease.year, PayrollRelease.month,
                    PayrollRelease.released_at, PayrollRelease.released_by_account_id,
                    PayrollRelease.employee_count, PayrollRelease.open_closures,
                )
            )
            .where(PayrollRelease.tenant_id == actor.tenant_id)
            .order_by(PayrollRelease.year.desc(), PayrollRelease.month.desc())
            .limit(limit)
        )
    ).all()
    return [await _info(db, release, bool(has_datev)) for release, has_datev in rows]


@router.get("/payroll-accounting/{month}", response_model=AccountingMonth)
async def get_month(
    month: MonthPath,
    compare: bool = Query(default=False, description="Freigegebenen Monat mit dem aktuellen Stand vergleichen"),
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> AccountingMonth:
    """Freigegebener Monat (Schnappschuss) bzw. – nur mit Bearbeiten – der aktuelle Stand."""
    await _ensure_enabled(db, actor.tenant_id)
    year, number = parse_month(month)
    release = await _release(db, actor.tenant_id, year, number)
    changed: list[int] | None = None
    if release is not None:
        data = json.loads(_decrypt(release.snapshot))
        if compare:
            _require_edit(actor)
            changed = changed_employees(data, await build_month(db, actor.tenant_id, year, number, data["includes_pay"]))
        info = await _info(db, release)
        _audit(db, actor, AuditAction.PAYROLL_ACCOUNTING_ACCESSED, year, number, f"Lohnbuchhaltung {month} (freigegeben) angesehen")
    else:
        if not actor.can_edit_payroll:
            raise AppError(404, "MONTH_NOT_RELEASED", "Dieser Monat ist noch nicht freigegeben.")
        data = await build_month(db, actor.tenant_id, year, number, include_pay=True)
        info = None
        _audit(db, actor, AuditAction.PAYROLL_ACCOUNTING_ACCESSED, year, number, f"Lohnbuchhaltung {month} (aktueller Stand) angesehen")
    await db.commit()
    return AccountingMonth(
        month=month,
        release=info,
        includes_pay=data["includes_pay"],
        employees=data["employees"],
        summary=data["summary"],
        changed_since_release=changed,
    )


@router.post("/payroll-accounting/{month}/release", response_model=AccountingMonth, status_code=201)
async def release_month(
    month: MonthPath,
    payload: ReleaseRequest,
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> AccountingMonth:
    """Monat freigeben: Schnappschuss und Exportdateien einfrieren. Offene Monatsabschlüsse sind kein
    Verbot – ohne confirm_open_closures kommt 409 OPEN_CLOSURES als Warnung."""
    settings_row = await _ensure_enabled(db, actor.tenant_id)
    _require_edit(actor)
    year, number = parse_month(month)
    first, last = month_bounds(year, number)
    if first > date.today():
        raise AppError(400, "MONTH_IN_FUTURE", "Künftige Monate lassen sich nicht freigeben.")
    if await _release(db, actor.tenant_id, year, number) is not None:
        raise AppError(409, "ALREADY_RELEASED", "Dieser Monat ist bereits freigegeben.")

    data = await build_month(db, actor.tenant_id, year, number, include_pay=True)
    open_closures = data["summary"]["open_closures"]
    if open_closures and not payload.confirm_open_closures:
        raise AppError(
            409, "OPEN_CLOSURES",
            f"Bei {open_closures} Mitarbeiter(n) ist der Monatsabschluss noch nicht abgeschlossen. Trotzdem freigeben?",
        )

    employees = await employees_of_month(db, actor.tenant_id, year, number)
    csv_content = await render_payroll_csv(db, actor.tenant_id, employees, first, last, include_pay=True)
    datev_content: str | None = None
    if settings_row.datev_consultant_number and settings_row.datev_client_number and employees:
        export = await build_datev_export(db, actor.tenant_id, employees, year, number)
        datev_content = export.render(settings_row.datev_consultant_number, settings_row.datev_client_number)

    release = PayrollRelease(
        tenant_id=actor.tenant_id,
        year=year,
        month=number,
        released_by_account_id=actor.account_id,
        employee_count=len(employees),
        open_closures=open_closures,
        snapshot=encrypt_secret(json.dumps(data, ensure_ascii=False)),
        csv_file=encrypt_secret(csv_content),
        datev_file=encrypt_secret(datev_content) if datev_content is not None else None,
    )
    db.add(release)
    _log_export(db, actor, "CSV", first, last, len(employees))
    if datev_content is not None:
        _log_export(db, actor, "DATEV", first, last, len(employees))
    _audit(
        db, actor, AuditAction.PAYROLL_RELEASED, year, number,
        f"Lohnbuchhaltung {month} freigegeben ({len(employees)} Mitarbeiter"
        + (f", {open_closures} ohne abgeschlossenen Monat" if open_closures else "")
        + (", mit DATEV-Datei" if datev_content is not None else "")
        + ")",
    )
    await db.commit()
    await db.refresh(release)
    return AccountingMonth(
        month=month,
        release=await _info(db, release),
        includes_pay=True,
        employees=data["employees"],
        summary=data["summary"],
        changed_since_release=[],
    )


@router.delete("/payroll-accounting/{month}/release", status_code=204)
async def revoke_release(
    month: MonthPath,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Freigabe zurücknehmen (nur Admin): Schnappschuss und Dateien werden gelöscht, der Monat zeigt
    wieder den aktuellen Stand. Das Audit-Protokoll behält, wer wann freigegeben und zurückgenommen hat."""
    await _ensure_enabled(db, actor.tenant_id)
    year, number = parse_month(month)
    release = await _release(db, actor.tenant_id, year, number)
    if release is None:
        raise AppError(404, "MONTH_NOT_RELEASED", "Dieser Monat ist nicht freigegeben.")
    _audit(db, actor, AuditAction.PAYROLL_RELEASE_REVOKED, year, number, f"Freigabe der Lohnbuchhaltung {month} zurückgenommen")
    await db.delete(release)
    await db.commit()


@router.get("/payroll-accounting/{month}/files/{kind}")
async def download_file(
    month: MonthPath,
    kind: Literal["csv", "datev"],
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exportdatei des freigegebenen Monats – unverändert so, wie sie bei der Freigabe entstand."""
    await _ensure_enabled(db, actor.tenant_id)
    year, number = parse_month(month)
    release = await _release(db, actor.tenant_id, year, number)
    if release is None:
        raise AppError(404, "MONTH_NOT_RELEASED", "Dieser Monat ist nicht freigegeben.")
    if kind == "datev" and release.datev_file is None:
        raise AppError(404, "FILE_NOT_AVAILABLE", "Bei der Freigabe war DATEV nicht eingerichtet.")
    content = _decrypt(release.csv_file if kind == "csv" else release.datev_file)
    _audit(
        db, actor, AuditAction.PAYROLL_ACCOUNTING_ACCESSED, year, number,
        f"Lohnbuchhaltung {month}: {'CSV' if kind == 'csv' else 'DATEV-Datei'} heruntergeladen",
    )
    await db.commit()
    if kind == "csv":
        return Response(
            content=content.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="lohnbuchhaltung_{month}.csv"'},
        )
    return Response(
        content=content.encode("cp1252", errors="replace"),
        media_type="text/plain; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="datev-lodas_{month}.txt"'},
    )
