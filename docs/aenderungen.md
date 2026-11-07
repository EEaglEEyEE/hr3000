# HR3000 – Änderungen

Neueste zuerst. Bei jeder Änderung hier einen Eintrag ergänzen (Datum, was sich für Nutzer oder
Betrieb ändert). Einzelheiten stehen in der Git-Historie.

## 07.11.2026

- **Betrieb:** Stempelungen eines Mitarbeiters werden über einen zusätzlichen Datenbank-Index
  schneller gefunden, und das Firmenlogo wird nur noch geladen, wo es angezeigt wird (Anmeldeseite,
  Tablet, Monatsbericht) – nicht mehr bei jedem Abruf der Einstellungen. Für Nutzer ändert sich
  nichts.

## 06.11.2026

- **Tablets bleiben bei Störungen gekoppelt:** Konnte sich ein Tablet beim Start nicht anmelden
  (Server nicht erreichbar oder Anmeldung abgelehnt), löschte es bisher seine Kopplung und musste
  neu eingerichtet werden. Jetzt zeigt es einen Hinweis und versucht es jede Minute erneut. Auch
  Stempelungen in der Offline-Warteschlange werden bei solchen Störungen nicht mehr als Fehler
  markiert, sondern später erneut gesendet.
- **Server-Auslastung für den Plattform-Betreiber:** Im Super-Admin gibt es die Seite „Server“ mit
  CPU, Arbeitsspeicher, Datenträger und Last – aktuell und als Verlauf über 24 Stunden, 7 oder 30
  Tage. Für Firmen ändert sich nichts.
- **Betrieb:** Nach dem Einrichten der Testumgebung gingen am 06.11.2026 mittags Anfragen teilweise
  an die Testumgebung statt an die Produktion – Anmeldungen schlugen zeitweise fehl, Listen waren
  leer, Stempelungen am Tablet konnten mit einer Fehlermeldung abgelehnt werden. Es sind keine Daten
  verloren gegangen. Behoben: Die Dienste der Testumgebung haben eigene Namen.
- **Betrieb:** `scripts/rollout.sh` kann bis zu einem bestimmten Stand ausrollen
  (`rollout.sh <commit>`), ohne Angabe wie bisher den neuesten.
- **Betrieb:** Sicherheitsupdates der Backend-Bibliotheken Pillow 13.0.0, brotli 1.2.1 und
  certifi 2026.10.18 (von `pip-audit` gemeldet; Pillow nutzt die PDF-Erzeugung).

## 05.11.2026

- **Einheitliche Begriffe:** „Tablet“ statt „Kiosk“ (z. B. „Tablet-Admin-PIN“, Quelle einer
  Stempelung), „Chip“ statt „NFC-Karte“/„RFID“ („Chip-UID“ am Mitarbeiter) und „Teamleiter/in“
  statt „Teamleader“ bzw. „Vorgesetzte/r“. Spalten und Werte der Exporte bleiben unverändert.

- **Dialog „Neuer Mitarbeiter“ aufgeräumt:** oben nur die Grunddaten; das Arbeitszeitmodell wird
  ausdrücklich gewählt – „Standard aus den Einstellungen“, „Stunden je Wochentag“, „Nach Aufwand“
  oder „Kein Arbeitszeitmodell“. Bisher bekam ein neuer Mitarbeiter immer das Standardmodell, auch
  wenn alle Stundenfelder leer waren (eine Aushilfe oder ein reines HR-Konto hatte dann ein Soll und
  täglich „Stempelung fehlt“). Weitere Angaben sowie Login, PIN und Chip sind beim Anlegen
  eingeklappt.

- **Mitarbeiterseite mit sechs statt neun Reitern:** „Arbeitszeit“ enthält das Arbeitszeitmodell und
  (mit Schichtplanung) darunter die Schichtplanung des Mitarbeiters; „Personalakte“ fasst „Vertrag &
  Vergütung“, „Dokumente“ und „Checklisten“ zusammen.

- **Anmeldung am Tablet als eine Auswahl:** Unter „Einstellungen“ → „Stempeln“ wird statt fünf
  Schaltern gewählt: „Kachel antippen“, „+ PIN“, „oder Chip“, „Chip oder Kachel + PIN“ oder „Nur
  Chip“, dazu – nur wo sinnvoll – Chip selbst registrieren und PIN selbst festlegen. Die bisherigen
  Einstellungen gelten unverändert weiter. Neu: „PIN beim ersten Mal selbst festlegen“ lässt sich
  auch ohne PIN-Pflicht einstellen, wenn Mitarbeiter ihren Chip selbst registrieren (dafür brauchen
  sie einen PIN) – bisher war der Schalter dann gesperrt, wirkte aber trotzdem.

