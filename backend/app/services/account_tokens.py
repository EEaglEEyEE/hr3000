"""Einmal-Links per E-Mail: "Passwort vergessen" und "E-Mail bestätigen" (Selbstregistrierung).

Der Link enthält ein zufälliges Token (secrets.token_urlsafe); gespeichert wird nur dessen
SHA-256. Ein Token gilt einmal, läuft ab und macht beim Ausstellen ältere offene Tokens
desselben Kontos und Zwecks ungültig.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountToken, AccountTokenPurpose, Employee, HrUser

PASSWORD_RESET_TTL = timedelta(hours=1)
EMAIL_VERIFY_TTL = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_token(
    db: AsyncSession,
    *,
    tenant_id: int,
    purpose: AccountTokenPurpose,
    ttl: timedelta,
    hr_user: HrUser | None = None,
    employee: Employee | None = None,
) -> str:
    """Neues Token ausstellen (ältere offene desselben Kontos/Zwecks verfallen). Ruft kein commit."""
    if (hr_user is None) == (employee is None):
        raise ValueError("Genau ein Konto (HR-Nutzer oder Mitarbeiter) angeben.")
    owner = AccountToken.hr_user_id == hr_user.id if hr_user else AccountToken.employee_id == employee.id
    await db.execute(
        update(AccountToken)
        .where(owner, AccountToken.purpose == purpose.value, AccountToken.used_at.is_(None))
        .values(used_at=_now())
    )
    raw = secrets.token_urlsafe(32)
    db.add(
        AccountToken(
            tenant_id=tenant_id,
            hr_user_id=hr_user.id if hr_user else None,
            employee_id=employee.id if employee else None,
            purpose=purpose.value,
            token_hash=_hash(raw),
            expires_at=_now() + ttl,
        )
    )
    return raw


async def consume_token(db: AsyncSession, raw: str, purpose: AccountTokenPurpose) -> AccountToken | None:
    """Gültiges, unbenutztes Token zum Zweck einlösen (markiert es als benutzt) – sonst None.
    Ruft kein commit."""
    if not raw or len(raw) > 200:
        return None
    token = await db.scalar(
        select(AccountToken).where(AccountToken.token_hash == _hash(raw), AccountToken.purpose == purpose.value)
    )
    if token is None or token.used_at is not None or token.expires_at <= _now():
        return None
    token.used_at = _now()
    return token
