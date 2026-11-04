from datetime import datetime

from pydantic import BaseModel

from app.schemas.absence import AbsenceResponse
from app.schemas.document import DocumentResponse
from app.schemas.employee import EmployeeResponse
from app.schemas.employee_default_shift import EmployeeDefaultShiftResponse
from app.schemas.leave_entitlement import LeaveEntitlementResponse
from app.schemas.notification import NotificationResponse
from app.schemas.punch import PunchResponse
from app.schemas.shift_plan_entry import ShiftPlanEntryResponse


class EmployeeDataExportResponse(BaseModel):
    """DSGVO Art. 15 Auskunftsrecht: sämtliche über den Mitarbeiter
    gespeicherten personenbezogenen Daten, gebündelt in einer Antwort.
    Absichtlich keine Passwort-/PIN-Hashes (siehe EmployeeResponse) – ein
    Hash ist kein personenbezogenes Datum im Sinne der Auskunftspflicht,
    dessen Herausgabe wäre nur ein Sicherheitsrisiko."""

    exported_at: datetime
    employee: EmployeeResponse
    punches: list[PunchResponse]
    absences: list[AbsenceResponse]
    leave_entitlements: list[LeaveEntitlementResponse]
    default_shifts: list[EmployeeDefaultShiftResponse]
    shift_plan_entries: list[ShiftPlanEntryResponse]
    notifications: list[NotificationResponse]
    # Nur Metadaten der Personalakte (Titel, Kategorie, Datum) – die Dateien selbst
    # werden auf Anfrage separat ausgehändigt.
    documents: list[DocumentResponse]
