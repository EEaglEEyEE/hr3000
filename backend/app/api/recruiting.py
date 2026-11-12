"""Recruiting: Stellen, Bewerbungen und Karriereseite.

Intern (``/recruiting``): Admin/HR sehen und verwalten alles; alle anderen Konten (Führungskräfte und
Konten ohne Rolle) sehen nur Stellen, in deren Hiring Team sie stehen – sonst 404. Ist Recruiting in
den Einstellungen aus, antworten alle Endpoints außer ``/recruiting/access`` mit 404.

Öffentlich (``/public/careers``): Karriereseite der Firma aus der Subdomain, ohne Anmeldung, nur
veröffentlichte Stellen bis zum Bewerbungsschluss.

Regeln (Sichtbarkeit, Anhänge, Löschfristen): app/services/recruiting_service.py.
"""
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.checklists import start_checklist
from app.api.deps import Actor, _require_tenant_context, get_current_actor
from app.api.employees import create_employee
from app.db import get_db
from app.errors import AppError
from app.models import (
    Account,
    AuditAction,
    ChecklistTemplate,
    Department,
    Employee,
    Location,
    RecruitingApplication,
    RecruitingAttachment,
    RecruitingJob,
    RecruitingJobMember,
    RecruitingNote,
    RecruitingRating,
    RecruitingStageEvent,
    RecruitingStat,
)
from app.models.checklist import ChecklistKind
from app.models.recruiting import (
    ATTACHMENT_CV,
    ATTACHMENT_OTHER,
    JOB_PUBLISHED,
    SOURCE_CAREER_PAGE,
    SOURCE_MANUAL,
    STAGE_HIRED,
    STAGE_INTERVIEW,
    STAGE_NEW,
    STAGE_OFFER,
    STAGE_SCREENING,
)
from app.schemas.checklist import ChecklistStartRequest
from app.schemas.employee import EmployeeCreateRequest
from app.schemas.recruiting import (
    ApplicationCreateRequest,
    ApplicationDetailResponse,
    ApplicationListItem,
    ApplicationUpdateRequest,
    AttachmentKind,
    AttachmentResponse,
    CareersResponse,
    HireRequest,
    HireResponse,
    JobMemberResponse,
    JobResponse,
    JobWriteRequest,
    NoteRequest,
    NoteResponse,
    PublicApplicationForm,
    PublicApplicationResponse,
    PublicJobDetailResponse,
    PublicJobResponse,
    RatingRequest,
    RatingResponse,
    RecruitingAccessResponse,
    Stage,
    StageChangeRequest,
    StageEventResponse,
    TeamCandidateResponse,
)
from app.services import document_service, personal_data_service, rate_limiter
from app.services import recruiting_service as svc
from app.services.audit_service import log_action
from app.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/recruiting", tags=["recruiting"])
public_router = APIRouter(prefix="/public/careers", tags=["careers"])

# Bewerbungen über die Karriereseite je IP-Adresse und Stunde
APPLY_LIMIT = 5
APPLY_WINDOW_SECONDS = 3600
OPEN_STAGES = (STAGE_NEW, STAGE_SCREENING, STAGE_INTERVIEW, STAGE_OFFER)


# --- Zugriff ---------------------------------------------------------------------------------


def _require_account(actor: Actor) -> None:
    if actor.account is None:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    _require_tenant_context(actor)


async def recruiting_actor(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> Actor:
    """Angemeldetes Konto der Firma bei eingeschaltetem Recruiting (sonst 404)."""
    _require_account(actor)
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not settings_row.recruiting_enabled:
        raise AppError(404, "RECRUITING_DISABLED", "Recruiting ist nicht eingeschaltet.")
    return actor


def _require_manager(actor: Actor) -> None:
    if not actor.is_full_hr_level:
        raise AppError(403, "HR_PERMISSION_REQUIRED", "Nur für Administratoren und HR.")


def _job_not_found() -> AppError:
    return AppError(404, "RECRUITING_JOB_NOT_FOUND", "Stelle nicht gefunden.")


def _application_not_found() -> AppError:
    return AppError(404, "RECRUITING_APPLICATION_NOT_FOUND", "Bewerbung nicht gefunden.")


async def _job_for(db: AsyncSession, actor: Actor, job_id: int) -> RecruitingJob:
    job = await db.get(RecruitingJob, job_id)
    if job is None or job.tenant_id != actor.tenant_id:
        raise _job_not_found()
    visible = await svc.visible_job_ids(db, actor)
    if visible is not None and job.id not in visible:
        raise _job_not_found()
    return job


async def _application_for(db: AsyncSession, actor: Actor, application_id: int) -> RecruitingApplication:
    application = await db.get(RecruitingApplication, application_id)
    if application is None or application.tenant_id != actor.tenant_id:
        raise _application_not_found()
    visible = await svc.visible_job_ids(db, actor)
    if visible is not None and application.job_id not in visible:
        raise _application_not_found()
    return application


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, entity_type: str, entity_id: int, detail: str) -> None:
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=action,
        entity_type=entity_type, entity_id=entity_id, detail=detail[:1000],
    )