- **„Zu klären“ ist der Posteingang:** Reiter „Tage“, „Korrekturanträge“, „Urlaubsanträge“ und
  „Monatsgrenzen“, jeweils mit der Anzahl. Der eigene Menüpunkt „Urlaubsanträge“ entfällt; offene
  Anträge zählen jetzt in der roten Zahl an „Zu klären“ mit. Die Kachel „Urlaubsanträge“ auf der
  Startseite und alte Links führen zum Reiter.

- **Einstellungen nach Themen, Menü kürzer:** Das Menü hat nur noch das Tagesgeschäft und „Planung &
  Abrechnung“ (höchstens 10 Punkte). Standorte, Teams, Feiertage, Tablets, Pausenregeln,
  Schichtvorlagen, Zuschläge, Lohnarten und das Audit-Log stehen jetzt unter „Einstellungen“, links
  nach Themen geordnet: Unternehmen, Arbeitszeit & Pausen, Abwesenheiten & Urlaub, Stempeln &
  Tablets, Prüfungen, Abrechnung, Konto. Alle Urlaubswerte stehen zusammen unter „Urlaub &
  Anträge“. Alte Links und Lesezeichen führen an die neue Stelle. Fehler beim Speichern eines
  Schalters (z. B. wegen eines abgeschlossenen Monats) werden jetzt angezeigt.
- **Rechte einheitlich:** Menü, Seiten und Backend vergeben dieselben Rechte. HR sieht jetzt auch
  Teams, Schichtvorlagen, Schichtplan-Kalender und das Audit-Log – erlaubt war das schon vorher, nur
  das Menü zeigte es nicht. Wer eine Seite ohne Berechtigung direkt aufruft, bekommt einen Hinweis.

- **Urlaubsanspruch dauerhaft im Vertrag:** Im Reiter „Vertrag“ hat jeder Vertragsabschnitt jetzt
  „Jahresurlaub (Tage, 5-Tage-Woche)“ (leer = „Standard-Jahresurlaub“). Der Anspruch eines Jahres wird
  daraus berechnet – anteilig für Teilzeit und, mit der neuen Einstellung „Teilurlaub bei Eintritt oder
  Austritt im Jahr berechnen“, auch für Ein- und Austritt im Jahr (gesetzlicher Mindesturlaub bleibt,
  wenn er voll zusteht). Bruchteile werden nie abgerundet. Wer den Anspruch eines Jahres ändert,
  schreibt ihn für dieses Jahr fest („fest eingetragen“), „Wieder berechnen“ hebt das auf.
  **Bestehende Firmen:** Alle schon angelegten Jahreswerte bleiben unverändert fest eingetragen, die
  Teilurlaub-Einstellung ist aus. Neu berechnet werden nur Jahre ohne Eintrag (z. B. 2027), wie bisher
  mit Teilzeit-Anteil.
- **Monatsabschluss einfacher:** Bestätigt der Mitarbeiter den Monatsnachweis, ist der Monat
  abgeschlossen – der eigene Zustand „Vom Mitarbeiter bestätigt“ und der zweite Klick „Abschließen“
  entfallen (bestehende bestätigte Monate wurden abgeschlossen). Mitarbeiter ohne Login werden beim
  Vorlegen direkt abgeschlossen. „Vorlegen“ fragt nach, wenn für den Monat noch Abwesenheits- oder
  Korrekturanträge offen sind.
- „Gleitzeitkonten führen ab“, „Schichtplanung aktivieren“ und „Maximale Schichtlänge“ rechneten auch
  vorgelegte und abgeschlossene Monate neu (die Salden passten dann nicht mehr zum Nachweis). Jetzt
  lassen sie sich nur ändern, solange kein solcher Monat betroffen ist.
- **Eine Regel für „offen“:** „Zu klären“, die Übersicht beim Monatsabschluss, der Monatsbericht und
  der Lohn-Export (Spalte „Offene/fehlerhafte Tage“, DATEV-Hinweis) zählen jetzt dieselben Tage –
  bisher gab es vier leicht unterschiedliche Zählweisen; der Lohn-Export zählt damit auch Sonderfälle
  und berücksichtigt „Erledigt“. **„Erledigt“ verfällt**, sobald sich der Tag danach ändert (z. B. eine
  Stempelung nachgetragen wird); der Tag erscheint dann wieder unter „Zu klären“.
