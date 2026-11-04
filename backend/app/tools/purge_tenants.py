"""Fällige Firmen endgültig löschen – täglich per Cron (eingerichtet von scripts/rollout.sh):

    cd /opt/hr3000 && docker compose exec -T backend python -m app.tools.purge_tenants

Gelöscht werden gekündigte Firmen ab ihrem Löschtermin (Vertragsende + 30 Tage) und
Selbstregistrierungen, deren E-Mail-Adresse nach 7 Tagen noch nicht bestätigt ist – siehe
services/tenant_lifecycle.py. Mit --dry-run wird nur angezeigt, was gelöscht würde.
"""

import asyncio
import sys
from datetime import UTC, datetime


async def _main(dry_run: bool) -> int:
    from app.db import AsyncSessionLocal
    from app.services.tenant_lifecycle import purge_tenant, tenants_due_for_purge, tenant_row_counts

    async with AsyncSessionLocal() as db:
        due = await tenants_due_for_purge(db)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        if not due:
            print(f"{stamp}: nichts fällig")
            return 0
        for tenant in due:
            reason = (
                f"Löschtermin {tenant.deletion_due_on:%d.%m.%Y}"
                if tenant.deletion_due_on
                else "E-Mail-Adresse nach 7 Tagen nicht bestätigt"
            )
            if dry_run:
                rows = sum((await tenant_row_counts(db, tenant.id)).values())
                print(f"{stamp}: würde löschen {tenant.subdomain} (id {tenant.id}, {reason}, {rows} Zeilen)")
                continue
            tenant_id, subdomain = tenant.id, tenant.subdomain
            counts = await purge_tenant(db, tenant_id)
            print(f"{stamp}: gelöscht {subdomain} (id {tenant_id}, {reason}, {sum(counts.values())} Zeilen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main("--dry-run" in sys.argv[1:])))