@router.get("/access", response_model=RecruitingAccessResponse)
async def get_access(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> RecruitingAccessResponse:
    """Für Menü und Reiter – antwortet auch bei ausgeschaltetem Recruiting (dann alles False)."""
    _require_account(actor)
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    if not settings_row.recruiting_enabled:
        return RecruitingAccessResponse(enabled=False, can_manage=False, member=False, can_see_salary=False)
    member = bool(await svc.member_job_ids(db, actor.tenant_id, actor.account_id))
    return RecruitingAccessResponse(
        enabled=True, can_manage=actor.is_full_hr_level, member=member, can_see_salary=actor.has_payroll_access
    )


# --- Stellen ---------------------------------------------------------------------------------


async def _names(db: AsyncSession, model, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {row.id: row.name for row in (await db.execute(select(model.id, model.name).where(model.id.in_(ids)))).all()}


async def _job_responses(db: AsyncSession, tenant_id: int, jobs: list[RecruitingJob]) -> list[JobResponse]:
    job_ids = {job.id for job in jobs} or {0}
    departments = await _names(db, Department, {job.department_id for job in jobs if job.department_id})
    locations = await _names(db, Location, {job.location_id for job in jobs if job.location_id})
    members: dict[int, list[int]] = {}
    for job_id, account_id in (
        await db.execute(
            select(RecruitingJobMember.job_id, RecruitingJobMember.account_id)
            .where(RecruitingJobMember.job_id.in_(job_ids))
            .order_by(RecruitingJobMember.id)
        )
    ).all():
        members.setdefault(job_id, []).append(account_id)
    names = await svc.account_names(db, tenant_id, {a for ids in members.values() for a in ids})
    emails = dict(
        (await db.execute(select(Account.id, Account.email).where(Account.id.in_(names.keys() or {0})))).all()
    )
    counts: dict[int, int] = {}
    open_counts: dict[int, int] = {}
    for job_id, stage, count in (
        await db.execute(
            select(RecruitingApplication.job_id, RecruitingApplication.stage, func.count())
            .where(RecruitingApplication.job_id.in_(job_ids))
            .group_by(RecruitingApplication.job_id, RecruitingApplication.stage)
        )
    ).all():
        counts[job_id] = counts.get(job_id, 0) + count
        if stage in OPEN_STAGES:
            open_counts[job_id] = open_counts.get(job_id, 0) + count
    deleted: dict[int, dict[str, int]] = {}
    for stat in (await db.execute(select(RecruitingStat).where(RecruitingStat.job_id.in_(job_ids)))).scalars().all():
        deleted.setdefault(stat.job_id, {})[stat.stage] = stat.count
    today = date.today()
    return [
        JobResponse(
            id=job.id,
            title=job.title,
            slug=svc.slugify(job.title),
            department_id=job.department_id,
            department_name=departments.get(job.department_id) if job.department_id else None,
            location_id=job.location_id,
            location_name=locations.get(job.location_id) if job.location_id else None,
            employment_type=job.employment_type,
            description=job.description,
            status=job.status,
            application_deadline=job.application_deadline,
            published_at=job.published_at,
            created_at=job.created_at,
            public=svc.is_public(job, today),
            members=[
                JobMemberResponse(account_id=account_id, name=names.get(account_id, ""), email=emails.get(account_id))
                for account_id in members.get(job.id, [])
            ],
            application_count=counts.get(job.id, 0),
            open_count=open_counts.get(job.id, 0),
            deleted_counts=deleted.get(job.id, {}),
        )
        for job in jobs
    ]


async def _check_reference(db: AsyncSession, model, object_id: int | None, tenant_id: int, code: str, label: str) -> None:
    if object_id is None:
        return
    row = await db.get(model, object_id)
    if row is None or row.tenant_id != tenant_id:
        raise AppError(404, code, f"{label} nicht gefunden.")


async def _apply_job(db: AsyncSession, job: RecruitingJob, payload: JobWriteRequest) -> list[str]:
    """Übernimmt die Angaben; gibt die geänderten Felder zurück (Audit ohne Inhalte)."""
    await _check_reference(db, Department, payload.department_id, job.tenant_id, "DEPARTMENT_NOT_FOUND", "Abteilung")
    await _check_reference(db, Location, payload.location_id, job.tenant_id, "LOCATION_NOT_FOUND", "Standort")
    changed = []
    for field in ("title", "department_id", "location_id", "employment_type", "description", "status", "application_deadline"):
        value = getattr(payload, field)
        if getattr(job, field) != value:
            setattr(job, field, value)
            changed.append(field)
    if job.status == JOB_PUBLISHED and job.published_at is None:
        job.published_at = svc.now()
    return changed


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)) -> list[JobResponse]:
    stmt = select(RecruitingJob).where(RecruitingJob.tenant_id == actor.tenant_id)
    visible = await svc.visible_job_ids(db, actor)
    if visible is not None:
        stmt = stmt.where(RecruitingJob.id.in_(visible or {0}))
    jobs = (await db.execute(stmt.order_by(RecruitingJob.created_at.desc(), RecruitingJob.id.desc()))).scalars().all()
    return await _job_responses(db, actor.tenant_id, list(jobs))


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(
    payload: JobWriteRequest, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> JobResponse:
    _require_manager(actor)
    job = RecruitingJob(tenant_id=actor.tenant_id, created_by_account_id=actor.account_id, created_at=svc.now())
    await _apply_job(db, job, payload)
    db.add(job)
    await db.flush()
    await svc.set_members(db, job, payload.member_account_ids)
    _audit(db, actor, AuditAction.RECRUITING_JOB_CHANGED, "recruiting_job", job.id, f"Stelle angelegt ({job.status})")
    await db.commit()
    return (await _job_responses(db, actor.tenant_id, [job]))[0]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)) -> JobResponse:
    job = await _job_for(db, actor, job_id)
    return (await _job_responses(db, actor.tenant_id, [job]))[0]


