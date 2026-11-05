# HR3000 – Änderungen

Neueste zuerst. Bei jeder Änderung hier einen Eintrag ergänzen (Datum, was sich für Nutzer oder
Betrieb ändert). Einzelheiten stehen in der Git-Historie.

## 04.11.2026

- **Monatsstunden im Arbeitszeitmodell:** Neue Art „Monatsstunden (fest)“: jeden Monat dasselbe
  Soll (z. B. 108,5 Std.), egal ob der Monat 20 oder 23 Arbeitstage hat.
- **Arbeitstage ohne Stempelung abschaltbar:** Unter „Einstellungen“ → „Mitarbeiter & Regeln“ lässt sich
  „Arbeitstage ganz ohne Stempelung“ abschalten. Dann erscheinen unter „Zu klären“ nur noch
  unvollständig gestempelte Tage, und im Monatsbericht steht kein „Stempelung fehlt“.
- Der Lohn-Export zählt Tage ohne Tagessoll (flexibles Modell, kein Modell) nicht mehr als
  offen.
- **Kontakt:** Öffentliche Adresse ist jetzt support@hr3000.de (Impressum, Datenschutz, Website,
  README).
- **Kündigen und Löschen:**
  - Admins kündigen unter „Einstellungen“ → „Allgemein“ → „Konto kündigen“ zum Monatsende.
  - Danach bleiben 30 Tage zum Exportieren, dann werden alle Daten der Firma automatisch
    gelöscht.
  - Bis dahin lässt sich die Kündigung zurücknehmen; ein Hinweis in der HR-Ansicht nennt den
    Löschtermin.
  - Der Super-Admin kann im Namen einer Firma kündigen oder sie sofort endgültig löschen.
- **Passwort ändern** für alle: Seitenleiste, „Mein Bereich“ und Super-Admin.
- **Passwort vergessen** per Link aus der E-Mail, sobald ein Mailversand eingerichtet ist.
- **E-Mail-Bestätigung bei der Registrierung,** sobald der Mailversand der Plattform steht.
  Unbestätigte Registrierungen verfallen nach 7 Tagen.
- In „Mein Bereich“ erscheint der Reiter „Schichtplanung“ nur noch, wenn die Firma
  Schichtplanung nutzt. Das Audit-Log beschreibt jetzt richtig, was es protokolliert.
- **Open Source:** Der Quellcode ist öffentlich unter https://github.com/EEaglEEyEE/hr3000 (Lizenz AGPL-3.0), verlinkt auf der Website. Mit README und Anleitung zum Selbstbetrieb.
- **Doku öffentlich** unter `hr3000.de/doku`: Handbücher und Änderungen, verlinkt in Kopf und Fuß der Website.
- **Selbstregistrierung** unter `hr3000.de/registrieren`:
  - Firmen legen sich selbst an (Tarif „Kostenlos“), mit Live-Prüfung der Wunsch-Adresse.
  - Pflicht-Häkchen „nur Unternehmen“ und Zustimmung zu Nutzungsbedingungen und AV-Vertrag;
    Zeitpunkt und Fassung der Zustimmung werden gespeichert.
  - Schutz durch Limits je IP und Tag sowie ein Honeypot-Feld.
  - In der Mandantenliste des Super-Admins steht „Selbst registriert am …“.
- **Rechtstexte:** Nutzungsbedingungen (`/agb`) und Vertrag zur Auftragsverarbeitung (`/avv`)
  als Entwurf; die Datenschutzerklärung beschreibt jetzt auch die Registrierung.
- **Website `hr3000.de`:** Startseite, `/login` mit Firmensuche und Weiterleitung, Impressum,
  Datenschutz. Ohne Cookies, Tracking und externe Dienste.
- **Plattform-Domain:**
  - Jede Firma ist automatisch unter `firma.hr3000.de` erreichbar, die Tablet-App unter
    `kiosk.firma.hr3000.de`.
  - Zertifikate werden beim ersten Aufruf geholt, nach Freigabe durch das Backend.
  - Der QR-Code zum Einrichten eines Tablets nennt die neue Adresse.
  - Die alten `…hr.lassners.de`-Adressen laufen weiter.
