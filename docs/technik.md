# HR3000 – Technik

Für die Weiterentwicklung. Stand: 04.11.2026. Konventionen und Arbeitsweise stehen in der
`CLAUDE.md` im Repo-Root. Diese Seite erklärt, wie die Teile zusammenspielen.

## 1. Bausteine

| Teil | Technik | Ordner |
|---|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, MySQL 8.4 | `backend/` |
| HR-Webapp | React, TypeScript, Vite, TanStack Query, typisierter Client aus OpenAPI | `hr-webapp/` |
| Tablet-App | React-PWA (vite-plugin-pwa), Offline-Warteschlange, Web-NFC | `kiosk-app/` |
| Website | statisches HTML/CSS/JS, kein Build | `website/` |
| Reverse Proxy | Caddy 2 (TLS automatisch) | `Caddyfile` |
| Betrieb | Docker Compose, Skripte | `docker-compose.yml`, `scripts/` |

Der Ordner `stamper_3000/` (Flutter-Client) ist ein früherer Ansatz und nicht im Einsatz.

## 2. Weg einer Anfrage

```
Browser/Tablet ──HTTPS──> Caddy ──┬── /api/*  ──> backend:8000 (Präfix /api entfernt)
                                  ├── sonst   ──> hr-webapp:80 bzw. kiosk-app:80
                                  └── hr3000.de selbst ──> website/ (statisch) + /api/public/*
```

- **Mandant aus dem Host** (`backend/app/middleware/tenant.py`):
  - Unter der Plattform-Domain (`TENANT_BASE_DOMAIN=hr3000.de`) ist der Mandant das Label vor
    der Domain: `firma.hr3000.de` und `kiosk.firma.hr3000.de` → `firma`.
  - Für feste Hosts (`HR_HOSTS`/`KIOSK_HOSTS`) gilt das erste Label: `lassner.kiosk.hr.lassners.de`
    → `lassner`.
  - `SUPER_ADMIN_HOSTNAME` hat keinen Mandanten.
  - Ohne Mandanten-Kontext laufen nur `/health`, `/internal/tls-allowed` und `/public/*`.
  - Welche Namen gültig sind, steht an einer einzigen Stelle: `services/platform_domain.py`.
- **Zertifikate:**
  - Feste Hosts bekommen ihr Zertifikat beim Start.
  - Für die Plattform-Domain gibt es einen Sammel-Block `https://` mit On-Demand-TLS: Caddy
    fragt vor jedem neuen Zertifikat `GET /internal/tls-allowed?domain=…` (`api/tls.py`).
  - Hosts, die mit `kiosk.` beginnen, gehen an die Tablet-App.
  - Hosts unter der Plattform-Domain nie zusätzlich fest eintragen, sonst holt Caddy dafür kein
    Zertifikat.
- **Website-Schnittstellen** (`api/public.py`):
  - Firmensuche (`/public/tenant-lookup`), Adress-Prüfung (`/public/subdomain-available`) und
    Registrierung (`/public/signup`), mit Limits je IP.
  - Sie werden nicht ins Zugriffsprotokoll geschrieben (`main.SkipPublicAccessLog`).
- **Neue Firmen** entstehen immer über `services/tenant_provisioning.provision_tenant`, egal ob
  durch den Super-Admin oder per Registrierung, und zwar in einer Transaktion: Mandant,
  Einstellungen, Pausenstaffel, Erst-Admin.

## 3. Fachliche Kernstücke

- **Tagesberechnung:** `services/timesheet_service.py`
  - `calculate_day` berechnet Soll und Ist; `_pair_punches` macht aus den Stempelungen Paare.
  - „Jetzt“ kommt aus `_utcnow()`, in Tests über das Fixture `at_time`.
  - Ein offenes Kommen gilt nach der maximalen Schichtlänge als vergessenes Gehen.
- **Gleitzeitkonto:**
  - `daily_summaries` ist nur ein Cache; `Employee.balance_through` markiert, bis wann er
    aktuell ist.
  - Schreibende Stellen rufen `invalidate_balance` bzw. `invalidate_tenant_balances`, lesende
    `rebuild_balance`.
- **„Zu klären“:** `GET /timesheet/open-days`.
  - Zuerst rechnet es veraltete Tage nach (`_refresh_stale_day_cache`).
  - Sonderfälle sind `DayFlag`s, je Mandant abschaltbar (`disabled_day_flags`).
  - Arbeitstage ganz ohne Stempelung: Schalter `AppSettings.report_days_without_punches`.
    Ausgewertet über `missing_punch_reported` (Monatsbericht, Lohn-Export) und beim Füllen des
    Tages-Caches in `rebuild_balance` (Zu klären, Übersicht Monatsabschluss).
