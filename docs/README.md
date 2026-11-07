# HR3000 – Dokumentation

HR3000 ist eine Web-App für Zeiterfassung (Tablet am Eingang oder Browser), Gleitzeit,
Abwesenheiten, Schichtplanung und Personalakte. Mehrere Firmen können sie nutzen; Anbieter
ist die Lassners IT Factory. Website: https://hr3000.de · Quellcode (AGPL-3.0): https://github.com/EEaglEEyEE/hr3000

| Dokument | Für wen |
|---|---|
| [Handbuch für Admins, HR und Teamleader](handbuch-admin.md) | Firmen, die HR3000 nutzen: Einrichtung, Tagesgeschäft, Abrechnung, Einstellungen |
| [Handbuch für Mitarbeiter](handbuch-mitarbeiter.md) | Stempeln am Tablet, „Mein Bereich“ |
| [Betrieb der Plattform](betrieb.md) (intern, nicht im öffentlichen Repo) | Betreiber: Super-Admin, Domain/DNS, Rollout, Sicherungen, Wiederherstellung, Störungen |
| [Technik](technik.md) | Entwicklung: Aufbau, Mandanten und Zertifikate, Kernlogik, Sicherheit, Tests |
| [Änderungen](aenderungen.md) | Was sich wann geändert hat |

**Rechtstexte** liegen als Website-Seiten unter `website/`: Impressum, Datenschutz,
Nutzungsbedingungen (`agb`) und AV-Vertrag (`avv`).

**Älter, nur zur Einordnung (intern, nicht im öffentlichen Repo):**
- `konzept.md`: ursprüngliches Fachkonzept, in Teilen überholt.
- `feature-kiosk-bildschirmzeiten.md`: Auftrag für die Bildschirmzeiten, umgesetzt am
  04.11.2026.

**Vorschläge (intern, noch nicht entschieden):**
- `konzept-konten.md`: ein Kontomodell statt HR-Konten und Mitarbeiter-Logins (07.11.2026).

**Öffentlich unter https://hr3000.de/doku**: die beiden Handbücher und die Änderungen, erzeugt
mit `python3 scripts/build_website_docs.py` (nach jeder Änderung ausführen und `website/doku/`
committen). `betrieb.md` und `technik.md` bleiben intern.

**Pflege:** Die Doku wird mit jeder Änderung aktualisiert:
- Neue oder geänderte Funktionen kommen ins passende Handbuch und nach `aenderungen.md`.
- Betriebsänderungen kommen nach `betrieb.md`.
- Technische Änderungen kommen nach `technik.md`.
