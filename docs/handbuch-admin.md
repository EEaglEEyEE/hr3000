# HR3000 – Handbuch für Admins, HR und Teamleiter/innen

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
| Admin | alles, auch alle Bereiche der „Einstellungen“ und „Vergütung & Lohn-Export“ (siehe unten) |
| HR | Mitarbeiter, Abwesenheiten, „Zu klären“, „Monatsabschluss“, „Auswertungen“, „Lohn-Export“ (CSV ohne Beträge), „Checklisten“, „Schichtplan-Kalender“; unter „Einstellungen“ „Standorte“, „Teams“, „Feiertage“, „Schichtplanung“ (Schichtvorlagen), „Tablets“ und „Audit-Log“; Vergütung und „Lohnarten“ nur mit „Vergütung & Lohn-Export“ |
| Teamleiter/in | „Tagesgeschäft“ für die eigenen Teams |
| Keine (nur Mein Bereich) | nur die eigene Ansicht, siehe Mitarbeiter-Handbuch |

- **„Vergütung & Lohn-Export“:** Admins haben es immer; HR bekommt es per Häkchen unter
  „HR-Berechtigung“ (Standard aus). Es öffnet überall dasselbe: Vergütung und „Zulagen &
  Einmalzahlungen“ unter „Personalakte“ → „Vertrag & Vergütung“, Auswertung „Lohnkosten“, Beträge im
  Lohn-Export, „DATEV LODAS“ und die Seite „Lohnarten“. Zuschlagsregeln selbst ändern bleibt Admins
  vorbehalten. Nach der Freigabe sieht die Person die neuen Bereiche spätestens nach der nächsten
  Anmeldung.

- **Passwörter:**
  - **Selbst ändern:** in der Seitenleiste „Passwort ändern“ (in „Mein Bereich“ oben). Danach
    enden alle anderen Sitzungen dieses Kontos.
  - **Vergessen:** auf der Anmeldeseite „Passwort vergessen?“. Es kommt ein Link per E-Mail,
    1 Stunde gültig. Den Link gibt es nur, wenn ein Mailversand eingerichtet ist: eigener
    Mailserver unter „Einstellungen“ → „E-Mail-Versand“ oder der Versand der Plattform.
    Sonst steht dort „Bitte wende dich an deine Personalabteilung“.
  - **Für andere:** HR erzeugt im Mitarbeiter-Dialog ein neues Einmalpasswort („Neues
    Passwort erzeugen …“). Es wird einmal angezeigt oder auf Wunsch per E-Mail verschickt.
  - **Erst-Admin:** Ohne Mailversand setzt der Plattform-Betreiber dessen Passwort zurück.

## 2. Erste Schritte nach der Registrierung

1. **„Einstellungen“ → „Standorte“** → „Neuer Standort“: Name, Zeitzone, Bundesland. Das
   Bundesland bestimmt die Feiertage.
2. **„Einstellungen“:** unter „Arbeitszeit“ „Gleitzeitkonten führen ab“, unter „Urlaub &
   Anträge“ den „Standard-Jahresurlaub“, unter „Allgemein“ das „Standard-Bundesland“.
3. **„Mitarbeiter“** → „Neuer Mitarbeiter“ oder „CSV-Import“.
   - Umstieg von einem anderen System: auf derselben Seite unter „Werte aus dem Altsystem
     übernehmen“ eine zweite CSV hochladen (Pflichtspalte `personalnummer`). Optional sind
     `saldo_stunden` (Gleitzeit-Übertrag, auch negativ), `urlaubsanspruch_tage` und
     `uebertrag_vorjahr_tage` für das Jahr des Stichtags sowie das Arbeitszeitmodell ab Stichtag
     (`wochenstunden`, `arbeitstage`, `tagesstunden`, `monatsstunden`, `monatsgrenze`,
     `pause_minuten`). Leere Zellen ändern nichts.
   - „Stichtag“ wählen, „Vorschau“ prüfen, dann „Übernehmen“. Fehlerhafte Zeilen werden
     übersprungen und angezeigt. Ein zweiter Gleitzeit-Übertrag zum selben Stichtag wird
     abgelehnt, ebenso Änderungen in abgeschlossenen Monaten. Rechnet das Gleitzeitkonto schon vor
     dem Stichtag („Gleitzeitkonten führen ab“ früher oder ältere Stempelungen), wird der Übertrag
     abgelehnt, weil die Tage dazwischen sonst doppelt zählen: „Gleitzeitkonten führen ab“ auf den
     Stichtag setzen.
   - Wer mitten im Jahr umsteigt: als `urlaubsanspruch_tage` den restlichen Anspruch für den Rest
     des Jahres eintragen, da bereits genommener Urlaub nicht im neuen System steht. Der Wert gilt
     dann fest für dieses Jahr; ab dem Folgejahr wird der Anspruch berechnet.
4. **„Einstellungen“ → „Tablets“** → „Neues Tablet“, dann „QR-Code“ und mit dem Tablet scannen. Die
   Tablet-Adresse ist `https://kiosk.<firma>.hr3000.de`.