@router.put("/jobs/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int, payload: JobWriteRequest, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> JobResponse:
    _require_manager(actor)
    job = await _job_for(db, actor, job_id)
    changed = await _apply_job(db, job, payload)
    if await svc.set_members(db, job, payload.member_account_ids):
        changed.append("hiring_team")
    if changed:
        _audit(db, actor, AuditAction.RECRUITING_JOB_CHANGED, "recruiting_job", job.id, "Geändert: " + ", ".join(changed))
    await db.commit()
    return (await _job_responses(db, actor.tenant_id, [job]))[0]


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)) -> Response:
    _require_manager(actor)
    job = await _job_for(db, actor, job_id)
    has_applications = await db.scalar(
        select(func.count()).select_from(RecruitingApplication).where(RecruitingApplication.job_id == job.id)
    )
    has_stats = await db.scalar(select(func.count()).select_from(RecruitingStat).where(RecruitingStat.job_id == job.id))
    if has_applications or has_stats:
        raise AppError(
            409, "RECRUITING_JOB_IN_USE",
            "Zu dieser Stelle gibt es Bewerbungen bzw. eine Statistik. Bitte die Stelle schließen statt sie zu löschen.",
        )
    await db.execute(delete(RecruitingJobMember).where(RecruitingJobMember.job_id == job.id))
    _audit(db, actor, AuditAction.RECRUITING_JOB_CHANGED, "recruiting_job", job.id, "Stelle gelöscht")
    await db.delete(job)
    await db.commit()
    return Response(status_code=204)


