"""Öffentliche API (v1) und Webhooks.

Zugang: Admins legen unter „Einstellungen“ → „API & Webhooks“ einen API-Zugang mit Rechten (Scopes) an
und bekommen Client-ID und Secret (einmal angezeigt). Damit holt das Fremdsystem über
POST /v1/auth/token ein Token (1 Stunde) und ruft die Lese-Endpunkte unter /v1 mit
„Authorization: Bearer <token>“ auf – immer über die Adresse der Firma (https://firma.hr3000.de/api/v1/…).
Nur lesend; je Zugang höchstens 1200 Anfragen in 10 Minuten.
"""
import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import (
    API_SCOPES,
    WEBHOOK_EVENTS,
    Absence,
    AbsenceTypeDefinition,
    ApiClient,
    Department,
    Employee,
    Punch,
    Webhook,
    WebhookDelivery,
)
from app.services import rate_limiter, webhook_service
from app.services.auth_service import create_token, decode_token
from app.services.personal_data_service import mark_leave
from app.services.secret_box import encrypt_secret

router = APIRouter(tags=["public_api"])
_bearer = HTTPBearer(auto_error=False)
TOKEN_TTL = timedelta(hours=1)
_MAX_RANGE_DAYS = 366


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --- Verwaltung (Admins) -------------------------------------------------------------------------


class ApiClientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=len(API_SCOPES))

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: list[str]) -> list[str]:
        unknown = set(value) - set(API_SCOPES)
        if unknown:
            raise ValueError(f"Unbekannte Rechte: {', '.join(sorted(unknown))}")
        return sorted(set(value))


class ApiClientResponse(BaseModel):
    id: int
    name: str
    client_id: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiClientCreated(ApiClientResponse):
    # Nur jetzt sichtbar
    client_secret: str


def _client_response(client: ApiClient) -> ApiClientResponse:
    return ApiClientResponse(
        id=client.id, name=client.name, client_id=client.client_id, scopes=client.scopes.split(","),
        created_at=client.created_at, last_used_at=client.last_used_at, revoked_at=client.revoked_at,
    )