5. Optional unter „Einstellungen“: „Pausenregeln“ prüfen (die gesetzliche Staffel nach § 4 ArbZG
   ist vorbelegt), „Teams“ anlegen, „Abwesenheitsarten“ anpassen.

## 3. Menü

- **Tagesgeschäft:** „Startseite“, „Mitarbeiter“, „Anwesenheit“, „Kalender“, „Zu klären“ (der
  Posteingang mit Urlaubs- und Korrekturanträgen; die rote Zahl zählt alles Offene)
- **Planung & Abrechnung:** „Schichtplan-Kalender“ (nur mit eingeschalteter Schichtplanung),
  „Monatsabschluss“, „Auswertungen“, „Lohn-Export“, „Checklisten“
- **Unten:** „Mein Bereich“ (wenn der Login zu einem Mitarbeiter gehört), „Einstellungen“ (Admin
  und HR, je nach Rolle mit unterschiedlichen Bereichen), „Darstellung“ (Hell/Dunkel/Wie System),
  „Abmelden“
- Standorte, Teams, Feiertage, Tablets, Pausenregeln, Schichtvorlagen, Zuschläge, Lohnarten und
  das Audit-Log stehen unter „Einstellungen“ (siehe Abschnitt 9); alte Links und Lesezeichen
  führen dorthin.
- **Glocke:** Benachrichtigungen, mit „Alle als gelesen markieren“

## 4. Tagesgeschäft

- **Startseite:**
  - eigene Werte: „Gleitzeitsaldo“, „Resturlaub“, „Heute“, „Diese Woche“
  - Kacheln „Zu klären“ und „Urlaubsanträge“ (öffnet „Zu klären“ → „Urlaubsanträge“; nur sichtbar,
    wenn Anträge erlaubt sind oder welche offen sind)
  - „Heute“: Anwesend / In Pause / Dienstgang / Abwesend
  - „Nächste Termine“
- **Anwesenheit:** Wochenraster („Vorherige Woche“ / „Nächste Woche“ / „Heute“).
- **Kalender:** Monatsansicht mit Abwesenheiten, Feiertagen und Geburtstagen, Filter „Teams:“.
- **Zu klären** – der Posteingang mit vier Reitern, jeweils mit der Anzahl des Offenen:
  „Tage“, „Korrekturanträge“ (nur Admin und HR), „Urlaubsanträge“ und „Monatsgrenzen“.
- **„Tage“:**
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
    Berechnung nichts und gilt, solange sich der Tag nicht ändert – kommt z. B. eine Stempelung dazu
    oder ändert sich das Soll, erscheint der Tag wieder.
  - Dieselbe Regel „offen“ gilt überall: „Zu klären“, „Monatsabschluss“ (offene Tage), Monatsbericht
    und Lohn-Export („Offene/fehlerhafte Tage“, DATEV-Hinweis).
- **„Korrekturanträge“:** von Mitarbeitern beantragte Korrekturen ihrer Stempelungen,
  „Übernehmen“ / „Ablehnen“.
- **„Urlaubsanträge“:** „Genehmigen“ / „Ablehnen“. Teamleiter/innen sehen die Anträge ihrer Teams.
  Früher ein eigener Menüpunkt; alte Links führen hierher.
- **„Monatsgrenzen“:** Aushilfen „nach Aufwand“ ab 90 % ihrer Monatsgrenze.

## 5. Mitarbeiter

- **Liste:** Suche, Standortfilter, „Auch inaktive anzeigen“, Hinweis auf die Tarifgrenze.
- **Dialog „Neuer Mitarbeiter“ / „Mitarbeiter bearbeiten“:**
  - Oben die Grunddaten: Vor- und Nachname, Personalnummer, Standort („Standortwechsel gilt ab“),
    Team, „Eintrittsdatum“.
  - Nur beim Anlegen „Arbeitszeitmodell“: „Standard aus den Einstellungen“ (wenn dort eines
    hinterlegt ist), „Stunden je Wochentag“, „Nach Aufwand (Aushilfe, ohne Soll)“ oder „Kein
    Arbeitszeitmodell (ohne Soll, z. B. reines HR-Konto)“. Gilt ab Eintritt; Wochen- oder
    Monatsstunden, Pausen und Kernzeit im Reiter „Arbeitszeit“.
  - „Weitere Angaben (Austritt, Geburtstag, Aktiv, Pausen)“: „Aktiv“, Austritts- und
    Geburtsdatum, „Pausen automatisch stempeln (nach Pausenregeln)“. Beim Anlegen eingeklappt.
  - „Login und Stempeln am Tablet (E-Mail, Passwort, PIN, Chip)“: „Login (Mein Bereich)“ mit
    Login-E-Mail und Passwort, „Stempel-PIN (Tablet)“ mit „PIN zurücksetzen“, „Chip
    (Tablet)“ mit „Chip-UID (optional)“. Beim Anlegen eingeklappt.
  - „HR-Berechtigung“ (beim Bearbeiten, nur Admin)
  - Die Kernarbeitszeit steht im Arbeitszeitmodell (Reiter „Arbeitszeit“), damit sie mit
    jeder Fassung „gilt ab“ hat.
