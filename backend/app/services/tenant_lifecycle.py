"""Kündigung und Löschung von Firmen (Mandanten) – so, wie es Nutzungsbedingungen (§ 9) und
AV-Vertrag (§ 7) zusagen: Kündigung zum Monatsende, danach 30 Tage Zugriff zum Exportieren,
dann werden alle Daten der Firma gelöscht. Kopien in Datensicherungen verschwinden mit deren
Aufbewahrungsfristen (höchstens 12 Monate).

Gelöscht wird generisch aus dem Datenmodell: Tabellen mit ``tenant_id`` direkt, alle übrigen über
einen Fremdschlüssel auf eine solche Tabelle (z.B. Abwesenheiten über den Mitarbeiter) – abhängige
Zeilen zuerst. Eine neue Tabelle ohne diesen Bezug lässt ``purge_plan`` scheitern (Test
``test_every_table_is_covered``), damit beim Löschen nie Daten liegen bleiben.

Ausgeführt wird die Löschung täglich von ``app/tools/purge_tenants.py`` (Cron) oder sofort durch
den Super-Admin. Außerdem verfallen Selbstregistrierungen, deren E-Mail-Adresse nach 7 Tagen
noch nicht bestätigt ist.
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Table, delete, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.models import Base, EmployeeDocument, HrUser, Tenant
from app.services.document_service import delete_document_file

logger = logging.getLogger(__name__)

EXPORT_DAYS_AFTER_CONTRACT_END = 30
UNVERIFIED_SIGNUP_DAYS = 7


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- Kündigung ---------------------------------------------------------------------------


def cancellation_dates(today: date) -> tuple[date, date]:
    """Kündigung heute -> (Vertragsende = letzter Tag des Monats, Löschtermin = +30 Tage)."""
    contract_end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    return contract_end, contract_end + timedelta(days=EXPORT_DAYS_AFTER_CONTRACT_END)


def cancel(tenant: Tenant, now: datetime | None = None) -> bool:
    """Kündigung vermerken. Schon gekündigt -> unverändert (False). Ruft kein commit."""
    if tenant.cancelled_at is not None:
        return False
    now = now or _now()
    tenant.cancelled_at = now
    tenant.contract_end, tenant.deletion_due_on = cancellation_dates(now.date())
    return True


def revoke_cancellation(tenant: Tenant) -> bool:
    """Kündigung zurücknehmen (bis zur Löschung möglich). Ruft kein commit."""
    if tenant.cancelled_at is None:
        return False
    tenant.cancelled_at = None
    tenant.contract_end = None
    tenant.deletion_due_on = None
    return True


# --- Löschung ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _Scope:
    table: Table
    condition: ColumnElement[bool]


def _scope_condition(table: Table, tenant_id: int, scoped: dict[str, Table]) -> ColumnElement[bool]:
    if "tenant_id" in table.c:
        return table.c.tenant_id == tenant_id
    fks = [fk for fk in table.foreign_keys if fk.column.table.name in scoped]
    if not fks:
        raise RuntimeError(f"Tabelle {table.name} hat weder tenant_id noch einen Bezug zu einer Firmentabelle.")

    def via(fk) -> ColumnElement[bool]:
        parent = scoped[fk.column.table.name]
        return fk.parent.in_(select(parent.c.id).where(parent.c.tenant_id == tenant_id))

    required = [fk for fk in fks if not fk.parent.nullable]
    if required:
        return via(sorted(required, key=lambda fk: fk.parent.name)[0])
    return or_(*(via(fk) for fk in fks))


# Plattform-Tabellen ohne Firmendaten – bewusst nicht Teil der Löschung einer Firma. Nur Tabellen
# eintragen, die nachweislich nichts über eine Firma oder ihre Mitarbeiter enthalten.
PLATFORM_TABLES = {
    "tenants",
    "server_metric_samples",  # Auslastung des ganzen Servers (Super-Admin), ohne Firmenbezug
}


def purge_plan(tenant_id: int) -> list[_Scope]:
    """Alle Tabellen (außer Plattform-Tabellen) mit der Bedingung "gehört zu dieser Firma",
    abhängige zuerst."""
    tables = Base.metadata.sorted_tables
    scoped = {t.name: t for t in tables if "tenant_id" in t.c}
    return [
        _Scope(t, _scope_condition(t, tenant_id, scoped))
        for t in reversed(tables)
        if t.name not in PLATFORM_TABLES
    ]


async def tenant_row_counts(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for scope in purge_plan(tenant_id):
        counts[scope.table.name] = await db.scalar(select(func.count()).select_from(scope.table).where(scope.condition))
    return counts


async def purge_tenant(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    """Löscht die Firma mit allen Daten (inkl. verschlüsselter Dokument-Dateien) endgültig.
    Gibt die Anzahl gelöschter Zeilen je Tabelle zurück. Committet selbst."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError(f"Mandant {tenant_id} existiert nicht.")
    subdomain = tenant.subdomain
    storage_keys = list(
        (await db.scalars(select(EmployeeDocument.storage_key).where(EmployeeDocument.tenant_id == tenant_id))).all()
    )
    counts = await tenant_row_counts(db, tenant_id)
    for scope in purge_plan(tenant_id):
        await db.execute(delete(scope.table).where(scope.condition))
    await db.execute(delete(Tenant.__table__).where(Tenant.__table__.c.id == tenant_id))
    await db.commit()
    # Dateien erst nach dem Commit: scheitert die DB, bleiben sie lieber liegen als umgekehrt.
    for key in storage_keys:
        await delete_document_file(key)
    logger.info(
        "Mandant %s (%s) gelöscht: %s Zeilen, %s Dokument-Dateien",
        tenant_id, subdomain, sum(counts.values()), len(storage_keys),
    )
    return counts


async def tenants_due_for_purge(db: AsyncSession, now: datetime | None = None) -> list[Tenant]:
    """Gekündigte Firmen nach dem Löschtermin und Selbstregistrierungen, deren E-Mail-Adresse
    nach 7 Tagen noch nicht bestätigt ist."""
    now = now or _now()
    verified_admin = exists().where(HrUser.tenant_id == Tenant.id, HrUser.email_verification_pending == false())
    stmt = select(Tenant).where(
        or_(
            Tenant.deletion_due_on <= now.date(),
            (Tenant.self_signup.is_(True))
            & (Tenant.created_at < now - timedelta(days=UNVERIFIED_SIGNUP_DAYS))
            & ~verified_admin,
        )
    )
    return list((await db.scalars(stmt.order_by(Tenant.id))).all())