- **Zuschlagsregeln bearbeiten und mit Verlauf:** Regeln lassen sich jetzt in der Oberfläche
  bearbeiten. Ein geänderter Satz, ein anderes Zeitfenster oder andere Wochentage gelten ab „Änderung
  gilt ab“ – zurückliegende Monate (Lohn-Export, Lohnkosten, Monatsbericht) rechnen mit der
  bisherigen Fassung. „Frühere Fassungen anzeigen“ zeigt den Verlauf.
- **Berechtigung „Vergütung & Lohn-Export“:** Unter „HR-Berechtigung“ lässt sich HR-Personen
  freigeben, was bisher nur Admins durften: Vergütung und Zulagen, Lohnkosten, Beträge im
  Lohn-Export, DATEV und die Seite „Lohnarten“ (Admins haben es immer, Standard für HR aus). Den
  Lohn-Export ohne Beträge sieht HR jetzt auch im Menü – erlaubt war er schon vorher. Berater- und
  Mandantennummer für DATEV lassen sich damit auch ohne Zugriff auf die Einstellungen pflegen.
- **Lohn-Export zeigt den Stand des Monats:** wie viele der gewählten Mitarbeiter abgeschlossen,
  vorgelegt oder noch offen sind, und ob bzw. wann der Monat schon exportiert wurde (CSV; DATEV für
  Admins). So geht nichts versehentlich zweimal oder zu früh ans Lohnbüro.
- **Neue Seite „Lohnarten“** (Abrechnung, nur Admins): alle Lohnarten für die DATEV-Datei an einer
  Stelle – je Zeitart (gearbeitete Stunden, Urlaub, Krankheit, Kind krank, Sonderurlaub, Feiertag,
  Arbeitszeit-Angaben, ausgezahlte Überstunden), je Zuschlag und je Zulagen-/Einmalzahlungsart.
  Bisher standen sie auf der Seite „Lohn-Export“ und bei jeder einzelnen Zulage.
- **Zulagen aus einem Katalog:** Zulagen und Einmalzahlungen haben jetzt eine Art (z. B.
  „Fahrtkosten“) mit Lohnart; derselbe Name ergibt immer dieselbe Spalte im Lohn-Export – Tippfehler
  führten bisher zu getrennten Spalten. Bestehende Zulagen wurden ihrer Art zugeordnet (hatte ein
  Name verschiedene Lohnarten, gibt es je Lohnart eine Art mit der Lohnart in Klammern).
- **DATEV nach Zeitarten:** Mit hinterlegter Lohnart überträgt die DATEV-Datei für Stundenlöhner
  auch Urlaubs-, Krankheits- und Feiertagsstunden sowie ausgezahlte Überstunden. Ohne Lohnart bleibt
  es beim Hinweis in der Vorschau. Arbeitszeit-Angaben (z. B. Homeoffice) zählen ohne eigene
  Lohnart als gearbeitete Stunden.
- **Abrechnung mit einem Rechenweg:** Lohn-Export (CSV), DATEV-Datei und Lohnkosten rechnen jetzt
  gemeinsam und jeden Tag nur einmal – vorher lief die Berechnung je Export mehrfach. Neu im
  Lohn-Export: „Ausgezahlte Überstunden (Std.)“ (Auszahlungen aus den Korrekturbuchungen des
  Gleitzeitkontos). Die Lohnkosten-Auswertung zählt Zulagen und Einmalzahlungen mit (Spalte
  „Zulagen“).
- **Arbeitszeitmodell und Schicht an einer Stelle:** Der Reiter „Arbeitszeitmodell“ fasst jetzt
  alles zur regelmäßigen Arbeitszeit zusammen: Modell in zwei Fragen („Feste Arbeitstage“ /
  „Flexibel ohne feste Tage“ / „Nach Aufwand (Aushilfe)“, bei festen Tagen „Wochenstunden“ – auf
  Wunsch je Wochentag unterschiedlich – oder „Monatsstunden (fest)“), optional eine
  „Schichtvorlage (Uhrzeiten)“, die Pause und neu die „Kernarbeitszeit / Pünktlichkeit“ – alles
  mit „Gültig ab“ und Verlauf. Die Standard-Schicht im Reiter „Schichtplanung“ entfällt dafür; dort
  steht die regelmäßige Arbeitszeit jetzt lesend über den Ausnahmen. Die Kernzeit im
  Mitarbeiter-Dialog entfällt (sie wurde in alle Fassungen übernommen). Bestehende
  Standard-Schichten rechnen unverändert weiter, bis sie im Arbeitszeitmodell gespeichert werden.
