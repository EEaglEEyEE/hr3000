# HR3000 – Handbuch für Admins, HR und Teamleader

Stand: 04.11.2026. Für Mitarbeiter: [Handbuch für Mitarbeiter](handbuch-mitarbeiter.md).
Bezeichnungen in „…“ entsprechen genau der Oberfläche.

## 1. Anmelden und Rollen

- Adresse der Firma: `https://<firma>.hr3000.de`, oder über `https://hr3000.de/login` mit dem
  Firmenkürzel. Admins, HR und Mitarbeiter nutzen dieselbe Anmeldeseite („E-Mail“, „Passwort“).
- Neue Firma: selbst unter `https://hr3000.de/registrieren`. Wer registriert, wird Erst-Admin
  mit dem selbst gewählten Passwort. Ist der Mailversand der Plattform eingerichtet, kommt
  vorher eine Bestätigungsmail; erst nach dem Klick auf den Link klappt die Anmeldung.
  Unbestätigte Registrierungen werden nach 7 Tagen gelöscht.
- Rollen (beim Mitarbeiter unter „HR-Berechtigung“, nur durch Admins):

| Rolle | Darf |
|---|---|
| Admin | alles, auch „Einstellungen“, Vergütung („Vertrag & Vergütung“), „Lohn-Export“, „Zuschläge“, „Pausenregeln“, „Teams“, „Audit-Log“ |
| HR | Mitarbeiter, Abwesenheiten, „Zu klären“, „Monatsabschluss“, „Auswertungen“, „Feiertage“, „Standorte“, „Tablets“, „Checklisten“ – ohne Vergütung und Einstellungen |
| Teamleader | „Tagesgeschäft“ für die eigenen Teams |
| Keine (nur Mein Bereich) | nur die eigene Ansicht, siehe Mitarbeiter-Handbuch |

- **Passwörter:**
  - **Selbst ändern:** in der Seitenleiste „Passwort ändern“ (in „Mein Bereich“ oben). Danach
    enden alle anderen Sitzungen dieses Kontos.
  - **Vergessen:** auf der Anmeldeseite „Passwort vergessen?“. Es kommt ein Link per E-Mail,
    1 Stunde gültig. Den Link gibt es nur, wenn ein Mailversand eingerichtet ist: eigener
    Mailserver unter „Einstellungen“ → „Logo & E-Mail“ oder der Versand der Plattform.
    Sonst steht dort „Bitte wende dich an deine Personalabteilung“.
  - **Für andere:** HR erzeugt im Mitarbeiter-Dialog ein neues Einmalpasswort („Neues
    Passwort erzeugen …“). Es wird einmal angezeigt oder auf Wunsch per E-Mail verschickt.
  - **Erst-Admin:** Ohne Mailversand setzt der Plattform-Betreiber dessen Passwort zurück.

## 2. Erste Schritte nach der Registrierung

1. **„Standorte“** → „Neuer Standort“: Name, Zeitzone, Bundesland. Das Bundesland bestimmt
   die Feiertage.
2. **„Einstellungen“ → „Allgemein“:** „Gleitzeitkonten führen ab“, „Standard-Jahresurlaub“,
   „Standard-Bundesland“.
3. **„Mitarbeiter“** → „Neuer Mitarbeiter“ oder „CSV-Import“.
   - Umstieg von einem anderen System: auf derselben Seite unter „Werte aus dem Altsystem
     übernehmen“ eine zweite CSV hochladen (Pflichtspalte `personalnummer`). Optional sind
     `saldo_stunden` (Gleitzeit-Übertrag, auch negativ), `urlaubsanspruch_tage` und
     `uebertrag_vorjahr_tage` für das Jahr des Stichtags sowie das Arbeitszeitmodell ab Stichtag
     (`wochenstunden`, `arbeitstage`, `tagesstunden`, `monatsstunden`, `monatsgrenze`,
     `pause_minuten`). Leere Zellen ändern nichts.
   - „Stichtag“ wählen, „Vorschau“ prüfen, dann „Übernehmen“. Fehlerhafte Zeilen werden
     übersprungen und angezeigt. Ein zweiter Gleitzeit-Übertrag zum selben Stichtag wird
     abgelehnt, ebenso Änderungen in abgeschlossenen Monaten.
   - Wer mitten im Jahr umsteigt: als `urlaubsanspruch_tage` den restlichen Anspruch für den Rest
     des Jahres eintragen, da bereits genommener Urlaub nicht im neuen System steht.
