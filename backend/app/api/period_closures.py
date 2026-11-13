from datetime import UTC, date, datetime, timedelta

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AuditAction,
    CorrectionRequestStatus,
    DailySummary,
    DocumentCategory,
    Employee,
    EmployeeDocument,
    PeriodClosure,
    PeriodStatus,
    PunchCorrectionRequest,
    SummaryStatus,
)
from app.schemas.period import (
    PeriodBulkResultRow,
    PeriodBulkSubmitRequest,
    PeriodCloseRequest,
    PeriodClosureResponse,
    PeriodDisputeRequest,
    PeriodOverviewRow,
    PeriodSubmitRequest,
)
from app.services.audit_service import log_action
from app.services.scope_service import ensure_employee_visible
from app.services.document_service import store_document
from app.services.notification_service import notify_period_disputed, notify_period_submitted
from app.services.timesheet_service import (
    day_fingerprint,
    day_reviews,
    needs_review,
    refresh_stale_day_cache,
    review_valid,
    utc_today,
)
from app.services.period_service import (
    build_month_report,
    month_bounds,
    month_label,
    render_time_report_pdf,
    render_time_reports_pdf,
    validate_month,
)

router = APIRouter(tags=["period-closures"])


async def _employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


async def _get_closure(db: AsyncSession, employee_id: int, year: int, month: int) -> PeriodClosure | None:
    return (
        await db.execute(
            select(PeriodClosure).where(
                PeriodClosure.employee_id == employee_id,
                PeriodClosure.year == year,
                PeriodClosure.month == month,
            )
        )
    ).scalar_one_or_none()


def _require_self(actor: Actor, employee_id: int) -> Employee:
    if actor.employee is None or actor.employee.id != employee_id:
        raise AppError(403, "FORBIDDEN", "Nur der Mitarbeiter selbst kann den Monatsnachweis bestätigen oder beanstanden.")
    return actor.employee


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, employee: Employee, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=action,
        entity_type="employee",
        entity_id=employee.id,
        detail=detail,
    )


