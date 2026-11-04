import asyncio
import hashlib
import re
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.models import EmployeeDocument
from app.services.secret_box import decrypt_bytes, encrypt_bytes

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sniff_content_type(data: bytes, filename: str) -> str | None:
    """Bestimmt den Typ am Dateikopf (Magic Bytes) statt am – frei wählbaren –
    Dateinamen/Client-Header. Erlaubt sind nur PDF, PNG, JPEG, DOCX und XLSX;
    alles andere (HTML, SVG, Skripte, EXE ...) wird abgelehnt."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04"):
        lowered = filename.lower()
        if lowered.endswith(".docx"):
            return _DOCX
        if lowered.endswith(".xlsx"):
            return _XLSX
    return None


def sanitize_filename(name: str | None) -> str:
    base = (name or "dokument").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", base).strip(" .")
    return (base or "dokument")[:255]


def _path_for(storage_key: str) -> Path:
    # storage_key ist immer eine selbst erzeugte UUID (hex) – nie Nutzereingabe.
    return Path(settings.documents_dir) / storage_key[:2] / storage_key


async def save_document_bytes(data: bytes) -> str:
    storage_key = uuid.uuid4().hex

    def _write() -> None:
        path = _path_for(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encrypt_bytes(data))

    await asyncio.to_thread(_write)
    return storage_key


async def read_document_bytes(storage_key: str) -> bytes | None:
    def _read() -> bytes | None:
        path = _path_for(storage_key)
        if not path.is_file():
            return None
        return decrypt_bytes(path.read_bytes())

    return await asyncio.to_thread(_read)


async def delete_document_file(storage_key: str) -> None:
    await asyncio.to_thread(lambda: _path_for(storage_key).unlink(missing_ok=True))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def ensure_tenant_quota(db: AsyncSession, tenant_id: int, additional_bytes: int) -> None:
    used = (
        await db.execute(
            select(func.coalesce(func.sum(EmployeeDocument.size_bytes), 0)).where(
                EmployeeDocument.tenant_id == tenant_id
            )
        )
    ).scalar_one()
    if used + additional_bytes > settings.max_tenant_document_bytes:
        raise AppError(413, "DOCUMENT_QUOTA_EXCEEDED", "Das Speicherkontingent für Dokumente ist erschöpft.")


async def store_document(
    db: AsyncSession,
    *,
    tenant_id: int,
    employee_id: int,
    data: bytes,
    filename: str,
    category,
    title: str,
    employee_visible: bool,
    confidential: bool,
    retention_until: date | None,
    uploaded_by_hr_user_id: int | None,
    uploaded_by_employee_id: int | None,
    content_type: str | None = None,
) -> EmployeeDocument:
    """Gemeinsamer Weg für Uploads UND intern erzeugte Dokumente (z.B.
    Monatsnachweise): Typprüfung, Kontingent, verschlüsselt ablegen, Zeile
    anlegen (committet nicht)."""
    if not data:
        raise AppError(400, "EMPTY_FILE", "Die Datei ist leer.")
    if len(data) > settings.max_document_bytes:
        raise AppError(413, "DOCUMENT_TOO_LARGE", f"Die Datei ist größer als {settings.max_document_bytes // (1024 * 1024)} MB.")
    detected = sniff_content_type(data, filename)
    if detected is None:
        raise AppError(
            400, "UNSUPPORTED_FILE_TYPE", "Erlaubt sind nur PDF, PNG, JPEG, DOCX und XLSX."
        )
    await ensure_tenant_quota(db, tenant_id, len(data))
    storage_key = await save_document_bytes(data)
    document = EmployeeDocument(
        tenant_id=tenant_id,
        employee_id=employee_id,
        category=category,
        title=title,
        original_filename=sanitize_filename(filename),
        content_type=content_type or detected,
        size_bytes=len(data),
        sha256=sha256_hex(data),
        storage_key=storage_key,
        confidential=confidential,
        employee_visible=employee_visible,
        retention_until=retention_until,
        uploaded_by_hr_user_id=uploaded_by_hr_user_id,
        uploaded_by_employee_id=uploaded_by_employee_id,
    )
    db.add(document)
    return document


async def delete_employee_documents(db: AsyncSession, employee_id: int) -> int:
    """Löscht alle Dokumente eines Mitarbeiters (Datei + Zeile), außer solchen
    unter laufender Aufbewahrungsfrist – genutzt bei der DSGVO-Anonymisierung.
    Gibt die Anzahl gelöschter Dokumente zurück, committet nicht."""
    today = date.today()
    result = await db.execute(select(EmployeeDocument).where(EmployeeDocument.employee_id == employee_id))
    deleted = 0
    for document in result.scalars().all():
        if document.retention_until is not None and document.retention_until >= today:
            continue
        await delete_document_file(document.storage_key)
        await db.delete(document)
        deleted += 1
    return deleted