- **Detailseite:** Knöpfe „Monatsbericht“, „DSGVO-Datenexport“, „Anonymisieren“ (nur bei
  Ausgeschiedenen), „Bearbeiten“. Reiter:
  - „Zeiterfassung“: „Stempelung nachtragen“, „Korrigieren“, „Endgültig löschen“
  - „Kalender“
  - „Saldenübersicht“: Gleitzeitsaldo, Wochen- und Tagesansicht, „Korrekturbuchungen
    Gleitzeitkonto“ (Übertrag / Auszahlung / Korrektur)
  - „Abwesenheiten“: „Urlaubsanspruch“ und „Neue Abwesenheit“ mit Art, Von, Bis und Umfang
    („Ganzer Tag“ / „Halber Tag“ / „Stunden“). Ganztägige Abwesenheiten dürfen sich nicht
    überschneiden. Ausnahme Krankheit im Urlaub: Nach Rückfrage werden die Urlaubstage
    zurückgegeben (§ 9 BUrlG), der Urlaub wird um die Krankheitstage gekürzt bzw. geteilt.
    - Der „Urlaubsanspruch“ eines Jahres wird berechnet („Anspruch (berechnet)“): Jahresurlaub laut
      Vertrag, sonst „Standard-Jahresurlaub“, bezogen auf die 5-Tage-Woche. Mit „Urlaubsanspruch für
      Teilzeit anteilig berechnen“ zählt er anteilig nach Arbeitstagen ÷ 5, mit „Teilurlaub bei
      Eintritt oder Austritt im Jahr berechnen“ anteilig nach Beschäftigungstagen. Beim Teilurlaub
      bleibt der gesetzliche Mindesturlaub (20 Tage bei 5 Arbeitstagen, bei Teilzeit anteilig), wenn
      die Wartezeit von sechs Monaten im Jahr erfüllt ist, der Mitarbeiter nicht vorher ausscheidet
      und der Austritt nicht im ersten Halbjahr liegt. Gerundet wird nie nach unten: ab einem halben
      Tag auf volle Tage, darunter auf den nächsten halben Tag.
    - „Bearbeiten“: Ein geänderter Anspruch gilt fest für dieses Jahr („Anspruch (fest
      eingetragen)“); „Wieder berechnen“ bzw. „Anspruch wieder berechnen“ hebt das auf. Bei „Nach
      Aufwand (Aushilfe)“ wird mit Teilzeit-Anteil nichts berechnet, der Anspruch wird eingetragen.
  - „Arbeitszeit“: alles zur regelmäßigen Arbeitszeit an einer Stelle – oben das
    Arbeitszeitmodell, mit eingeschalteter Schichtplanung darunter „Schichtplanung“ (siehe unten).
    Das Arbeitszeitmodell jeweils mit „Gültig ab“ und „Verlauf“ (jede Fassung mit „Bearbeiten“ /
    „Löschen“):
    - „Modell“: „Feste Arbeitstage“, „Flexibel ohne feste Tage“ (Wochenstunden ohne feste
      Arbeitstage, abgerechnet je Woche – passt für Teilzeit, die mal an 2, mal an 3 Tagen
      arbeitet; Tage ohne Stempelung sind nie „zu klären“) oder „Nach Aufwand (Aushilfe)“ (ohne
      Soll, optional mit Monatsgrenze).
    - „Soll“ bei festen Arbeitstagen: „Wochenstunden“ mit „Arbeitstage“ – gleichmäßig verteilt
      oder mit „Stunden je Wochentag unterschiedlich (Teilzeit)“ je Tag – oder „Monatsstunden
      (fest)“: jeden Monat dasselbe Soll (z. B. 108,5 Std.), egal wie viele Arbeitstage der Monat
      hat. Das Soll wird gleichmäßig auf die Arbeitstage des Monats verteilt, das Tagessoll
      schwankt daher leicht. Feiertage und Abwesenheiten werden mit dem Tagessoll des jeweiligen
      Monats gutgeschrieben.
    - „Schichtvorlage (Uhrzeiten, optional)“: feste Uhrzeiten aus einer Schichtvorlage, z. B.
      „Früh (06:00–14:30)“, für Schichtplan, Pünktlichkeit und Ruhezeit-Prüfung. Das Soll bleibt
      das des Arbeitszeitmodells.
    - „Pause“: „Wie Pausenregeln“ (Standard; mit Schichtvorlage, die eine eigene Pause hat, heißt
      der Knopf „Wie Schichtvorlage“), „Feste Minuten“ ab einer Arbeitszeit („… Minuten ab … Std.
      Arbeit“, leer = ab der ersten Minute; gestempelte Pausen zählen mit) oder „Feste Uhrzeit“
      (z. B. 12:00–12:30, abgezogen, soweit der Mitarbeiter da war). Die Pausenstaffel gilt immer
      mindestens.
    - „Kernarbeitszeit / Pünktlichkeit“: „Wie in den Einstellungen“, „Eigene Kernzeit“ (mit „Je
      Wochentag unterschiedlich“ auch je Tag; ohne Häkchen an einem Tag gilt dort keine Kernzeit)
      oder „Keine Prüfung (z. B. Außendienst)“. Eine neue Fassung übernimmt die Kernzeit der
      bisherigen, wenn sie nicht geändert wird.
    - Ältere Standard-Schichten (früher im Reiter „Schichtplanung“ zugewiesen) rechnen unverändert
      weiter; ihr Soll kommt aus der Schichtvorlage, bis die Fassung hier gespeichert wird – dann
      wird es fest ins Arbeitszeitmodell übernommen.
    - Urlaubs- und Krankheitstage zählen nur an Arbeitstagen des Modells. Ohne Arbeitszeitmodell
      sowie bei „Flexibel“ und „Nach Aufwand“ zählen Mo–Fr (der Urlaubsanspruch bezieht sich auf die
      5-Tage-Woche); wer regelmäßig samstags arbeitet, bekommt ein Modell mit Samstag.
  - „Personalakte“ (Admin und HR) mit den Unterreitern „Vertrag“ (mit „Vergütung & Lohn-Export“
    „Vertrag & Vergütung“), „Dokumente“ und „Checklisten“.
  - „Vertrag“ bzw. „Vertrag & Vergütung“: „Neuer Vertragsabschnitt“ mit
    „Jahresurlaub (Tage, 5-Tage-Woche)“: leer heißt „Standard-Jahresurlaub“ aus den Einstellungen;
    daraus wird der Urlaubsanspruch je Jahr berechnet (siehe „Abwesenheiten“). Dort zusätzlich
    „Zulagen & Einmalzahlungen“:
    - „Neue Zulage“: „Je Monat“ (in angebrochenen Monaten anteilig nach Kalendertagen) oder „Je
      Stunde (auf den Stundenlohn)“ (Betrag × Ist-Stunden), mit „Gültig ab“ und optional „Gültig
      bis“. Laufende Zulagen mit „Beenden“ abschließen.
    - „Neue Einmalzahlung“, z. B. Weihnachtsgeld, mit „Auszahlung am“.
    - „Bezeichnung“ schlägt die Arten aus „Lohnarten“ vor; ein neuer Name legt dort eine neue Art an
      (dann optional mit „Lohnart“). Die Lohnart einer vorhandenen Art steht nur unter „Lohnarten“.
      Inaktive Arten lassen sich nicht neu vergeben.
    - Beträge nur mit „Vergütung & Lohn-Export“; im Audit-Log steht jede Änderung ohne Betrag. Abgeschlossene
      Monate lassen sich nicht mehr ändern.
  - „Dokumente“: verschlüsselt abgelegt; mit „Für den Mitarbeiter in Mein Bereich sichtbar“
    und „Vertraulich“
  - „Checklisten“
  - „Schichtplanung“ (im Reiter „Arbeitszeit“): „Regelmäßige Arbeitszeit“ (aus dem
    Arbeitszeitmodell, nur lesend) und „Ausnahmen“ für einzelne Tage. Bei „Flexibel“ und „Nach Aufwand“ liefert eine geplante Schicht
    nur die Uhrzeiten, kein Tagessoll.
