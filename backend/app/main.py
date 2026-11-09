import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.absences import router as absences_router
from app.api.absence_types import router as absence_types_router
from app.api.dashboard import router as dashboard_router
from app.api.punch_correction_requests import router as punch_correction_requests_router
from app.api.audit_log import router as audit_log_router
from app.api.calendar_feed import router as calendar_feed_router
from app.api.auth import router as auth_router
from app.api.break_rules import router as break_rules_router
from app.api.devices import router as devices_router
from app.api.employee_data_export import router as employee_data_export_router
from app.api.documents import router as documents_router
from app.api.balance_adjustments import router as balance_adjustments_router
from app.api.branding import router as branding_router
from app.api.checklists import router as checklists_router
from app.api.period_closures import router as period_closures_router
from app.api.reports import router as reports_router
from app.api.surcharges import router as surcharges_router
from app.api.wage_types import router as wage_types_router
from app.api.employment import router as employment_router
from app.api.employee_default_shifts import router as employee_default_shifts_router
from app.api.employees import router as employees_router
from app.api.holidays import router as holidays_router
from app.api.hr_users import router as hr_users_router
from app.api.departments import router as departments_router
from app.api.personal_data import router as personal_data_router
from app.api.attributes import router as attributes_router
from app.api.change_requests import router as change_requests_router
from app.api.document_templates import router as document_templates_router
from app.api.public_api import router as public_api_router
from app.api.two_factor import router as two_factor_router
from app.api.leave_entitlements import router as leave_entitlements_router
from app.api.locations import router as locations_router
from app.api.notifications import router as notifications_router
from app.api.payroll_export import router as payroll_export_router
from app.api.migration import router as migration_router
from app.api.punches import router as punches_router
from app.api.plan import router as plan_router
from app.api.settings import router as settings_router
from app.api.shift_plan_entries import router as shift_plan_entries_router
from app.api.shift_plan_pdf import router as shift_plan_pdf_router
from app.api.shift_templates import router as shift_templates_router
from app.api.team_calendar import router as team_calendar_router
from app.api.timesheets import router as timesheets_router
from app.api.tenants import router as tenants_router
from app.api.server_metrics import router as server_metrics_router
from app.api.tls import router as tls_router
from app.api.public import router as public_router
from app.api.work_time_model import router as work_time_model_router
from app.api.work_time_profiles import router as work_time_profiles_router
from app.api.ws import router as ws_router
from app.config import settings
from app.db import AsyncSessionLocal
from app.errors import AppError
from app.middleware.tenant import TenantResolutionMiddleware
from app.services.holiday_import_service import ensure_holidays_imported_for_all_tenants
from app.services.server_metrics import run_sampler
from app.services.reminder_service import run_reminders
from app.services.webhook_service import run_deliveries

logger = logging.getLogger(__name__)


class SkipPublicAccessLog(logging.Filter):
    """Aufrufe der Website-Schnittstellen (/public/…, z.B. Firmensuche auf hr3000.de/login)
    nicht mit IP-Adresse ins uvicorn-Zugriffsprotokoll – so steht es in der
    Datenschutzerklärung der Website (website/datenschutz)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (isinstance(args, tuple) and len(args) >= 3 and str(args[2]).startswith("/public/"))


logging.getLogger("uvicorn.access").addFilter(SkipPublicAccessLog())


_DEFAULT_JWT_SECRET = "change-me-in-.env"


def _ensure_production_secrets() -> None:
    """Verhindert den Start mit dem Platzhalter-JWT-Secret außerhalb des Debug-
    Modus – sonst könnte jeder mit Kenntnis des Quelltexts Tokens fälschen."""
    from app.config import settings

    if not settings.debug and (
        settings.jwt_secret_key == _DEFAULT_JWT_SECRET or len(settings.jwt_secret_key) < 32
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY ist nicht (oder zu schwach) gesetzt – bitte ein zufälliges Secret mit mind. 32 Zeichen in der .env hinterlegen."
        )
    if not settings.debug:
        from cryptography.fernet import Fernet

        try:
            Fernet(settings.encryption_key.encode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "ENCRYPTION_KEY fehlt oder ist kein gültiger Fernet-Schlüssel (siehe .env.example)."
            ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_production_secrets()
    # Sorgt dafür, dass nie manuell auf "Feiertage importieren" geklickt werden
    # muss – siehe app/services/holiday_import_service.py. Läuft für jeden
    # aktiven Mandanten einzeln.
    try:
        async with AsyncSessionLocal() as db:
            await ensure_holidays_imported_for_all_tenants(db)
    except Exception:
        logger.exception("Automatischer Feiertags-Import beim Start fehlgeschlagen.")
    # Server-Auslastung für den Super-Admin jede Minute speichern (0 = aus), siehe
    # app/services/server_metrics.py.
    sampler = None
    if settings.server_metrics_interval_seconds > 0:
        sampler = asyncio.create_task(
            run_sampler(
                AsyncSessionLocal,
                settings.server_metrics_interval_seconds,
                settings.server_metrics_retention_days,
                settings.server_metrics_disk_path,
            )
        )
    # Erinnerungen (Probezeit, Befristung, Austritt, verfallender Urlaub), siehe
    # app/services/reminder_service.py – nur bei Mandanten mit eingeschalteten Erinnerungen.
    reminders = None
    if settings.reminders_interval_seconds > 0:
        reminders = asyncio.create_task(run_reminders(AsyncSessionLocal, settings.reminders_interval_seconds))
    # Webhooks aus der Ausgangswarteschlange zustellen, siehe app/services/webhook_service.py.
    webhooks = None
    if settings.webhook_interval_seconds > 0:
        webhooks = asyncio.create_task(run_deliveries(AsyncSessionLocal, settings.webhook_interval_seconds))
    yield
    for task in (sampler, reminders, webhooks):
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="HR3000 Backend", lifespan=lifespan)

app.add_middleware(TenantResolutionMiddleware)

app.include_router(tenants_router)
app.include_router(server_metrics_router)
app.include_router(auth_router)
app.include_router(calendar_feed_router)
app.include_router(employees_router)
app.include_router(locations_router)
app.include_router(devices_router)
app.include_router(punches_router)
app.include_router(timesheets_router)
app.include_router(absences_router)
app.include_router(absence_types_router)
app.include_router(dashboard_router)
app.include_router(punch_correction_requests_router)
app.include_router(hr_users_router)
app.include_router(departments_router)
app.include_router(personal_data_router)
app.include_router(attributes_router)
app.include_router(change_requests_router)
app.include_router(document_templates_router)
app.include_router(public_api_router)
app.include_router(two_factor_router)
app.include_router(break_rules_router)
app.include_router(settings_router)
app.include_router(plan_router)
app.include_router(holidays_router)
app.include_router(leave_entitlements_router)
app.include_router(shift_templates_router)
app.include_router(employee_default_shifts_router)
app.include_router(shift_plan_entries_router)
app.include_router(shift_plan_pdf_router)
app.include_router(audit_log_router)
app.include_router(notifications_router)
app.include_router(payroll_export_router)
app.include_router(migration_router)
app.include_router(employee_data_export_router)
app.include_router(team_calendar_router)
app.include_router(work_time_model_router)
app.include_router(work_time_profiles_router)
app.include_router(employment_router)
app.include_router(documents_router)
app.include_router(period_closures_router)
app.include_router(reports_router)
app.include_router(checklists_router)
app.include_router(branding_router)
app.include_router(balance_adjustments_router)
app.include_router(surcharges_router)
app.include_router(wage_types_router)
app.include_router(ws_router)
app.include_router(tls_router)
app.include_router(public_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
