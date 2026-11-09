"""Eigene Felder der Personalakte: Abschnitte und Felder je Firma, Werte je Mitarbeiter.

Felder mit `dated` führen einen Verlauf: jeder Wert hat ein „Gültig ab“ (valid_from), aktuell ist der
jüngste bis heute; künftige Werte sind erlaubt. Ohne `dated` gibt es je Mitarbeiter und Feld genau
einen Wert (valid_from leer).
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AttributeSection(Base):
    __tablename__ = "attribute_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100))
    # Mitarbeiter in „Mein Bereich“: NONE (nicht sichtbar), VIEW (sehen), EDIT (sehen und Änderung vorschlagen)
    employee_access: Mapped[str] = mapped_column(String(10), default="NONE", server_default="NONE")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class AttributeDefinition(Base):
    __tablename__ = "attribute_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    section_id: Mapped[int] = mapped_column(ForeignKey("attribute_sections.id"))
    label: Mapped[str] = mapped_column(String(100))
    # TEXT, NUMBER, DATE, SELECT, BOOLEAN, EMPLOYEE (eine Person der Firma)
    field_type: Mapped[str] = mapped_column(String(10))
    # Auswahlwerte (JSON-Liste) bei SELECT
    options: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mit Verlauf und „Gültig ab“
    dated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class AttributeValue(Base):
    __tablename__ = "attribute_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attribute_definitions.id", ondelete="CASCADE"))
    # Als Text gespeichert (Zahl mit Punkt, Datum ISO, Ja/Nein als true/false, Person als ID); leer = gelöscht
    value: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