@router.get("/employees/{employee_id}/period-closures", response_model=list[PeriodClosureResponse])
async def list_period_closures(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[PeriodClosureResponse]:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    is_self = actor.employee is not None and actor.employee.id == employee_id
    if not is_self:
        if not actor.is_full_hr_level:
            raise AppError(403, "HR_PERMISSION_REQUIRED", "Keine Berechtigung für den Monatsabschluss.")
    result = await db.execute(
        select(PeriodClosure)
        .where(PeriodClosure.employee_id == employee.id)
        .order_by(PeriodClosure.year.desc(), PeriodClosure.month.desc())
    )
    return [PeriodClosureResponse.model_validate(c) for c in result.scalars().all()]


async def _open_requests(db: AsyncSession, employee: Employee, first: date, last: date) -> list[str]:
    """Noch nicht entschiedene Anträge, die den Monat betreffen – nach dem Vorlegen sind sie wegen der
    Sperre nicht mehr entscheidbar."""
    absences = (
        await db.execute(
            select(func.count()).select_from(Absence).where(
                Absence.employee_id == employee.id,
                Absence.approval_status == AbsenceApprovalStatus.PENDING,
                Absence.date_from <= last,
                Absence.date_to >= first,
            )
        )
    ).scalar_one()
    corrections = (
        await db.execute(
            select(func.count()).select_from(PunchCorrectionRequest).where(
                PunchCorrectionRequest.employee_id == employee.id,
                PunchCorrectionRequest.status == CorrectionRequestStatus.PENDING,
                PunchCorrectionRequest.work_date >= first,
                PunchCorrectionRequest.work_date <= last,
            )
        )
    ).scalar_one()
    found = []
    if absences:
        found.append(f"{absences} Abwesenheitsantrag" + ("" if absences == 1 else "/-anträge"))
    if corrections:
        found.append(f"{corrections} Korrekturantrag" + ("" if corrections == 1 else "/-anträge"))
    return found


async def _submit(
    db: AsyncSession,
    actor: Actor,
    employee: Employee,
    year: int,
    month: int,
    ignore_open_days: bool,
    ignore_open_requests: bool = False,
) -> PeriodClosure:
    validate_month(year, month)
    first, last = month_bounds(year, month)
    if last >= date.today():
        raise AppError(409, "PERIOD_NOT_ENDED", "Der Monat ist noch nicht beendet.")
    if employee.anonymized_at is not None:
        raise AppError(409, "EMPLOYEE_ANONYMIZED", "Der Mitarbeiter wurde anonymisiert.")

    existing = await _get_closure(db, employee.id, year, month)
    if existing is not None and existing.status != PeriodStatus.DISPUTED:
        raise AppError(409, "PERIOD_ALREADY_SUBMITTED", "Der Monat wurde bereits vorgelegt oder abgeschlossen.")

    if not ignore_open_requests:
        requests = await _open_requests(db, employee, first, last)
        if requests:
            raise AppError(
                409,
                "OPEN_REQUESTS_PRESENT",
                f"Für den Monat ist noch offen: {', '.join(requests)} – nach dem Vorlegen erst nach Wieder öffnen entscheidbar.",
            )
    report = await build_month_report(db, employee, year, month)
    if report.open_days and not ignore_open_days:
        shown = ", ".join(d.strftime("%d.%m.") for d in report.open_days[:8])
        more = f" (+{len(report.open_days) - 8} weitere)" if len(report.open_days) > 8 else ""
        raise AppError(409, "OPEN_DAYS_PRESENT", f"Es gibt noch offene oder fehlerhafte Tage: {shown}{more}.")

    pdf = render_time_report_pdf(report)
    title = f"Monatsnachweis {month_label(year, month)}"
    if existing is not None:
        title += f" (neu vorgelegt {date.today().strftime('%d.%m.%Y')})"
    document = await store_document(
        db,
        tenant_id=employee.tenant_id,
        employee_id=employee.id,
        data=pdf,
        filename=f"Monatsnachweis_{year}-{month:02d}_{employee.employee_number}.pdf",
        category=DocumentCategory.TIME_REPORT,
        title=title,
        employee_visible=True,
        confidential=False,
        # ArbZG §16 Abs. 2: Nachweise über Mehrarbeit sind mindestens zwei Jahre aufzubewahren.
        retention_until=last + timedelta(days=731),
        uploaded_by_account_id=actor.account_id,
    )
    await db.flush()

    now = datetime.now(UTC).replace(tzinfo=None)
    closure = existing or PeriodClosure(tenant_id=employee.tenant_id, employee_id=employee.id, year=year, month=month)
    closure.status = PeriodStatus.SUBMITTED
    closure.target_minutes = report.target_minutes
    closure.actual_minutes = report.actual_minutes
    closure.delta_minutes = report.delta_minutes
    closure.balance_end_minutes = report.balance_end_minutes
    closure.settled_minutes = report.settled_minutes
    closure.document_id = document.id
    closure.report_sha256 = document.sha256
    closure.submitted_at = now
    closure.submitted_by_account_id = actor.account_id
    closure.confirmed_at = None
    closure.disputed_at = None
    closure.dispute_reason = None
    closure.closed_at = None
    closure.closed_without_confirmation = False
    db.add(closure)
    await db.flush()

    _audit(db, actor, AuditAction.PERIOD_SUBMITTED, employee, f"Monatsnachweis {month_label(year, month)} vorgelegt")
    if not employee.login_email:
        # Ohne Login kann niemand bestätigen: direkt abschließen (statt eines zweiten Klicks).
        closure.status = PeriodStatus.CLOSED
        closure.closed_at = now
        closure.closed_without_confirmation = True
        _audit(db, actor, AuditAction.PERIOD_CLOSED, employee, f"Monat {month_label(year, month)} abgeschlossen (Mitarbeiter ohne Login)")
    else:
        await notify_period_submitted(db, employee.tenant_id, employee, month_label(year, month))
    await db.commit()
    await db.refresh(closure)
    return closure


@router.post("/employees/{employee_id}/period-closures/{year}/{month}/submit", response_model=PeriodClosureResponse)
async def submit_period(
    employee_id: int,
    year: int,
    month: int,
    payload: PeriodSubmitRequest | None = None,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PeriodClosureResponse:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    closure = await _submit(
        db, actor, employee, year, month, bool(payload and payload.ignore_open_days), bool(payload and payload.ignore_open_requests)
    )
    return PeriodClosureResponse.model_validate(closure)


@router.post("/employees/{employee_id}/period-closures/{year}/{month}/confirm", response_model=PeriodClosureResponse)
async def confirm_period(
    employee_id: int,
    year: int,
    month: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> PeriodClosureResponse:
    employee = _require_self(actor, employee_id)
    closure = await _get_closure(db, employee_id, year, month)
    if closure is None or closure.status != PeriodStatus.SUBMITTED:
        raise AppError(409, "PERIOD_NOT_SUBMITTED", "Für diesen Monat liegt kein Nachweis zur Bestätigung vor.")
    # Die Bestätigung schließt den Monat ab (gleiche Wirkung wie früher "bestätigt" + "abschließen").
    now = datetime.now(UTC).replace(tzinfo=None)
    closure.status = PeriodStatus.CLOSED
    closure.confirmed_at = now
    closure.closed_at = now
    closure.closed_without_confirmation = False
    _audit(db, actor, AuditAction.PERIOD_CONFIRMED, employee, f"Monatsnachweis {month_label(year, month)} bestätigt und abgeschlossen")
    await db.commit()
    await db.refresh(closure)
    return PeriodClosureResponse.model_validate(closure)


@router.post("/employees/{employee_id}/period-closures/{year}/{month}/dispute", response_model=PeriodClosureResponse)
async def dispute_period(
    employee_id: int,
    year: int,
    month: int,
    payload: PeriodDisputeRequest,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> PeriodClosureResponse:
    employee = _require_self(actor, employee_id)
    closure = await _get_closure(db, employee_id, year, month)
    if closure is None or closure.status != PeriodStatus.SUBMITTED:
        raise AppError(409, "PERIOD_NOT_SUBMITTED", "Für diesen Monat liegt kein Nachweis zur Bestätigung vor.")
    closure.status = PeriodStatus.DISPUTED
    closure.disputed_at = datetime.now(UTC).replace(tzinfo=None)
    closure.dispute_reason = payload.reason.strip()
    _audit(db, actor, AuditAction.PERIOD_DISPUTED, employee, f"Monatsnachweis {month_label(year, month)} beanstandet")
    await notify_period_disputed(db, employee.tenant_id, employee, month_label(year, month))
    await db.commit()
    await db.refresh(closure)
    return PeriodClosureResponse.model_validate(closure)


@router.post("/employees/{employee_id}/period-closures/{year}/{month}/close", response_model=PeriodClosureResponse)
async def close_period(
    employee_id: int,
    year: int,
    month: int,
    payload: PeriodCloseRequest | None = None,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PeriodClosureResponse:
    """Vorgelegten Monat ohne Bestätigung des Mitarbeiters abschließen (die Bestätigung schließt
    selbst ab)."""
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    closure = await _get_closure(db, employee_id, year, month)
    if closure is None or closure.status != PeriodStatus.SUBMITTED:
        raise AppError(409, "PERIOD_NOT_CLOSABLE", "Der Monat kann nur nach Vorlage abgeschlossen werden.")
    closure.closed_without_confirmation = True
    closure.status = PeriodStatus.CLOSED
    closure.closed_at = datetime.now(UTC).replace(tzinfo=None)
    suffix = " (ohne Bestätigung des Mitarbeiters)" if closure.closed_without_confirmation else ""
    _audit(db, actor, AuditAction.PERIOD_CLOSED, employee, f"Monat {month_label(year, month)} abgeschlossen{suffix}")
    await db.commit()
    await db.refresh(closure)
    return PeriodClosureResponse.model_validate(closure)


@router.post("/employees/{employee_id}/period-closures/{year}/{month}/reopen", status_code=204)
async def reopen_period(
    employee_id: int,
    year: int,
    month: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Zieht eine Vorlage zurück bzw. öffnet einen abgeschlossenen Monat wieder. Abgeschlossene
    Monate darf nur ein Administrator öffnen."""
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    closure = await _get_closure(db, employee_id, year, month)
    if closure is None:
        raise AppError(404, "PERIOD_NOT_FOUND", "Für diesen Monat gibt es keinen Abschluss.")
    if closure.status == PeriodStatus.CLOSED and not actor.is_admin_level:
        raise AppError(403, "ADMIN_PERMISSION_REQUIRED", "Abgeschlossene Monate darf nur ein Administrator wieder öffnen.")

    if closure.document_id is not None:
        document = await db.get(EmployeeDocument, closure.document_id)
        if document is not None:
            # Der überholte Nachweis bleibt in der Akte (Aufbewahrung), ist aber nicht mehr für den Mitarbeiter sichtbar.
            document.employee_visible = False
            document.title = f"{document.title} (zurückgezogen)"[:200]
    previous = closure.status.value
    await db.delete(closure)
    _audit(db, actor, AuditAction.PERIOD_REOPENED, employee, f"Monat {month_label(year, month)} wieder geöffnet (war {previous})")
    await db.commit()


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            # inline: öffnet direkt im Browser (Druckansicht), Download bleibt möglich.
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/employees/{employee_id}/month-report")
async def employee_month_report(
    employee_id: int,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Monatsbericht eines Mitarbeiters als PDF-Druckansicht (jeder Monat, auch laufend/offen)."""
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    is_self = actor.employee is not None and actor.employee.id == employee_id
    if not is_self:
        if not actor.is_hr_level:
            raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
        await ensure_employee_visible(db, actor, employee)
    report = await build_month_report(db, employee, year, month)
    pdf = render_time_report_pdf(report, for_confirmation=False)
    return _pdf_response(pdf, f"Monatsbericht_{year}-{month:02d}_{employee.employee_number}.pdf")


_MAX_BULK_REPORTS = 300


@router.get("/month-reports")
async def all_month_reports(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Monatsberichte aller im Monat beschäftigten Mitarbeiter in einem PDF (Sammeldruck)."""
    first, last = month_bounds(year, month)
    employees = (
        await db.execute(
            select(Employee)
            .where(
                Employee.tenant_id == actor.tenant_id,
                Employee.anonymized_at.is_(None),
                (Employee.hire_date.is_(None)) | (Employee.hire_date <= last),
                (Employee.termination_date.is_(None)) | (Employee.termination_date >= first),
            )
            .order_by(Employee.last_name, Employee.first_name)
        )
    ).scalars().all()
    if not employees:
        raise AppError(404, "NO_EMPLOYEES", "In diesem Monat ist niemand beschäftigt.")
    if len(employees) > _MAX_BULK_REPORTS:
        raise AppError(400, "TOO_MANY_EMPLOYEES", f"Höchstens {_MAX_BULK_REPORTS} Berichte pro Sammeldruck.")
    reports = [await build_month_report(db, e, year, month) for e in employees]
    return _pdf_response(render_time_reports_pdf(reports), f"Monatsberichte_{year}-{month:02d}.pdf")


@router.get("/period-closures", response_model=list[PeriodOverviewRow])
async def period_overview(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[PeriodOverviewRow]:
    first, last = month_bounds(year, month)
    employees = (
        await db.execute(
            select(Employee)
            .where(
                Employee.tenant_id == actor.tenant_id,
                Employee.anonymized_at.is_(None),
                (Employee.hire_date.is_(None)) | (Employee.hire_date <= last),
                (Employee.termination_date.is_(None)) | (Employee.termination_date >= first),
            )
            .order_by(Employee.last_name, Employee.first_name)
        )
    ).scalars().all()
    ids = [e.id for e in employees]
    closures = {}
    open_counts: dict[int, int] = {}
    if ids:
        for closure in (
            await db.execute(
                select(PeriodClosure).where(
                    PeriodClosure.employee_id.in_(ids), PeriodClosure.year == year, PeriodClosure.month == month
                )
            )
        ).scalars().all():
            closures[closure.employee_id] = closure
        # Dieselbe Regel "Tag offen" wie "Zu klären" (inkl. Fingerabdruck von "Erledigt") – aus dem
        # Tages-Cache, der nach Änderungen an Einstellungen, Modellen usw. erst nachgerechnet wird.
        await refresh_stale_day_cache(db, actor.tenant_id)
        today = utc_today()
        reviews = await day_reviews(db, ids, first, last)
        rows = await db.execute(
            select(DailySummary).where(
                DailySummary.employee_id.in_(ids),
                DailySummary.work_date >= first,
                DailySummary.work_date <= min(last, today),
                or_(
                    DailySummary.status.in_(
                        [SummaryStatus.OPEN_MISSING_PUNCH, SummaryStatus.ERROR, SummaryStatus.PRESENT, SummaryStatus.ON_BREAK, SummaryStatus.ON_ERRAND]
                    ),
                    DailySummary.flags.is_not(None),
                ),
            )
        )
        for summary in rows.scalars().all():
            flags = summary.flags.split(",") if summary.flags else []
            if not needs_review(summary.status, flags, summary.work_date, today, exempt=summary.review_exempt):
                continue
            fingerprint = day_fingerprint(summary.status, summary.target_minutes, summary.actual_minutes, flags)
            if not review_valid(reviews, summary.employee_id, summary.work_date, fingerprint):
                open_counts[summary.employee_id] = open_counts.get(summary.employee_id, 0) + 1

    return [
        PeriodOverviewRow(
            employee_id=e.id,
            first_name=e.first_name,
            last_name=e.last_name,
            employee_number=e.employee_number,
            status=closures[e.id].status if e.id in closures else None,
            closure_id=closures[e.id].id if e.id in closures else None,
            delta_minutes=closures[e.id].delta_minutes if e.id in closures else None,
            dispute_reason=closures[e.id].dispute_reason if e.id in closures else None,
            open_day_count=open_counts.get(e.id, 0),
        )
        for e in employees
    ]


@router.post("/period-closures/submit-all", response_model=list[PeriodBulkResultRow])
async def submit_all_periods(
    payload: PeriodBulkSubmitRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[PeriodBulkResultRow]:
    """Legt den Monat für alle (aktiven, im Monat beschäftigten) Mitarbeiter vor, soweit möglich;
    Mitarbeiter mit offenen Tagen o.Ä. werden übersprungen und mit Grund gemeldet."""
    validate_month(payload.year, payload.month)
    first, last = month_bounds(payload.year, payload.month)
    employees = (
        await db.execute(
            select(Employee)
            .where(
                Employee.tenant_id == actor.tenant_id,
                Employee.anonymized_at.is_(None),
                (Employee.hire_date.is_(None)) | (Employee.hire_date <= last),
                (Employee.termination_date.is_(None)) | (Employee.termination_date >= first),
            )
            .order_by(Employee.last_name, Employee.first_name)
        )
    ).scalars().all()

    results: list[PeriodBulkResultRow] = []
    for employee in employees:
        existing = await _get_closure(db, employee.id, payload.year, payload.month)
        if existing is not None and existing.status != PeriodStatus.DISPUTED:
            continue  # bereits vorgelegt/abgeschlossen – nicht erneut melden
        row = dict(employee_id=employee.id, first_name=employee.first_name, last_name=employee.last_name)
        try:
            await _submit(db, actor, employee, payload.year, payload.month, payload.ignore_open_days, payload.ignore_open_requests)
            results.append(PeriodBulkResultRow(**row, submitted=True))
        except AppError as exc:
            # Alle Prüfungen in _submit liegen vor dem ersten Schreibzugriff – ein Rollback ist hier
            # nicht nötig (und würde die Session-Objekte, inkl. actor, verfallen lassen).
            results.append(PeriodBulkResultRow(**row, submitted=False, reason=exc.message))
    return results