4. **„Tablets“** → „Neues Tablet“, dann „QR-Code“ und mit dem Tablet scannen. Die
   Tablet-Adresse ist `https://kiosk.<firma>.hr3000.de`.
5. Optional: „Pausenregeln“ prüfen (die gesetzliche Staffel nach § 4 ArbZG ist vorbelegt),
   „Teams“ anlegen, „Abwesenheitsarten“ anpassen.

## 3. Menü

- **Tagesgeschäft:** „Startseite“, „Mitarbeiter“, „Anwesenheit“, „Kalender“, „Zu klären“,
  „Urlaubsanträge“ (nur sichtbar, wenn Anträge erlaubt sind oder welche offen sind)
- **Abrechnung:** „Monatsabschluss“, „Auswertungen“, „Lohn-Export“, „Zuschläge“
- **Arbeitszeit:** „Pausenregeln“, „Schichtvorlagen“ und „Schichtplan-Kalender“ (nur mit
  eingeschalteter Schichtplanung), „Feiertage“
- **Organisation:** „Teams“, „Standorte“, „Tablets“, „Checklisten“, „Audit-Log“
- **Unten:** „Mein Bereich“ (wenn der Login zu einem Mitarbeiter gehört), „Einstellungen“,
  „Darstellung“ (Hell/Dunkel/Wie System), „Abmelden“
- **Glocke:** Benachrichtigungen, mit „Alle als gelesen markieren“

## 4. Tagesgeschäft

- **Startseite:**
  - eigene Werte: „Gleitzeitsaldo“, „Resturlaub“, „Heute“, „Diese Woche“
  - Kacheln „Zu klären“ und „Urlaubsanträge“
  - „Heute“: Anwesend / In Pause / Dienstgang / Abwesend
  - „Nächste Termine“
- **Anwesenheit:** Wochenraster („Vorherige Woche“ / „Nächste Woche“ / „Heute“).
- **Kalender:** Monatsansicht mit Abwesenheiten, Feiertagen und Geburtstagen, Filter „Teams:“.
- **Zu klären:**
  - Hier landen Tage mit fehlenden oder widersprüchlichen Stempelungen und die Sonderfälle,
    die in den Einstellungen eingeschaltet sind:
    - Arbeitstage ganz ohne Stempelung („Stempelung fehlt“)
    - außerplanmäßig gestempelt
    - gestempelt trotz Abwesenheit
    - Arbeit an einem Feiertag
    - außerhalb des Beschäftigungszeitraums
    - mehr als 10 Std.
    - zu spät / zu früh
    - außerhalb der Gleitzeit-Rahmenzeit
  - Ein „Kommen“ ohne „Gehen“ gilt nach der „Maximalen Schichtlänge“ als vergessenes „Gehen“.
  - Je Tag: „Korrigieren →“ oder „Erledigt“ (mit „Rückgängig“). „Erledigt“ ändert an der
    Berechnung nichts.
  - Darunter: „Korrekturanträge“ der Mitarbeiter („Übernehmen“ / „Ablehnen“) und
    „Monatsgrenzen“.
- **Urlaubsanträge:** „Genehmigen“ / „Ablehnen“.

## 5. Mitarbeiter

- **Liste:** Suche, Standortfilter, „Auch inaktive anzeigen“, Hinweis auf die Tarifgrenze.
- **Dialog „Neuer Mitarbeiter“ / „Mitarbeiter bearbeiten“:**
  - Stammdaten, Standort („Standortwechsel gilt ab“), Team, Aktiv
  - Eintritts-, Austritts- und Geburtsdatum
  - „Pausen automatisch stempeln (nach Pausenregeln)“
  - „Kernarbeitszeit / Pünktlichkeit“: wie Einstellungen, eigene Kernzeit oder „Keine Prüfung“.
    Die eigene Kernzeit geht mit „Je Wochentag unterschiedlich“ auch je Tag, ohne Häkchen an einem
    Tag gilt dort keine Kernzeit.
  - „Login (Mein Bereich)“: Login-E-Mail und Passwort
  - „Stempel-PIN (Tablet)“ mit „PIN zurücksetzen“
  - „NFC-Karte (Tablet)“ mit „Karten-UID (optional)“
  - „HR-Berechtigung“
