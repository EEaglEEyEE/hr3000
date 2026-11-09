# HR3000 – Handbuch für Admins, HR und Führungskräfte

Stand: 04.11.2026. Für Mitarbeiter: [Handbuch für Mitarbeiter](handbuch-mitarbeiter.md).
Bezeichnungen in „…“ entsprechen genau der Oberfläche.

## 1. Anmelden und Rollen

- Adresse der Firma: `https://<firma>.hr3000.de`, oder über `https://hr3000.de/login` mit dem
  Firmenkürzel. Admins, HR und Mitarbeiter nutzen dieselbe Anmeldeseite („E-Mail“, „Passwort“).
- **Ein Konto je Person:** Jede E-Mail-Adresse gibt es in der Firma nur einmal, egal ob für einen
  Mitarbeiter oder ein reines Verwaltungskonto (z. B. den Erst-Admin aus der Registrierung). Wer
  Mitarbeiter ist und eine Rolle hat, sieht mit einem Login die Verwaltung und „Mein Bereich“.
  Verwaltungskonten ohne Mitarbeiter haben kein „Mein Bereich“.
- Neue Firma: selbst unter `https://hr3000.de/registrieren`. Wer registriert, wird Erst-Admin
  mit dem selbst gewählten Passwort. Ist der Mailversand der Plattform eingerichtet, kommt
  vorher eine Bestätigungsmail; erst nach dem Klick auf den Link klappt die Anmeldung.
  Unbestätigte Registrierungen werden nach 7 Tagen gelöscht.
- Rollen (beim Mitarbeiter unter „HR-Berechtigung“, nur durch Admins):

| Rolle | Darf |
|---|---|
| Admin | alles, auch alle Bereiche der „Einstellungen“ und „Vergütung & Lohn-Export“ (siehe unten) |
| HR | Mitarbeiter, Abwesenheiten, „Zu klären“, „Monatsabschluss“, „Analysen“, „Lohn-Export“ (CSV ohne Beträge), „On- & Offboarding“, „Schichtplan-Kalender“; unter „Einstellungen“ „Standorte“, „Teams“, „Feiertagskalender“, „Schichtplanung“ (Schichtvorlagen), „Tablets“ und „Audit-Protokoll“; Vergütung und „Lohnarten“ nur mit „Vergütung & Lohn-Export“ |
| Führungskraft | „Tagesgeschäft“ für die eigenen Teams |
| Keine (nur Mein Bereich) | nur die eigene Ansicht, siehe Mitarbeiter-Handbuch |

- **„Vergütung & Lohn-Export“:** Admins haben es immer; HR bekommt es per Häkchen unter
  „HR-Berechtigung“ (Standard aus). Es öffnet überall dasselbe: Vergütung und „Zulagen &
  Einmalzahlungen“ unter „Personalakte“ → „Vertrag & Vergütung“, Bericht „Lohnkosten“, Beträge im
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
- **Zwei-Faktor-Anmeldung:**
  - **Selbst einrichten:** in der Seitenleiste „Zwei-Faktor-Anmeldung“ → „Einrichten“. Den
    QR-Code mit einer Authenticator-App scannen (z. B. Microsoft oder Google Authenticator), den
    6-stelligen Code eingeben, dann die 10 Wiederherstellungscodes sicher aufbewahren. Ab dann
    fragt die Anmeldeseite nach dem Passwort zusätzlich nach dem Code. Ein- und Ausschalten
    beendet alle anderen Sitzungen.
  - **Pflicht:** „Einstellungen“ → „Allgemein“ → „Zwei-Faktor-Anmeldung verpflichtend für“. Dort
    die Gruppen ankreuzen: Admin, HR, Führungskräfte, Mitarbeiter ohne Rolle oder „Alle“. Wer zu
    einer angekreuzten Gruppe gehört, richtet sie bei der nächsten Anmeldung ein und kann sie danach
    nicht selbst abschalten. Das Stempeln am Tablet bleibt unverändert. Standard: niemand.
  - **Handy verloren:** mit einem Wiederherstellungscode anmelden, oder ein Admin klickt im
    Mitarbeiter-Dialog „Zwei-Faktor-Anmeldung zurücksetzen“. Seine eigene setzt man nicht
    zurück; das macht ein anderer Admin.

## 2. Erste Schritte nach der Registrierung

1. **„Einstellungen“ → „Standorte“** → „Neuer Standort“: Name, Zeitzone, Bundesland. Das
   Bundesland bestimmt die Feiertage.
2. **„Einstellungen“:** unter „Arbeitszeit“ „Überstundenkonten führen ab“, unter „Urlaub &
   Anträge“ den „Standard-Jahresurlaub“, unter „Allgemein“ das „Standard-Bundesland“.
3. **„Mitarbeiter“** → „Neuer Mitarbeiter“ oder „CSV-Import“.
   - Umstieg von einem anderen System: auf derselben Seite unter „Werte aus dem Altsystem
     übernehmen“ eine zweite CSV hochladen (Pflichtspalte `personalnummer`). Optional sind
     `saldo_stunden` (Überstunden-Übertrag, auch negativ), `urlaubsanspruch_tage` und
     `uebertrag_vorjahr_tage` für das Jahr des Stichtags sowie das Arbeitszeitmodell ab Stichtag
     (`wochenstunden`, `arbeitstage`, `tagesstunden`, `monatsstunden`, `monatsgrenze`,
     `pause_minuten`). Leere Zellen ändern nichts.
   - „Stichtag“ wählen, „Vorschau“ prüfen, dann „Übernehmen“. Fehlerhafte Zeilen werden
     übersprungen und angezeigt. Ein zweiter Überstunden-Übertrag zum selben Stichtag wird
     abgelehnt, ebenso Änderungen in abgeschlossenen Monaten. Rechnet das Überstundenkonto schon vor
     dem Stichtag („Überstundenkonten führen ab“ früher oder ältere Stempelungen), wird der Übertrag
     abgelehnt, weil die Tage dazwischen sonst doppelt zählen: „Überstundenkonten führen ab“ auf den
     Stichtag setzen.
   - Wer mitten im Jahr umsteigt: als `urlaubsanspruch_tage` den restlichen Anspruch für den Rest
     des Jahres eintragen, da bereits genommener Urlaub nicht im neuen System steht. Der Wert gilt
     dann fest für dieses Jahr; ab dem Folgejahr wird der Anspruch berechnet.
