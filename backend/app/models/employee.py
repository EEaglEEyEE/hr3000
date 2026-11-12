from datetime import date, datetime

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.account import HrRole

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.cost_center import EmployeeCostCenter


class Employee(Base):
    __tablename__ = "employees"
    # employee_number/nfc_uid sind nur innerhalb eines Tenants
    # eindeutig, nicht global – siehe app/middleware/tenant.py.
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_number", name="uq_employees_tenant_number"),
        UniqueConstraint("tenant_id", "nfc_uid", name="uq_employees_tenant_nfc_uid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalisiert direkt auf der Zeile (zusätzlich zu location_id ableitbar)
    # – nötig für die (tenant_id, ...)-Unique-Constraints oben und weil Employee
    # auf praktisch jedem Request gefiltert wird, siehe Plan zur Mandantenfähigkeit.
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    # Abteilung (hierarchisch, app/models/department.py) – einzige Organisationsstruktur; ihre Leitungen
    # sind die Führungskräfte. supervisor_id ist die abweichende Führungskraft (Ausnahme je Person).
    # Wirksame Führungskraft und Zuständigkeit: app/services/org_service.py, scope_service.py.
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
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
    # Überstundenkonto: bis einschließlich dieses Tages sind die overtime_balances-Zeilen aktuell.
    # NULL bzw. ein früheres Datum = ab dort neu berechnen (siehe timesheet_service.rebuild_balance).
    balance_through: Mapped[date | None] = mapped_column(Date, nullable=True)

    location: Mapped["Location"] = relationship(back_populates="employees")
    # Zugang zur Webapp (Konto mit E-Mail/Passwort und ggf. Rolle), siehe app/models/account.py
    account: Mapped["Account | None"] = relationship(back_populates="employee", lazy="selectin")
    # Aufteilung auf Kostenstellen (app/models/cost_center.py)
    cost_centers: Mapped[list["EmployeeCostCenter"]] = relationship(lazy="selectin", cascade="all, delete-orphan")

    def __init__(self, **kwargs) -> None:
        # Ohne Angabe gilt „kein Konto“ als geladen – sonst würde ein Zugriff auf employee.account bei
        # neu angelegten Mitarbeitern nachladen (im async-Kontext nicht erlaubt). Zuerst setzen, damit
        # login_email & Co. in kwargs das Konto danach anlegen können.
        self.account = kwargs.pop("account", None)
        self.cost_centers = kwargs.pop("cost_centers", [])
        super().__init__(**kwargs)

    @property
    def has_pin(self) -> bool:
        return self.pin_hash is not None

    # Status wie in der Personalakte üblich: ONBOARDING (Eintritt in der Zukunft), ACTIVE, LEAVE
    # (Auszeit: heute in Elternzeit/Pflegezeit, gesetzt über personal_data_service.mark_leave),
    # INACTIVE (deaktiviert oder Austritt vorbei).
    @property
    def employment_status(self) -> str:
        today = date.today()
        if not self.active or (self.termination_date is not None and self.termination_date < today):
            return "INACTIVE"
        if self.hire_date is not None and self.hire_date > today:
            return "ONBOARDING"
        if getattr(self, "_on_leave", False):
            return "LEAVE"
        return "ACTIVE"

    # --- Zugang dieses Mitarbeiters (liegt im verknüpften Konto) -------------------------------
    # Lesen liefert die Werte des Kontos (None ohne Konto); Schreiben legt das Konto bei Bedarf an.
    # Zugang entfernen = E-Mail und Passwort auf None (das Konto bleibt für den Verlauf).

    def _login_account(self) -> "Account":
        if self.account is None:
            from app.models.account import Account

            self.account = Account(tenant_id=self.tenant_id)
        return self.account

    @property
    def login_email(self) -> str | None:
        return self.account.email if self.account is not None else None

    @login_email.setter
    def login_email(self, value: str | None) -> None:
        if value is not None or self.account is not None:
            self._login_account().email = value

    @property
    def password_hash(self) -> str | None:
        return self.account.password_hash if self.account is not None else None

    @password_hash.setter
    def password_hash(self, value: str | None) -> None:
        if value is not None or self.account is not None:
            self._login_account().password_hash = value

    @property
    def hr_role(self) -> HrRole | None:
        return self.account.role if self.account is not None else None

    @hr_role.setter
    def hr_role(self, value: HrRole | None) -> None:
        if value is not None or self.account is not None:
            self._login_account().role = value

    @property
    def two_factor_enabled(self) -> bool:
        return self.account is not None and self.account.two_factor_enabled

    @property
    def hr_custom_role(self):
        """Eigene Rolle des Zugangs (nur bei Rolle HR), siehe app/models/role.py."""
        return self.account.custom_role if self.account is not None else None

    @property
    def hr_payroll_access(self) -> bool:
        return bool(self.account.payroll_access) if self.account is not None else False

    @hr_payroll_access.setter
    def hr_payroll_access(self, value: bool) -> None:
        if value or self.account is not None:
            self._login_account().payroll_access = bool(value)