- **Monatssoll:** Arbeitszeitmodell mit `monthly_hours` → Vorlage mit
  `TargetPeriod.MONTHLY`; `shift_planning_service._resolve_target_minutes` verteilt es auf die
  Arbeitstage des Kalendermonats (Rest auf die ersten Tage, Summe exakt).
  - „Erledigt“ ist ein `DayReview` und ändert die Berechnung nicht.
- **Abwesenheiten:** Kategorien (`AbsenceType`), halbe Tage (`Absence.half_day`), Stunden
  (`Absence.duration_minutes`), Urlaubskonto in `services/leave_service.py`.
- **Monatsabschluss:** gesperrte Monate; mitarbeiterbezogene Schreibvorgänge mit Datum rufen
  `ensure_period_open` bzw. `ensure_range_open`.
- **Tarife:** `TenantPlan` (FREE, PAID, UNLIMITED), Grenze `free_employee_limit` = 5,
  `services/plan_service.py`, sonst 402 `PLAN_LIMIT_REACHED`.
- **Tablet:** Einstellungen holt sich die App alle 30 s über `GET /device/config`, z. B.
  Bildschirmzeiten mit Zeitzone des Standorts (`kiosk-app/src/screenHours.ts`).
  Stempelungen tragen einen Idempotency-Key, damit die Offline-Warteschlange nichts doppelt
  bucht.

- **Konten:**
  - Passwort selbst ändern: `POST /auth/change-password`. Andere Sitzungen enden über den
    Passwort-Fingerabdruck `pwv` im Token.
  - Einmal-Links für „Passwort vergessen“ und „E-Mail bestätigen“: `services/account_tokens.py`.
    Gespeichert wird nur der SHA-256, ein Link gilt einmal, und ein neuer Link macht ältere
    ungültig.
  - Diese Links gibt es nur mit Mailversand (`email_service.resolve_smtp_config`: Mailserver
    der Firma, sonst der Plattform).
- **Kündigung und Löschung:** `services/tenant_lifecycle.py`.
  - Der Löschplan wird generisch aus `Base.metadata` gebildet: Tabellen mit `tenant_id` direkt,
    alle übrigen über ihren Fremdschlüssel; abhängige Zeilen zuerst.
  - Der Test `test_every_table_is_covered` schlägt an, wenn eine neue Tabelle keinen Firmenbezug
    hat. `test_purge_removes_everything_of_one_company_and_nothing_else` prüft die Löschung mit
    zwei befüllten Firmen.

## 4. Sicherheit

- **Eingaben:** Pydantic-Validierung an jedem Endpoint. Fehler kommen einheitlich als
  `{"detail": …, "code": …}`.
- **Rechte:** Rollen werden im Backend geprüft; das Frontend blendet nur aus. Mandantentrennung
  in jeder Abfrage, Vergütung nur für Admins.
- **Zugangsdaten:**
  - Passwörter und PINs als bcrypt-Hash (höchstens 72 Byte).
  - Anmeldeversuche begrenzt.
  - JWT mit kurzer Laufzeit plus Refresh-Token.
- **Verschlüsselung:** Dokumente und SMTP-Passwörter per Fernet (`ENCRYPTION_KEY`). Sicherungen
  extern mit restic.
- **Secrets:** nur in `.env` auf dem Server, nie im Code.
- **HTTP-Header:** CSP nur `'self'`, HSTS, kein Einbetten in fremde Seiten (Caddyfile, Snippet
  `security_headers`).

## 5. Tests

- **Backend:** `pytest` mit SQLite im Speicher, parallel über `pytest-xdist`.

  ```bash
  cd backend && ~/.build-caches/hr3000_backend_venv/bin/python -m pytest -q -n auto
  ```

- **HR-Webapp und Tablet-App:** Vitest mit Testing Library (`npm test`). Die API wird über
  `mockApi()` ersetzt, Logins über `loginAs()`.
- Alle Tests laufen im Docker-Build; ein roter Test stoppt den Rollout.
- Neue Funktionen bekommen immer Tests für Sonderfälle.

## 6. Lokal entwickeln

- **Backend** (Python 3.12+): Virtualenv anlegen, `pip install -r backend/requirements.lock`.
  Testdaten in SQLite mit `backend/scripts/seed_local_dev.py` (Aufruf im Docstring), dann
  `DEBUG=true uvicorn app.main:app --port 8000` aus `backend/`. Mit `DEBUG=true` gilt ohne
  Subdomain die Testfirma `musterfirma`.
- **HR-Webapp / Tablet-App:** `npm ci` und `npm run dev` im jeweiligen Ordner. Der Vite-Proxy
  leitet `/api` an `localhost:8000` weiter.
- **Website:** statisch, z. B. `python3 -m http.server -d website 5182`.
- Nach Backend-Schemaänderungen: `cd hr-webapp && npm run generate:api`.
- Tipp: Virtualenv und `node_modules` nicht in Cloud-synchronisierten Ordnern anlegen; manche
  Sync-Clients zerstören Symlinks, dann laufen Tests scheinbar grün, obwohl nichts ausgeführt
  wurde.
