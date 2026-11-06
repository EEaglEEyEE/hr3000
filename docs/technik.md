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
  - „Jetzt“ kommt aus `_utcnow()`, in Tests über das Fixture `at_time`. Auch „heute“ (`today_in`,
    `utc_today` für mandantenweite Listen) leitet sich davon ab – nicht `date.today()` verwenden.
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
  - „Erledigt“ ist ein `DayReview` und ändert die Berechnung nicht. Es speichert einen
    Fingerabdruck des Tages (`day_fingerprint`: Status|Soll|Ist|Hinweise, Migration 0096); weicht
    der aktuelle Stand ab, gilt der Tag wieder als offen (`review_valid`; ältere Einträge ohne
    Fingerabdruck gelten weiter).
  - Eine Regel „Tag offen“ (`timesheet_service.needs_review`) für `GET /timesheet/open-days`, die
    Abschluss-Übersicht (`GET /period-closures`), den Monatsbericht (`build_month_report`) und den
    Rechenkern der Abrechnung (`PayrollDay.open`).
- **Zulagen/Einmalzahlungen:** `PayComponent` (`ALLOWANCE` mit `PER_MONTH`/`PER_HOUR` und
  Gültigkeit, `ONE_TIME` mit `pay_date`) mit Art `PayComponentType` (Katalog je Mandant: `kind`,
  `name`, `wage_type`, `active`; Name/Lohnart stehen nur dort, Migration 0092). Anlegen mit
  `type_id` oder `type_name` (früher `name`, als Alias weiter angenommen: Art finden bzw. anlegen).
  Endpunkte unter
  `/employees/{id}/pay-components` (nur Admin, Audit wie Vergütung ohne Beträge, Sperre über
  `ensure_*_open`). Beträge je Zeitraum in `services/pay_component_service.py` (Monatsbetrag
  anteilig nach Kalendertagen, Stundenbetrag × Ist im Gültigkeitsteil, Cent kaufmännisch
  gerundet). Lohn-Export: Spalten nur bei `actor.is_admin_level`.
- **Rechenkern Abrechnung:** `services/payroll_export_service.payroll_period` rechnet je Mitarbeiter
  jeden Tag einmal (`calculate_day`, gestempelte Zeit, `DayCalculation.credit_parts` = Gutschrift je
  Zeitart, Feiertag als `PUBLIC_HOLIDAY`) und sammelt Auszahlungen (`AdjustmentKind.PAYOUT`).
  `PayrollPeriod.summary(start, end)` liefert Summen auch für Teilzeiträume (Stundenlohn-Abschnitte,
  Gültigkeit von Zulagen) ohne neue Rechnung. Genutzt von CSV-Lohn-Export, DATEV-Export,
  `pay_component_amounts` und der Lohnkosten-Auswertung (inkl. Zulagen).
- **Migration (Werte aus dem Altsystem):** `POST /migration/employee-values` (multipart: Datei,
  `cutover`, `apply`), `services/migration_import_service.py` parst ohne DB, `api/migration.py`
  prüft Sichtbarkeit, Sperren und doppelten `OPENING_BALANCE` zum Stichtag und übernimmt
  `BalanceAdjustment`, `LeaveEntitlement` (Jahr des Stichtags) und Arbeitszeitmodell
  (`set_work_time_model`).
- **Einstellungen übertragen:** `GET /migration/settings-export` / `POST
  /migration/settings-import?apply=` (nur Admin, `TenantSettingsFile` Version 1). Übertragbare
  Felder: `PORTABLE_SETTINGS` in `api/migration.py`; Import über `update_settings`,
  `create_break_rule` (gültig ab heute), `create_absence_type`, `create_surcharge_rule`. Die
  Vorschau schreibt nichts.