- **Tarif:**
  - Bis 5 aktive Mitarbeiter ist alles kostenlos.
  - Ab 6 aktiven Mitarbeitern kostet jeder aktive Mitarbeiter 1 € im Monat; freigeschaltet wird
    über den Anbieter.
  - Ausgeschiedene Mitarbeiter zählen nicht.

## 6. Abwesenheiten

- **Arten** unter „Einstellungen“ → „Abwesenheitsarten“:
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
- **Urlaubsanspruch:** Jahresurlaub im Vertrag, der Anspruch je Jahr wird berechnet (Teilzeit,
  Teilurlaub bei Ein- und Austritt) oder je Jahr fest eingetragen.
- **Urlaubsübertrag:** automatisch, mit Höchstgrenze und Verfallsdatum (TT.MM.).

## 7. Abrechnung

- **„Monatsabschluss“:**
  - Monat wählen.
  - Je Mitarbeiter: „Vorlegen“, dann bestätigt der Mitarbeiter in „Mein Bereich“ – damit ist der
    Monat abgeschlossen (kein zweiter Schritt mehr). Mitarbeiter ohne Login werden beim Vorlegen
    direkt abgeschlossen. Zustände: offen, „Zur Bestätigung vorgelegt“, „Widerspruch“ (wieder
    offen), „Abgeschlossen“.
  - Sind für den Monat noch Abwesenheits- oder Korrekturanträge offen, fragt „Vorlegen“ nach – danach
    ließen sie sich erst nach „Zurückziehen“ entscheiden. „Alle vorlegen“ überspringt solche
    Mitarbeiter mit Hinweis.
  - Außerdem „Ohne Bestätigung abschließen“, „Zurückziehen“, „Wieder öffnen“ (nur Admins) und „Alle
    Berichte drucken“.
  - Abgeschlossene Monate lassen sich nicht mehr ändern. Auch „Gleitzeitkonten führen ab“,
    „Schichtplanung aktivieren“ und „Maximale Schichtlänge“ lassen sich nur ändern, solange davon
    kein vorgelegter oder abgeschlossener Monat betroffen ist.