- Schichtvorlagen haben nur noch ein „Soll pro Schichttag“; Wochen- und Monatsstunden gehören ins
  Arbeitszeitmodell (ältere Vorlagen behalten ihren Zieltyp).
- Bei „Flexibel“ und „Nach Aufwand“ liefert eine geplante Schicht nur noch die Uhrzeiten. Bisher
  brachte sie ein Tagessoll mit – ein ausgefallener Einsatz einer Aushilfe stand dann als Minus da.
- **Urlaubs- und Krankheitstage ohne Arbeitszeitmodell** zählen jetzt Mo–Fr statt Mo–Sa, passend
  zum Urlaubsanspruch (5-Tage-Woche). Wer regelmäßig samstags arbeitet, bekommt ein Modell mit
  Samstag. Die Krankheitsquote zählt Aushilfen „nach Aufwand“ nicht mehr mit 7 Soll-Tagen pro Woche.
- Kalender und Schichtplan-PDF zeigen an Tagen ohne Schichtvorlage das Tagessoll (z. B. „7,5 h“)
  bzw. „flexibel“ statt eines internen Vorlagennamens.

- **Pausen an einer Stelle:** Die Seite „Pausenregeln“ bündelt jetzt alles: gesetzliche
  Pausenstaffel (strengere Werte des Betriebs als weitere Zeilen – die bisherigen „festen Minuten“
  sind darin aufgegangen), „Gesetzliche Mindestpause nicht unterschreiten“, feste Pausenzeiten und
  neue Rechenoptionen mit „gilt ab“: „Pausen genau nach § 4 ArbZG rechnen“ und „Pausenabzug
  höchstens bis zur Schwelle“. Der Standard für „Pausen automatisch stempeln“ steht jetzt hier.
  Feste Minuten im Arbeitszeitmodell und in Schichtvorlagen gelten auf Wunsch erst ab einer
  Arbeitszeit („ab … Std.“). Für bestehende Firmen ändert sich an den Stunden nichts.
- **Pünktlichkeit:** Statt „Pünktlichkeit prüfen“ plus Häkchen gibt es unter „Kernarbeitszeit &
  Gleitzeit“ nur noch die Häkchen „Zu spät gekommen“, „Zu früh gegangen“ und „Außerhalb der
  Gleitzeit-Rahmenzeit“. Nach einer Änderung dieser Regeln gibt es Hinweise erst ab dem Tag der
  Änderung – vorher erschien die ganze Vergangenheit unter „Zu klären“.

- **DATEV LODAS:** Die Datei überträgt nur noch gearbeitete (gestempelte) Stunden. Gutschriften
  für Urlaub, Krankheit und Feiertage nennt die „Vorschau“ je Mitarbeiter, damit sie nicht doppelt
  bezahlt werden. Mitarbeiter ohne hinterlegte Vergütung erscheinen als Hinweis.
- Mitarbeiter lassen sich jetzt auch mit „Monatsstunden (fest)“ und eigener Pause anlegen.
- **Feiertage bei mehreren Bundesländern:** Liegt ein Standort in einem anderen Bundesland als dem
  „Standard-Bundesland“, gelten die gesetzlichen Feiertage des Standard-Bundeslands künftig nur noch
  für die passenden Standorte. Feiertage werden gleich beim Anlegen eines Standorts bzw. beim Ändern
  seines Bundeslands importiert, nicht erst beim nächsten Update. Eigene Feiertage der Firma bleiben
  für alle Standorte.
- Teamleader sehen den Reiter „Schichtplanung“ nur noch lesend und in „Zu klären“ keinen
  „Korrigieren“-Hinweis mehr (beides dürfen nur HR und Admin). Texte zu „Schichtplanung aktivieren“,
  „Pausen automatisch stempeln“ und „Pausen-Buttons anzeigen“ beschreiben jetzt genau, was passiert.
- Strengere Prüfung der Eingaben: Stempel-PIN 4–8 Ziffern, Zeitzone des Standorts aus der Liste
  (ein Tippfehler legte die Berechnung lahm), „Standard-Jahresurlaub“ 0–365 Tage, „Gleitzeitkonten
  führen ab“ zwischen 2000 und 2100, Auszahlungen nur als Minus, Notiz bei der Genehmigung höchstens
  300 Zeichen.
- Der Gleitzeit-Rahmen meldet an Tagen mit Schicht (Uhrzeiten aus der Schichtplanung) nichts mehr –
  bisher bekam jede Spät- oder Nachtschicht „außerhalb Gleitzeit-Rahmen“.