- **Testumgebung:** `docker-compose.staging.yml` (Projekt `hr3000-staging`, ohne Caddy, Container
  im Prod-Netz unter `staging-*` erreichbar – die Dienstnamen selbst müssen mit `staging-` beginnen,
  weil Compose jeden Dienstnamen in jedem Netz als DNS-Namen anmeldet; geprüft in
  `tests/test_staging_compose.py` und `staging.sh check_names`), `scripts/staging.sh`, Demo-Daten aus
  `app/tools/seed_demo.py` (nur mit `DEMO_SEED_ALLOWED=1`). Prod-Caddy leitet Hosts unter
  `STAGING_BASE_DOMAIN` weiter; `api/tls.py` fragt für sie das Staging-Backend
  (`staging_tls_ask_url`).
- **Berechtigung „Vergütung & Lohn-Export“:** `Actor.has_payroll_access` (Admin immer; volle HR mit
  `HrUser.payroll_access` bzw. `Employee.hr_payroll_access`, Migration 0094), Dependency
  `get_current_payroll_principal` für Vergütung, Zulagen, Lohnkosten, DATEV (inkl. `GET/PUT
  /payroll-export/datev/settings`), Lohnarten und `PUT /surcharge-rules/{id}/wage-type`; Beträge im
  CSV-Export und DATEV-Einträge im Export-Status ebenso. Vergabe über `PATCH
  /employees/{id}/hr-role` (`payroll_access`, nur bei HR; andere Rollen setzen es zurück). Token-Claim
  `payroll` nur für die Anzeige (`AuthContext.canPayroll`).
- **Zuschlagsregeln mit Verlauf:** `SurchargeRule.valid_from/valid_to/family_id` (Migration 0095;
  `family` = erste Fassung). `PATCH /surcharge-rules/{id}` mit `valid_from` und geändertem Satz,
  Zeitfenster oder Wochentagen legt eine neue Fassung an (bisherige endet am Vortag,
  `ensure_tenant_open_from`); ohne `valid_from` direkt in der Fassung. `compute_surcharges` wertet je
  Tag nur gültige Fassungen aus; `merge_by_family` fasst für die CSV-Spalten zusammen (Name der
  neuesten Fassung), Monatsbericht, Lohnkosten und DATEV rechnen je Fassung (Satz/Lohnart).
  `GET /surcharge-rules?include_history=true` liefert auch abgelaufene Fassungen.
- **Export-Protokoll:** `PayrollExportLog` (`payroll_export_logs`, Migration 0093: Art CSV/DATEV,
  Zeitraum, Anzahl, wer, wann – ohne Inhalte), geschrieben beim CSV-Export und beim DATEV-Download.
  `GET /payroll-export/status?month=` liefert Abschluss-Stand der Gewählten (`PeriodClosure`:
  abgeschlossen / vorgelegt+bestätigt / offen) und die Exporte des Monats (DATEV nur für Admins).
- **Lohnarten:** `WageTypeMapping` (`wage_type_mappings`: `item` = `WageTypeItem` WORKED,
  VACATION, SICK, CHILD_SICK, SPECIAL_LEAVE, PUBLIC_HOLIDAY, WORK_TIME, OVERTIME_PAYOUT),
  `services/wage_type_service.py`, `api/wage_types.py` (`/wage-types`, `/pay-component-types`, nur
  Admin, Audit `SETTINGS_CHANGED`). Zuschläge behalten ihre Lohnart an `SurchargeRule.wage_type`.
  „Einstellungen übertragen“ nimmt `wage_types` und `pay_component_types` mit; alte Dateien mit
  `settings.datev_hours_wage_type` werden zu WORKED.
- **DATEV LODAS:** `services/datev_export_service.py` baut aus dem Rechenkern die Bewegungsdaten
  (`u_lod_bwd_buchung_standard`, Bearbeitungsschlüssel 01 = Stunden, 02 = Betrag): je Zeitart in
  Stundenlohn-Abschnitten (`worked_minutes`, `credit_minutes` je Kategorie mit Lohnart; WORK_TIME
  ohne eigene Lohnart zählt als WORKED), Auszahlungen (OVERTIME_PAYOUT), Zuschlagsstunden und
  Zulagen; ohne Lohnart als Hinweis. Endpunkte `GET /payroll-export/datev` (Datei, cp1252, CRLF)
  und `/payroll-export/datev/preview` (JSON), nur Admin; Berater-/Mandantennummer in
  `AppSettings.datev_*`. Grundlage: LODAS-Schnittstellenhandbuch.