@router.get("/api-clients", response_model=list[ApiClientResponse])
async def list_api_clients(actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> list[ApiClientResponse]:
    rows = (await db.execute(select(ApiClient).where(ApiClient.tenant_id == actor.tenant_id).order_by(ApiClient.id))).scalars()
    return [_client_response(r) for r in rows]


@router.post("/api-clients", response_model=ApiClientCreated, status_code=201)
async def create_api_client(
    payload: ApiClientRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> ApiClientCreated:
    secret = secrets.token_urlsafe(32)
    client = ApiClient(
        tenant_id=actor.tenant_id, name=payload.name.strip(), client_id="hr3000_" + secrets.token_hex(12),
        secret_hash=_hash(secret), scopes=",".join(payload.scopes), created_by_account_id=actor.account_id,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return ApiClientCreated(**_client_response(client).model_dump(), client_secret=secret)


@router.delete("/api-clients/{client_id}", status_code=204)
async def revoke_api_client(client_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> None:
    """Zugang sperren – ausgegebene Tokens gelten sofort nicht mehr."""
    client = await db.get(ApiClient, client_id)
    if client is None or client.tenant_id != actor.tenant_id:
        raise AppError(404, "API_CLIENT_NOT_FOUND", "API-Zugang nicht gefunden.")
    client.revoked_at = client.revoked_at or _now()
    await db.commit()


class WebhookRequest(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    events: list[str] = Field(min_length=1, max_length=len(WEBHOOK_EVENTS))

    @field_validator("events")
    @classmethod
    def _events(cls, value: list[str]) -> list[str]:
        unknown = set(value) - set(WEBHOOK_EVENTS)
        if unknown:
            raise ValueError(f"Unbekannte Ereignisse: {', '.join(sorted(unknown))}")
        return sorted(set(value))


class WebhookUpdateRequest(BaseModel):
    active: bool | None = None
    events: list[str] | None = None

    @field_validator("events")
    @classmethod
    def _events(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else WebhookRequest._events(value)


class WebhookResponse(BaseModel):
    id: int
    url: str
    events: list[str]
    active: bool
    created_at: datetime
    last_delivery_at: datetime | None
    last_status: str | None


class WebhookCreated(WebhookResponse):
    # Signatur-Secret, nur jetzt sichtbar
    secret: str


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event: str
    status: str
    attempts: int
    response_status: int | None
    last_error: str | None
    created_at: datetime


def _webhook_response(webhook: Webhook) -> WebhookResponse:
    return WebhookResponse(
        id=webhook.id, url=webhook.url, events=webhook.events.split(","), active=webhook.active,
        created_at=webhook.created_at, last_delivery_at=webhook.last_delivery_at, last_status=webhook.last_status,
    )


async def _webhook(db: AsyncSession, webhook_id: int, tenant_id: int) -> Webhook:
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None or webhook.tenant_id != tenant_id:
        raise AppError(404, "WEBHOOK_NOT_FOUND", "Webhook nicht gefunden.")
    return webhook


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> list[WebhookResponse]:
    rows = (await db.execute(select(Webhook).where(Webhook.tenant_id == actor.tenant_id).order_by(Webhook.id))).scalars()
    return [_webhook_response(r) for r in rows]


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
async def create_webhook(payload: WebhookRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> WebhookCreated:
    count = await db.scalar(select(func.count()).select_from(Webhook).where(Webhook.tenant_id == actor.tenant_id))
    if count >= 10:
        raise AppError(400, "TOO_MANY_WEBHOOKS", "Höchstens 10 Webhooks je Firma.")
    secret = "whsec_" + secrets.token_urlsafe(24)
    webhook = Webhook(
        tenant_id=actor.tenant_id, url=webhook_service.validate_url(payload.url), secret=encrypt_secret(secret),
        events=",".join(payload.events), active=True,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    return WebhookCreated(**_webhook_response(webhook).model_dump(), secret=secret)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: int, payload: WebhookUpdateRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> WebhookResponse:
    webhook = await _webhook(db, webhook_id, actor.tenant_id)
    if payload.active is not None:
        webhook.active = payload.active
    if payload.events is not None:
        webhook.events = ",".join(payload.events)
    await db.commit()
    return _webhook_response(webhook)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> None:
    webhook = await _webhook(db, webhook_id, actor.tenant_id)
    for delivery in (await db.execute(select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook.id))).scalars():
        await db.delete(delivery)
    await db.delete(webhook)
    await db.commit()


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookDeliveryResponse, status_code=201)
async def test_webhook(webhook_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> WebhookDeliveryResponse:
    """Test-Ereignis in die Warteschlange (wird mit der nächsten Runde zugestellt)."""
    webhook = await _webhook(db, webhook_id, actor.tenant_id)
    delivery = WebhookDelivery(
        tenant_id=webhook.tenant_id, webhook_id=webhook.id, event="test",
        payload='{"event": "test", "data": {}}', status="PENDING", attempts=0, next_attempt_at=_now(),
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return WebhookDeliveryResponse.model_validate(delivery)


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(webhook_id: int, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)) -> list[WebhookDeliveryResponse]:
    webhook = await _webhook(db, webhook_id, actor.tenant_id)
    rows = (
        await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook.id).order_by(WebhookDelivery.id.desc()).limit(20)
        )
    ).scalars()
    return [WebhookDeliveryResponse.model_validate(r) for r in rows]


# --- Token und Lese-Endpunkte (v1) ---------------------------------------------------------------


class TokenRequest(BaseModel):
    client_id: str = Field(max_length=40)
    client_secret: str = Field(max_length=100)


class ApiToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/v1/auth/token", response_model=ApiToken)
async def issue_api_token(request: Request, payload: TokenRequest, db: AsyncSession = Depends(get_db)) -> ApiToken:
    tenant = getattr(request.state, "tenant", None)
    key = f"api-token:{request.client.host if request.client else 'unknown'}"
    rate_limiter.check_rate_limit(key, 10, 15 * 60)
    client = (await db.execute(select(ApiClient).where(ApiClient.client_id == payload.client_id))).scalar_one_or_none()
    if (
        tenant is None or client is None or client.tenant_id != tenant.id or client.revoked_at is not None
        or not secrets.compare_digest(client.secret_hash, _hash(payload.client_secret))
    ):
        rate_limiter.record_failure(key)
        raise AppError(401, "INVALID_CLIENT", "Client-ID oder Secret falsch.")
    token = create_token(
        subject=str(client.id), token_type="api_access", expires_delta=TOKEN_TTL,
        extra_claims={"tenant_id": client.tenant_id, "scopes": client.scopes.split(",")},
    )
    return ApiToken(access_token=token, expires_in=int(TOKEN_TTL.total_seconds()))


def require_scope(scope: str):
    async def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: AsyncSession = Depends(get_db),
    ) -> ApiClient:
        if credentials is None:
            raise AppError(401, "TOKEN_INVALID", "Bitte ein API-Token mitsenden.")
        claims = decode_token(credentials.credentials)
        tenant = getattr(request.state, "tenant", None)
        client = await db.get(ApiClient, int(claims["sub"])) if claims.get("type") == "api_access" else None
        if client is None or client.revoked_at is not None or tenant is None or client.tenant_id != tenant.id:
            raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.")
        if scope not in client.scopes.split(","):
            raise AppError(403, "SCOPE_MISSING", f"Diesem Zugang fehlt das Recht {scope}.")
        rate_key = f"api:{client.id}"
        rate_limiter.check_rate_limit(rate_key, 1200, 600, code="API_RATE_LIMIT")
        rate_limiter.record_failure(rate_key)
        if client.last_used_at is None or _now() - client.last_used_at > timedelta(minutes=5):
            client.last_used_at = _now()
            await db.commit()
        return client

    return dependency


class Page(BaseModel):
    limit: int
    offset: int
    total: int


class ApiEmployee(BaseModel):
    id: int
    personnel_number: str
    first_name: str
    last_name: str
    email: str | None
    status: str
    active: bool
    hire_date: date | None
    termination_date: date | None
    location_id: int
    team_id: int | None
    department: str | None
    position: str | None
    supervisor_id: int | None


class EmployeesPage(BaseModel):
    data: list[ApiEmployee]
    page: Page


def _range(date_from: date, date_to: date) -> None:
    if date_to < date_from or (date_to - date_from).days > _MAX_RANGE_DAYS:
        raise AppError(400, "INVALID_RANGE", f"Zeitraum höchstens {_MAX_RANGE_DAYS} Tage.")


@router.get("/v1/employees", response_model=EmployeesPage)
async def api_employees(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    active: bool | None = None,
    client: ApiClient = Depends(require_scope("employees:read")),
    db: AsyncSession = Depends(get_db),
) -> EmployeesPage:
    stmt = select(Employee).where(Employee.tenant_id == client.tenant_id)
    if active is not None:
        stmt = stmt.where(Employee.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    people = list((await db.execute(stmt.order_by(Employee.id).limit(limit).offset(offset))).scalars().all())
    await mark_leave(db, people)
    names = dict((await db.execute(select(Department.id, Department.name).where(Department.tenant_id == client.tenant_id))).all())
    return EmployeesPage(
        data=[
            ApiEmployee(
                id=p.id, personnel_number=p.employee_number, first_name=p.first_name, last_name=p.last_name,
                email=p.login_email, status=p.employment_status, active=p.active, hire_date=p.hire_date,
                termination_date=p.termination_date, location_id=p.location_id, team_id=p.team_id,
                department=names.get(p.department_id) if p.department_id else None, position=p.position,
                supervisor_id=p.supervisor_id,
            )
            for p in people
        ],
        page=Page(limit=limit, offset=offset, total=total or 0),
    )


class ApiAbsenceType(BaseModel):
    id: int
    name: str
    category: str


@router.get("/v1/absence-types", response_model=list[ApiAbsenceType])
async def api_absence_types(client: ApiClient = Depends(require_scope("absences:read")), db: AsyncSession = Depends(get_db)) -> list[ApiAbsenceType]:
    rows = (
        await db.execute(select(AbsenceTypeDefinition).where(AbsenceTypeDefinition.tenant_id == client.tenant_id).order_by(AbsenceTypeDefinition.id))
    ).scalars()
    return [ApiAbsenceType(id=r.id, name=r.name, category=r.category.value) for r in rows]


class ApiAbsence(BaseModel):
    id: int
    employee_id: int
    absence_type_id: int | None
    category: str
    date_from: date
    date_to: date
    half_day: bool
    duration_minutes: int | None
    status: str


class AbsencesPage(BaseModel):
    data: list[ApiAbsence]
    page: Page


@router.get("/v1/absences", response_model=AbsencesPage)
async def api_absences(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    employee_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    client: ApiClient = Depends(require_scope("absences:read")),
    db: AsyncSession = Depends(get_db),
) -> AbsencesPage:
    _range(date_from, date_to)
    stmt = (
        select(Absence)
        .join(Employee, Employee.id == Absence.employee_id)
        .where(Employee.tenant_id == client.tenant_id, Absence.date_from <= date_to, Absence.date_to >= date_from)
    )
    if employee_id is not None:
        stmt = stmt.where(Absence.employee_id == employee_id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(Absence.date_from, Absence.id).limit(limit).offset(offset))).scalars()
    return AbsencesPage(
        data=[
            ApiAbsence(
                id=a.id, employee_id=a.employee_id, absence_type_id=a.absence_type_id, category=a.type.value,
                date_from=a.date_from, date_to=a.date_to, half_day=a.half_day, duration_minutes=a.duration_minutes,
                status=a.approval_status.value,
            )
            for a in rows
        ],
        page=Page(limit=limit, offset=offset, total=total or 0),
    )


class ApiPunch(BaseModel):
    id: int
    employee_id: int
    type: str
    timestamp_utc: datetime
    source: str


class PunchesPage(BaseModel):
    data: list[ApiPunch]
    page: Page


@router.get("/v1/punches", response_model=PunchesPage)
async def api_punches(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    employee_id: int | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    client: ApiClient = Depends(require_scope("attendances:read")),
    db: AsyncSession = Depends(get_db),
) -> PunchesPage:
    """Stempelungen (Kommen, Gehen, Pause …) im Zeitraum, Zeitpunkte in UTC."""
    _range(date_from, date_to)
    stmt = select(Punch).where(
        Punch.tenant_id == client.tenant_id,
        Punch.timestamp_utc >= datetime.combine(date_from, datetime.min.time()),
        Punch.timestamp_utc < datetime.combine(date_to + timedelta(days=1), datetime.min.time()),
    )
    if employee_id is not None:
        stmt = stmt.where(Punch.employee_id == employee_id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(Punch.timestamp_utc, Punch.id).limit(limit).offset(offset))).scalars()
    return PunchesPage(
        data=[
            ApiPunch(id=p.id, employee_id=p.employee_id, type=p.punch_type.value, timestamp_utc=p.timestamp_utc, source=p.source.value)
            for p in rows
        ],
        page=Page(limit=limit, offset=offset, total=total or 0),
    )

