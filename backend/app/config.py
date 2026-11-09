from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+asyncmy://hr3000:hr3000@localhost:3306/hr3000"
    jwt_secret_key: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    jwt_device_token_expire_hours: int = 12

    # Mehrmandantenfähigkeit, siehe app/middleware/tenant.py.
    debug: bool = False
    super_admin_hostname: str = "admin.hrapp3000.localhost"
    # Nur wirksam, wenn debug=True: Fallback-Mandant, wenn weder eine echte
    # Subdomain noch der X-Tenant-Subdomain-Header vorliegt (z.B. localhost:8000
    # in der lokalen Entwicklung).
    dev_default_tenant_subdomain: str = "musterfirma"
    # Plattform-Domain (z.B. "hr3000.de"): jeder Mandant ist automatisch unter
    # <subdomain>.<domain> bzw. <subdomain>.kiosk.<domain> erreichbar (Caddyfile:
    # Wildcard + On-Demand-TLS, Freigabe über app/api/tls.py). Leer = nur die fest
    # eingetragenen Hosts (HR_HOSTS/KIOSK_HOSTS).
    tenant_base_domain: str | None = None
    # Testumgebung auf demselben Server (scripts/staging.sh): Hosts unter dieser Domain (z.B.
    # "test.hr3000.de" -> demo.test.hr3000.de, kiosk.demo.test.hr3000.de) leitet Caddy an die
    # Staging-Container weiter; über Zertifikate entscheidet das Staging-Backend (staging_tls_ask_url).
    # Nur in der Produktions-.env setzen, leer = keine Testumgebung.
    staging_base_domain: str | None = None
    staging_tls_ask_url: str = "http://staging-backend:8000/internal/tls-allowed"
    # Selbstregistrierung von Firmen auf der Website (hr3000.de/registrieren, api/public.py).
    # Wirkt nur mit gesetzter Plattform-Domain. Grenzen gegen Missbrauch (u.a. damit Bots nicht
    # das Let's-Encrypt-Kontingent der Domain verbrauchen): je IP und plattformweit pro Tag.
    self_signup_enabled: bool = True
    self_signup_per_ip_per_day: int = 3
    self_signup_per_day: int = 20

    # E-Mail-Versand für Benachrichtigungen (Urlaubsanträge, "Zu klären"-Digest),
    # siehe app/services/email_service.py – rein optional: ohne smtp_host wird
    # nur geloggt statt versendet, kein Feature setzt SMTP voraus.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    # Schlüssel (Fernet, urlsafe-base64, 32 Byte) für in der DB gespeicherte
    # Geheimnisse wie das SMTP-Passwort eines Mandanten, siehe
    # app/services/secret_box.py. Leer = Ableitung aus jwt_secret_key (dann
    # macht ein Wechsel des JWT-Secrets die gespeicherten Passwörter unlesbar).
    encryption_key: str | None = None

    # Ablage der Personalakten-Dokumente (verschlüsselte Dateien), siehe
    # app/services/document_service.py. Im Container ein eigenes Volume.
    documents_dir: str = "data/documents"
    max_document_bytes: int = 15 * 1024 * 1024
    # Gesamtkontingent je Mandant.
    max_tenant_document_bytes: int = 2 * 1024 * 1024 * 1024

    # Kostenloser Tarif: so viele aktive Mitarbeiter je Mandant (darüber nur mit Abo).
    free_employee_limit: int = 5

    # Server-Auslastung für den Super-Admin (services/server_metrics.py): Messabstand in Sekunden
    # (0 = aus), Aufbewahrung in Tagen und der Pfad, dessen Datenträger gemessen wird. Gemessen wird
    # der ganze Server (/proc ist im Container nicht abgeschottet).
    server_metrics_interval_seconds: int = 60
    # Erinnerungen prüfen (Sekunden, 0 = aus); verschickt wird höchstens einmal pro Tag und Mandant
    reminders_interval_seconds: int = 3600
    # Webhook-Zustellung alle n Sekunden (0 = aus)
    webhook_interval_seconds: int = 15
    server_metrics_retention_days: int = 30
    server_metrics_disk_path: str = "/"


settings = Settings()