4. **„Einstellungen“ → „Tablets“** → „Neues Tablet“, dann „QR-Code“ und mit dem Tablet scannen. Die
   Tablet-Adresse ist `https://kiosk.<firma>.hr3000.de`.
5. Optional unter „Einstellungen“: „Pausenregeln“ prüfen (die gesetzliche Staffel nach § 4 ArbZG
   ist vorbelegt), „Teams“ anlegen, „Abwesenheitsarten“ anpassen.

## 3. Menü

- **Tagesgeschäft:** „Startseite“, „Mitarbeiter“, „Anwesenheit“, „Kalender“, „Organigramm“, „Zu
  klären“ (der Posteingang mit Urlaubs- und Korrekturanträgen; die rote Zahl zählt alles Offene)
- **Planung & Abrechnung:** „Schichtplan-Kalender“ (nur mit eingeschalteter Schichtplanung),
  „Monatsabschluss“, „Analysen“, „Lohn-Export“, „On- & Offboarding“
- **Unten:** „Mein Bereich“ (wenn der Login zu einem Mitarbeiter gehört), „Einstellungen“ (Admin
  und HR, je nach Rolle mit unterschiedlichen Bereichen), „Darstellung“ (Hell/Dunkel/Wie System),
  „Abmelden“
- Standorte, Teams, Abteilungen, Kostenstellen, Feiertage, Tablets, Pausenregeln, Schichtvorlagen, Zuschläge, Lohnarten und
  das Audit-Protokoll stehen unter „Einstellungen“ (siehe Abschnitt 9); alte Links und Lesezeichen
  führen dorthin.
- **Glocke:** Benachrichtigungen, mit „Alle als gelesen markieren“; unten jeder für sich
  „Benachrichtigungen auch per E-Mail“ (wirkt nur, wenn die Firma einen Mailversand eingerichtet hat)

## 4. Tagesgeschäft

- **Startseite:**
  - eigene Werte: „Überstundenkonto“, „Resturlaub“, „Heute“, „Diese Woche“
  - Kacheln „Zu klären“ und „Urlaubsanträge“ (öffnet „Zu klären“ → „Urlaubsanträge“; nur sichtbar,
    wenn Anträge erlaubt sind oder welche offen sind)
  - „Heute“: Anwesend / In Pause / Dienstgang / Abwesend
  - „Nächste Termine“
- **Anwesenheit:** Wochenraster („Vorherige Woche“ / „Nächste Woche“ / „Heute“).
- **Kalender:** Monatsansicht mit Abwesenheiten, Feiertagen und Geburtstagen, Filter „Teams:“.
  „Kalender abonnieren (iCal)“ erzeugt einen privaten Abo-Link für Outlook, Google oder Apple
  Kalender (Abwesenheiten aller sichtbaren Mitarbeiter und Feiertage). Den Link wie ein Passwort
  behandeln; ein neuer Link macht den alten ungültig, „Abo beenden“ schaltet ihn ab.
- **Zu klären** – der Posteingang mit vier Reitern, jeweils mit der Anzahl des Offenen:
  „Tage“, „Korrekturanträge“ (nur Admin und HR), „Urlaubsanträge“, „Grenzen“ und
  „Datenänderungen“ (nur Admin und HR).
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
- **„Datenänderungen“:** Vorschläge der Mitarbeiter zu ihren eigenen Daten (Adresse, Bank, Steuer,
  eigene Felder aus Abschnitten mit „schlagen Änderungen vor“), je Feld alt → neu, „Übernehmen“ oder
  „Ablehnen“ mit optionalem Hinweis. Mit Bank-, Steuer- oder SV-Angaben entscheidet nur, wer
  „Vergütung & Lohn-Export“ hat. Eigene Vorschläge übernimmt jemand anderes.
- **„Urlaubsanträge“:** „Genehmigen“ / „Ablehnen“. Führungskräfte sehen die Anträge, die gerade bei
  ihnen liegen (ihr Team bzw. als Führungskraft oder Vertretung, je nach „Genehmigt von“ der Art).
  Je Antrag stehen dort der Resturlaub des Jahres (bei Urlaub) und wer aus demselben Team im
  Zeitraum ebenfalls abwesend ist oder es beantragt hat.
  Früher ein eigener Menüpunkt; alte Links führen hierher.
- **„Grenzen“:** Aushilfen „nach Aufwand“ ab 90 % ihrer Monatsgrenze und – wenn unter
  „Einstellungen“ → „Arbeitszeit“ → „Grenzen fürs Überstundenkonto“ eingestellt – Überstundenkonten
  ab 90 % der Obergrenze oder unter der Untergrenze. Das Konto wird nicht gekappt.

## 5. Mitarbeiter

- **Liste:** Suche, Standortfilter, „Auch inaktive anzeigen“, Hinweis auf die Tarifgrenze.
  „Bearbeiten“ öffnet den Mitarbeiter direkt im Reiter „Einstellungen“.
- **„Organigramm“:** baut sich aus der „Führungskraft“ je Mitarbeiter auf. Oben stehen alle ohne
  (aktive) Führungskraft, darunter ihre Mitarbeiter, je Person mit Position und Abteilung; die Zahl
  zeigt, wie viele im Bereich sind. Suche nach Name, Position oder Abteilung. Mitarbeiter sehen es
  in „Mein Bereich“ nur, wenn unter „Einstellungen“ → „Allgemein“ „Mitarbeiter sehen das
  Organigramm“ an ist.
