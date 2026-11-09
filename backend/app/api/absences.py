from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_hr_or_self, get_current_hr_principal
from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.models import (
    Absence,
    AbsenceApproval,
    AbsenceApprovalStatus,
    AbsenceType,
    AbsenceTypeDefinition,
    AuditAction,
    DocumentCategory,
    Employee,
)
from app.schemas.absence import (
    AbsenceCreateRequest,
    AbsenceDecideRequest,
    AbsenceResponse,
    AbsenceUpdateRequest,
    PendingAbsenceResponse,
    SubstituteCandidate,
    TeamOverlap,
)
from app.services.absence_type_service import CATEGORY_LABELS, resolve_absence_type
from app.services.audit_service import log_action
from app.services.notification_service import notify_absence_decided, notify_absence_requested, notify_substitute_assigned
from app.services.settings_service import get_or_create_settings
from app.services.scope_service import ensure_employee_visible, visible_employee_ids
from app.services import approval_service, webhook_service
from app.services.document_service import store_document
from app.services.leave_service import leave_balance
from app.services.period_service import ensure_range_open
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["absences"])


async def _get_absence_in_tenant(db: AsyncSession, absence_id: int, tenant_id: int) -> Absence:
    """Absence hat kein eigenes tenant_id (leitet sich über employee_id ab),
    daher Prüfung über einen Join statt einem einfachen Attribut-Vergleich."""
    result = await db.execute(
        select(Absence)
        .join(Employee, Employee.id == Absence.employee_id)
        .where(Absence.id == absence_id, Employee.tenant_id == tenant_id)
    )
    absence = result.scalar_one_or_none()
    if absence is None:
        raise AppError(404, "ABSENCE_NOT_FOUND", "Abwesenheit nicht gefunden.")
    return absence


async def _has_authority_over_employee(db: AsyncSession, actor: Actor, employee: Employee) -> bool:
    """Ob der Actor diesen Mitarbeiter final entscheiden/direkt-genehmigen
    darf: Admin/HR (unbeschränkt) oder Supervisor des Teams des Mitarbeiters
    (siehe app/services/team_scope_service.py)."""
    if actor.is_full_hr_level:
        return True
    if not actor.is_supervisor_level:
        return False
    try:
        await ensure_employee_visible(db, actor, employee)
    except AppError:
        return False
    return True


async def _resolve_substitute(
    db: AsyncSession, tenant_id: int, employee: Employee, substitute_id: int | None, mode: str, required: bool
) -> Employee | None:
    """Vertretung prüfen (AbsenceTypeDefinition.substitute_mode): Pflicht nur, wenn `required`
    (Antrag des Mitarbeiters selbst), aktiv, derselbe Mandant, nicht die Person selbst."""
    if substitute_id is None:
        if required:
            raise AppError(400, "SUBSTITUTE_REQUIRED", "Für diese Abwesenheitsart bitte eine Vertretung angeben.")
        return None
    if mode == "NONE":
        raise AppError(400, "SUBSTITUTE_NOT_ALLOWED", "Für diese Abwesenheitsart gibt es keine Vertretung.")
    substitute = await db.get(Employee, substitute_id)
    if substitute is None or substitute.tenant_id != tenant_id or not substitute.active:
        raise AppError(404, "SUBSTITUTE_NOT_FOUND", "Vertretung nicht gefunden.")
    if substitute.id == employee.id:
        raise AppError(400, "SUBSTITUTE_SELF", "Die Vertretung muss eine andere Person sein.")
    return substitute


async def _type_name(db: AsyncSession, absence: Absence) -> str:
    definition = await db.get(AbsenceTypeDefinition, absence.absence_type_id) if absence.absence_type_id else None
    return definition.name if definition is not None else CATEGORY_LABELS.get(absence.type, "Abwesenheit")


async def _notify_substitute(db: AsyncSession, tenant_id: int, absence: Absence, employee: Employee) -> None:
    if absence.substitute_employee_id is None:
        return
    substitute = await db.get(Employee, absence.substitute_employee_id)
    if substitute is not None:
        await notify_substitute_assigned(db, tenant_id, absence, employee, substitute, await _type_name(db, absence))