- **Super-Admin** jetzt unter `admin.hr3000.de`, mit Werkzeug „Passwort vergessen“ auf dem Server.
- **Tarife:** bis 5 aktive Mitarbeiter kostenlos; ab 6 aktiven Mitarbeitern kostet jeder 1 € im
  Monat (6 Mitarbeiter = 6 €). Bestehende Firmen sind „Unbegrenzt“.
- **Bildschirmzeiten am Tablet:** Der Bildschirm bleibt nur im eingestellten Zeitfenster an
  (Firma oder je Tablet, über Mitternacht möglich).
- **Betrieb:**
  - verschlüsselte Kopie der Sicherungen auf der Hetzner Storage Box (restic, täglich 03:45)
  - Container-Protokolle sind größenbegrenzt
  - Rollout per `scripts/rollout.sh` mit Migrationstest auf einer Datenbank-Kopie

## 29.10.2026

- Neue Abwesenheits-Kategorien: Arbeitszeit, Feiertag, Kind krank. Die Kategorie lässt sich
  nachträglich ändern; bestehende Einträge werden neu berechnet.

## 26.10.2026

- Abwesenheiten auf die Stunde genau (z. B. 3 Std. Homeoffice); Pausen im Monatsbericht.
- Datenbank-Passwort in Backup- und Deploy-Skripten nicht mehr in der Prozessliste.

## 23.10.2026

- Halbe Urlaubstage, auch zwei verschiedene Hälften an einem Tag.
- „Erledigt“ unter „Zu klären“; erledigte Fälle verschwinden zuverlässig.
- Vergessenes „Gehen“ wird nach der maximalen Schichtlänge erkannt.
- Kernarbeitszeit, Gleitzeit-Rahmen und Pünktlichkeitsprüfung, je Firma und Mitarbeiter
  einstellbar.

## 21.10.2026

- Dienstgang-Stempelungen (standardmäßig aus) und Stempeln im Web-Login (Homeoffice).
- Heutiger Tag in Kalender und Anwesenheit hervorgehoben.
- Urlaubsanträge der Mitarbeiter abschaltbar.

## 15.–19.10.2026

- Arbeitszeitmodell „nach Aufwand“ für Aushilfen.
- Einklappbare Seitenleiste und Handy-Ansicht.
- Bezeichnung „Teamleader“; PIN legt der Mitarbeiter beim ersten Stempeln selbst fest.

## 12.–13.10.2026

- **Mandantenfähigkeit:** Super-Admin, Schichtplanung, Audit-Log, Benachrichtigungen,
  DSGVO-Export, Teamkalender.
- **Tablet-App** als PWA: Offline-Warteschlange, PIN, NFC und RFID-Leser, Kopplung per
  QR-Code bzw. Kurzcode, Hell/Dunkel, eigene Chips registrieren.
- **Personalakte:** Verträge, Vergütung (nur Admin), verschlüsselte Dokumente.
- **Abrechnung:** Monatsabschluss mit PDF und Bestätigung durch den Mitarbeiter, Zuschläge,
  Auswertungen, Lohn-Export (CSV).
- **Weiteres:**
  - Checklisten für On- und Offboarding
  - eigene Abwesenheitsarten und Urlaubsübertrag
  - Korrekturanträge
  - Startseite mit Salden
  - vollständiges Gleitzeitkonto mit Korrekturbuchungen
  - Nachtschichten über Mitternacht
  - Teilzeit je Wochentag

## 10.08.2026

- Erste Fassung: Stempeln am Kiosk, Gleitzeitsaldo mit Pausenabzug nach ArbZG, Abwesenheiten,
  „Zu klären“, HR-Webapp mit Mitarbeitern, Standorten, Tablets und Arbeitszeitmodellen.