- **Detailseite:** Knöpfe „Monatsbericht“, „DSGVO-Datenexport“, „Anonymisieren“ (nur bei
  Ausgeschiedenen), „Bearbeiten“. Reiter:
  - „Zeiterfassung“: „Stempelung nachtragen“, „Korrigieren“, „Endgültig löschen“
  - „Kalender“
  - „Saldenübersicht“: Gleitzeitsaldo, Wochen- und Tagesansicht, „Korrekturbuchungen
    Gleitzeitkonto“ (Übertrag / Auszahlung / Korrektur)
  - „Abwesenheiten“: „Urlaubsanspruch“ und „Neue Abwesenheit“ mit Art, Von, Bis und Umfang
    („Ganzer Tag“ / „Halber Tag“ / „Stunden“)
  - „Arbeitszeitmodell“, jeweils mit „Gültig ab“ und Verlauf:
    - „Gleichmäßig verteilt“: Wochenstunden auf feste Arbeitstage verteilt
    - „Monatsstunden (fest)“: jeden Monat dasselbe Soll (z. B. 108,5 Std.), egal wie viele
      Arbeitstage der Monat hat. Das Soll wird gleichmäßig auf die Arbeitstage des Monats
      verteilt, das Tagessoll schwankt daher leicht. Feiertage und Abwesenheiten werden mit dem
      Tagessoll des jeweiligen Monats gutgeschrieben.
    - „Stunden je Wochentag (Teilzeit)“
    - „Flexibel ohne feste Tage“: Wochenstunden ohne feste Arbeitstage, abgerechnet je Woche.
      Passt für Teilzeit, die mal an 2, mal an 3 Tagen arbeitet: Tage ohne Stempelung sind nie
      „zu klären“.
    - „Nach Aufwand (Aushilfe)“
    - „Pause“: „Wie Pausenregeln“ (Standard), „Feste Minuten“ (an jedem Arbeitstag mindestens so
      viel Pause, gestempelte Pausen zählen mit) oder „Feste Uhrzeit“ (z. B. 12:00–12:30, abgezogen,
      soweit der Mitarbeiter da war). Eine eigene Pause ersetzt die festen Pausen des Betriebs; die
      gesetzliche Pausenstaffel gilt immer mindestens.
  - „Vertrag“, für Admins „Vertrag & Vergütung“. Dort zusätzlich „Zulagen & Einmalzahlungen“:
    - „Neue Zulage“: „Je Monat“ (in angebrochenen Monaten anteilig nach Kalendertagen) oder „Je
      Stunde (auf den Stundenlohn)“ (Betrag × Ist-Stunden), mit „Gültig ab“ und optional „Gültig
      bis“. Laufende Zulagen mit „Beenden“ abschließen.
    - „Neue Einmalzahlung“, z. B. Weihnachtsgeld, mit „Auszahlung am“.
    - Optional eine „Lohnart“ für den Export ans Lohnbüro.
    - Nur Admins sehen die Beträge; im Audit-Log steht jede Änderung ohne Betrag. Abgeschlossene
      Monate lassen sich nicht mehr ändern.
  - „Dokumente“: verschlüsselt abgelegt; mit „Für den Mitarbeiter in Mein Bereich sichtbar“
    und „Vertraulich“
  - „Checklisten“
  - „Schichtplanung“: Standard-Schichten und Ausnahmen
- **Tarif:**
  - Bis 5 aktive Mitarbeiter ist alles kostenlos.
  - Ab 6 aktiven Mitarbeitern kostet jeder aktive Mitarbeiter 1 € im Monat; freigeschaltet wird
    über den Anbieter.
  - Ausgeschiedene Mitarbeiter zählen nicht.

## 6. Abwesenheiten