- **Arbeitszeitmodell und Schicht:** Eine Fassung (`EmployeeDefaultShift`, effektiv-datiert, je
  Mitarbeiter höchstens eine zur Zeit) trägt den Vertrag selbst: Arbeitstage (`weekdays_mask`,
  `day_minutes`), Art (`flexible`, `on_demand` + `monthly_cap_minutes`), Soll
  (`target_minutes` + `target_period`), eigene Pause (`break_mode`, `fixed_break_*`,
  `min_break_minutes` ab `min_break_after_minutes`) und Kernzeit (`core_time_*`). Eine
  Schichtvorlage (`shift_template_id`, optional) liefert nur die Uhrzeiten – Soll und Pause nur,
  solange die Fassung keine eigenen hat (ältere Standard-Schichten, Antwortfeld
  `target_from_template`). Seit Migration 0091 gibt es keine versteckten Modellvorlagen
  (`is_work_time_model`) und keine Kernzeit am Mitarbeiter mehr.
  - Auflösung je Tag: `shift_planning_service.resolve_effective_shift` → `EffectiveDayPlan`
    (Tagesausnahme `ShiftPlanEntry` nur mit Schichtplanung, sonst Fassung, sonst „ohne Plan“);
    `plan.version` ist immer die Fassung des Tages. Bei flexibel/nach Aufwand liefert eine
    Tagesausnahme nur Uhrzeiten (kein Tagessoll).
  - Schreiben: `PUT /employees/{id}/work-time-model` (neue Fassung ab Stichtag, ersetzt spätere)
    und `PUT …/versions/{id}` (nachträglich); Kernzeit ohne Angabe = wie die bisherige Fassung.
  - Beim Anlegen (`POST /employees`): `work_time_model` gilt ab Eintritt; ohne Angabe nimmt das
    Backend das Standardmodell der Firma (`default_day_minutes`), außer bei `no_work_time_model`
    (bewusst ohne Modell; beides zugleich = 422).
    `POST/PATCH/DELETE /employees/{id}/default-shifts` (Soll aus der Vorlage) sind veraltet
    (`deprecated`), die Oberfläche nutzt sie nicht mehr.
  - Soll-/Pausenänderung einer Schichtvorlage ab Stichtag (`_version_for_target_change`) teilt nur
    Fassungen, die Soll bzw. Pause von der Vorlage erben; Fassungen mit eigenem Soll und eigener
    Pause wechseln nur auf die neue Vorlagen-Fassung.
- **Kernzeit je Wochentag:** `core_time_days` (Text, 7 Einträge „HH:MM-HH:MM“ oder leer, Format
  und Schema in `schemas/core_time.py`) an `AppSettings` und an der Fassung (nur bei `CUSTOM`).
  NULL = jeden Tag `core_time_start/-end`. Ausgewertet in `timesheet_service._punctuality_flags`
  (Modus der Fassung: `TENANT`/leer, `CUSTOM`, `NONE`); der Gleitzeit-Rahmen wird je Tag geprüft
  (`CORE_TIME_OUTSIDE_FRAME`).
- **Monatssoll:** Fassung mit `TargetPeriod.MONTHLY`; `shift_planning_service._plan_from_version`
  verteilt es auf die Arbeitstage des Kalendermonats (Rest auf die ersten Tage, Summe exakt).
- **Urlaubs-/Fehltage ohne feste Tage:** `leave_service.is_leave_day` zählt ohne Arbeitszeitmodell,
  bei flexibel und nach Aufwand Mo–Fr (wie der Anspruch, 5-Tage-Woche). Die Krankheitsquote
  (`reports._planned_workdays`) zählt ohne Modell Mo–Fr und bei „nach Aufwand“ keine Soll-Tage.