@router.get("/team-candidates", response_model=list[TeamCandidateResponse])
async def list_team_candidates(
    actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> list[TeamCandidateResponse]:
    _require_manager(actor)
    return [
        TeamCandidateResponse(
            account_id=account.id,
            name=svc.account_name(account, employee) or "",
            email=account.email,
            role=account.role.value if account.role is not None else None,
        )
        for account, employee in await svc.team_candidates(db, actor.tenant_id)
    ]


# --- Bewerbungen -----------------------------------------------------------------------------


async def _list_items(db: AsyncSession, tenant_id: int, applications: list[RecruitingApplication]) -> list[ApplicationListItem]:
    ids = {a.id for a in applications} or {0}
    settings_row = await get_or_create_settings(db, tenant_id)
    titles = dict(
        (await db.execute(select(RecruitingJob.id, RecruitingJob.title).where(
            RecruitingJob.id.in_({a.job_id for a in applications} or {0})
        ))).all()
    )
    ratings = {
        application_id: (avg, count)
        for application_id, avg, count in (
            await db.execute(
                select(RecruitingRating.application_id, func.avg(RecruitingRating.score), func.count())
                .where(RecruitingRating.application_id.in_(ids))
                .group_by(RecruitingRating.application_id)
            )
        ).all()
    }
    attachments = dict(
        (await db.execute(
            select(RecruitingAttachment.application_id, func.count())
            .where(RecruitingAttachment.application_id.in_(ids))
            .group_by(RecruitingAttachment.application_id)
        )).all()
    )
    items = []
    for application in applications:
        avg, count = ratings.get(application.id, (None, 0))
        items.append(
            ApplicationListItem(
                id=application.id,
                job_id=application.job_id,
                job_title=titles.get(application.job_id, ""),
                first_name=application.first_name,
                last_name=application.last_name,
                email=application.email,
                stage=application.stage,
                source=application.source,
                talent_pool=application.talent_pool,
                created_at=application.created_at,
                closed_at=application.closed_at,
                delete_on=svc.delete_on(application, settings_row),
                average_rating=round(float(avg), 1) if avg is not None else None,
                rating_count=count,
                attachment_count=attachments.get(application.id, 0),
                employee_id=application.employee_id,
            )
        )
    return items


async def _detail(db: AsyncSession, actor: Actor, application: RecruitingApplication) -> ApplicationDetailResponse:
    base = (await _list_items(db, actor.tenant_id, [application]))[0]
    attachments = (
        await db.execute(
            select(RecruitingAttachment)
            .where(RecruitingAttachment.application_id == application.id)
            .order_by(RecruitingAttachment.id)
        )
    ).scalars().all()
    notes = (
        await db.execute(
            select(RecruitingNote).where(RecruitingNote.application_id == application.id).order_by(RecruitingNote.id)
        )
    ).scalars().all()
    ratings = (
        await db.execute(
            select(RecruitingRating).where(RecruitingRating.application_id == application.id).order_by(RecruitingRating.id)
        )
    ).scalars().all()
    events = (
        await db.execute(
            select(RecruitingStageEvent)
            .where(RecruitingStageEvent.application_id == application.id)
            .order_by(RecruitingStageEvent.id)
        )
    ).scalars().all()
    names = await svc.account_names(
        db, actor.tenant_id,
        {n.author_account_id for n in notes if n.author_account_id}
        | {r.account_id for r in ratings}
        | {e.account_id for e in events if e.account_id},
    )
    salary_visible = actor.has_payroll_access
    return ApplicationDetailResponse(
        **base.model_dump(),
        phone=application.phone,
        cover_letter=svc.decrypt_text(application.cover_letter_encrypted),
        salary_expectation=svc.decrypt_text(application.salary_expectation_encrypted) if salary_visible else None,
        salary_visible=salary_visible,
        rejection_reason=application.rejection_reason,
        rejection_note=application.rejection_note,
        privacy_acknowledged_at=application.privacy_acknowledged_at,
        hired_at=application.hired_at,
        attachments=[
            AttachmentResponse(
                id=a.id, kind=a.kind, original_filename=a.original_filename, content_type=a.content_type,
                size_bytes=a.size_bytes, created_at=a.created_at,
            )
            for a in attachments
        ],
        notes=[
            NoteResponse(
                id=n.id,
                author_account_id=n.author_account_id,
                author_name=names.get(n.author_account_id) if n.author_account_id else None,
                body=svc.decrypt_text(n.body_encrypted) or "",
                created_at=n.created_at,
                can_delete=actor.is_full_hr_level or n.author_account_id == actor.account_id,
            )
            for n in notes
        ],
        ratings=[
            RatingResponse(
                account_id=r.account_id, name=names.get(r.account_id), score=r.score,
                comment=svc.decrypt_text(r.comment_encrypted), updated_at=r.updated_at,
                mine=r.account_id == actor.account_id,
            )
            for r in ratings
        ],
        events=[
            StageEventResponse(
                from_stage=e.from_stage, to_stage=e.to_stage,
                account_name=names.get(e.account_id) if e.account_id else None, created_at=e.created_at,
            )
            for e in events
        ],
        can_manage=actor.is_full_hr_level,
    )


@router.get("/applications", response_model=list[ApplicationListItem])
async def list_applications(
    job_id: int | None = Query(default=None, ge=1),
    stage: Stage | None = None,
    actor: Actor = Depends(recruiting_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationListItem]:
    stmt = select(RecruitingApplication).where(RecruitingApplication.tenant_id == actor.tenant_id)
    visible = await svc.visible_job_ids(db, actor)
    if visible is not None:
        stmt = stmt.where(RecruitingApplication.job_id.in_(visible or {0}))
    if job_id is not None:
        stmt = stmt.where(RecruitingApplication.job_id == job_id)
    if stage is not None:
        stmt = stmt.where(RecruitingApplication.stage == stage)
    applications = (
        await db.execute(stmt.order_by(RecruitingApplication.created_at.desc(), RecruitingApplication.id.desc()))
    ).scalars().all()
    return await _list_items(db, actor.tenant_id, list(applications))


@router.get("/applications/due-for-deletion", response_model=list[ApplicationListItem])
async def list_due_for_deletion(
    within_days: int = Query(default=30, ge=0, le=365),
    actor: Actor = Depends(recruiting_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationListItem]:
    """Abgeschlossene Bewerbungen, die der Hintergrundlauf in den nächsten ``within_days`` Tagen löscht
    (bereits fällige zuerst)."""
    _require_manager(actor)
    due = await svc.due_applications(db, actor.tenant_id, date.today() + timedelta(days=within_days))
    return await _list_items(db, actor.tenant_id, [application for application, _ in due])


def _check_salary_access(actor: Actor, value: str | None) -> None:
    if value is not None and not actor.has_payroll_access:
        raise AppError(
            403, "PAYROLL_PERMISSION_REQUIRED", "Die Gehaltsvorstellung nur mit Berechtigung „Vergütung & Lohn-Export“."
        )


@router.post("/applications", response_model=ApplicationDetailResponse, status_code=201)
async def create_application(
    payload: ApplicationCreateRequest, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    """Manuell erfasste Bewerbung (Quelle „manuell erfasst“) – auch für Entwürfe und geschlossene Stellen."""
    _require_manager(actor)
    _check_salary_access(actor, payload.salary_expectation)
    job = await _job_for(db, actor, payload.job_id)
    application = RecruitingApplication(
        tenant_id=actor.tenant_id,
        job_id=job.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        phone=payload.phone or None,
        cover_letter_encrypted=svc.encrypt_text(payload.cover_letter),
        salary_expectation_encrypted=svc.encrypt_text(payload.salary_expectation),
        stage=STAGE_NEW,
        source=SOURCE_MANUAL,
        talent_pool=payload.talent_pool,
        created_by_account_id=actor.account_id,
        created_at=svc.now(),
    )
    db.add(application)
    await db.flush()
    svc.record_stage(db, application, None, actor.account_id)
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id,
           f"Bewerbung manuell erfasst (Stelle {job.id})")
    await db.commit()
    return await _detail(db, actor, application)


@router.get("/applications/{application_id}", response_model=ApplicationDetailResponse)
async def get_application(
    application_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    application = await _application_for(db, actor, application_id)
    return await _detail(db, actor, application)


@router.patch("/applications/{application_id}", response_model=ApplicationDetailResponse)
async def update_application(
    application_id: int,
    payload: ApplicationUpdateRequest,
    actor: Actor = Depends(recruiting_actor),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailResponse:
    _require_manager(actor)
    _check_salary_access(actor, payload.salary_expectation)
    application = await _application_for(db, actor, application_id)
    changed = []
    for field in ("first_name", "last_name", "talent_pool"):
        value = getattr(payload, field)
        if value is not None and getattr(application, field) != value:
            setattr(application, field, value)
            changed.append(field)
    if payload.email is not None and application.email != str(payload.email):
        application.email = str(payload.email)
        changed.append("email")
    if payload.phone is not None and application.phone != (payload.phone or None):
        application.phone = payload.phone or None
        changed.append("phone")
    if payload.cover_letter is not None:
        application.cover_letter_encrypted = svc.encrypt_text(payload.cover_letter)
        changed.append("cover_letter")
    if payload.salary_expectation is not None:
        application.salary_expectation_encrypted = svc.encrypt_text(payload.salary_expectation)
        changed.append("salary_expectation")
    if changed:
        _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id,
               "Geändert: " + ", ".join(changed))
    await db.commit()
    return await _detail(db, actor, application)


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(
    application_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> Response:
    """Sofort löschen (Admin/HR) – mit Notizen, Bewertungen und Anhängen; übrig bleibt die Zählung."""
    _require_manager(actor)
    application = await _application_for(db, actor, application_id)
    keys = await svc.delete_application(db, application, actor_account_id=actor.account_id, detail="Sofort gelöscht")
    await db.commit()
    await svc.delete_files(keys)
    return Response(status_code=204)


@router.post("/applications/{application_id}/stage", response_model=ApplicationDetailResponse)
async def change_stage(
    application_id: int,
    payload: StageChangeRequest,
    actor: Actor = Depends(recruiting_actor),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailResponse:
    application = await _application_for(db, actor, application_id)
    previous = application.stage
    svc.change_stage(db, application, payload.stage, actor.account_id, payload.rejection_reason, payload.rejection_note)
    detail = f"Phase {previous} → {application.stage}"
    if payload.rejection_reason:
        detail += f" (Grund {payload.rejection_reason})"
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id, detail)
    await db.commit()
    return await _detail(db, actor, application)


@router.post("/applications/{application_id}/notes", response_model=ApplicationDetailResponse, status_code=201)
async def add_note(
    application_id: int, payload: NoteRequest, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    application = await _application_for(db, actor, application_id)
    db.add(
        RecruitingNote(
            tenant_id=actor.tenant_id, application_id=application.id, author_account_id=actor.account_id,
            body_encrypted=svc.encrypt_text(payload.body), created_at=svc.now(),
        )
    )
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id, "Notiz hinzugefügt")
    await db.commit()
    return await _detail(db, actor, application)


@router.delete("/applications/{application_id}/notes/{note_id}", response_model=ApplicationDetailResponse)
async def delete_note(
    application_id: int, note_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    application = await _application_for(db, actor, application_id)
    note = await db.get(RecruitingNote, note_id)
    if note is None or note.application_id != application.id:
        raise AppError(404, "RECRUITING_NOTE_NOT_FOUND", "Notiz nicht gefunden.")
    if not actor.is_full_hr_level and note.author_account_id != actor.account_id:
        raise AppError(403, "FORBIDDEN", "Nur eigene Notizen können gelöscht werden.")
    await db.delete(note)
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id, "Notiz gelöscht")
    await db.commit()
    return await _detail(db, actor, application)


@router.put("/applications/{application_id}/rating", response_model=ApplicationDetailResponse)
async def set_rating(
    application_id: int, payload: RatingRequest, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    application = await _application_for(db, actor, application_id)
    rating = (
        await db.execute(
            select(RecruitingRating).where(
                RecruitingRating.application_id == application.id, RecruitingRating.account_id == actor.account_id
            )
        )
    ).scalar_one_or_none()
    if rating is None:
        rating = RecruitingRating(tenant_id=actor.tenant_id, application_id=application.id, account_id=actor.account_id)
        db.add(rating)
    rating.score = payload.score
    rating.comment_encrypted = svc.encrypt_text(payload.comment)
    rating.updated_at = svc.now()
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id,
           f"Bewertung gespeichert ({payload.score})")
    await db.commit()
    return await _detail(db, actor, application)


@router.delete("/applications/{application_id}/rating", response_model=ApplicationDetailResponse)
async def delete_rating(
    application_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    application = await _application_for(db, actor, application_id)
    result = await db.execute(
        delete(RecruitingRating).where(
            RecruitingRating.application_id == application.id, RecruitingRating.account_id == actor.account_id
        )
    )
    if result.rowcount:
        _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id,
               "Bewertung entfernt")
    await db.commit()
    return await _detail(db, actor, application)


@router.post("/applications/{application_id}/attachments", response_model=ApplicationDetailResponse, status_code=201)
async def upload_attachment(
    application_id: int,
    file: UploadFile = File(...),
    kind: AttachmentKind = Form(ATTACHMENT_OTHER),
    actor: Actor = Depends(recruiting_actor),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailResponse:
    _require_manager(actor)
    application = await _application_for(db, actor, application_id)
    if await svc.attachment_count(db, application.id) >= svc.MAX_ATTACHMENTS:
        raise AppError(400, "TOO_MANY_FILES", f"Höchstens {svc.MAX_ATTACHMENTS} Anhänge je Bewerbung.")
    data = await file.read(svc.max_attachment_bytes() + 1)
    filename = file.filename or "anhang"
    attachment = await svc.add_attachment(db, application, data, filename, kind)
    await db.flush()
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id,
           f"Anhang {attachment.id} hinzugefügt")
    await db.commit()
    return await _detail(db, actor, application)


async def _attachment_for(db: AsyncSession, application: RecruitingApplication, attachment_id: int) -> RecruitingAttachment:
    attachment = await db.get(RecruitingAttachment, attachment_id)
    if attachment is None or attachment.application_id != application.id:
        raise AppError(404, "RECRUITING_ATTACHMENT_NOT_FOUND", "Anhang nicht gefunden.")
    return attachment


@router.get("/applications/{application_id}/attachments/{attachment_id}/download")
async def download_attachment(
    application_id: int,
    attachment_id: int,
    inline: bool = False,
    actor: Actor = Depends(recruiting_actor),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Anhang herunterladen bzw. ansehen (``inline``, nur PDF/Bilder – andere Typen gibt es hier nicht)."""
    application = await _application_for(db, actor, application_id)
    attachment = await _attachment_for(db, application, attachment_id)
    data = await document_service.read_document_bytes(attachment.storage_key)
    if data is None:
        raise AppError(410, "DOCUMENT_FILE_MISSING", "Die Datei ist nicht mehr verfügbar.")
    _audit(db, actor, AuditAction.RECRUITING_ATTACHMENT_ACCESSED, "recruiting_application", application.id,
           f"Anhang {attachment.id} {'angesehen' if inline else 'heruntergeladen'}")
    await db.commit()
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.original_filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/applications/{application_id}/attachments/{attachment_id}", response_model=ApplicationDetailResponse)
async def delete_attachment(
    application_id: int, attachment_id: int, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> ApplicationDetailResponse:
    _require_manager(actor)
    application = await _application_for(db, actor, application_id)
    attachment = await _attachment_for(db, application, attachment_id)
    key = attachment.storage_key
    await db.delete(attachment)
    _audit(db, actor, AuditAction.RECRUITING_DELETED, "recruiting_application", application.id,
           f"Anhang {attachment_id} gelöscht")
    await db.commit()
    await svc.delete_files([key])
    return await _detail(db, actor, application)


@router.post("/applications/{application_id}/hire", response_model=HireResponse, status_code=201)
async def hire_application(
    application_id: int, payload: HireRequest, actor: Actor = Depends(recruiting_actor), db: AsyncSession = Depends(get_db)
) -> HireResponse:
    """„Als Mitarbeiter übernehmen“: legt den Mitarbeiter über den üblichen Anlage-Weg an, übernimmt
    die gewählten Anhänge in die Personalakte und startet auf Wunsch die Onboarding-Checkliste."""
    _require_manager(actor)
    application = await _application_for(db, actor, application_id)
    if application.employee_id is not None:
        raise AppError(409, "RECRUITING_ALREADY_HIRED", "Die Bewerbung wurde bereits als Mitarbeiter übernommen.")
    if application.stage != STAGE_HIRED:
        raise AppError(409, "RECRUITING_NOT_HIRED", "Übernehmen geht erst in der Phase „Eingestellt“.")
    # Erst alles prüfen, dann anlegen – sonst bliebe bei einem Fehler ein halber Stand zurück.
    attachments = []
    for attachment_id in payload.attachment_ids:
        attachments.append(await _attachment_for(db, application, attachment_id))
    if payload.checklist_template_id is not None:
        template = await db.get(ChecklistTemplate, payload.checklist_template_id)
        if template is None or template.tenant_id != actor.tenant_id or template.kind != ChecklistKind.ONBOARDING:
            raise AppError(404, "CHECKLIST_TEMPLATE_NOT_FOUND", "Onboarding-Vorlage nicht gefunden.")
    contents = []
    for attachment in attachments:
        data = await document_service.read_document_bytes(attachment.storage_key)
        if data is None:
            raise AppError(410, "DOCUMENT_FILE_MISSING", "Ein Anhang ist nicht mehr verfügbar.")
        contents.append((attachment, data))

    employee = await create_employee(
        EmployeeCreateRequest(
            location_id=payload.location_id,
            first_name=payload.first_name or application.first_name,
            last_name=payload.last_name or application.last_name,
            employee_number=payload.employee_number,
            hire_date=payload.hire_date,
            department_id=payload.department_id,
            position=payload.position,
        ),
        actor,
        db,
    )
    # Verknüpfung sofort festhalten: verhindert eine zweite Übernahme, auch wenn ein Folgeschritt scheitert.
    application.employee_id = employee.id
    application.hired_at = svc.now()
    _audit(db, actor, AuditAction.RECRUITING_APPLICATION_CHANGED, "recruiting_application", application.id,
           f"Als Mitarbeiter übernommen (Mitarbeiter {employee.id})")
    await db.commit()
    employee_row = await db.get(Employee, employee.id)
    await personal_data_service.save(
        db, employee_row, {"private_email": str(payload.private_email or application.email), "phone": application.phone}
    )
    for attachment, data in contents:
        title = "Lebenslauf" if attachment.kind == ATTACHMENT_CV else f"Bewerbung: {attachment.original_filename}"
        document = await document_service.store_document(
            db, tenant_id=actor.tenant_id, employee_id=employee.id, data=data, filename=attachment.original_filename,
            category=payload.document_category, title=title[:200], employee_visible=False, confidential=False,
            retention_until=None, uploaded_by_account_id=actor.account_id, content_type=attachment.content_type,
        )
        await db.flush()
        _audit(db, actor, AuditAction.DOCUMENT_UPLOADED, "employee_document", document.id,
               f"{document.category.value}: {document.title} (aus Bewerbung übernommen)")
    await db.commit()
    checklist_started = False
    if payload.checklist_template_id is not None:
        await start_checklist(employee.id, ChecklistStartRequest(template_id=payload.checklist_template_id), actor, db)
        checklist_started = True
    return HireResponse(employee_id=employee.id, documents_copied=len(contents), checklist_started=checklist_started)


# --- Karriereseite (öffentlich) --------------------------------------------------------------


async def _careers_context(request: Request, db: AsyncSession):
    """Firma aus der Subdomain; 404, wenn es keine gibt oder Recruiting aus ist."""
    tenant = getattr(request.state, "tenant", None)
    if tenant is None:
        raise AppError(404, "CAREERS_NOT_FOUND", "Diese Seite gibt es nicht.")
    settings_row = await get_or_create_settings(db, tenant.id)
    if not settings_row.recruiting_enabled:
        raise AppError(404, "CAREERS_NOT_FOUND", "Diese Seite gibt es nicht.")
    return tenant, settings_row


async def _public_job(db: AsyncSession, tenant_id: int, job_id: int) -> RecruitingJob:
    job = await db.get(RecruitingJob, job_id)
    if job is None or job.tenant_id != tenant_id or not svc.is_public(job, date.today()):
        raise AppError(404, "RECRUITING_JOB_NOT_FOUND", "Diese Stelle gibt es nicht (mehr).")
    return job


async def _public_jobs(db: AsyncSession, jobs: list[RecruitingJob]) -> list[PublicJobResponse]:
    departments = await _names(db, Department, {job.department_id for job in jobs if job.department_id})
    locations = await _names(db, Location, {job.location_id for job in jobs if job.location_id})
    return [
        PublicJobResponse(
            id=job.id, slug=svc.slugify(job.title), title=job.title,
            department=departments.get(job.department_id) if job.department_id else None,
            location=locations.get(job.location_id) if job.location_id else None,
            employment_type=job.employment_type, application_deadline=job.application_deadline,
        )
        for job in jobs
    ]


@public_router.get("", response_model=CareersResponse)
async def careers(request: Request, db: AsyncSession = Depends(get_db)) -> CareersResponse:
    tenant, settings_row = await _careers_context(request, db)
    jobs = (
        await db.execute(
            select(RecruitingJob)
            .where(RecruitingJob.tenant_id == tenant.id, RecruitingJob.status == JOB_PUBLISHED)
            .order_by(RecruitingJob.published_at.desc(), RecruitingJob.id.desc())
        )
    ).scalars().all()
    today = date.today()
    return CareersResponse(
        company_name=tenant.name,
        privacy_text=settings_row.recruiting_privacy_text,
        privacy_url=settings_row.recruiting_privacy_url,
        jobs=await _public_jobs(db, [job for job in jobs if svc.is_public(job, today)]),
    )


@public_router.get("/jobs/{job_id}", response_model=PublicJobDetailResponse)
async def career_job(job_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> PublicJobDetailResponse:
    tenant, settings_row = await _careers_context(request, db)
    job = await _public_job(db, tenant.id, job_id)
    base = (await _public_jobs(db, [job]))[0]
    return PublicJobDetailResponse(
        **base.model_dump(),
        description=job.description,
        company_name=tenant.name,
        privacy_text=settings_row.recruiting_privacy_text,
        privacy_url=settings_row.recruiting_privacy_url,
        max_files=svc.MAX_ATTACHMENTS,
        max_file_mb=svc.max_attachment_bytes() // (1024 * 1024),
    )


@public_router.post("/jobs/{job_id}/applications", response_model=PublicApplicationResponse, status_code=201)
async def apply(
    job_id: int,
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str | None = Form(None),
    cover_letter: str | None = Form(None),
    salary_expectation: str | None = Form(None),
    privacy_acknowledged: bool = Form(False),
    talent_pool: bool = Form(False),
    # Honeypot: für Menschen unsichtbar; ausgefüllt = Bot
    website: str | None = Form(None),
    cv: UploadFile | None = File(None),
    attachments: list[UploadFile] | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> PublicApplicationResponse:
    """Bewerbung über die Karriereseite. Ohne Anmeldung; Rate-Limit je IP-Adresse, Honeypot gegen Bots."""
    tenant, _ = await _careers_context(request, db)
    key = f"careers-apply:{tenant.id}:{request.client.host if request.client else 'unknown'}"
    rate_limiter.check_rate_limit(key, APPLY_LIMIT, APPLY_WINDOW_SECONDS, code="TOO_MANY_APPLICATIONS")
    rate_limiter.record_failure(key)  # jede Bewerbung zählt
    try:
        form = PublicApplicationForm.model_validate(
            {
                "first_name": first_name, "last_name": last_name, "email": email, "phone": phone,
                "cover_letter": cover_letter, "salary_expectation": salary_expectation,
                "privacy_acknowledged": privacy_acknowledged, "talent_pool": talent_pool, "website": website,
            }
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False, include_context=False)) from exc
    job = await _public_job(db, tenant.id, job_id)
    if form.website:
        # Bot: Erfolg vortäuschen, nichts speichern
        return PublicApplicationResponse()

    files = [(ATTACHMENT_CV, cv)] if cv is not None else []
    files += [(ATTACHMENT_OTHER, upload) for upload in attachments or []]
    if len(files) > svc.MAX_ATTACHMENTS:
        raise AppError(400, "TOO_MANY_FILES", f"Höchstens {svc.MAX_ATTACHMENTS} Dateien.")
    checked = []
    for kind, upload in files:
        data = await upload.read(svc.max_attachment_bytes() + 1)
        filename = upload.filename or "anhang"
        checked.append((kind, data, filename, svc.check_attachment(data, filename)))

    application = RecruitingApplication(
        tenant_id=tenant.id,
        job_id=job.id,
        first_name=form.first_name,
        last_name=form.last_name,
        email=str(form.email),
        phone=form.phone or None,
        cover_letter_encrypted=svc.encrypt_text(form.cover_letter),
        salary_expectation_encrypted=svc.encrypt_text(form.salary_expectation),
        stage=STAGE_NEW,
        source=SOURCE_CAREER_PAGE,
        talent_pool=form.talent_pool,
        privacy_acknowledged_at=svc.now(),
        created_at=svc.now(),
    )
    db.add(application)
    await db.flush()
    svc.record_stage(db, application, None, None)
    for kind, data, filename, content_type in checked:
        await svc.add_attachment(db, application, data, filename, kind, content_type)
    log_action(
        db, tenant_id=tenant.id, actor_account_id=None, action=AuditAction.RECRUITING_APPLICATION_CHANGED,
        entity_type="recruiting_application", entity_id=application.id,
        detail=f"Bewerbung über die Karriereseite (Stelle {job.id}, {len(checked)} Anhänge)",
    )
    await svc.notify_new_application(db, job)
    await db.commit()
    await svc.send_confirmation(db, tenant.id, tenant.name, application.email, application.first_name, job.title)
    return PublicApplicationResponse()