- **Arten** unter „Einstellungen“ → „Abwesenheiten & Urlaub“ → „Abwesenheitsarten“:
  - je Art Name, Farbe und Kategorie
  - Kategorien: Urlaub, Krankheit, Kind krank, Sonderurlaub, Feiertag, Arbeitszeit, Unbezahlt,
    Freizeitausgleich
  - „Mitarbeiter dürfen selbst beantragen“, „Genehmigung nötig“, „Nachweis ab Tag“,
    „Deaktivieren“
  - Wird die Kategorie nachträglich geändert, rechnet HR3000 bestehende Einträge neu, außer in
    abgeschlossenen Monaten.
- **Halbe Tage:** möglich, höchstens zwei Hälften pro Tag, z. B. Weihnachten halb Sonderurlaub
  und halb Urlaub.
- **Stunden:** z. B. Homeoffice von 3 Std. mit der Kategorie Arbeitszeit.
- **Urlaubsübertrag:** automatisch, mit Höchstgrenze und Verfallsdatum (TT.MM.).

## 7. Abrechnung

- **„Monatsabschluss“:**
  - Monat wählen.
  - Je Mitarbeiter: „Vorlegen“, dann bestätigt der Mitarbeiter in „Mein Bereich“; danach
    „Abschließen“.
  - Außerdem „Ohne Bestätigung abschließen“, „Zurückziehen“, „Wieder öffnen“ und „Alle
    Berichte drucken“.
  - Abgeschlossene Monate lassen sich nicht mehr ändern.
- **„Auswertungen“:**
  - Reiter: Handlungsbedarf (BEM, Probezeit, Befristung, Austritt), Fehlzeiten, Urlaub,
    Überstunden, Lohnkosten (nur Admin)
  - jeweils „CSV exportieren“
- **„Lohn-Export“:** Monat und Standort wählen, CSV für das Lohnbüro. Zieht ein Admin den
  Export, kommt je Zulage bzw. Einmalzahlung eine Spalte mit dem Betrag im Zeitraum dazu (z. B.
  „Zulage Fahrtkosten (€)“, „Einmalzahlung Weihnachtsgeld (€)“). Bei HR fehlen diese Spalten.
- **„DATEV LODAS“** (auf der Seite „Lohn-Export“, nur Admins): Importdatei mit den
  Bewegungsdaten des gewählten Monats für das Lohnbüro (LODAS: ASCII-Import).
  - Einmalig „Beraternummer“ (4–7 Ziffern), „Mandantennummer“ (1–5 Ziffern) und „Lohnart
    Ist-Stunden“ eintragen und „Speichern“; darunter je Zuschlag eine Lohnart. Lohnarten für
    Zulagen und Einmalzahlungen stehen beim Mitarbeiter unter „Vertrag & Vergütung“.
  - Übertragen werden: Ist-Stunden von Mitarbeitern mit Vergütung „Stundenlohn“,
    Zuschlagsstunden und Zulagen/Einmalzahlungen als Betrag, jeweils nur mit Lohnart.
    Urlaub und Krankheit stehen nicht in der Datei.
  - Die Personalnummer muss rein aus Ziffern bestehen (wie in LODAS).
  - „Vorschau“ zeigt die Buchungen und Hinweise (z. B. fehlende Lohnart, offene Tage),
    „DATEV-Datei herunterladen“ speichert die Datei.
  - Vor der ersten echten Abrechnung den Aufbau mit dem Lohnbüro per Testimport abstimmen.
- **„Zuschläge“:** Lohnarten für den DATEV-Export trägt man auf der Seite „Lohn-Export“ ein.
  Regeln für Nacht, Sonntag, Feiertag und eigene Regeln
  („Standardregeln anlegen“, „Neue Regel“).

## 8. Arbeitszeit und Organisation

- **„Pausenregeln“:** alle Änderungen mit „Änderungen gültig ab“; Tage davor rechnen mit den
  bisherigen Regeln.
  - „Gesetzliche Pausenstaffel“: „Ab Arbeitsminuten“ / „Pausenabzug (Minuten)“. Gestempelte
    Pausen zählen mit, nur was fehlt, wird abgezogen. Gilt immer als Untergrenze.
  - „Feste Pausen des Betriebs“ für alle Mitarbeiter, auch ohne Pausenstempelung:
    - „Feste Uhrzeit“ („Pause von“ / „Pause bis“, z. B. 12:00–12:30, auch mehrere): abgezogen,
      soweit der Mitarbeiter in dieser Zeit da war. Wer um 12:15 geht, bekommt 15 Minuten
      abgezogen; wer vor 12:00 geht, keine. Gestempelte Pausen in dieser Zeit zählen nicht doppelt.
    - „Feste Minuten“ („Ab Arbeitsminuten“ / „Pause (Minuten)“): ab dieser Arbeitszeit mindestens
      so viel Pause; gestempelte Pausen zählen mit.
  - Ein Arbeitszeitmodell oder eine Schichtvorlage mit eigener Pause ersetzt die festen Pausen
    des Betriebs für diesen Mitarbeiter.
  - Die automatische Pause („Pausen automatisch stempeln“) bucht nur, was feste Pausenzeiten
    nicht schon abdecken.