- **Automatische Pause beim Ausstempeln:** Die automatisch gebuchte Pause wurde ohne Firmenzuordnung
  gespeichert, was die Datenbank ablehnt – das Ausstempeln konnte dann mit einem Fehler enden (die
  Stempelung selbst war gespeichert, die Pause wurde trotzdem abgezogen). Behoben.
- **Automatische Pausen bei Korrekturen:** Wird eine Stempelung nachgetragen, geändert oder gelöscht,
  setzt HR3000 die automatisch gebuchten Pausen des Tages neu. Bisher blieben sie z. B. hinter einem
  vorverlegten „Gehen“ stehen (Tag „widersprüchlich“) oder kamen zu einer nachgetragenen Pause dazu.
- **Vier-Augen-Prinzip (Schalter):** Unter „Einstellungen“ → „Abwesenheiten & Urlaub“ lässt sich
  einschalten, dass niemand eigene Anträge genehmigt – auch nicht HR, Admin oder Teamleader.
  Standard aus.
- **Krankheit im Urlaub:** Ganztägige Abwesenheiten dürfen sich nicht mehr überschneiden. Wird
  jemand im Urlaub krank, gibt HR3000 nach Rückfrage die Urlaubstage zurück und kürzt bzw. teilt
  den Urlaub (§ 9 BUrlG). Bisher wurde der Urlaub trotzdem verbraucht.
- **Lohn-Export bei „Flexibel ohne feste Tage“:** Das Soll stand bisher immer auf 0. Jetzt zählt
  das Wochensoll anteilig wie im Monatsbericht.
- **Lohn-Export:** schlägt den Vormonat vor und nimmt auch Mitarbeiter mit, die im Monat
  ausgetreten und schon inaktiv sind (gilt auch für DATEV).
- Ob ein Antrag genehmigt werden muss, steht nur noch je Abwesenheitsart („Genehmigung nötig“). Ein
  alter, unsichtbarer Firmenschalter dafür wurde in die Art „Urlaub“ übernommen; am Verhalten
  ändert sich nichts.
- „Werte aus dem Altsystem übernehmen“ lehnt einen Gleitzeit-Übertrag ab, wenn das Konto schon vor
  dem Stichtag rechnet. Sonst würden diese Tage doppelt zählen.

- **Feste Pausen:** Unter „Pausenregeln“ gibt es neben der gesetzlichen Staffel jetzt „Feste
  Pausen des Betriebs“: eine feste Uhrzeit (z. B. 12:00–12:30, abgezogen, soweit anwesend) oder
  feste Minuten ab einer Arbeitszeit, jeweils auch ohne Pausenstempelung. Je Mitarbeiter geht
  das im Arbeitszeitmodell unter „Pause“. Die gesetzliche Pause gilt immer mindestens.
- **Umstieg von einem Altsystem:** Unter „Mitarbeiter“ → „CSV-Import“ lassen sich jetzt auch
  Werte bestehender Mitarbeiter übernehmen: Gleitzeit-Übertrag, Urlaubsanspruch, Übertrag aus
  dem Vorjahr und Arbeitszeitmodell zu einem Stichtag, mit Vorschau vor dem Übernehmen.
- **Einstellungen übertragen:** Unter „Einstellungen“ → „Allgemein“ lassen sich Einstellungen,
  Pausenregeln, Abwesenheitsarten und Zuschläge als Datei exportieren und in einer anderen Firma
  importieren, mit Vorschau.
- **DATEV LODAS:** Auf der Seite „Lohn-Export“ erzeugen Admins eine Importdatei für DATEV LODAS
  mit Ist-Stunden (Stundenlohn), Zuschlagsstunden sowie Zulagen und Einmalzahlungen, jeweils nach
  Lohnart. Mit Vorschau und Hinweisen. Urlaub und Krankheit überträgt die Datei nicht.
- **Zulagen und Einmalzahlungen:** Unter „Vertrag & Vergütung“ (nur Admins) lassen sich
  wiederkehrende Zulagen (je Monat oder je Stunde auf den Stundenlohn) und Einmalzahlungen wie
  Weihnachtsgeld hinterlegen. Sie erscheinen im Lohn-Export, wenn ein Admin ihn zieht.
- **Kernzeit je Wochentag:** Unter „Einstellungen“ → „Kernarbeitszeit & Gleitzeit“ und bei der
  eigenen Kernzeit eines Mitarbeiters lässt sich die Kernzeit je Wochentag festlegen, z. B.
  freitags kürzer oder an einzelnen Tagen gar keine.
- Die „Pausenregelung“ in Schichtvorlagen (feste Pausenzeit bzw. Mindestpause) wird jetzt auch
  wirklich abgezogen. Bisher war sie nur gespeichert.

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