- **Dialog „Neuer Mitarbeiter“ und Reiter „Einstellungen“:** Angelegt wird im Dialog „Neuer
  Mitarbeiter“, geändert im Reiter „Einstellungen“ der Detailseite – mit denselben Feldern. Dort
  übernimmt „Speichern“ die Änderungen, „Änderungen verwerfen“ holt die gespeicherten Werte zurück.
  - Oben die Grunddaten: Vor- und Nachname, Personalnummer, Standort („Standortwechsel gilt ab“),
    Team, „Abteilung“, „Position“, „Führungskraft“, „Vertretung bei Genehmigungen“, „Anstelldatum“.
  - Nur beim Anlegen „Arbeitszeitmodell“: „Standard aus den Einstellungen“ (wenn dort eines
    hinterlegt ist), ein „Arbeitszeitmodell „…““ (wenn es Modelle gibt, siehe Abschnitt 8),
    „Stunden je Wochentag“, „Nach Aufwand (Aushilfe, ohne Soll)“ oder „Kein Arbeitszeitmodell (ohne
    Soll, z. B. reines HR-Konto)“. Gilt ab Eintritt; Wochen- oder Monatsstunden, Pausen und
    Kernzeit im Reiter „Arbeitszeit“.
  - „Weitere Angaben (Austritt, Geburtstag, Aktiv, Pausen)“: „Aktiv“, Austritts- und
    Geburtsdatum, „Pausen automatisch stempeln (nach Pausenregeln)“. Beim Anlegen eingeklappt.
  - „Login und Stempeln am Tablet (E-Mail, Passwort, PIN, Chip)“: „Login (Mein Bereich)“ mit
    Login-E-Mail und Passwort, „Stempel-PIN (Tablet)“ mit „PIN zurücksetzen“, „Chip
    (Tablet)“ mit „Chip-UID (optional)“ und „QR-Code fürs Tablet“: Der QR-Code gilt am Tablet wie
    der Chip („QR-Code scannen“, Frontkamera); ohne Chip vergibt HR3000 eine zufällige Chip-UID
    (dann speichern). „Drucken“ für einen Ausdruck. Beim Anlegen eingeklappt.
  - „HR-Berechtigung“ (nur im Reiter „Einstellungen“, nur Admin): wirkt sofort, ohne „Speichern“.
  - Die Kernarbeitszeit steht im Arbeitszeitmodell (Reiter „Arbeitszeit“), damit sie mit
    jeder Fassung „gilt ab“ hat.
- **Detailseite:** Knöpfe „Monatsbericht“, „DSGVO-Datenexport“, „Anonymisieren“ (nur bei
  Ausgeschiedenen). Reiter:
  - „Zeiterfassung“: „Stempelung nachtragen“, „Korrigieren“, „Endgültig löschen“
  - „Kalender“
  - „Überstundenkonto“: Überstundenkonto, Wochen- und Tagesansicht, „Korrekturbuchungen
    Überstundenkonto“ mit der „Aktion“:
    - „Kontostand anpassen (+/−)“: Plus- oder Minusbuchung mit Begründung
    - „Neuen Kontostand festlegen“: Stand am Ende des gewählten Tages; gebucht wird die Differenz
    - „Überstunden auszahlen“: Stunden und „Faktor“ (z. B. 1,5 für 50 % Zuschlag). Das Konto sinkt
      um die Stunden; der Lohn-Export zeigt sie zusätzlich gewichtet.
    - „Anfangskontostand (Altsystem/Vorjahr)“
    Freizeitausgleich nimmt man als Abwesenheit der Kategorie „Freizeitausgleich“ – sie senkt das
    Konto um das Tagessoll.
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
    - „Urlaubskonto korrigieren (± Tage)“: zusätzliche oder abgezogene Tage mit „Begründung“, optional
      „Verfällt am“ (nur bei Plus-Tagen). Verbraucht wird zuerst, was am frühesten verfällt – auch
      gegenüber dem Übertrag. Die Korrekturen stehen im Konto und sind für den Mitarbeiter sichtbar.
    - „Bearbeiten“: Ein geänderter Anspruch gilt fest für dieses Jahr („Anspruch (fest
      eingetragen)“); „Wieder berechnen“ bzw. „Anspruch wieder berechnen“ hebt das auf. Bei „Nach
      Aufwand (Aushilfe)“ wird mit Teilzeit-Anteil nichts berechnet, der Anspruch wird eingetragen.
  - „Arbeitszeit“: alles zur regelmäßigen Arbeitszeit an einer Stelle – oben das
    Arbeitszeitmodell, mit eingeschalteter Schichtplanung darunter „Schichtplanung“ (siehe unten).
    Das Arbeitszeitmodell jeweils mit „Gültig ab“ und „Verlauf“ (jede Fassung mit „Bearbeiten“ /
    „Löschen“). Entweder ein Arbeitszeitmodell oder individuelle Angaben:
    - „Arbeitszeitmodell zuweisen“ (nur wenn es Modelle gibt): „Arbeitszeitmodell“ und „Modell
      gültig ab“, dann „Modell zuweisen“. Soll, Arbeitstage, Pause, Kernzeit, Gleitzeit-Rahmen und
      Toleranz kommen aus dem Modell und folgen automatisch dessen Änderungen. „Aktuell gültig“ und
      der „Verlauf“ nennen das Modell.
    - Darunter individuell eintragen („Neues Arbeitszeitmodell ab Stichtag“, bei einem Modell
      „Individuell eintragen ab Stichtag (statt zugewiesenem Modell)“) – beendet ein Modell ab diesem
      Tag. Wer eine Modell-Fassung mit „Bearbeiten“ ändert, macht sie ebenfalls individuell.
    Die Angaben im Einzelnen:
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
  - „Personalakte“ (Admin und HR) mit den Unterreitern „Stammdaten“, „Weitere Angaben“, „Vertrag“
    (mit „Vergütung & Lohn-Export“ „Vertrag & Vergütung“), „Dokumente“, „On- & Offboarding“ und
    „Verlauf“.
  - „Weitere Angaben“: die eigenen Felder der Firma (siehe „Felder der Personalakte“). Bei Feldern
    mit Verlauf gibt es ein „Gültig ab“ (leer = heute), darunter die früheren und künftigen Werte
    mit „entfernen“.
  - „Verlauf“: was sich am Mitarbeiter wann geändert hat und wer es war (aus dem
    Audit-Protokoll; Vergütung nur mit „Vergütung & Lohn-Export“).
  - „Stammdaten“: Status (Onboarding, Aktiv, Auszeit, Inaktiv – ergibt sich aus Eintritt,
    Austritt, „Aktiv“ und laufender Elternzeit/Pflegezeit), Kostenstellen (auch anteilig, zusammen
    100 %), „Kontakt und Adresse“, „Person und Familie“ (u. a. Kinder, Kinderfreibeträge) und mit
    „Vergütung & Lohn-Export“ „Lohn: Bank, Steuer, Sozialversicherung“ (IBAN, Steuer-ID,
    Steuerklasse, SV-Nummer, Krankenkasse). Die Angaben liegen verschlüsselt; IBAN, Steuer-ID und
    SV-Nummer werden auf ihr Format geprüft. Der Status steht auch in der Mitarbeiterliste.
  - „Vertrag“ bzw. „Vertrag & Vergütung“: „Neuer Vertragsabschnitt“ mit
    „Jahresurlaub (Tage, 5-Tage-Woche)“: leer heißt „Standard-Jahresurlaub“ aus den Einstellungen;
    daraus wird der Urlaubsanspruch je Jahr berechnet (siehe „Abwesenheiten“). Dort zusätzlich
    „Zulagen & Einmalzahlungen“:
    - „Neue Zulage“: „Je Monat“ (in angebrochenen Monaten anteilig nach Kalendertagen) oder „Je
      Stunde (auf den Stundenlohn)“ (Betrag × Ist-Stunden), mit „Gültig ab“ und optional „Gültig
      bis“. Laufende Zulagen mit „Beenden“ abschließen.
    - „Neue Einmalzahlung“, z. B. Weihnachtsgeld, mit „Auszahlung am“ – als Betrag oder „in % des
      Monatsgehalts“ (z. B. 50 = Urlaubsgeld, 100 = 13. Monatsgehalt; berechnet mit dem Monatsgehalt am
      Zahltag, ohne Monatsgehalt 0 €). Mit „jährlich wiederholen“ jedes Jahr am selben Tag, bis
      „Beenden“.
    - „Bezeichnung“ schlägt die Arten aus „Lohnarten“ vor; ein neuer Name legt dort eine neue Art an
      (dann optional mit „Lohnart“). Die Lohnart einer vorhandenen Art steht nur unter „Lohnarten“.
      Inaktive Arten lassen sich nicht neu vergeben.
    - Beträge nur mit „Vergütung & Lohn-Export“; im Audit-Protokoll steht jede Änderung ohne Betrag. Abgeschlossene
      Monate lassen sich nicht mehr ändern.
  - „Dokumente“: verschlüsselt abgelegt; mit „Für den Mitarbeiter in Mein Bereich sichtbar“
    und „Vertraulich“
  - „On- & Offboarding“
  - „Schichtplanung“ (im Reiter „Arbeitszeit“): „Regelmäßige Arbeitszeit“ (aus dem
    Arbeitszeitmodell, nur lesend) und „Ausnahmen“ für einzelne Tage. Bei „Flexibel“ und „Nach Aufwand“ liefert eine geplante Schicht
    nur die Uhrzeiten, kein Tagessoll.
  - „Einstellungen“ (Admin und HR): Grunddaten, Login, PIN, Chip und HR-Berechtigung des
    Mitarbeiters (siehe oben); ersetzt den früheren Knopf „Bearbeiten“.