- **„Auswertungen“:**
  - Reiter: Handlungsbedarf (BEM, Probezeit, Befristung, Austritt), Fehlzeiten, Urlaub,
    Überstunden, Lohnkosten (nur mit „Vergütung & Lohn-Export“; mit Spalte „Zulagen“ für Zulagen und
    Einmalzahlungen im Zeitraum)
  - jeweils „CSV exportieren“
- **„Lohn-Export“:** Monat (vorbelegt: Vormonat) und Standort wählen, CSV für das Lohnbüro.
  Exportiert werden alle, die im Monat beschäftigt waren – auch wer im Monat ausgetreten ist. Mit
  „Vergütung & Lohn-Export“ kommt je Zulage bzw. Einmalzahlung eine Spalte mit dem Betrag im Zeitraum
  dazu (z. B. „Zulage Fahrtkosten (€)“, „Einmalzahlung Weihnachtsgeld (€)“), sonst fehlen diese
  Spalten.
  „Ausgezahlte Überstunden (Std.)“ zeigt die Auszahlungen aus den „Korrekturbuchungen
  Gleitzeitkonto“ mit Datum im Zeitraum. Über dem Export steht der Stand des „Monatsabschluss“
  (z. B. „1 von 2 abgeschlossen, 1 offen“ – solange nicht alles abgeschlossen ist, können sich die
  Werte noch ändern) und „Schon exportiert“ mit Zeitpunkt und Person (DATEV-Exporte nur mit
  „Vergütung & Lohn-Export“).
- **„DATEV LODAS“** (auf der Seite „Lohn-Export“, mit „Vergütung & Lohn-Export“): Importdatei mit den
  Bewegungsdaten des gewählten Monats für das Lohnbüro (LODAS: ASCII-Import).
  - Einmalig „Beraternummer“ (4–7 Ziffern) und „Mandantennummer“ (1–5 Ziffern) eintragen und
    „Speichern“. Alle Lohnarten stehen unter „Lohnarten“ („Lohnarten pflegen“).
  - Übertragen werden, jeweils nur mit Lohnart: Stunden je Zeitart von Mitarbeitern mit Vergütung
    „Stundenlohn“ (gearbeitete Stunden; Urlaub, Krankheit, Kind krank, Sonderurlaub und Feiertag,
    sobald dafür eine Lohnart hinterlegt ist; Arbeitszeit-Angaben wie Homeoffice ohne eigene Lohnart
    als gearbeitete Stunden), ausgezahlte Überstunden (für alle), Zuschlagsstunden und Zulagen/
    Einmalzahlungen als Betrag. Was ohne Lohnart bleibt, nennt die „Vorschau“ je Mitarbeiter, damit
    das Lohnbüro es z. B. als Fehlzeiten erfasst. Mitarbeiter ohne hinterlegte Vergütung erscheinen
    als Hinweis.
  - Die Personalnummer muss rein aus Ziffern bestehen (wie in LODAS).
  - „Vorschau“ zeigt die Buchungen und Hinweise (z. B. fehlende Lohnart, offene Tage),
    „DATEV-Datei herunterladen“ speichert die Datei.
  - Vor der ersten echten Abrechnung den Aufbau mit dem Lohnbüro per Testimport abstimmen.
- **„Zuschläge“:** Regeln für Nacht, Sonntag, Feiertag und eigene Regeln („Standardregeln
  anlegen“, „Neue Regel“ mit optionalem „Gilt ab“; leer = auch rückwirkend). Ihre Lohnarten stehen
  unter „Lohnarten“.
  - Bearbeiten (Stift): Ändert sich Satz, Zeitfenster oder Wochentage, gilt die Änderung ab
    „Änderung gilt ab“ (vorbelegt: heute) – Tage davor rechnen mit der bisherigen Fassung, nichts
    in vorgelegten oder abgeschlossenen Monaten. Feld leeren = bestehende Fassung rückwirkend
    korrigieren. Name und Gruppe ändern sich ohne Stichtag.
  - „Frühere Fassungen anzeigen“ zeigt die abgelaufenen Fassungen mit Gültigkeit; Löschen einer
    Fassung lässt die vorherige wieder weiterlaufen. Im Lohn-Export bleibt es bei einer Spalte je
    Regel.
