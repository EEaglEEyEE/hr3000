from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.middleware.tenant as tenant_middleware
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import (
    AppSettings,
    Base,
    BreakRule,
    Device,
    Employee,
    Holiday,
    Account,
    Location,
    Punch,
    ShiftTemplate,
    Department,
    Tenant,
)

# Tabellen mit direkter, nicht-nullable tenant_id (siehe Migrationsplan A2).
# Die ~20 bestehenden Test-Dateien setzen tenant_id nirgends explizit – dieser
# Hook füllt sie transparent mit dem Standard-Testmandanten (id=1), statt jeden
# einzelnen Test-Helper mechanisch anzupassen.
_TENANT_SCOPED_MODELS = [
    Location,
    Employee,
    Punch,
    Device,
    AppSettings,
    BreakRule,
    Holiday,
    Department,
    ShiftTemplate,
]


def _autofill_tenant_id(mapper, connection, target) -> None:
    if target.tenant_id is None:
        target.tenant_id = 1


def _autofill_account_tenant_id(mapper, connection, target) -> None:
    # tenant_id=None ist bei Account ein gültiger, bewusst gesetzter Wert
    # (Super-Admin) – nur auffüllen, wenn er beim Konstruieren nie berührt wurde.
    if "tenant_id" not in inspect(target).dict:
        target.tenant_id = 1


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.services import rate_limiter

    rate_limiter.clear_all()
    yield
    rate_limiter.clear_all()


@pytest.fixture
async def db_session(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncSession, None]:
    # Aktiviert den Dev-Escape-Hatch der Tenant-Resolution-Middleware, damit der
    # Testclient (Host "test", keine echte Subdomain) auf den Standard-
    # Testmandanten fällt, siehe app/middleware/tenant.py.
    monkeypatch.setattr(settings, "debug", True)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Die Middleware öffnet ihre eigene Session (kein FastAPI-DI für
    # Middleware) – muss auf dieselbe In-Memory-DB zeigen wie db_session,
    # sonst findet sie den unten geseedeten Tenant nie.
    monkeypatch.setattr(tenant_middleware, "AsyncSessionLocal", session_factory)

    async with session_factory() as seed_session:
        seed_session.add(Tenant(id=1, subdomain="musterfirma", name="Musterfirma"))
        # Schichtplanung standardmäßig an, damit die bestehenden Schichtplan-Tests
        # unverändert laufen; neue Mandanten starten produktiv ohne (siehe
        # AppSettings.shift_planning_enabled).
        seed_session.add(AppSettings(tenant_id=1, shift_planning_enabled=True))
        await seed_session.commit()

    listeners = [(model, _autofill_tenant_id) for model in _TENANT_SCOPED_MODELS]
    listeners.append((Account, _autofill_account_tenant_id))
    for model, listener in listeners:
        event.listen(model, "before_insert", listener)

    try:
        async with session_factory() as session:
            yield session
    finally:
        for model, listener in listeners:
            event.remove(model, "before_insert", listener)
        await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def at_time(monkeypatch):
    """Legt "jetzt" für die Tagesberechnung fest (UTC, naiv) – z.B. um eine laufende Schicht an
    einem festen Testdatum zu prüfen, ohne dass die maximale Schichtlänge schon überschritten ist."""
    from datetime import datetime

    import app.services.timesheet_service as timesheet_service

    def _set(now: datetime) -> None:
        monkeypatch.setattr(timesheet_service, "_utcnow", lambda: now)

    return _set