- **Tarif:**
  - Bis 5 aktive Mitarbeiter ist alles kostenlos.
  - Ab 6 aktiven Mitarbeitern kostet jeder aktive Mitarbeiter 1 € im Monat; freigeschaltet wird
    über den Anbieter.
  - Ausgeschiedene Mitarbeiter zählen nicht.

## 6. Abwesenheiten

- **Arten** unter „Einstellungen“ → „Abwesenheitsarten“:
  - je Art Name, Farbe und Kategorie
  - Kategorien: Urlaub, Krankheit, Kind krank, Sonderurlaub, Feiertag, Arbeitszeit, Unbezahlt,
    Freizeitausgleich, Mutterschutz/Elternzeit, Kurzarbeit, Unentschuldigt, Pflege von Angehörigen.
    Die letzten vier rechnen wie „Unbezahlt“ (das Soll entfällt), stehen im „Lohn-Export“ aber in
    einer eigenen Spalte, sobald sie im Monat vorkommen; im „Monatsbericht“ und in den „Analysen“
    zählen sie unter „Unbezahlt“.
  - „Mitarbeiter dürfen selbst beantragen“, „Genehmigung nötig“, „Nachweis ab Tag“,
    „Deaktivieren“
  - „Genehmigt von“ (bei „Genehmigung nötig“): „Teamleitung oder Admin/HR“ (Standard, wie
    bisher), „Führungskraft“ (die Führungskraft am Mitarbeiter, wenn sie eine Rolle und einen Zugang
    hat), „erst Führungskraft, dann Admin/HR“ (zwei Schritte) oder „nur Admin/HR“. Ist die
    Führungskraft heute abwesend und hat eine „Vertretung bei Genehmigungen“ (Mitarbeiter-Dialog),
    entscheidet die Vertretung. Ohne passende Führungskraft entscheiden Admin und HR. Admin und HR
    dürfen jeden Schritt entscheiden. Bei wem ein Antrag gerade liegt, steht als „Wartet auf“ in den
    Anträgen und beim Mitarbeiter.
  - „Kommentar erforderlich“: Die „Notiz“ ist dann beim Eintragen Pflicht (nicht bei Krankheit und
    Kind krank – dort würden Gesundheitsdaten abgefragt).
  - Bei Arten mit „Nachweis ab Tag“ steht in der Liste „Nachweis hochladen“ (PDF, PNG, JPEG): für
    den Mitarbeiter selbst und für alle, die über ihn entscheiden. Der Nachweis liegt danach unter
    „Dokumente“ (bei Krankheit als „Krankmeldung“) und ist für den Mitarbeiter sichtbar.
  - „Vertretung“: „nicht abfragen“, „optional“ oder „Pflicht beim Antrag“. Dann gibt es im Antrag das
    Feld „Vertretung“ (aktive Kolleginnen und Kollegen). Pflicht gilt nur für Anträge der Mitarbeiter
    selbst; HR darf es leer lassen. Die Vertretung bekommt eine Benachrichtigung, sobald die
    Abwesenheit gilt (sofort oder nach der Genehmigung), und steht in der Liste und unter
    „Zu klären“ → „Urlaubsanträge“.
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
  - Abgeschlossene Monate lassen sich nicht mehr ändern. Auch „Überstundenkonten führen ab“,
    „Schichtplanung aktivieren“ und „Maximale Schichtlänge“ lassen sich nur ändern, solange davon
    kein vorgelegter oder abgeschlossener Monat betroffen ist.
- **„Analysen“:**
  - Reiter: Handlungsbedarf (BEM, Probezeit, Befristung, Austritt, Dokumente mit abgelaufener
    Aufbewahrungsfrist – nur Hinweis, gelöscht wird nichts automatisch), Fehlzeiten, Urlaub,
    Überstunden, Lohnkosten (nur mit „Vergütung & Lohn-Export“; mit Spalte „Zulagen“ für Zulagen und
    Einmalzahlungen im Zeitraum)
  - jeweils „CSV exportieren“