- **Pausen:** `timesheet_service.break_policy` liefert je Tag eine `BreakPolicy`.
  - `BreakRule.kind`: `LEGAL` = Pausenstaffel (früheres `FIXED_MINUTES` ist darin aufgegangen,
    Migration 0090; die API nimmt es noch an und speichert `LEGAL`) und `FIXED_WINDOW` (feste
    Uhrzeit, Ortszeit, nicht über Mitternacht). Alle effektiv-datiert.
  - Eigene Pause des Tages (`_own_break`): die der Fassung, sonst die der Schichtvorlage (an
    geplanten Schichttagen immer die der Schicht). `break_mode=FIXED` + `fixed_break_*` ersetzt die
    Pausenzeiten des Mandanten; `min_break_minutes` ab `min_break_after_minutes` ist eine weitere
    Staffelstufe. Pausenänderungen an Schichtvorlagen versionieren wie Soll-Änderungen.
  - `BreakPolicy.shortfall` ist der einzige Rechenweg für den Fehlbetrag (Tagesberechnung,
    `maybe_auto_insert_break`, `surcharge_service.work_intervals`). `precise`
    (`AppSettings.break_precise_from`): Schwelle nach Arbeitszeit ohne Pausen, gestempelte Pausen
    erst ab 15 Min.; `capped` (`break_capped_from`): Abzug höchstens bis zur Schwelle. Beide ab Datum.
  - `AppSettings.legal_break_minimum`: Prüfung beim Ändern der Staffel (`staffel_covers_law`), kein
    Rechenschritt.
  - Feste Pausenzeiten gelten am Arbeitstag und am Folgetag (Nachtschicht).
  - `refresh_auto_breaks` setzt automatische Pausen nach manuellen Änderungen neu.
- **Pünktlichkeit:** kein eigener Schalter mehr – `LATE_ARRIVAL`/`EARLY_LEAVE`/`OUTSIDE_FLEX_FRAME`
  über `disabled_day_flags` (neue Mandanten: zu spät/zu früh aus). `AppSettings.punctuality_from`
  (bei jeder Regeländerung = heute) begrenzt die Hinweise auf Tage ab der Änderung.
- **Abwesenheiten:** Kategorien (`AbsenceType`), halbe Tage (`Absence.half_day`), Stunden
  (`Absence.duration_minutes`), Urlaubskonto in `services/leave_service.py`.
- **Urlaubsanspruch:** `EmploymentContract.annual_vacation_days` (leer = `default_annual_vacation_days`).
  `leave_service.computed_entitlement` rechnet tagesgenau: Basis je Tag aus dem Vertragsabschnitt ×
  Teilzeitfaktor (`prorate_part_time_vacation`) ÷ Tage im Jahr, mit `prorate_partial_year_vacation` nur
  über die Beschäftigungstage plus gesetzlicher Untergrenze (`full_statutory_leave`, Wartezeit
  `waiting_period_end`); `round_vacation` rundet nie ab; `None` bei „nach Aufwand“.
  `LeaveEntitlement.entitled_manual` = Jahreswert fest (Migration 0098 setzt bestehende Zeilen fest,
  `prorate_partial_year_vacation` für bestehende Mandanten aus); sonst gilt der berechnete Wert, die
  Zeile hält dann nur Übertrag und den Stand beim Anlegen.
- **Monatsabschluss:** gesperrte Monate; mitarbeiterbezogene Schreibvorgänge mit Datum rufen
  `ensure_period_open` bzw. `ensure_range_open`. Zustände `SUBMITTED` → `CLOSED` (bzw. `DISPUTED` =
  wieder offen); die Bestätigung des Mitarbeiters schließt ab (früher `CONFIRMED`, Migration 0097),
  ohne Login schließt das Vorlegen direkt ab. `_submit` prüft offene Anträge des Monats
  (`OPEN_REQUESTS_PRESENT`, übergehbar mit `ignore_open_requests`). Mandantenweite Einstellungen, die
  rückwirkend rechnen (`balance_start_date`, `shift_planning_enabled`, `max_shift_span_hours`), prüfen
  `ensure_tenant_open_from` ab dem frühesten betroffenen Tag.