async def _responses(db: AsyncSession, absences: list[Absence]) -> list[AbsenceResponse]:
    """AbsenceResponse mit dem Namen der Vertretung (für HR und Mitarbeiter gleichermaßen)."""
    ids = {a.substitute_employee_id for a in absences if a.substitute_employee_id is not None}
    names: dict[int, str] = {}
    if ids:
        rows = await db.execute(select(Employee.id, Employee.first_name, Employee.last_name).where(Employee.id.in_(ids)))
        names = {row.id: f"{row.first_name} {row.last_name}" for row in rows}
    responses = []
    for a in absences:
        waiting = None
        if a.approval_status == AbsenceApprovalStatus.PENDING:
            employee = await db.get(Employee, a.employee_id)
            waiting = await approval_service.waiting_for(db, a, employee) if employee is not None else None
        responses.append(
            AbsenceResponse.model_validate(a).model_copy(
                update={"substitute_name": names.get(a.substitute_employee_id or 0), "waiting_for": waiting}
            )
        )
    return responses


async def _team_overlaps(
    db: AsyncSession, employee: Employee, date_from: date, date_to: date, with_types: bool, exclude_absence_id: int | None = None
) -> list[TeamOverlap]:
    """Genehmigte und beantragte Abwesenheiten anderer aktiver Personen derselben Abteilung, die den
    Zeitraum berühren (ohne Arbeitszeit-Angaben wie Homeoffice). Ohne Abteilung: keine."""
    if employee.department_id is None:
        return []
    rows = (
        await db.execute(
            select(Absence, Employee.first_name, Employee.last_name)
            .join(Employee, Employee.id == Absence.employee_id)
            .where(
                Employee.tenant_id == employee.tenant_id,
                Employee.department_id == employee.department_id,
                Employee.id != employee.id,
                Employee.active.is_(True),
                Absence.approval_status.in_([AbsenceApprovalStatus.APPROVED, AbsenceApprovalStatus.PENDING]),
                Absence.type != AbsenceType.WORK_TIME,
                Absence.date_from <= date_to,
                Absence.date_to >= date_from,
            )
            .order_by(Absence.date_from, Employee.last_name)
        )
    ).all()
    result = []
    for absence, first_name, last_name in rows:
        if absence.id == exclude_absence_id:
            continue
        result.append(
            TeamOverlap(
                employee_id=absence.employee_id,
                name=f"{first_name} {last_name}",
                date_from=absence.date_from,
                date_to=absence.date_to,
                half_day=absence.half_day,
                pending=absence.approval_status == AbsenceApprovalStatus.PENDING,
                type_name=await _type_name(db, absence) if with_types else None,
            )
        )
    return result


def _is_full_day(absence: Absence) -> bool:
    return not absence.half_day and absence.duration_minutes is None


async def _ensure_day_parts_fit(
    db: AsyncSession,
    employee_id: int,
    date_from: date,
    date_to: date,
    half_day: bool,
    duration_minutes: int | None,
    exclude_id: int | None = None,
) -> None:
    """Teil-Abwesenheiten eines Tages: höchstens zwei halbe Tage (z.B. ½ Sonderurlaub + ½ Urlaub)
    und beliebig viele Stundenangaben (z.B. 3 Std. Homeoffice) – aber nie zusammen mit einer
    ganztägigen Abwesenheit, sonst wäre unklar, was gutgeschrieben bzw. verbraucht wird."""
    stmt = select(Absence).where(
        Absence.employee_id == employee_id,
        Absence.date_from <= date_to,
        Absence.date_to >= date_from,
        Absence.approval_status != AbsenceApprovalStatus.REJECTED,
    )
    if exclude_id is not None:
        stmt = stmt.where(Absence.id != exclude_id)
    others = (await db.execute(stmt)).scalars().all()
    if half_day or duration_minutes is not None:
        if any(_is_full_day(other) for other in others):
            raise AppError(409, "ABSENCE_OVERLAP", "An diesem Tag ist bereits eine ganztägige Abwesenheit eingetragen.")
        if half_day and sum(1 for other in others if other.half_day) >= 2:
            raise AppError(409, "ABSENCE_OVERLAP", "An diesem Tag sind bereits zwei halbe Tage eingetragen.")
    elif any(not _is_full_day(other) for other in others):
        raise AppError(
            409,
            "ABSENCE_OVERLAP",
            "In diesem Zeitraum ist bereits ein halber Tag oder eine Stundenangabe eingetragen – bitte zuerst anpassen.",
        )


