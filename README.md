# HR3000

Zeiterfassung, Urlaub und Schichtplanung für kleine und mittlere Betriebe – Stempeln am Tablet
im Eingang oder im Browser, Gleitzeitkonto, Abwesenheiten, Monatsabschluss und digitale
Personalakte. Mehrmandantenfähig.

- **Gehostet:** https://hr3000.de – bis 5 aktive Mitarbeiter kostenlos, danach 1 € je aktivem
  Mitarbeiter und Monat. Selbst registrieren unter https://hr3000.de/registrieren.
- **Doku:** https://hr3000.de/doku (Quelle in [`docs/`](docs/))
- **Lizenz:** [GNU AGPL-3.0](LICENSE)

## Funktionen

- Stempeln am Tablet (PWA, PIN, NFC/RFID-Chips, offline-fähig) und im Browser (Homeoffice)
- Arbeitszeitmodelle mit Historie: gleichmäßig, je Wochentag, flexibel, nach Aufwand
- Gleitzeitkonto, Kernzeit/Gleitzeit-Rahmen, automatische Pausen nach ArbZG oder eigenen Regeln
- Abwesenheiten (auch halbe Tage und Stunden), Urlaubskonto mit Übertrag, Genehmigungen, Teamkalender
- „Zu klären“: fehlende Stempelungen und Sonderfälle werden automatisch erkannt
- Schichtplanung mit Vorlagen und PDF
- Monatsabschluss mit Bestätigung durch Mitarbeiter, Zuschläge, Auswertungen, Lohn-Export (CSV)
- Personalakte mit verschlüsselten Dokumenten, Rollen (Admin, HR, Teamleader), Audit-Log
- DSGVO-Datenexport und Anonymisierung

## Aufbau

| Teil | Technik |
|---|---|
| `backend/` | Python, FastAPI, Pydantic, SQLAlchemy (async), Alembic, MySQL |
| `hr-webapp/` | React, TypeScript, Vite |
| `kiosk-app/` | React-PWA für Tablets |
| `website/` | statische Website (hr3000.de) |
| `Caddyfile`, `docker-compose.yml`, `scripts/` | Betrieb mit Docker Compose und Caddy (TLS automatisch) |

Mehr dazu: [`docs/technik.md`](docs/technik.md).

## Selbst betreiben

Auf einem Linux-Server mit Docker (als root):

```bash
git clone https://github.com/EEaglEEyEE/hr3000.git /opt/hr3000 && cd /opt/hr3000
bash scripts/deploy.sh   # 1. Lauf: legt .env mit zufälligen Secrets an
nano .env                # Domain, Super-Admin-E-Mail und Hosts eintragen
bash scripts/deploy.sh   # 2. Lauf: baut, testet und startet
```

- Mit den Platzhalter-Secrets aus `.env.example` startet das Backend bewusst nicht.
- Die Backend- und Frontend-Tests laufen beim Bauen; ein roter Test bricht den Build ab.
- Das Backend legt beim ersten Start die Datenbank an und gibt das Einmalpasswort des
  Super-Admins (`SUPER_ADMIN_EMAIL`) im Log aus: `docker compose logs backend`.
- Für den Betrieb auf einem eigenen Server liegen `scripts/bootstrap_server.sh`,
  `scripts/deploy.sh` (Ersteinrichtung) und `scripts/rollout.sh` (Updates mit Backup und
  Migrationstest) bei.

## Tests

```bash
cd backend && python -m pytest -q -n auto
cd hr-webapp && npm test
cd kiosk-app && npm test
```

## Sicherheit

Sicherheitslücken bitte nicht öffentlich melden, sondern per E-Mail an support@hr3000.de.

## Lizenz

Copyright © 2026 Johannes Lassner, Lassners IT Factory.

HR3000 ist freie Software: Du kannst sie unter den Bedingungen der GNU Affero General Public
License, Version 3, weitergeben und verändern. Wer eine veränderte Fassung als Netzwerkdienst
anbietet, muss deren Quellcode den Nutzern zugänglich machen (AGPL § 13). HR3000 wird ohne
jede Gewährleistung bereitgestellt; Einzelheiten in der [LICENSE](LICENSE).