- **Tarife:** `TenantPlan` (FREE, PAID, UNLIMITED), Grenze `free_employee_limit` = 5,
  `services/plan_service.py`, sonst 402 `PLAN_LIMIT_REACHED`.
- **Tablet:** Einstellungen holt sich die App alle 30 s über `GET /device/config`, z. B.
  Bildschirmzeiten mit Zeitzone des Standorts (`kiosk-app/src/screenHours.ts`).
  Stempelungen tragen einen Idempotency-Key, damit die Offline-Warteschlange nichts doppelt
  bucht. „Anmeldung am Tablet“ ist in der Webapp nur eine Auswahl (`KioskLoginCard`,
  `kioskLoginMode`) über die weiter bestehenden Felder `require_pin_for_punch`,
  `kiosk_rfid_enabled` und `rfid_required` (+ `kiosk_card_self_registration`,
  `kiosk_pin_self_setup`); Backend und Tablets sind unverändert.

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
- **Server-Auslastung (Super-Admin):** `services/server_metrics.py` liest CPU (`/proc/stat`, Differenz
  zweier Messungen), Last (`/proc/loadavg`), Speicher (`MemTotal − MemAvailable`) und Datenträger
  (`shutil.disk_usage`). `run_sampler` läuft als Task aus `main.lifespan` (ein Uvicorn-Prozess, also
  ein Sammler) und speichert je `SERVER_METRICS_INTERVAL_SECONDS` eine Zeile in
  `server_metric_samples` (Migration 0099, ohne Mandantenbezug, daher in
  `tenant_lifecycle.PLATFORM_TABLES` von der Firmenlöschung ausgenommen); stündlich werden Zeilen älter als
  `SERVER_METRICS_RETENTION_DAYS` gelöscht. `GET /platform/server-metrics?range=24h|7d|30d` (nur
  `get_current_super_admin_principal`) mittelt in Python je Abschnitt (5 Min./1 Std./6 Std.) und
  misst den aktuellen Stand live (CPU über 0,5 s). Ohne `/proc` (macOS) gibt es keine Werte.
  Oberfläche: `ServerMetricsPage` mit `components/platform/MetricChart.tsx` (SVG, eine Kennzahl je
  Grafik, Fadenkreuz-Tooltip auch per Pfeiltasten, Tabellenansicht; Linienfarbe `--series-1` in
  `index.css`, hell/dunkel gegen die Kartenfläche geprüft).
- **Rechte:** Rollen werden im Backend geprüft; das Frontend blendet nur aus. Mandantentrennung
  in jeder Abfrage, Vergütung nur mit „Vergütung & Lohn-Export“.
  - Webapp: eine Rechte-Tabelle in `hr-webapp/src/lib/access.ts` (`all`/`hr`/`payroll`/`admin` =
    `get_current_hr_principal`/`…_full_hr_…`/`…_payroll_…`/`…_admin_principal`). Menü
    (`AppLayout`), Seitenschutz (`RequireAccess` in `App.tsx`) und die Bereiche der Einstellungen
    (`SettingsPage`, je Bereich eine Stufe) lesen alle daraus. Neue Seite oder neuer Bereich: Stufe
    passend zur Backend-Abhängigkeit eintragen.
  - Einstellungen: `/einstellungen/:seite`; frühere eigene Seiten (Standorte, Teams, Feiertage,
    Tablets, Pausenregeln, Schichtvorlagen, Zuschläge, Lohnarten, Audit-Log) sind Bereiche dort,
    die alten Pfade leiten um (`MOVED_TO_SETTINGS`), alte Reiter `?bereich=` ebenso.
  - „Zu klären“: `/zu-klaeren/:reiter` (`tage`, `korrekturen`, `urlaubsantraege`, `monatsgrenzen`);
    `/urlaubsantraege` leitet um. Die Zahl im Menü zählt offene Tage, überschrittene Monatsgrenzen,
    offene Abwesenheitsanträge und (Admin/HR) Korrekturanträge.
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
