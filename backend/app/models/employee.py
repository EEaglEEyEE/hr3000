from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.hr_user import HrRole


class Employee(Base):
    __tablename__ = "employees"
    # employee_number/nfc_uid/login_email sind nur innerhalb eines Tenants
    # eindeutig, nicht global – siehe app/middleware/tenant.py.
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_number", name="uq_employees_tenant_number"),
        UniqueConstraint("tenant_id", "nfc_uid", name="uq_employees_tenant_nfc_uid"),
        UniqueConstraint("tenant_id", "login_email", name="uq_employees_tenant_login_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalisiert direkt auf der Zeile (zusätzlich zu location_id ableitbar)
    # – nötig für die (tenant_id, ...)-Unique-Constraints oben und weil Employee
    # auf praktisch jedem Request gefiltert wird, siehe Plan zur Mandantenfähigkeit.
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    # Grundlage für die Supervisor-Rollenbeschränkung, siehe
    # app/services/team_scope_service.py. Nullable, da nicht jeder
    # Mitarbeiter zwingend einem Team zugeordnet sein muss.
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    employee_number: Mapped[str] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Rein informativ (wirkt NICHT auf `active` zurück) – siehe app/api/employees.py.
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Nur wirksam, wenn zusätzlich AppSettings.show_birthdays_in_calendar an
    # ist (siehe app/api/timesheets.py get_timesheet) – erlaubt es, den
    # Geburtstag einzelner Mitarbeiter trotz global aktiviertem Kalender-
    # Marker zu verbergen. Default True, da "deaktivierbar" (nicht "optional
    # aktivierbar") die im Konzept beschriebene Semantik ist.
    show_birthday_in_calendar: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optionale zusätzliche Bestätigung beim Stempeln, siehe Konzept Abschnitt 6
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # NFC/RFID-Kartenkennung (Web-NFC serialNumber) als Alternative zum PIN beim
    # Stempeln am Tablet, siehe app/api/punches.py create_punch. Kein Geheimnis
    # (jeder NFC-Leser kann sie von der Karte auslesen) – daher unverschlüsselt.
    nfc_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Login (E-Mail/Passwort). hr_role=None -> reiner Self-Service (nur eigene
    # Daten, read-only). hr_role gesetzt -> voller HR-Webapp-Zugriff mit
    # denselben Zugangsdaten, siehe app/api/deps.py get_current_hr_principal.
    login_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hr_role: Mapped[HrRole | None] = mapped_column(Enum(HrRole), nullable=True)
    # Berechtigung „Vergütung & Lohn-Export“ bei hr_role HR (Admins haben sie immer)
    hr_payroll_access: Mapped[bool] = mapped_column(Boolean, default=False)
    # Wenn gesetzt, fügt das System beim Ausstempeln (GO) automatisch die gesetzlich
    # vorgeschriebene Pause als BREAK_START/BREAK_END-Punches ein, sofern der
    # Mitarbeiter selbst keine Pause gestempelt hat. Siehe app/services/
    # timesheet_service.py maybe_auto_insert_break.
    # Standard: an – die gesetzliche Pause wird beim Ausstempeln automatisch gebucht, wenn keine gestempelt wurde.
    auto_break_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # DSGVO-Anonymisierung (siehe app/api/employees.py anonymize_employee):
    # gesetzt, sobald Name/Kontaktdaten überschrieben wurden. Punches/Absences
    # bleiben für die Aufbewahrungsfrist erhalten – nur die Stammdaten werden
    # unkenntlich gemacht. None = nicht anonymisiert.
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Gleitzeitkonto: bis einschließlich dieses Tages sind die overtime_balances-Zeilen aktuell.
    # NULL bzw. ein früheres Datum = ab dort neu berechnen (siehe timesheet_service.rebuild_balance).
    balance_through: Mapped[date | None] = mapped_column(Date, nullable=True)

    location: Mapped["Location"] = relationship(back_populates="employees")

    @property
    def has_pin(self) -> bool:
        return self.pin_hash is not None