- **„Lohn-Export“:** Monat (vorbelegt: Vormonat) und Standort wählen, CSV für das Lohnbüro.
  Exportiert werden alle, die im Monat beschäftigt waren – auch wer im Monat ausgetreten ist. Mit
  „Vergütung & Lohn-Export“ kommt je Zulage bzw. Einmalzahlung eine Spalte mit dem Betrag im Zeitraum
  dazu (z. B. „Zulage Fahrtkosten (€)“, „Einmalzahlung Weihnachtsgeld (€)“), sonst fehlen diese
  Spalten.
  „Ausgezahlte Überstunden (Std.)“ zeigt die Auszahlungen aus den „Korrekturbuchungen
  Überstundenkonto“ mit Datum im Zeitraum; gab es eine Auszahlung mit Faktor, kommt die Spalte
  „Ausgezahlte Überstunden gewichtet (Std.)“ dazu (DATEV: Stunden ungewichtet, mit Hinweis). Über dem Export steht der Stand des „Monatsabschluss“
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
„On- & Offboarding“ im Menü.

- **„Arbeitszeitmodelle“** (Admin und HR) – z. B. „Vollzeit Büro“ oder „Teilzeit 30 Std.“, einmal
  angelegt und vielen Mitarbeitern zugewiesen:
  - „Neues Arbeitszeitmodell“: „Name“ und dieselben Angaben wie ein Arbeitszeitmodell („Modell“,
    „Soll“, „Schichtvorlage (Uhrzeiten, optional)“, „Pause“, „Kernarbeitszeit / Pünktlichkeit“),
    dazu „Gleitzeit-Rahmen“ („Wie Einstellungen“, „Eigener Rahmen“ mit „Rahmen von“ / „Rahmen
    bis“, „Kein Rahmen“) und „Toleranz der Pünktlichkeitsprüfung (Minuten)“ (leer = wie in den
    Einstellungen). Ein neues Modell gilt von Anfang an, kann also auch rückwirkend zugewiesen
    werden.
  - „Ändern ab Stichtag“: neue Fassung mit „Gültig ab“ – gilt für **alle zugewiesenen
    Mitarbeiter** ab diesem Tag, die Zeit davor bleibt unverändert. Hat einer davon ab diesem Tag
    einen vorgelegten oder abgeschlossenen Monat, wird nichts geändert; die Meldung nennt die
    Betroffenen.
  - „Verlauf“ zeigt die Fassungen, „Umbenennen“ ändert nur den Namen.
  - „Archivieren“: nicht mehr neu zuweisbar, bestehende Zuweisungen gelten weiter („Archivierte
    Modelle anzeigen“, „Wieder aktivieren“). „Löschen“ geht nur, solange das Modell nie zugewiesen
    war.
  - Zugewiesen wird am Mitarbeiter (Reiter „Arbeitszeit“) oder beim Anlegen. Je Mitarbeiter gilt
    entweder ein Modell oder die individuelle Eingabe.

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
- **„Feiertagskalender“:** je Standort automatisch importiert; eigene Feiertage mit „Feiertag
  hinzufügen“.
  Mit „Halber Tag“ (z. B. Heiligabend, Silvester) gilt an dem Tag das halbe Soll – die andere
  Hälfte wird normal gestempelt; ein Urlaubstag zählt dort als halber Tag. Bei Stundenlohn wird die
  freie Hälfte nicht als Feiertag vergütet (sonst eine Abwesenheit der Kategorie „Feiertag“ mit
  Stunden eintragen).
- **„Teams“:** Teams anlegen, Führungskräfte zuordnen.
- **„Kostenstellen“:** Nummer und Bezeichnung; benutzte archivieren statt löschen.
- **„Dokumentkategorien“** (nur Admin): eigene Kategorien neben den festen, je mit „Mitarbeiter dürfen
  hochladen“, „für Mitarbeiter sichtbar (Vorgabe)“ und „vertraulich (nur Admins)“. Beim Hochladen in
  der Personalakte stehen sie in der Auswahl „Kategorie“ und setzen Sichtbarkeit und Vertraulichkeit
  vor. Lädt ein Mitarbeiter selbst hoch, bekommen Admin und HR eine Benachrichtigung.
- **„Dokumentvorlagen“** (nur Admin): Name, Kategorie in der Akte, „für Mitarbeiter sichtbar“ und
  der Text. Absätze durch Leerzeilen, „# “ für eine Überschrift, **fett**. Platzhalter in doppelten
  geschweiften Klammern, z. B. {{vorname}}, {{nachname}}, {{personalnummer}}, {{position}},
  {{abteilung}}, {{standort}}, {{eintrittsdatum}}, {{austrittsdatum}}, {{geburtsdatum}}, {{strasse}},
  {{plz}}, {{ort}}, {{firma}}, {{heute}} und eigene Felder als {{feld:Bezeichnung}}. Am Mitarbeiter unter
  „Dokumente“ → „Aus Vorlage erstellen“: „Vorschau“ oder „In die Akte legen“ (PDF mit Firmenlogo).
  Unbekannte Platzhalter brechen ab, damit kein halbfertiges Dokument entsteht.
- **„Felder der Personalakte“** (nur Admin): eigene Abschnitte mit „Sichtbar“ (nur Admin/HR,
  Mitarbeiter sehen es, Mitarbeiter sehen es und schlagen Änderungen vor) und Felder der Art Text,
  Zahl, Datum, Auswahl, Ja/Nein oder Person, auf Wunsch „mit Verlauf“. Art und Verlauf lassen sich
  später nicht ändern; nicht mehr gebrauchte Felder und Abschnitte archivieren.
- **„Abteilungen“:** Abteilungen anlegen und verschachteln („Übergeordnete Abteilung“, z. B.
  Vertrieb → Innendienst). Löschen geht nur bei leeren Abteilungen. Teams bleiben daneben für
  Schichtplanung und die Sicht der Führungskräfte.
