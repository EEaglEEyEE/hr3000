from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppSettings(Base):
    """Anwendungseinstellungen – genau eine Zeile pro Mandant, siehe
    app/services/settings_service.py get_or_create_settings."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True)
    require_pin_for_punch: Mapped[bool] = mapped_column(Boolean, default=False)
    # Siehe app/api/absences.py create_absence – ohne diese Einstellung wird
    # jede Absenz weiterhin direkt final (APPROVED) angelegt.
    vacation_approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # Bundesland-Kürzel (z.B. "BY"), siehe app/services/holiday_calendar.py –
    # Vorbelegung für den Feiertags-Import, falls dort kein Bundesland angegeben wird.
    default_bundesland: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Vorbelegung für LeaveEntitlement.entitled_days beim ersten Zugriff auf
    # einen neuen Mitarbeiter/Jahr, siehe app/services/leave_service.py
    # get_or_create_entitlement – 0 bedeutet "kein automatischer Standard",
    # entspricht dem bisherigen (impliziten) Verhalten.
    default_annual_vacation_days: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    # Blendet Geburtstage im Mitarbeiter-Kalender ein (siehe
    # app/api/timesheets.py get_timesheet, TimesheetDay.is_birthday) – pro
    # Mitarbeiter über Employee.show_birthday_in_calendar wieder abschaltbar.
    show_birthdays_in_calendar: Mapped[bool] = mapped_column(Boolean, default=False)
    # Wirft-Datum der letzten "Zu klären"-Digest-Benachrichtigung (siehe
    # app/services/notification_service.py notify_open_days_digest) – es gibt
    # keinen echten Cron in dieser Umgebung, daher wird der Digest beim
    # nächsten Aufruf von GET /timesheet/open-days mitgeschickt, aber
    # höchstens einmal pro Kalendertag und Mandant.
    open_days_digest_sent_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Schichtplanung (Schichtvorlagen, Schichtplan-Kalender, Tagesausnahmen) ist
    # optional – ohne sie gilt nur das einfache Arbeitszeitmodell (Arbeitstage +
    # Wochenstunden pro Mitarbeiter), siehe app/api/work_time_model.py. Neue
    # Mandanten starten ohne Schichtplanung, Bestandsmandanten behalten sie
    # (Migration 0045 setzt dort true).
    shift_planning_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Ab diesem Tag führt der Mandant Gleitzeitkonten (früher nichts zählen, Altsalden per
    # Korrekturbuchung "Übertrag"). NULL = ab der ersten Stempelung je Mitarbeiter.
    balance_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # --- Standardwerte für neue Mitarbeiter (individualisierbar je Mandant) ---
    default_auto_break: Mapped[bool] = mapped_column(Boolean, default=True)
    default_show_birthday: Mapped[bool] = mapped_column(Boolean, default=True)
    # Arbeitszeitmodell für neue Mitarbeiter: Soll-Minuten Mo..So, kommagetrennt (NULL = keins)
    default_day_minutes: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # --- Regeln ---
    prorate_part_time_vacation: Mapped[bool] = mapped_column(Boolean, default=True)
    # Resturlaub automatisch ins Folgejahr übertragen (sonst trägt HR den Übertrag ein).
    vacation_carry_over_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    # Höchstens so viele Tage übertragen (NULL = unbegrenzt).
    vacation_carry_over_max_days: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Übertragener Urlaub verfällt nach diesem Tag des Folgejahres ("MM-TT", z.B. "03-31"; NULL = kein Verfall).
    vacation_carry_over_expiry: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Sonderfälle, die NICHT unter "Zu klären" erscheinen sollen (kommagetrennte DayFlags)
    disabled_day_flags: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Wie lange nach dem "Kommen" ein "Gehen" am Folgetag noch zur Schicht gehört (Nachtschicht)
    max_shift_span_hours: Mapped[int] = mapped_column(Integer, default=16)
    # --- Kernarbeitszeit / Gleitzeit (alles optional, Standard aus) ---
    # Kernzeit, in der Mitarbeiter anwesend sein sollen (z.B. 09:00–15:00); NULL = keine Kernzeit.
    core_time_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    core_time_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Zu spät kommen / zu früh gehen (gegenüber Schicht bzw. Kernzeit) unter "Zu klären" melden
    punctuality_check: Mapped[bool] = mapped_column(Boolean, default=False)
    late_tolerance_minutes: Mapped[int] = mapped_column(Integer, default=5)
    # Gleitzeit-Rahmen (frühestes Kommen / spätestes Gehen); NULL = kein Rahmen
    flex_frame_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    flex_frame_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    # PIN zum Zurücksetzen eines Kiosk-Tablets (gehasht); ohne PIN ist kein Zurücksetzen möglich
    kiosk_admin_pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # RFID-Pflicht am Kiosk: Stempeln nur mit Chip/Karte (Aktion wählen, Chip vorhalten).
    rfid_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # --- Kiosk-Anzeige ---
    # RFID/NFC-Chips am Tablet nutzen (Terminalmodus + Mitarbeiter per Chip öffnen). Aus = nur Kacheln.
    kiosk_rfid_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Mitarbeiter mit PIN dürfen ihren Chip am Tablet selbst registrieren (PIN + Chip vorhalten).
    kiosk_card_self_registration: Mapped[bool] = mapped_column(Boolean, default=True)
    # Mitarbeiter ohne PIN legen ihn beim ersten Stempeln am Tablet selbst fest (bei PIN-Pflicht).
    kiosk_pin_self_setup: Mapped[bool] = mapped_column(Boolean, default=True)
    # Gleitzeitsaldo/Resturlaub am Gemeinschafts-Tablet zeigen (Datenschutz: abschaltbar).
    kiosk_show_balance: Mapped[bool] = mapped_column(Boolean, default=True)
    kiosk_show_vacation: Mapped[bool] = mapped_column(Boolean, default=True)
    # Pausen-Buttons am Tablet (aus = Pausen nur über automatische Pausenregelung)
    kiosk_break_buttons: Mapped[bool] = mapped_column(Boolean, default=True)
    # Dienstgang-Buttons (Start/Ende) am Tablet und im Portal
    kiosk_errand_buttons: Mapped[bool] = mapped_column(Boolean, default=False)
    # Mitarbeiter dürfen selbst Abwesenheiten/Urlaub beantragen (aus = nur HR/Teamleader tragen ein)
    absence_requests_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Mitarbeiter dürfen über den Web-Login (Startseite) selbst stempeln – Standard aus.
    portal_punching_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Begrüßungs-/Hinweistext über den Kacheln
    kiosk_greeting: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Sortierung der Kacheln: LAST_NAME | FIRST_NAME
    kiosk_sort: Mapped[str] = mapped_column(String(10), default="LAST_NAME")
    # Darstellung am Tablet: DARK | LIGHT
    kiosk_theme: Mapped[str] = mapped_column(String(5), default="DARK")
    # Bildschirm nur in diesem Zeitfenster wach halten (Standort-Zeitzone); beide NULL = immer an.
    # von > bis = über Mitternacht. Mögliche Erweiterung: Wochentage (bewusst noch nicht, YAGNI).
    kiosk_screen_on_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    kiosk_screen_on_until: Mapped[time | None] = mapped_column(Time, nullable=True)

    # Eigenes Firmenlogo (nur Anzeige in Web-App/Kiosk/Berichten, nicht als Favicon/App-Icon).
    logo_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logo_data: Mapped[str | None] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True)
    # Eigener SMTP-Server des Mandanten für Benachrichtigungs- und Zugangsdaten-
    # Mails (siehe app/services/email_service.py). Ohne smtp_host gilt der
    # Plattform-SMTP aus den Umgebungsvariablen. Das Passwort wird nur
    # verschlüsselt gespeichert und nie ausgegeben (smtp_password_set).
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # NONE | STARTTLS | SSL
    smtp_security: Mapped[str] = mapped_column(String(10), default="STARTTLS")
    # Mail-Benachrichtigungen (Urlaubsanträge, "Zu klären") zusätzlich zur Glocke.
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def smtp_password_set(self) -> bool:
        return bool(self.smtp_password_encrypted)

    @property
    def kiosk_admin_pin_set(self) -> bool:
        return bool(self.kiosk_admin_pin_hash)