- **Schichtplanung:**
  - einschalten unter „Einstellungen“ → „Allgemein“
  - „Schichtvorlagen“: Beginn, Ende, Tages-/Wochen-/Monatssoll, Pausenregelung, Standort.
    „Pausenregelung“: „Flexibel (Pause stempeln, optional feste Minuten)“ mit „Feste Pause
    (Minuten, optional)“ oder „Feste Pausenzeit (wird automatisch abgezogen)“ mit „Pause von“ /
    „Pause bis“. Eine geänderte Pause gilt ab „Neue Pause gilt ab“.
  - „Schichtplan-Kalender“: Schichten per Ziehen zuweisen, „PDF exportieren“
- **„Feiertage“:** je Standort automatisch importiert; eigene Feiertage mit „Feiertag
  hinzufügen“.
- **„Teams“:** Teams anlegen, Teamleader zuordnen.
- **„Tablets“:**
  - „Neues Tablet“: Name, Standort, Darstellung, Bildschirmzeiten
  - „QR-Code“: Mit der Kamera scannen öffnet den Kiosk fertig eingerichtet. Ohne Kamera gibt
    es einen Kopplungscode zum Eintippen (einmalig, läuft ab).
  - „Token kopieren“, „Bearbeiten“
- **„Checklisten“:** Vorlagen für On- und Offboarding, offene Aufgaben „Als erledigt
  markieren“.
- **„Audit-Log“:** wer wann was geändert hat, filterbar.

## 9. Einstellungen (nur Admin)

Grundsatz: Neue Funktionen sind einzeln schaltbar und standardmäßig so eingestellt, dass sich
für bestehende Firmen nichts ändert.

- **Allgemein:**
  - „Tarif“
  - „Konto kündigen“, siehe Abschnitt 11
  - „Einstellungen übertragen“: „Exportieren“ speichert fachliche Einstellungen, Pausenregeln,
    Abwesenheitsarten und Zuschläge als Datei. „Datei importieren“ (z. B. in einer neuen Firma)
    zeigt erst eine Vorschau, „Übernehmen“ wendet sie an. Einstellungen werden überschrieben,
    Pausenregeln, Abwesenheitsarten und Zuschläge nur ergänzt; kollidierende Pausenregeln werden
    übersprungen und angezeigt. Nicht übertragen werden Mailserver, Tablet-Admin-PIN,
    „Gleitzeitkonten führen ab“ und die DATEV-Berater-/Mandantennummer.
  - „Gleitzeitkonten führen ab“: Datum. Leer heißt ab der ersten Stempelung; eine Änderung
    rechnet alle Konten neu.
  - „Standard-Jahresurlaub“, „Standard-Bundesland“
  - „Schichtplanung aktivieren“
  - „Stempeln über den Web-Login (Home-Office)“: Stempel-Karte in „Mein Bereich“, mit
    Serverzeit
  - „Geburtstage im Kalender anzeigen“
