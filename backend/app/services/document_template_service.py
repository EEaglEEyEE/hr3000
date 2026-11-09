"""Dokumentvorlagen füllen und als PDF erzeugen (WeasyPrint, wie Monatsbericht und Schichtplan).

Text der Vorlage: Absätze durch Leerzeilen, „# “ am Zeilenanfang für eine Überschrift, **fett**.
Platzhalter in doppelten geschweiften Klammern ({{vorname}}); eigene Felder als {{feld:Bezeichnung}}.
Alles wird HTML-maskiert – Vorlagen können kein HTML/Skript einschleusen.
"""
import html
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AttributeDefinition, Department, Employee, Location, Tenant
from app.services import attribute_service, personal_data_service
from app.services.settings_service import tenant_logo_data_url

PLACEHOLDERS: dict[str, str] = {
    "vorname": "Vorname",
    "nachname": "Nachname",
    "personalnummer": "Personalnummer",
    "position": "Position",
    "abteilung": "Abteilung",
    "standort": "Standort",
    "eintrittsdatum": "Eintrittsdatum",
    "austrittsdatum": "Austrittsdatum",
    "geburtsdatum": "Geburtsdatum",
    "strasse": "Straße (persönliche Daten)",
    "plz": "PLZ",
    "ort": "Ort",
    "firma": "Name der Firma",
    "heute": "heutiges Datum",
}
_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


async def values(db: AsyncSession, employee: Employee) -> dict[str, str]:
    tenant = await db.get(Tenant, employee.tenant_id)
    location = await db.get(Location, employee.location_id)
    department = await db.get(Department, employee.department_id) if employee.department_id else None
    personal = await personal_data_service.load(db, employee.id)
    result = {
        "vorname": employee.first_name, "nachname": employee.last_name, "personalnummer": employee.employee_number,
        "position": employee.position or "", "abteilung": department.name if department else "",
        "standort": location.name if location else "", "eintrittsdatum": _date(employee.hire_date),
        "austrittsdatum": _date(employee.termination_date), "geburtsdatum": _date(employee.birth_date),
        "strasse": personal.get("street") or "", "plz": personal.get("zip_code") or "", "ort": personal.get("city") or "",
        "firma": tenant.name if tenant else "", "heute": _date(date.today()),
    }
    definitions = (
        await db.execute(select(AttributeDefinition).where(AttributeDefinition.tenant_id == employee.tenant_id))
    ).scalars().all()
    grouped = await attribute_service.values_for(db, employee.id)
    for definition in definitions:
        now = attribute_service.current(grouped.get(definition.id, []))
        result[f"feld:{definition.label.lower()}"] = await attribute_service.display(db, definition, now.value if now else None) or ""
    return result


def fill(body: str, data: dict[str, str]) -> tuple[str, list[str]]:
    """Platzhalter ersetzen; gibt (Text, unbekannte Platzhalter) zurück."""
    unknown: list[str] = []

    def replace(match: re.Match) -> str:
        key = match.group(1).strip().lower()
        if key in data:
            return data[key]
        unknown.append(match.group(1).strip())
        return match.group(0)

    return _PATTERN.sub(replace, body), unknown


def to_html(text: str, logo: str | None) -> str:
    blocks = []
    for block in re.split(r"\n\s*\n", text.strip()):
        escaped = html.escape(block.strip())
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        if escaped.startswith("# "):
            blocks.append(f"<h1>{escaped[2:]}</h1>")
        else:
            blocks.append("<p>" + escaped.replace("\n", "<br>") + "</p>")
    header = f'<img class="logo" src="{html.escape(logo, quote=True)}">' if logo else ""
    return (
        "<html><head><meta charset='utf-8'><style>"
        "@page { size: A4; margin: 25mm 22mm; } body { font-family: sans-serif; font-size: 11pt; line-height: 1.45; }"
        "h1 { font-size: 15pt; margin: 0 0 12pt; } p { margin: 0 0 9pt; } .logo { max-height: 18mm; margin-bottom: 12mm; }"
        f"</style></head><body>{header}{''.join(blocks)}</body></html>"
    )


async def render_pdf(db: AsyncSession, employee: Employee, body: str) -> tuple[bytes, list[str]]:
    text, unknown = fill(body, await values(db, employee))
    from weasyprint import HTML

    pdf = HTML(string=to_html(text, await tenant_logo_data_url(db, employee.tenant_id))).write_pdf()
    return pdf, unknown