- **„Lohnarten“** (mit „Vergütung & Lohn-Export“): alle Lohnarten für die DATEV-Datei an einer Stelle.
  - „Zeitarten“: je eine Lohnart für „Gearbeitete Stunden“, „Urlaub“, „Krankheit“, „Kind krank“,
    „Sonderurlaub“, „Feiertag“, „Arbeitszeit-Angaben (z. B. Homeoffice)“ (leer = wie gearbeitet) und
    „Ausgezahlte Überstunden“; „Lohnarten speichern“. Leer = wird nicht übertragen.
  - „Zuschläge“: Lohnart je Zuschlagsregel (speichert beim Verlassen des Felds).
  - „Zulagen und Einmalzahlungen“: der Katalog der Arten mit „Bezeichnung“, „Lohnart“ und „Aktiv“;
    neue Art mit „Art hinzufügen“. Gelöscht werden kann nur eine Art, die nirgends verwendet wird –
    sonst auf inaktiv setzen. Eine geänderte Bezeichnung oder Lohnart gilt für alle Zulagen dieser
    Art.

## 8. Arbeitszeit und Organisation

Alle Seiten dieses Abschnitts stehen unter „Einstellungen“, der „Schichtplan-Kalender“ und die
„Checklisten“ im Menü.

- **„Pausenregeln“** – alles zu Pausen an einer Stelle; Änderungen mit „Änderungen gültig ab“, Tage
  davor rechnen mit den bisherigen Regeln:
  - „Gesetzliche Pausenstaffel“: „Ab Arbeitsminuten“ / „Pausenabzug (Minuten)“. Gestempelte
    Pausen zählen mit, nur was fehlt, wird abgezogen. Strengere Werte des Betriebs (z. B. 30 Min.
    schon ab 4 Std.) sind einfach weitere Zeilen. „Gesetzliche Mindestpause nicht unterschreiten“
    (Standard an) verhindert, dass die Staffel unter § 4 ArbZG sinkt; aus nur bei abweichender
    Regelung (z. B. Tarifvertrag).
  - „Feste Pausenzeiten“ („Pause von“ / „Pause bis“, z. B. 12:00–12:30, auch mehrere): abgezogen,
    soweit der Mitarbeiter in dieser Zeit da war, auch ohne Pausenstempelung. Wer um 12:15 geht,
    bekommt 15 Minuten abgezogen; wer vor 12:00 geht, keine. Gestempelte Pausen in dieser Zeit
    zählen nicht doppelt; die Staffel gilt zusätzlich als Mindestwert.
  - „Berechnung“, jeweils mit „gilt ab“ (frühere Tage bleiben, wie sie sind):
    - „Pausen genau nach § 4 ArbZG rechnen“: Die Pausenpflicht richtet sich nach der Arbeitszeit
      ohne Pausen, gestempelte Pausen zählen erst ab 15 Minuten.
    - „Pausenabzug höchstens bis zur Schwelle“: Wer 6:10 Std. ohne Pause arbeitet, behält 6:00 Std.
      statt 5:40 Std.
    - „Pausen automatisch stempeln – Standard für neue Mitarbeiter“ (je Mitarbeiter im Dialog
      änderbar). Die automatische Pause bucht nur, was feste Pausenzeiten nicht schon abdecken, und
      wird bei Korrekturen neu gesetzt.
  - Je Mitarbeiter abweichend: Arbeitszeitmodell → „Pause“; ohne eigene Pause gilt die der
    Schichtvorlage (an geplanten Schichttagen immer die der Schicht).
    Eine eigene feste Pausenzeit ersetzt die festen Pausenzeiten des Betriebs; eigene feste Minuten
    kommen zur Staffel dazu (es gilt der höhere Wert).
- **Schichtplanung:**
  - einschalten unter „Einstellungen“ → „Schichtplanung“ (nur Admin)
  - „Schichtvorlagen“ (ebenfalls unter „Schichtplanung“, auch für HR): Beginn, Ende, „Soll pro Schichttag (Minuten)“ (gilt an geplanten
    Schichttagen), Pausenregelung, Standort. Wochen- und Monatsstunden gehören ins
    Arbeitszeitmodell; ältere Vorlagen mit Wochen- oder Monatssoll behalten ihren „Zieltyp“.
    „Pausenregelung“: „Flexibel (Pause stempeln, optional feste Minuten)“ mit „Feste Pause
    (Minuten, optional)“ und „ab Arbeitszeit (Std., optional)“ oder „Feste Pausenzeit (wird automatisch abgezogen)“ mit „Pause von“ /
    „Pause bis“. Eine geänderte Pause gilt ab „Neue Pause gilt ab“.
  - „Schichtplan-Kalender“: Schichten per Ziehen zuweisen, „PDF exportieren“
- **„Feiertage“:** je Standort automatisch importiert; eigene Feiertage mit „Feiertag
  hinzufügen“.