- **Mitarbeiter & Regeln:**
  - „Standardwerte für neue Mitarbeiter“
  - „Urlaubsanspruch für Teilzeit anteilig berechnen“
  - welche Sonderfälle unter „Zu klären“ erscheinen (9 einzeln abschaltbare Häkchen). Das
    Häkchen „Arbeitstage ganz ohne Stempelung“ gilt auch für den Monatsbericht und den
    Lohn-Export: Ist es aus, gelten nur unvollständig gestempelte Tage als offen, und im
    Monatsbericht steht kein „Stempelung fehlt“ mehr. Das Soll zählt trotzdem, ein Arbeitstag
    ohne Stempelung geht also ins Minus.
  - „Maximale Schichtlänge (Stunden)“
  - „Kernarbeitszeit & Gleitzeit“: Kernzeit, „Pünktlichkeit prüfen“ mit Toleranz,
    Gleitzeit-Rahmen. Das erzeugt nur Hinweise und kürzt keine Stunden. Mit „Kernzeit je
    Wochentag unterschiedlich“ gilt je Tag eine eigene Kernzeit (z. B. freitags 09:00–12:00) oder
    gar keine; speichern mit „Kernzeiten übernehmen“. „Keine Kernzeit“ entfernt auch die Zeiten je
    Tag.
- **Abwesenheiten & Urlaub:** Abwesenheitsarten, „Mitarbeiter dürfen Urlaub/Abwesenheiten
  beantragen“, „Urlaubsübertrag ins neue Jahr“.
- **Kiosk:**
  - „PIN zum Stempeln erforderlich“
  - „PIN beim ersten Stempeln selbst festlegen“
  - „Chips/RFID am Tablet nutzen“
  - „Mitarbeiter registrieren ihren Chip selbst“
  - „RFID-Pflicht“
  - „Anzeige am Tablet“:
    - Saldo und Resturlaub nach dem Stempeln
    - „Pausen-Buttons anzeigen“, „Dienstgang-Buttons anzeigen“
    - „Darstellung am Tablet“ Dunkel/Hell
    - „Bildschirm nur zu bestimmten Zeiten anlassen“ (von–bis, über Mitternacht möglich; je
      Tablet abweichend einstellbar)
    - „Sortierung der Kacheln“
    - „Hinweistext über den Kacheln“
  - „Kiosk-Admin-PIN“: wird zum Zurücksetzen des Tablets gebraucht.
  - Änderungen erreichen die Tablets innerhalb von 30 Sekunden.
- **Logo & E-Mail:**
  - „Firmenlogo“: max. 256 KB
  - „E-Mail-Versand (SMTP)“: eigener Mailserver für Benachrichtigungen und Zugangsdaten, mit
    „Testmail an mich senden“

## 10. Tablets im Betrieb

- Ein Android-Tablet mit Chrome reicht. Für Chips dient NFC oder ein USB- bzw.
  Bluetooth-Leser im Tastatur-Modus.
- Bei Netzausfall puffert das Tablet die Stempelungen und sendet sie automatisch nach. Offene
  Einträge zeigt die „Offline-Warteschlange“.
- Bildschirm aus nach Zeitfenster: Das Tablet hält den Bildschirm nur im eingestellten Fenster
  wach. Morgens weckt man es per Ein/Aus-Taste. Mit einer Geräteverwaltung (z. B. Endpoint
  Central): Bildschirm-Timeout 1 Minute, „Beim Laden wach bleiben“ aus.
- Tablet neu koppeln: am Tablet „Gerät zurücksetzen“ (mit Kiosk-Admin-PIN), dann den QR-Code
  erneut scannen.

## 11. Kündigen und Löschen

- **Kündigen:** „Einstellungen“ → „Allgemein“ → „Konto kündigen“ → „HR3000 kündigen…“. Zur
  Bestätigung die Adresse der Firma eintippen (z. B. `musterfirma`). Nur Admins können kündigen.
- **Fristen:**
  - Die Kündigung gilt zum Monatsende.
  - Danach könnt ihr HR3000 noch **30 Tage** normal nutzen und alles exportieren:
    „Auswertungen“, „Lohn-Export“, „DSGVO-Datenexport“ und „Monatsbericht“ je Mitarbeiter.
  - Anschließend werden **alle Daten der Firma endgültig gelöscht**: Mitarbeiter, Zeiten,
    Abwesenheiten, Dokumente, Einstellungen, Zugänge.
  - Kopien in den Datensicherungen verschwinden spätestens nach 12 Monaten.
- **Hinweise:** Während der Frist steht oben in der HR-Ansicht ein Hinweis mit dem
  Löschtermin. Mit eingerichtetem Mailversand kommt zusätzlich eine Bestätigung per E-Mail.
- **Zurücknehmen:** bis zur Löschung jederzeit mit „Kündigung zurücknehmen“ an derselben
  Stelle.