async def _resolve_full_day_overlap(
    db: AsyncSession,
    employee_id: int,
    date_from: date,
    date_to: date,
    category: AbsenceType,
    split_vacation: bool,
    exclude_id: int | None = None,
) -> None:
    """Ganztägige Abwesenheiten dürfen sich nicht überschneiden – sonst zählt ein Tag doppelt (z.B.
    Urlaub verbraucht, obwohl krank). Ausnahme mit Rückfrage: Krankheit während eines Urlaubs
    (§ 9 BUrlG). Mit split_vacation werden die Urlaubstage zurückgegeben: der Urlaub wird um die
    Krankheitstage gekürzt bzw. in zwei Teile geteilt."""
    stmt = select(Absence).where(
        Absence.employee_id == employee_id,
        Absence.date_from <= date_to,
        Absence.date_to >= date_from,
        Absence.approval_status != AbsenceApprovalStatus.REJECTED,
    )
    if exclude_id is not None:
        stmt = stmt.where(Absence.id != exclude_id)
    others = [a for a in (await db.execute(stmt)).scalars().all() if _is_full_day(a)]
    if not others:
        return
    if category != AbsenceType.SICK or any(o.type != AbsenceType.VACATION for o in others):
        raise AppError(409, "ABSENCE_OVERLAP", "In diesem Zeitraum ist bereits eine ganztägige Abwesenheit eingetragen.")
    if not split_vacation:
        ranges = ", ".join(f"{o.date_from:%d.%m.%Y}–{o.date_to:%d.%m.%Y}" for o in others)
        raise AppError(
            409,
            "ABSENCE_OVERLAP_VACATION",
            f"In diesem Zeitraum ist Urlaub eingetragen ({ranges}). Bei Krankheit im Urlaub werden die "
            "Urlaubstage zurückgegeben (§ 9 BUrlG).",
        )
    for vacation in others:
        note = (vacation.note + " · " if vacation.note else "") + f"wegen Krankheit {date_from:%d.%m.}–{date_to:%d.%m.%Y} gekürzt"
        before = (vacation.date_from, date_from - timedelta(days=1)) if vacation.date_from < date_from else None
        after = (date_to + timedelta(days=1), vacation.date_to) if vacation.date_to > date_to else None
        if before is None and after is None:
            await db.delete(vacation)
            continue
        first, second = (before, after) if before is not None else (after, None)
        vacation.date_from, vacation.date_to = first
        vacation.note = note[:400]
        if second is not None:
            db.add(
                Absence(
                    employee_id=vacation.employee_id,
                    type=vacation.type,
                    absence_type_id=vacation.absence_type_id,
                    date_from=second[0],
                    date_to=second[1],
                    half_day=False,
                    duration_minutes=None,
                    created_by_account_id=vacation.created_by_account_id,
                    note=note[:400],
                    approval_status=vacation.approval_status,
                )
            )
    await db.flush()


def _ensure_duration_allowed(category: AbsenceType, duration_minutes: int | None) -> None:
    # Urlaub zählt in Tagen (Urlaubskonto) – dafür gibt es ganze und halbe Tage.
    if duration_minutes is not None and category == AbsenceType.VACATION:
        raise AppError(400, "DURATION_NOT_FOR_VACATION", "Urlaub bitte als ganzen oder halben Tag eintragen, nicht in Stunden.")