- **„Teams“:** Teams anlegen, Teamleiter/innen zuordnen.
- **„Tablets“:**
  - „Neues Tablet“: Name, Standort, Darstellung, Bildschirmzeiten
  - „QR-Code“: Mit der Kamera scannen öffnet die Tablet-App fertig eingerichtet. Ohne Kamera gibt
    es einen Kopplungscode zum Eintippen (einmalig, läuft ab).
  - „Token kopieren“, „Bearbeiten“
- **„Checklisten“:** Vorlagen für On- und Offboarding, offene Aufgaben „Als erledigt
  markieren“.
- **„Audit-Log“:** wer wann was geändert hat, filterbar.

## 9. Einstellungen

Grundsatz: Neue Funktionen sind einzeln schaltbar und standardmäßig so eingestellt, dass sich
für bestehende Firmen nichts ändert.

- **Aufbau:** links die Bereiche nach Themen, auf dem Handy eine Auswahlliste. Admins sehen alle
  Bereiche. HR sieht „Standorte“, „Teams“, „Feiertage“, „Schichtplanung“ (nur die Schichtvorlagen,
  wenn die Schichtplanung an ist), „Tablets“ und „Audit-Log“, mit „Vergütung & Lohn-Export“ auch
  „Lohnarten“. Kann eine Änderung nicht gespeichert werden (z. B. weil ein Monat schon vorgelegt
  oder abgeschlossen ist), steht der Grund oben im Bereich.
- **Unternehmen:**
  - „Allgemein“: „Standard-Bundesland“, „Geburtstage im Kalender anzeigen“, „Firmenlogo“ (max.
    256 KB)
  - „Standorte“, „Teams“, „Feiertage“ (siehe Abschnitt 8)
- **Arbeitszeit & Pausen:**
  - „Arbeitszeit“:
    - „Gleitzeitkonten führen ab“: Datum. Leer heißt ab der ersten Stempelung; eine Änderung
      rechnet alle Konten neu.
    - „Standardwerte für neue Mitarbeiter“
    - „Maximale Schichtlänge“
    - „Kernarbeitszeit & Gleitzeit“: Kernzeit, „Unter „Zu klären“ melden“ mit den Häkchen „Zu spät
      gekommen“, „Zu früh gegangen“ und „Außerhalb der Gleitzeit-Rahmenzeit“ (vorher ein eigener
      Schalter „Pünktlichkeit prüfen“), Toleranz und Gleitzeit-Rahmen. Das erzeugt nur Hinweise
      und kürzt keine Stunden. Hinweise gibt es erst ab dem Tag der letzten Änderung dieser Regeln,
      damit nicht die ganze Vergangenheit „zu klären“ ist. An Tagen mit Schicht (Uhrzeiten aus
      einer Schichtvorlage) gelten die Schichtzeiten, der Gleitzeit-Rahmen wird dann nicht geprüft.
      Je Mitarbeiter abweichend im Arbeitszeitmodell („Kernarbeitszeit / Pünktlichkeit“). Mit
      „Kernzeit je Wochentag unterschiedlich“ gilt je Tag eine eigene Kernzeit (z. B. freitags
      09:00–12:00) oder gar keine; speichern mit „Kernzeiten übernehmen“. „Keine Kernzeit“
      entfernt auch die Zeiten je Tag.
  - „Pausenregeln“ (siehe Abschnitt 8)
  - „Schichtplanung“: „Schichtplanung aktivieren“ und die Schichtvorlagen
- **Abwesenheiten & Urlaub:**
  - „Urlaub & Anträge“:
    - „Urlaubsanspruch“: „Standard-Jahresurlaub (Tage)“ (gilt, wenn im Vertrag kein
      Jahresurlaub steht), „Urlaubsanspruch für Teilzeit anteilig berechnen“, „Teilurlaub bei
      Eintritt oder Austritt im Jahr berechnen“ (bei Firmen, die HR3000 schon vor dem 05.11.2026
      genutzt haben, zunächst aus – dort galt bisher immer der volle Jahresurlaub)
    - „Urlaubsübertrag ins neue Jahr“
    - „Mitarbeiter dürfen Urlaub/Abwesenheiten beantragen“
    - „Vier-Augen-Prinzip: eigene Anträge genehmigt jemand anderes“ (an: Admin, HR und
      Teamleiter/innen bekommen eigene genehmigungspflichtige Abwesenheiten nicht direkt
      genehmigt, eine andere Person entscheidet unter „Zu klären“ → „Urlaubsanträge“; Standard aus)
  - „Abwesenheitsarten“ (siehe Abschnitt 6)