- **„Tablets“:**
  - „Neues Tablet“: Name, Standort, „Gerätename im MDM“ (optional, siehe Abschnitt 10 „Tablets per
    MDM verteilen“), Darstellung, Bildschirmzeiten
  - „QR-Code“: Mit der Kamera scannen öffnet die Tablet-App fertig eingerichtet. Ohne Kamera gibt
    es einen Kopplungscode zum Eintippen. Der Code gilt einmal und 15 Minuten.
  - Jeder Tablet-Eintrag gilt für **genau ein Gerät**. Die Spalte „Gekoppelt“ zeigt, seit wann ein
    Tablet daran hängt. Versucht ein anderes Gerät, sich mit demselben Zugang anzumelden, wird es
    abgewiesen. Admins und HR bekommen dann eine Warnung (Glocke und E-Mail, höchstens einmal pro
    Stunde), die Liste zeigt „Anderes Gerät abgewiesen“ und das Audit-Protokoll einen Eintrag.
    Für ein weiteres Tablet einen eigenen Eintrag anlegen.
  - „Bearbeiten“, dort „Kopplung aufheben“ (z. B. bei Verlust des Tablets): Das bisherige Tablet ist
    sofort abgemeldet, danach mit dem QR-Code neu koppeln.
  - Reiter „Verteilung per MDM“: Registrierungsschlüssel je Standort, damit eine Geräteverwaltung
    (MDM) viele Geräte ohne QR-Code einrichtet. Geräte, die sich damit melden, erscheinen oben unter
    „Neue Geräte warten auf Freigabe“. Ablauf in Abschnitt 10.
- **„On- & Offboarding“:** Vorlagen für On- und Offboarding, offene Aufgaben „Als erledigt
  markieren“.
  - Je Aufgabe eine „Aktion“: „Abhaken“ (wie bisher), „Person lädt Dokument hoch“ (Kategorie
    wählen; die neue Person lädt in „Mein Bereich“ unter „Meine Aufgaben“ hoch, damit ist die Aufgabe
    erledigt), „Person trägt Daten ein“ (z. B. Bankdaten über „Änderung vorschlagen“) und „E-Mail beim
    Start senden“ (Text mit Platzhaltern wie in Dokumentvorlagen; an die Person, ihre Führungskraft
    oder Admin/HR, je nach „Zuständig“; ohne Mailversand bleibt die Aufgabe offen mit Hinweis).
- **„Audit-Protokoll“:** wer wann was geändert hat, dazu Anmeldungen in der Webapp (ohne
  IP-Adresse); filterbar, mit „CSV exportieren“ (die angezeigten Einträge, höchstens 500).

## 9. Einstellungen

Grundsatz: Neue Funktionen sind einzeln schaltbar und standardmäßig so eingestellt, dass sich
für bestehende Firmen nichts ändert.

- **Aufbau:** links die Bereiche nach Themen, auf dem Handy eine Auswahlliste. Admins sehen alle
  Bereiche. HR sieht „Standorte“, „Teams“, „Feiertagskalender“, „Schichtplanung“ (nur die Schichtvorlagen,
  wenn die Schichtplanung an ist), „Tablets“ und „Audit-Protokoll“, mit „Vergütung & Lohn-Export“ auch
  „Lohnarten“. Kann eine Änderung nicht gespeichert werden (z. B. weil ein Monat schon vorgelegt
  oder abgeschlossen ist), steht der Grund oben im Bereich.
- **Unternehmen:**
  - „Allgemein“: „Standard-Bundesland“, „Geburtstage im Kalender anzeigen“, „Firmenlogo“ (max.
    256 KB), „Erinnerungen an Admin und HR“ (Standard aus): einmal am Tag als Benachrichtigung und –
    mit Mailversand – per E-Mail: Probezeit endet in 14 Tagen, Befristung endet in 30 Tagen, Austritt
    in 14 Tagen, Resturlaub aus dem Vorjahr verfällt in 30 Tagen (das auch an die Person selbst)
  - „Standorte“, „Teams“, „Feiertagskalender“ (siehe Abschnitt 8)
- **Arbeitszeit & Pausen:**
  - „Arbeitszeit“:
    - „Überstundenkonten führen ab“: Datum. Leer heißt ab der ersten Stempelung; eine Änderung
      rechnet alle Konten neu.
    - „Standardwerte für neue Mitarbeiter“
    - „Maximale Schichtlänge“
    - „Grenzen fürs Überstundenkonto“: „Obergrenze (Std.)“ und „Untergrenze (Minusstunden)“, leer =
      keine Grenze (Hinweis unter „Zu klären“ → „Grenzen“)
    - „Kernarbeitszeit & Gleitzeit“: Kernzeit, „Unter „Zu klären“ melden“ mit den Häkchen „Zu spät
      gekommen“, „Zu früh gegangen“ und „Außerhalb der Gleitzeit-Rahmenzeit“ (vorher ein eigener
      Schalter „Pünktlichkeit prüfen“), Toleranz und Gleitzeit-Rahmen. Das erzeugt nur Hinweise
      und kürzt keine Stunden. Hinweise gibt es erst ab dem Tag der letzten Änderung dieser Regeln,
      damit nicht die ganze Vergangenheit „zu klären“ ist. An Tagen mit Schicht (Uhrzeiten aus
      einer Schichtvorlage) gelten die Schichtzeiten, der Gleitzeit-Rahmen wird dann nicht geprüft.
      Je Mitarbeiter abweichend im Arbeitszeitmodell („Kernarbeitszeit / Pünktlichkeit“);
      Gleitzeit-Rahmen und Toleranz lassen sich je Arbeitszeitmodell abweichend festlegen
      (Abschnitt 8). Mit „Kernzeit je Wochentag unterschiedlich“ gilt je Tag eine eigene Kernzeit (z. B. freitags
      09:00–12:00) oder gar keine; speichern mit „Kernzeiten übernehmen“. „Keine Kernzeit“
      entfernt auch die Zeiten je Tag.
  - „Pausenregeln“ (siehe Abschnitt 8)
  - „Schichtplanung“: „Schichtplanung aktivieren“ und die Schichtvorlagen
