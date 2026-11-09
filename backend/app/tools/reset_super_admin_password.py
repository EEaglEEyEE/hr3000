"""Neues Einmal-Passwort für den plattformweiten Super-Admin setzen ("Passwort vergessen").

Auf dem Server als root ausführen – das Passwort erscheint nur in diesem Terminal und wird
nirgends gespeichert oder protokolliert:

    cd /opt/hr3000 && docker compose exec backend python -m app.tools.reset_super_admin_password

Danach unter https://<SUPER_ADMIN_HOSTNAME> (z.B. admin.hr3000.de) mit der ausgegebenen
E-Mail und dem Passwort anmelden und das Passwort im Passwort-Manager ablegen.
"""

import asyncio
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, HrRole
from app.services.auth_service import hash_password


async def reset_super_admin_password(db: AsyncSession) -> tuple[str, str]:
    """Setzt ein zufälliges Passwort für den (einzigen) Super-Admin; gibt (E-Mail, Passwort) zurück."""
    admins = (
        await db.execute(select(Account).where(Account.role == HrRole.SUPER_ADMIN, Account.tenant_id.is_(None)))
    ).scalars().all()
    if len(admins) != 1:
        raise RuntimeError(f"Erwartet genau einen Super-Admin, gefunden: {len(admins)}.")
    password = secrets.token_urlsafe(18)
    admins[0].password_hash = hash_password(password)
    await db.commit()
    return admins[0].email, password


async def _main() -> int:
    from app.config import settings
    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            email, password = await reset_super_admin_password(db)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(
        "\nNeues Super-Admin-Passwort gesetzt (wird nicht erneut angezeigt):\n"
        f"  Adresse:  https://{settings.super_admin_hostname}\n"
        f"  E-Mail:   {email}\n"
        f"  Passwort: {password}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