@router.get("/employees/{employee_id}/absences", response_model=list[AbsenceResponse])
async def list_employee_absences(
    employee_id: int,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[AbsenceResponse]:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    stmt = select(Absence).where(Absence.employee_id == employee_id)
    if date_from is not None:
        stmt = stmt.where(Absence.date_to >= date_from)
    if date_to is not None:
        stmt = stmt.where(Absence.date_from <= date_to)
    stmt = stmt.order_by(Absence.date_from.asc())

    result = await db.execute(stmt)
    return await _responses(db, list(result.scalars().all()))


@router.get("/absences/pending", response_model=list[PendingAbsenceResponse])
async def list_pending_absences(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[PendingAbsenceResponse]:
    """Für die "Urlaubsanträge"-Seite: offene PENDING-Anträge, für einen
    Führungskräfte auf das, was gerade bei ihnen liegt."""
    stmt = (
        select(Absence)
        .join(Employee, Employee.id == Absence.employee_id)
        .where(Employee.tenant_id == actor.tenant_id, Absence.approval_status == AbsenceApprovalStatus.PENDING)
    )
    stmt = stmt.order_by(Absence.date_from.asc())

    absences = list((await db.execute(stmt)).scalars().all())
    if not actor.is_full_hr_level:
        # Führungskräfte: nur, was gerade bei ihnen liegt (eigener Bereich bzw. als Führungskraft/Vertretung)
        visible = []
        for absence in absences:
            employee = await db.get(Employee, absence.employee_id)
            if await approval_service.can_decide(db, actor, absence, employee):
                visible.append(absence)
        absences = visible
    pending = []
    for absence, base in zip(absences, await _responses(db, absences)):
        employee = await db.get(Employee, absence.employee_id)
        remaining = None
        if absence.type == AbsenceType.VACATION:
            remaining = (await leave_balance(db, absence.employee_id, absence.date_from.year)).remaining_days
        pending.append(
            PendingAbsenceResponse(
                **base.model_dump(),
                team_overlaps=await _team_overlaps(db, employee, absence.date_from, absence.date_to, True, absence.id),
                remaining_vacation_days=remaining,
            )
        )
    return pending


@router.get("/employees/{employee_id}/team-overlaps", response_model=list[TeamOverlap])
async def list_team_overlaps(
    employee_id: int,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[TeamOverlap]:
    """Wer aus der Abteilung im Zeitraum abwesend ist – für den Antrag. Genehmigende sehen die Art,
    Mitarbeiter nur Namen und Zeitraum und nur mit der Einstellung
    „absence_overlaps_for_employees“ (sonst leer)."""
    if date_to < date_from or (date_to - date_from).days > 366:
        raise AppError(400, "INVALID_RANGE", "Bitte einen Zeitraum von höchstens einem Jahr angeben.")
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
        return await _team_overlaps(db, employee, date_from, date_to, True)
    if not (await get_or_create_settings(db, actor.tenant_id)).absence_overlaps_for_employees:
        return []
    return await _team_overlaps(db, employee, date_from, date_to, False)


@router.get("/employees/{employee_id}/substitute-candidates", response_model=list[SubstituteCandidate])
async def list_substitute_candidates(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[SubstituteCandidate]:
    """Wer als Vertretung infrage kommt: aktive Kolleginnen und Kollegen des Mandanten (nur Namen) –
    auch für den Antrag im Self-Service."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    rows = await db.execute(
        select(Employee.id, Employee.first_name, Employee.last_name)
        .where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True), Employee.id != employee.id)
        .order_by(Employee.last_name, Employee.first_name)
    )
    return [SubstituteCandidate(id=r.id, first_name=r.first_name, last_name=r.last_name) for r in rows]


@router.post("/absences", response_model=AbsenceResponse, status_code=201)
async def create_absence(
    payload: AbsenceCreateRequest,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    """Erreichbar für HR-Level-Akteure (für jeden Mitarbeiter) UND per
    Self-Service für den eigenen Mitarbeiter (Urlaubsantrag stellen) – siehe
    approval_status-Logik unten, die genau zwischen diesen Fällen
    unterscheidet."""
    if actor.device is not None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")

    employee = await db.get(Employee, payload.employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")

    is_self = actor.employee is not None and actor.employee.id == employee.id
    if not actor.is_hr_level and not is_self:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    if actor.is_hr_level and not is_self:
        await ensure_employee_visible(db, actor, employee)

    if payload.date_to < payload.date_from:
        raise AppError(400, "INVALID_RANGE", "'date_to' darf nicht vor 'date_from' liegen.")

    await ensure_range_open(db, employee.id, payload.date_from, payload.date_to)
    await _ensure_day_parts_fit(db, employee.id, payload.date_from, payload.date_to, payload.half_day, payload.duration_minutes)

    absence_type = await resolve_absence_type(db, actor.tenant_id, payload.absence_type_id, payload.type)
    _ensure_duration_allowed(absence_type.category, payload.duration_minutes)
    if not payload.half_day and payload.duration_minutes is None:
        await _resolve_full_day_overlap(
            db, employee.id, payload.date_from, payload.date_to, absence_type.category, payload.split_vacation
        )
    has_authority = await _has_authority_over_employee(db, actor, employee)
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not has_authority and not settings_row.absence_requests_enabled:
        raise AppError(403, "ABSENCE_REQUESTS_DISABLED", "Anträge über das Portal sind abgeschaltet – bitte an HR wenden.")
    if not has_authority and not absence_type.employee_can_request:
        raise AppError(403, "ABSENCE_TYPE_NOT_REQUESTABLE", "Diese Abwesenheitsart kann nur HR eintragen.")
    substitute = await _resolve_substitute(
        db, actor.tenant_id, employee, payload.substitute_employee_id, absence_type.substitute_mode,
        required=absence_type.substitute_mode == "REQUIRED" and not has_authority,
    )
    if absence_type.comment_required and not (payload.note or "").strip():
        raise AppError(400, "COMMENT_REQUIRED", "Für diese Abwesenheitsart bitte einen Kommentar angeben.")

    approval_status = AbsenceApprovalStatus.APPROVED
    needs_approval = absence_type.requires_approval
    # Vier-Augen-Prinzip: Wer sonst genehmigen darf, bekommt eigene Anträge nicht direkt genehmigt.
    own_request_needs_other = is_self and settings_row.absence_four_eyes
    if needs_approval and (not has_authority or own_request_needs_other):
        approval_status = AbsenceApprovalStatus.PENDING

    absence = Absence(
        employee_id=payload.employee_id,
        type=absence_type.category,
        absence_type_id=absence_type.id,
        date_from=payload.date_from,
        date_to=payload.date_to,
        half_day=payload.half_day,
        duration_minutes=payload.duration_minutes,
        created_by_account_id=actor.account_id,
        note=payload.note,
        substitute_employee_id=substitute.id if substitute is not None else None,
        approval_status=approval_status,
    )
    db.add(absence)
    if approval_status == AbsenceApprovalStatus.PENDING:
        recipients = await approval_service.step_recipients(db, absence, employee)
        await notify_absence_requested(db, actor.tenant_id, employee, absence_type.name, recipients)
    else:
        await invalidate_balance(db, employee.id, payload.date_from)
        if substitute is not None:
            await db.flush()
            await notify_substitute_assigned(db, actor.tenant_id, absence, employee, substitute, absence_type.name)
    await db.flush()
    await webhook_service.emit_event(
        db, actor.tenant_id, "absence.created",
        {"absence_id": absence.id, "employee_id": employee.id, "status": absence.approval_status.value},
    )
    await db.commit()
    await db.refresh(absence)
    return (await _responses(db, [absence]))[0]


@router.patch("/absences/{absence_id}/decide", response_model=AbsenceResponse)
async def decide_absence(
    absence_id: int,
    payload: AbsenceDecideRequest,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    """Genehmigt/lehnt einen PENDING-Urlaubsantrag ab – nur für Supervisor
    (eigener Bereich) oder Admin/HR."""
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    if employee is None or not await approval_service.can_decide(db, actor, absence, employee):
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")

    if absence.approval_status != AbsenceApprovalStatus.PENDING:
        raise AppError(400, "NOT_PENDING", "Dieser Antrag wurde bereits entschieden.")
    if (
        actor.employee is not None
        and actor.employee.id == absence.employee_id
        and (await get_or_create_settings(db, actor.tenant_id)).absence_four_eyes
    ):
        raise AppError(403, "FOUR_EYES", "Eigene Anträge genehmigt jemand anderes (Vier-Augen-Prinzip).")
    await ensure_range_open(db, employee.id, absence.date_from, absence.date_to)

    chain = await approval_service.chain_for(db, absence)
    step_number, step_type = approval_service.current_step(chain, absence)
    db.add(
        AbsenceApproval(
            absence_id=absence.id, step=step_number, step_type=step_type, decided_by_account_id=actor.account_id,
            approved=payload.approve, note=(payload.note or None) and payload.note[:300], decided_at=datetime.now(UTC),
        )
    )
    if payload.approve and step_number < len(chain):
        # Nächster Schritt der Kette (z. B. nach der Führungskraft Admin/HR) – der Antrag bleibt offen.
        absence.approval_step = step_number + 1
        log_action(
            db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.ABSENCE_DECIDED,
            entity_type="absence", entity_id=absence.id,
            detail=f"Schritt {step_number} genehmigt für {employee.first_name} {employee.last_name}",
        )
        type_name = await _type_name(db, absence)
        await notify_absence_requested(
            db, actor.tenant_id, employee, type_name, await approval_service.step_recipients(db, absence, employee),
            f" (Schritt {step_number + 1} von {len(chain)})",
        )
        await db.commit()
        await db.refresh(absence)
        return (await _responses(db, [absence]))[0]

    absence.approval_status = (
        AbsenceApprovalStatus.APPROVED if payload.approve else AbsenceApprovalStatus.REJECTED
    )
    absence.decided_by_account_id = actor.account_id
    absence.decided_at = datetime.now(UTC)
    if payload.note:
        marker = f"[Entscheidung: {payload.note}]"
        absence.note = f"{absence.note} {marker}" if absence.note else marker

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.ABSENCE_DECIDED,
        entity_type="absence",
        entity_id=absence.id,
        detail=f"{'Genehmigt' if payload.approve else 'Abgelehnt'} für {employee.first_name} {employee.last_name}",
    )
    await notify_absence_decided(db, actor.tenant_id, absence, employee)
    await _notify_substitute(db, actor.tenant_id, absence, employee)
    await invalidate_balance(db, employee.id, absence.date_from)
    await webhook_service.emit_event(
        db, actor.tenant_id, "absence.decided",
        {"absence_id": absence.id, "employee_id": employee.id, "status": absence.approval_status.value},
    )

    await db.commit()
    await db.refresh(absence)
    return (await _responses(db, [absence]))[0]


@router.patch("/absences/{absence_id}", response_model=AbsenceResponse)
async def update_absence(
    absence_id: int,
    payload: AbsenceUpdateRequest,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    if employee is not None:
        await ensure_employee_visible(db, actor, employee)
    await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
    old_from = absence.date_from

    if payload.absence_type_id is not None or payload.type is not None:
        absence_type = await resolve_absence_type(db, actor.tenant_id, payload.absence_type_id, payload.type)
        absence.type = absence_type.category
        absence.absence_type_id = absence_type.id
    if payload.date_from is not None:
        absence.date_from = payload.date_from
    if payload.date_to is not None:
        absence.date_to = payload.date_to
    if payload.half_day is not None:
        absence.half_day = payload.half_day
    if payload.duration_minutes is not None:
        absence.duration_minutes = payload.duration_minutes
    elif payload.clear_duration:
        absence.duration_minutes = None
    if payload.note is not None:
        absence.note = payload.note
    substitute_changed = False
    if payload.clear_substitute:
        absence.substitute_employee_id = None
    elif payload.substitute_employee_id is not None and payload.substitute_employee_id != absence.substitute_employee_id:
        definition = await db.get(AbsenceTypeDefinition, absence.absence_type_id) if absence.absence_type_id else None
        try:
            substitute = await _resolve_substitute(
                db, actor.tenant_id, employee, payload.substitute_employee_id,
                definition.substitute_mode if definition is not None else "NONE", required=False,
            )
        except AppError:
            await db.rollback()
            raise
        absence.substitute_employee_id = substitute.id if substitute is not None else None
        substitute_changed = True

    if absence.date_to < absence.date_from:
        await db.rollback()
        raise AppError(400, "INVALID_RANGE", "'date_to' darf nicht vor 'date_from' liegen.")
    if (absence.half_day or absence.duration_minutes is not None) and absence.date_from != absence.date_to:
        await db.rollback()
        raise AppError(400, "HALF_DAY_SINGLE_DAY", "Halbe Tage und Stundenangaben sind nur für einen einzelnen Tag möglich.")
    if absence.half_day and absence.duration_minutes is not None:
        await db.rollback()
        raise AppError(400, "HALF_DAY_OR_DURATION", "Bitte entweder halber Tag oder Stunden angeben.")
    _ensure_duration_allowed(absence.type, absence.duration_minutes)
    await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
    await _ensure_day_parts_fit(
        db, absence.employee_id, absence.date_from, absence.date_to, absence.half_day, absence.duration_minutes, absence.id
    )
    if _is_full_day(absence):
        try:
            await _resolve_full_day_overlap(
                db, absence.employee_id, absence.date_from, absence.date_to, absence.type, payload.split_vacation, absence.id
            )
        except AppError:
            await db.rollback()
            raise
    await invalidate_balance(db, absence.employee_id, min(old_from, absence.date_from))
    if substitute_changed and employee is not None:
        await _notify_substitute(db, actor.tenant_id, absence, employee)

    await db.commit()
    await db.refresh(absence)
    return (await _responses(db, [absence]))[0]


@router.post("/absences/{absence_id}/certificate", response_model=AbsenceResponse)
async def upload_absence_certificate(
    absence_id: int,
    file: UploadFile = File(...),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> AbsenceResponse:
    """Nachweis (z. B. AU-Bescheinigung als Foto oder PDF) zu einer Abwesenheit hochladen – vom
    Mitarbeiter selbst oder von wem über ihn entscheiden darf. Liegt danach verschlüsselt in der
    Personalakte (Krankheit: Kategorie „Krankmeldung“), für den Mitarbeiter sichtbar."""
    if actor.device is not None:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    is_self = actor.employee is not None and actor.employee.id == absence.employee_id
    if employee is None or (not is_self and not await _has_authority_over_employee(db, actor, employee)):
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")

    data = await file.read(settings.max_document_bytes + 1)
    sick = absence.type in (AbsenceType.SICK, AbsenceType.CHILD_SICK)
    document = await store_document(
        db,
        tenant_id=actor.tenant_id,
        employee_id=employee.id,
        data=data,
        filename=file.filename or "nachweis",
        category=DocumentCategory.SICK_NOTE if sick else DocumentCategory.OTHER,
        title=f"Nachweis {await _type_name(db, absence)} {absence.date_from:%d.%m.%Y}–{absence.date_to:%d.%m.%Y}",
        employee_visible=True,
        confidential=False,
        retention_until=None,
        uploaded_by_account_id=actor.account_id,
    )
    await db.flush()
    absence.certificate_document_id = document.id
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.DOCUMENT_UPLOADED,
        entity_type="absence",
        entity_id=absence.id,
        detail=f"Nachweis hochgeladen für {employee.first_name} {employee.last_name}",
    )
    await db.commit()
    await db.refresh(absence)
    return (await _responses(db, [absence]))[0]


@router.delete("/absences/{absence_id}", status_code=204)
async def delete_absence(
    absence_id: int,
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    absence = await _get_absence_in_tenant(db, absence_id, actor.tenant_id)
    employee = await db.get(Employee, absence.employee_id)
    if employee is not None:
        await ensure_employee_visible(db, actor, employee)
    await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
    await invalidate_balance(db, absence.employee_id, absence.date_from)

    await db.delete(absence)
    await db.commit()