- **Abwesenheiten & Urlaub:**
  - „Urlaub & Anträge“:
    - „Urlaubsanspruch“: „Standard-Jahresurlaub (Tage)“ (gilt, wenn im Vertrag kein
      Jahresurlaub steht), „Urlaubsanspruch für Teilzeit anteilig berechnen“, „Teilurlaub bei
      Eintritt oder Austritt im Jahr berechnen“ (bei Firmen, die HR3000 schon vor dem 05.11.2026
      genutzt haben, zunächst aus – dort galt bisher immer der volle Jahresurlaub), „Urlaub bei
      Elternzeit kürzen“ (je vollem Kalendermonat mit Abwesenheit der Kategorie
      „Mutterschutz/Elternzeit“ 1/12 weniger, § 17 BEEG; Standard aus)
    - „Zusatzurlaub nach Betriebszugehörigkeit“: Stufen „ab … Jahren + … Tage“ (5-Tage-Woche, bei
      Teilzeit anteilig), gültig ab dem Kalenderjahr, in dem die Jahre vollendet werden; nur mit
      hinterlegtem Jahresurlaub
    - „Urlaubsübertrag ins neue Jahr“
    - „Mitarbeiter dürfen Urlaub/Abwesenheiten beantragen“
    - „Mitarbeiter sehen den Teamkalender ihres Teams“ (Standard aus): Reiter „Teamkalender“ in
      „Mein Bereich“. Die Art steht nur bei Abwesenheitsarten mit „Im Teamkalender: farbig (mit Art)“
      (unter „Abwesenheitsarten“, Standard „ausgegraut“), sonst nur, dass jemand fehlt; Homeoffice-
      Angaben erscheinen dort nicht.
    - „Mitarbeiter sehen beim Antrag, wer im Team gleichzeitig abwesend ist“ (nur Name und Zeitraum,
      ohne Art; Standard aus). Im Antrag von HR steht der Hinweis immer, mit Art.
    - „Vier-Augen-Prinzip: eigene Anträge genehmigt jemand anderes“ (an: Admin, HR und
      Führungskräfte bekommen eigene genehmigungspflichtige Abwesenheiten nicht direkt
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
    werden Mailserver, Tablet-Admin-PIN, „Überstundenkonten führen ab“ und die
    DATEV-Berater-/Mandantennummer. „Konto kündigen“ steht zuletzt, siehe Abschnitt 11.
  - „E-Mail-Versand“: „E-Mail-Versand (SMTP)“, eigener Mailserver für Benachrichtigungen und
    Zugangsdaten, mit „Testmail an mich senden“
  - „Audit-Protokoll“: wer wann was geändert hat und Anmeldungen, filterbar, mit „CSV exportieren“

### API & Webhooks

Unter „Einstellungen“ → „API & Webhooks“ (nur Admins) verbindet ihr Fremdsysteme, z. B. Lohnsoftware,
Zutrittskontrolle oder Auswertungen.

- **API-Zugang anlegen:** Name und Rechte („Mitarbeiter lesen“, „Abwesenheiten lesen“, „Stempelungen
  lesen“). Client-ID und Secret erscheinen nur einmal – sicher ablegen. „Sperren“ beendet den Zugang
  sofort, auch bereits ausgegebene Tokens.
- **Abruf:** Immer über die Adresse der Firma, z. B. `https://firma.hr3000.de/api/v1/…`.
  1. Token holen: `POST /api/v1/auth/token` mit JSON `{"client_id": "…", "client_secret": "…"}`.
     Antwort `access_token` (1 Stunde gültig).
  2. Abrufen mit Kopfzeile `Authorization: Bearer <access_token>`:
     - `GET /api/v1/employees?limit=100&offset=0&active=true`: Personalnummer, Name, Login-E-Mail,
       Status, Ein-/Austritt, Standort, Team, Abteilung, Position, Führungskraft
     - `GET /api/v1/absence-types`
     - `GET /api/v1/absences?from=2026-01-01&to=2026-01-31&employee_id=…`: Zeitraum höchstens ein Jahr,
       mit Status (APPROVED, PENDING, REJECTED)
     - `GET /api/v1/punches?from=…&to=…&employee_id=…`: Stempelungen, Zeitpunkte in UTC
  Antworten mit `data` und `page` (`limit`, `offset`, `total`). Die API liest nur. Je Zugang höchstens
  1200 Anfragen in 10 Minuten.
- **Webhooks:** https-Adresse und Ereignisse („Mitarbeiter angelegt“, „Mitarbeiter geändert“,
  „Abwesenheit eingetragen/beantragt“, „Antrag entschieden“). HR3000 schickt je Ereignis ein JSON wie
  `{"event": "absence.decided", "occurred_at": "…", "data": {"absence_id": 12, "employee_id": 5,
  "status": "APPROVED"}}`; Einzelheiten holt ihr über die API. Kopfzeilen: `X-HR3000-Event`,
  `X-HR3000-Delivery`, `X-HR3000-Timestamp` und `X-HR3000-Signature` = `sha256=` + HMAC-SHA256 über
  `<Timestamp>.<Body>` mit dem Signatur-Secret (wird beim Anlegen einmal angezeigt). Antwortet der
  Empfänger nicht mit 2xx, versucht HR3000 es nach 1, 5 und 30 Minuten sowie nach 2 und 6 Stunden
  erneut. Interne Adressen (z. B. 10.x, localhost) sind nicht erlaubt. „Test senden“, „Pausieren“,
  „Löschen“; der letzte Stand steht an jedem Webhook.

## 10. Tablets im Betrieb

- Ein Android-Tablet mit Chrome reicht, ein Notebook mit Chrome oder Edge geht genauso, aber nicht
  im Edge-Kiosk-Modus (siehe „Tablets per MDM verteilen“). Für Chips dient NFC oder ein USB- bzw.
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
- Tablet tauschen: Den QR-Code des Eintrags mit dem neuen Tablet scannen. Das alte ist damit
  abgemeldet. Zeigt ein Tablet „Dieser Tablet-Zugang ist auf einem anderen Gerät gekoppelt“, nutzt
  ein anderes Gerät den Zugang: prüfen, ob das gewollt ist, dann neu koppeln oder einen eigenen
  Eintrag anlegen.

### Tablets per MDM verteilen

Statt jedes Gerät per QR-Code zu koppeln, richtet eine Geräteverwaltung (MDM, z. B. Microsoft
Intune, ManageEngine Endpoint Central, Jamf) die Kiosk-App auf vielen Geräten auf einmal ein. Das
MDM verteilt dafür nur eine Start-URL mit dem Registrierungsschlüssel des Standorts. Die Zugänge der
einzelnen Geräte entstehen erst am Gerät und stehen nie im MDM.

1. **Schlüssel erzeugen:** „Tablets“ → Reiter „Verteilung per MDM“ → beim Standort „Schlüssel
   erzeugen“. Vorher die Gültigkeit wählen (7 Tage bis 1 Jahr oder unbefristet, Standard 30 Tage).
   Die Start-URL, z. B. `https://kiosk.firma.hr3000.de/#enroll=<schlüssel>`, wird nur einmal angezeigt.
   Wie ein Passwort behandeln: nur im MDM hinterlegen, nicht per Mail verschicken.
2. **Gerätenamen anhängen (empfohlen):** `&name=<Gerätename>`. Damit ordnet HR3000 das Gerät einem
   vorbereiteten Eintrag zu; ohne Namen wartet jedes Gerät auf Freigabe.
   - Android und iPad: Platzhalter des MDM in der Start-URL der Web-App bzw. in der
     Chrome-Konfiguration, in Endpoint Central z. B. `%devicename%` oder `%serialnumber%`, in Intune
     die entsprechenden Platzhalter für Gerätename oder Seriennummer. Die genaue Schreibweise steht in
     der Doku des MDM. Ersetzt das MDM einen Platzhalter nicht, behandelt HR3000 ihn wie „kein Name“.
   - Windows (jedes MDM oder RMM, das Skripte verteilt): Ein Skript baut die Start-URL mit dem
     Computernamen, in PowerShell z. B.
     `"https://kiosk.firma.hr3000.de/#enroll=$Schluessel&name=$env:COMPUTERNAME"`, und startet damit
     Chrome im Kiosk-Modus (`chrome.exe --kiosk "<URL>" --no-first-run`) oder Edge als App-Fenster
     (`msedge.exe --app="<URL>" --start-fullscreen`). **Nicht** den Edge-Kiosk-Modus verwenden
     (`msedge.exe --kiosk` bzw. zugewiesener Zugriff mit Edge): Er läuft laut Microsoft immer InPrivate
     und löscht die Anmeldung des Geräts bei jedem Neustart. Das Gerät stünde dann jedes Mal wieder in
     der Freigabe. Den Schlüssel als Parameter oder geschützte Variable des MDM übergeben, nicht fest
     ins Skript schreiben.
   - macOS: Konfigurationsprofil für Chrome oder Edge, Gerätename über die Platzhalter des MDM.
3. **Einträge vorbereiten (optional):** Unter „Tablets“ je Gerät einen Eintrag mit „Gerätename im
   MDM“ anlegen, z. B. `NB-FRA-01`. Meldet sich ein Gerät mit diesem Namen am selben Standort, wird es
   ohne Freigabe verbunden, solange der Eintrag noch nie benutzt wurde. Admin und HR bekommen eine
   Benachrichtigung.
4. **Freigeben:** Alle anderen Geräte erscheinen oben unter „Neue Geräte warten auf Freigabe“ mit
   gemeldetem Namen und Prüfcode. Denselben Code zeigt das Gerät auf dem Bildschirm. Codes
   vergleichen, dann „Freigeben“ (als neues Tablet oder als Ersatz für ein vorhandenes) oder
   „Ablehnen“. Das Gerät meldet sich innerhalb einer Minute von selbst an. Zu jeder neuen Anfrage
   bekommen Admin und HR eine Benachrichtigung.

Regeln:

- Der Schlüssel übernimmt nie einen Eintrag, der schon benutzt wurde, auch nicht nach „Kopplung
  aufheben“. Ein verlorenes Gerät mit der Start-URL landet so in der Freigabe und nicht im Betrieb.
- Verliert ein eingerichtetes Gerät sein Token (z. B. „Gerät zurücksetzen“) und startet neu, bekommt
  es seinen Eintrag ohne Freigabe zurück. Dafür muss es dieselbe Installation sein. Ein neu
  aufgesetztes Gerät oder ein Tauschgerät erscheint in der Freigabe: dort „Vorhandenes Tablet
  ersetzen“ wählen.
- Hinweis „bereits in Benutzung“ bei einer Anfrage: Ein Gerät meldet sich mit dem Namen eines
  aktiven Tablets. Nur freigeben, wenn das Gerät wirklich ersetzt wurde.
- „Erneuern“ macht den alten Schlüssel sofort ungültig, „Sperren“ löscht ihn. Eingerichtete Tablets
  bleiben in beiden Fällen angemeldet. Bei Verdacht (Schlüssel weitergegeben, Gerät verloren)
  erneuern und die Start-URL im MDM tauschen.
- Auf einem eingerichteten Gerät lässt sich die Start-URL auslesen (z. B. in den
  Browser-Richtlinien). Deshalb gilt: Freigabe als Standard, Schlüssel befristen, nach der
  Einrichtungsphase sperren oder erneuern.
- Das Gerät speichert seine Anmeldung im Browser. Kein Inkognito- oder InPrivate-Modus, kein
  „Browserdaten beim Beenden löschen“. Vor dem Rollout an einem Pilotgerät prüfen: Nach einem
  Neustart muss es ohne neue Freigabe wieder angemeldet sein.
- Höchstens 20 offene Anfragen je Standort. Nach 10 falschen Schlüsseln sperrt HR3000 die
  Registrierung von dieser Adresse für 5 Minuten.

## 11. Kündigen und Löschen

- **Kündigen:** „Einstellungen“ → „Tarif & Konto“ → „Konto kündigen“ → „HR3000 kündigen…“. Zur
  Bestätigung die Adresse der Firma eintippen (z. B. `musterfirma`). Nur Admins können kündigen.
- **Fristen:**
  - Die Kündigung gilt zum Monatsende.
  - Danach könnt ihr HR3000 noch **30 Tage** normal nutzen und alles exportieren:
    „Analysen“, „Lohn-Export“, „DSGVO-Datenexport“ und „Monatsbericht“ je Mitarbeiter.
  - Anschließend werden **alle Daten der Firma endgültig gelöscht**: Mitarbeiter, Zeiten,
    Abwesenheiten, Dokumente, Einstellungen, Zugänge.
  - Kopien in den Datensicherungen verschwinden spätestens nach 12 Monaten.
- **Hinweise:** Während der Frist steht oben in der HR-Ansicht ein Hinweis mit dem
  Löschtermin. Mit eingerichtetem Mailversand kommt zusätzlich eine Bestätigung per E-Mail.
- **Zurücknehmen:** bis zur Löschung jederzeit mit „Kündigung zurücknehmen“ an derselben
  Stelle.