- **Stempeln & Tablets:**
  - „Stempeln“:
    - „Stempeln über den Web-Login (Home-Office)“: Stempel-Karte in „Mein Bereich“, mit
      Serverzeit
    - „Anmeldung am Tablet“ – eine Auswahl: „Kachel antippen“, „Kachel antippen + PIN“, „Kachel
      antippen oder Chip vorhalten“ (ein Chip öffnet den Mitarbeiter direkt, oben die Leiste „Aktion
      wählen, dann Chip vorhalten“), „Chip vorhalten oder Kachel + PIN“ (ein gültiger Chip ersetzt
      den PIN) oder „Nur Chip“ (Aktion wählen, dann Chip vorhalten; Kacheln lösen keine Stempelung
      aus). Bisher waren das fünf Schalter („PIN zum Stempeln erforderlich“, „Chips/RFID am Tablet
      nutzen“, „RFID-Pflicht“ …); bestehende Einstellungen gelten unverändert weiter.
    - Mit Chip zusätzlich „Mitarbeiter registrieren ihren Chip selbst“ (Namen antippen, „Eigenen
      Chip registrieren“, mit dem eigenen PIN bestätigen, Chip vorhalten).
    - Mit PIN bzw. Chip-Registrierung zusätzlich „PIN beim ersten Mal selbst festlegen“.
  - „Anzeige am Tablet“:
    - Saldo und Resturlaub nach dem Stempeln
    - „Pausen-Buttons anzeigen“, „Dienstgang-Buttons anzeigen“
    - „Darstellung am Tablet“ Dunkel/Hell
    - „Bildschirm nur zu bestimmten Zeiten anlassen“ (von–bis, über Mitternacht möglich; je
      Tablet abweichend einstellbar)
    - „Sortierung der Kacheln“
    - „Hinweistext über den Kacheln“
    - „Tablet-Admin-PIN“: wird zum Zurücksetzen des Tablets gebraucht.
  - „Tablets“ (siehe Abschnitt 8)
  - Änderungen erreichen die Tablets innerhalb von 30 Sekunden.
- **Prüfungen:** „„Zu klären““: welche Sonderfälle unter „Zu klären“ erscheinen (einzeln
  abschaltbare Häkchen). Das Häkchen „Arbeitstage ganz ohne Stempelung“ gilt auch für den
  Monatsbericht und den Lohn-Export: Ist es aus, gelten nur unvollständig gestempelte Tage als
  offen, und im Monatsbericht steht kein „Stempelung fehlt“ mehr. Das Soll zählt trotzdem, ein
  Arbeitstag ohne Stempelung geht also ins Minus. Zu spät, zu früh und Gleitzeit-Rahmen stehen
  unter „Arbeitszeit“.
- **Abrechnung:** „Zuschläge“ und „Lohnarten“ (siehe Abschnitt 7)
- **Konto:**
  - „Tarif & Konto“: „Tarif“; „Einstellungen übertragen“: „Exportieren“ speichert fachliche
    Einstellungen, Pausenregeln, Abwesenheitsarten und Zuschläge als Datei. „Datei importieren“
    (z. B. in einer neuen Firma) zeigt erst eine Vorschau, „Übernehmen“ wendet sie an.
    Einstellungen werden überschrieben, Pausenregeln, Abwesenheitsarten und Zuschläge nur
    ergänzt; kollidierende Pausenregeln werden übersprungen und angezeigt. Nicht übertragen
    werden Mailserver, Tablet-Admin-PIN, „Gleitzeitkonten führen ab“ und die
    DATEV-Berater-/Mandantennummer. „Konto kündigen“ steht zuletzt, siehe Abschnitt 11.
  - „E-Mail-Versand“: „E-Mail-Versand (SMTP)“, eigener Mailserver für Benachrichtigungen und
    Zugangsdaten, mit „Testmail an mich senden“
  - „Audit-Log“: wer wann was geändert hat, filterbar

## 10. Tablets im Betrieb

- Ein Android-Tablet mit Chrome reicht. Für Chips dient NFC oder ein USB- bzw.
  Bluetooth-Leser im Tastatur-Modus.
- Bei Netzausfall puffert das Tablet die Stempelungen und sendet sie automatisch nach. Offene
  Einträge zeigt die „Offline-Warteschlange“. Auch bei Störungen des Servers bleiben sie dort und
  werden erneut gesendet; als Fehler markiert werden nur echte Ablehnungen wie „PIN falsch“.
- Ist der Server beim Start des Tablets nicht erreichbar oder lehnt er die Anmeldung ab, zeigt das
  Tablet „Gerät einrichten“ mit einem Hinweis. Es bleibt aber gekoppelt und versucht es jede Minute
  erneut – nach einer Störung ist es von selbst wieder da. Neu koppeln muss man nur, wenn das Tablet
  in der HR-Webapp entfernt wurde.
- Bildschirm aus nach Zeitfenster: Das Tablet hält den Bildschirm nur im eingestellten Fenster
  wach. Morgens weckt man es per Ein/Aus-Taste. Mit einer Geräteverwaltung (z. B. Endpoint
  Central): Bildschirm-Timeout 1 Minute, „Beim Laden wach bleiben“ aus.
- Tablet neu koppeln: am Tablet „Gerät zurücksetzen“ (mit Tablet-Admin-PIN), dann den QR-Code
  erneut scannen.

## 11. Kündigen und Löschen

- **Kündigen:** „Einstellungen“ → „Tarif & Konto“ → „Konto kündigen“ → „HR3000 kündigen…“. Zur
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

