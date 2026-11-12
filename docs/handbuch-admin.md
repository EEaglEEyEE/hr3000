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
| HR | Mitarbeiter, Abwesenheiten, „Zu klären“, „Monatsabschluss“, „Analysen“, „Lohn-Export“ (CSV ohne Beträge), „On- & Offboarding“, „Schichtplan-Kalender“; unter „Einstellungen“ „Standorte“, „Abteilungen“, „Feiertagskalender“, „Schichtplanung“ (Schichtvorlagen), „Tablets“ und „Audit-Protokoll“; Vergütung und „Lohnarten“ nur mit „Vergütung & Lohn-Export“ |
| Führungskraft | „Tagesgeschäft“ für den eigenen Bereich: sich selbst und alle direkt und indirekt Unterstellten (als Leitung oder – je nach Rechten – Stellvertretung einer Abteilung bzw. als abweichend eingetragene Führungskraft); mit eingeschalteten „Eigenen Berichten“ bzw. „Projektzeiten“ auch „Analysen“ → „Eigene Berichte“ bzw. „Projektzeiten“ für diesen Bereich |
| Keine (nur Mein Bereich) | nur die eigene Ansicht, siehe Mitarbeiter-Handbuch |

- **„Vergütung & Lohn-Export“:** Admins haben es immer; HR bekommt es per Häkchen unter
  „HR-Berechtigung“ (Standard aus). Es öffnet überall dasselbe: Vergütung und „Zulagen &
  Einmalzahlungen“ unter „Personalakte“ → „Vertrag & Vergütung“, Bericht „Lohnkosten“, Beträge im
  Lohn-Export, „DATEV LODAS“ und die Seite „Lohnarten“. Zuschlagsregeln selbst ändern bleibt Admins
  vorbehalten. Nach der Freigabe sieht die Person die neuen Bereiche spätestens nach der nächsten
  Anmeldung.
- **Eigene Rollen:** Admins legen unter „Einstellungen“ → „Rollen“ eigene Rollen an, z. B. für ein
  externes Lohnbüro oder eine Person, die nur Abwesenheiten pflegt. Je Bereich gibt es drei Stufen:
  „Kein Zugriff“, „Ansehen“ und „Bearbeiten“. Die Bereiche: „Mitarbeiter & Stammdaten“, „Personalakte:
  Dokumente“, „Vergütung & Lohn“, „Zeiterfassung & „Zu klären““, „Abwesenheiten“, „Schichtplanung“,
  „Monatsabschluss“, „Auswertungen“ (auch eigene Berichte: Vorschau und Export ab „Ansehen“, Speichern
  ab „Bearbeiten“), „Organisation“ (Abteilungen, Organigramm), „Checklisten“, „Stammdaten der Firma“
  (Standorte, Tablets, Feiertage, Kostenstellen, Arbeitszeitmodelle) und „Recruiting“ (Stellen und
  Bewerbungen; ohne diesen Bereich sieht das Konto nur Stellen, in deren Hiring Team es steht).
  Hinweise des Hinweisgebersystems hängen nicht an der Rolle: Sie sieht nur, wer als
  Meldestellen-Beauftragte:r benannt ist.
  - Eine eigene Rolle **schränkt HR ein**, sie gibt nie mehr Rechte: Zuweisen lässt sie sich nur bei
    der Rolle „HR“, beim Mitarbeiter unter „HR-Berechtigung“ → „Eigene Rolle“ oder bei
    Verwaltungskonten. Was nur Admins dürfen (z. B. „Einstellungen“ → „Allgemein“, Rollen vergeben),
    bleibt bei Admins. Admins und Führungskräfte bekommen keine eigene Rolle.
  - Mit eigener Rolle zählt das Häkchen „Vergütung & Lohn-Export“ nicht; es entscheidet der Bereich
    „Vergütung & Lohn“. „Ansehen“ zeigt die freigegebenen Monate der „Lohnbuchhaltung“, die Lohnarten
    und – zusammen mit „Mitarbeiter & Stammdaten“ – Gehalt und Zulagen im Profil. „Bearbeiten“ braucht
    es für den „Lohn-Export“, den aktuellen Stand und das Freigeben in der „Lohnbuchhaltung“ und zum
    Ändern von Gehalt, Zulagen, Bank-, Steuer- und Sozialversicherungsdaten.
  - Im Reiter „Vertrag & Vergütung“ gilt „Ansehen“ als reine Ansicht: Vergütung, Zulagen und
    Einmalzahlungen (Bereich „Vergütung & Lohn“) sowie die Vertragsdaten (Bereich „Mitarbeiter &
    Stammdaten“) erscheinen dann ohne Schaltflächen zum Anlegen, Beenden und Löschen.
  - Menü, Seiten und Reiter blenden aus, was die Rolle nicht erlaubt. Ist die Person auch Mitarbeiter,
    bleibt „Mein Bereich“ wie gewohnt; in nicht freigegebenen Bereichen sieht sie nur ihre eigenen
    Daten. Benachrichtigungen (z. B. neue Urlaubsanträge) bekommt sie nur zu freigegebenen Bereichen.
    Das „Audit-Protokoll“ und der „DSGVO-Datenexport“ bleiben Admins und HR ohne eigene Rolle
    vorbehalten.
  - Eine Stufe „Vorschlagen“ gibt es bewusst nicht: Änderungen an den eigenen Daten schlagen
    Mitarbeiter über „Mein Bereich“ vor („Vorschläge“).
  - Vorlage „Lohnbüro (nur lesen)“ per Klick: nur „Vergütung & Lohn“ auf „Ansehen“.
  - Änderungen greifen sofort; Menü und Seiten passen sich spätestens nach der nächsten Anmeldung an.
    Rollen, die einem Konto zugewiesen sind, lassen sich nicht löschen. Anlegen, Ändern, Löschen und
    jede Zuweisung stehen im „Audit-Protokoll“ („Rolle geändert (eigene Rolle)“).
  - Zwei-Faktor-Pflicht: Konten mit eigener Rolle gehören zur Gruppe „HR“.

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
   - Der CSV-Import nennt alle Spalten auf der Seite selbst. Das Arbeitszeitmodell kommt aus
     `wochenstunden` und `arbeitstage` oder aus `tagesstunden`; ein mehrwöchiges Modell aus
     `tagesstunden` (Woche 1) und `tagesstunden_woche2` bis `tagesstunden_woche4` (lückenlos, optional
     `turnus_beginn`); `abgegoltene_ueberstunden` trägt die mit dem Gehalt abgegoltenen Stunden je
     Monat ein. Im Dialog „Neuer Mitarbeiter“ gibt es dieses Feld bei „Stunden je Wochentag“.
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
   ist vorbelegt), „Abteilungen“ mit Leitungen anlegen, „Abwesenheitsarten“ anpassen.

## 3. Menü

- **Tagesgeschäft:** „Startseite“, „Mitarbeiter“, „Anwesenheit“, „Kalender“, „Organigramm“, „Zu
  klären“ (der Posteingang mit Urlaubs- und Korrekturanträgen; die rote Zahl zählt alles Offene)
- **Planung & Abrechnung:** „Schichtplan-Kalender“ (nur mit eingeschalteter Schichtplanung),
  „Monatsabschluss“, „Analysen“, „Lohn-Export“, „On- & Offboarding“, „Recruiting“ (nur mit eingeschaltetem
  Recruiting, für Admin und HR sowie für Konten im Hiring Team einer Stelle; Abschnitt 12)
- **Unten:** „Mein Bereich“ (wenn der Login zu einem Mitarbeiter gehört), „Einstellungen“ (Admin
  und HR, je nach Rolle mit unterschiedlichen Bereichen), „Darstellung“ (Hell/Dunkel/Wie System),
  „Abmelden“
- Standorte, Abteilungen, Kostenstellen, Feiertage, Tablets, Pausenregeln, Schichtvorlagen, Zuschläge, Lohnarten und
  das Audit-Protokoll stehen unter „Einstellungen“ (siehe Abschnitt 9); alte Links und Lesezeichen
  führen dorthin.
- **Hinweise:** nur für benannte Meldestellen-Beauftragte, wenn das Hinweisgebersystem an ist
  (siehe „Hinweisgebersystem“ in Abschnitt 9)
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
- **Kalender:** Monatsansicht mit Abwesenheiten, Feiertagen und Geburtstagen, Filter „Abteilungen:“ (eine
  Abteilung zeigt auch ihre Unterabteilungen; „Ohne Abteilung“).
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
- **„Korrekturanträge“:** von Mitarbeitern beantragte Korrekturen ihrer Stempelungen (Art
  „Korrektur“) und selbst eingetragene Zeiten aus dem Stundenzettel, wenn „Genehmigung nötig“ an ist
  (Art „Zeiten eingetragen“), „Übernehmen“ / „Ablehnen“. Übernommene eingetragene Zeiten erscheinen mit
  der Quelle „Selbst eingetragen“. Überschneiden sie sich inzwischen mit anderen Zeiten oder ist der
  Monat abgeschlossen, lässt sich der Antrag nicht übernehmen, nur ablehnen.
- **„Datenänderungen“:** Vorschläge der Mitarbeiter zu ihren eigenen Daten (Adresse, Bank, Steuer,
  eigene Felder aus Abschnitten mit „schlagen Änderungen vor“), je Feld alt → neu, „Übernehmen“ oder
  „Ablehnen“ mit optionalem Hinweis. Mit Bank-, Steuer- oder SV-Angaben entscheidet nur, wer
  „Vergütung & Lohn-Export“ hat. Eigene Vorschläge übernimmt jemand anderes.
- **„Urlaubsanträge“:** „Genehmigen“ / „Ablehnen“. Führungskräfte sehen die Anträge, die gerade bei
  ihnen liegen (ihr Bereich bzw. als Führungskraft oder Stellvertretung, je nach „Genehmigt von“ der Art).
  Je Antrag stehen dort der Resturlaub des Jahres (bei Urlaub) und wer aus derselben Abteilung im
  Zeitraum ebenfalls abwesend ist oder es beantragt hat.
  Früher ein eigener Menüpunkt; alte Links führen hierher.
- **„Grenzen“:** Aushilfen „nach Aufwand“ ab 90 % ihrer Monatsgrenze und – wenn unter
  „Einstellungen“ → „Arbeitszeit“ → „Grenzen fürs Überstundenkonto“ eingestellt – Überstundenkonten
  ab 90 % der Obergrenze oder unter der Untergrenze. Das Konto wird nicht gekappt.

## 5. Mitarbeiter

- **Liste:** Suche, Standortfilter, Abteilungsfilter (sobald es Abteilungen gibt: „Alle
  Abteilungen“, „Ohne Abteilung“ oder eine Abteilung – samt ihren Unterabteilungen, z. B.
  „Vertrieb“ zeigt auch „Vertrieb › Innendienst“), „Auch inaktive anzeigen“, Hinweis auf die
  Tarifgrenze. Die Spalte „Abteilung“ zeigt die Abteilung je Mitarbeiter (der volle Pfad beim
  Darüberfahren).
  „Bearbeiten“ öffnet den Mitarbeiter direkt im Reiter „Einstellungen“.
- **„Organigramm“:** der Abteilungsbaum: je Abteilung eine Karte mit Name, „Leitung: …“ bzw.
  „Leitungen: …“ (oder „ohne Leitung“), „Stellvertretung: …“ mit den Rechten in Klammern und den
  Mitarbeitern (ab fünf Personen zugeklappt, „… Mitarbeiter“ klappt auf), darunter
  die Unterabteilungen mit Verbindungslinien; die Zahl zeigt, wie viele Personen in der Abteilung und
  darunter sind. Wer keiner Abteilung angehört, steht unter „Ohne Abteilung“. Zwei Darstellungen
  („Baum“ / „Liste“, die Wahl merkt sich der Browser): „Baum“ von oben nach unten – ist er breiter als
  die Seite, lässt er sich in seinem Kasten seitlich verschieben; „Liste“ ist die eingerückte Ansicht,
  am Handy der Standard. Ab der dritten Ebene sind Unterabteilungen zugeklappt (Pfeil unter der
  Karte). Suche nach Abteilung, Name oder Position, Treffer sind markiert. Mitarbeiter sehen es
  in „Mein Bereich“ nur, wenn unter „Einstellungen“ → „Allgemein“ „Mitarbeiter sehen das
  Organigramm“ an ist.
  **Bearbeiten (Admin und HR):** „Neue Abteilung“ oben; an jeder Karte Stift (Name, übergeordnete
  Abteilung, Leitungen und Stellvertretungen – derselbe Dialog wie unter „Einstellungen“ →
  „Abteilungen“), Personen-Symbol (Mitarbeiter hinzufügen), Plus (Unterabteilung anlegen) und
  Papierkorb (Löschen, nur leere Abteilungen); an jeder Person das Pfeil-Symbol: in eine andere
  Abteilung oder „ohne Abteilung“ verschieben. „Mitarbeiter hinzufügen“ listet zuerst alle ohne
  Abteilung, dann alle aus anderen Abteilungen mit ihrer bisherigen Abteilung; Suche nach Name,
  Position oder Abteilung, je Gruppe „Alle auswählen“. Mehrere werden auf einmal aufgenommen, wer
  aus einer anderen Abteilung kommt, wechselt. Führungskraft wird die Leitung der Abteilung, außer
  bei einer je Person eingetragenen Führungskraft. Am
  Computer lassen sich Personen und Abteilungen auch mit der Maus auf eine andere Karte ziehen
  (gestrichelt umrandet = hier ablegen): eine Abteilung auf „Hierher ziehen: Abteilung auf die oberste
  Ebene“, eine Person auf „Ohne Abteilung“. Unter sich selbst lässt sich eine Abteilung nicht ziehen;
  würde jemand dadurch (indirekt) die eigene Führungskraft, erscheint ein Hinweis und nichts ändert
  sich. Führungskräfte sehen das Organigramm nur zum Lesen.
- **Dialog „Neuer Mitarbeiter“ und Reiter „Einstellungen“:** Angelegt wird im Dialog „Neuer
  Mitarbeiter“, geändert im Reiter „Einstellungen“ der Detailseite – mit denselben Feldern. Dort
  übernimmt „Speichern“ die Änderungen, „Änderungen verwerfen“ holt die gespeicherten Werte zurück.
  - Oben die Grunddaten: Vor- und Nachname, Personalnummer, Standort („Standortwechsel gilt ab“),
    „Abteilung“, „Position“, „Abweichende Führungskraft“ („Wie Abteilung (automatisch)“ = die Leitungen
    der Abteilung bzw. der nächsten darüber; darunter steht, wer das gerade ist, samt Stellvertretung),
    „Anstelldatum“. Eine Vertretung je Person gibt es nicht mehr – dafür sind die Stellvertretungen
    der Abteilung da.
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
  - „Zeiterfassung“: „Stempelung nachtragen“, „Korrigieren“, „Endgültig löschen“. Die Spalte
    „Quelle“ zeigt, woher eine Stempelung kommt: „Tablet“, „Web-Login“, „Selbst eingetragen“
    (Stundenzettel), „HR manuell“ (nachgetragen oder Korrekturantrag) oder „Automatisch (Pause)“.
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
      Tag. Wer eine Modell-Fassung mit „Bearbeiten“ ändert, macht sie ebenfalls individuell. Auch
      individuell gibt es den „Gleitzeit-Rahmen“ („Wie Einstellungen“, „Eigener Rahmen“, „Kein
      Rahmen“, mit „Rahmen je Wochentag unterschiedlich“ wie im Modell); die Toleranz gibt es nur im
      Modell.
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
    - „Mehrwöchig (Turnus)“ (ebenfalls bei „Soll“): ein Rhythmus über 2 bis 4 Wochen, z. B. Woche 1
      Mo–Mi und Woche 2 Do–Fr. Unter „Wochen im Turnus“ die Zahl der Wochen wählen und in der
      Tabelle je Woche die Stunden je Wochentag eintragen (leer = frei, höchstens 10 Std. je Tag
      und 60 je Woche, mindestens ein Tag mit Stunden). Darunter stehen die durchschnittlichen
      Wochenstunden und Arbeitstage. Woche 1 ist die Kalenderwoche (ab Montag) des „Gültig ab“-Datums;
      mit „Turnus beginnt am (optional)“ legt ihr den Start abweichend fest – ein beliebiger Tag der
      gewünschten Woche 1, gezählt wird ab deren Montag. Der Turnus wiederholt sich fortlaufend.
      Eine neue Fassung übernimmt den Startpunkt der bisherigen, der Rhythmus läuft also weiter;
      wer ihn leert, beginnt mit Woche 1 in der Woche des „Gültig ab“. Bei einem Arbeitszeitmodell
      gilt der Startpunkt für alle Zugewiesenen gleich, egal wann sie zugewiesen wurden; ohne Angabe
      beginnt Woche 1 beim Anlegen in der laufenden Woche, bei „Ändern ab Stichtag“ in der Woche
      des Stichtags. Tagessoll, „fehlt“ und „außerplanmäßig“, Feiertagsgutschrift, Urlaubstage und
      Monatsbericht folgen der Woche des jeweiligen Tages: Urlaub zählt nur an Tagen mit Stunden in
      dieser Woche. Der berechnete Urlaubsanspruch nutzt die durchschnittlichen Arbeitstage je
      Woche (2,5 Tage im Beispiel = halber Anspruch der 5-Tage-Woche). „Aktuell gültig“ zeigt alle
      Wochen und markiert die laufende mit „(jetzt)“. Eine Tagesausnahme im Schichtplan hat wie
      bisher Vorrang.
    - „Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)“ (optional, leer oder 0 = keine,
      höchstens 100; nicht bei „Nach Aufwand“): Mehrarbeit eines Kalendermonats bis zu dieser Grenze
      ist mit dem Gehalt abgegolten und kommt nicht aufs Überstundenkonto, erst der Teil darüber.
      Maßgeblich ist der Saldo des ganzen Monats (Ist − Soll), nicht der einzelne Tag; Minusstunden
      bleiben unverändert. Beispiel: Grenze 10 Std., der Monat endet mit +14 Std. – 10 Std. sind
      abgegolten, 4 Std. kommen aufs Konto; endet er mit −3 Std., zählen die −3 Std. Im laufenden
      Monat wirkt die Abgeltung fortlaufend auf den bisherigen Monatssaldo, das Konto zeigt also nie
      Stunden, die am Monatsende wieder wegfallen (ein späterer Minustag verringert zuerst die
      abgegoltenen Stunden). Bei „Flexibel ohne feste Tage“ zählt die Wochenabrechnung im Monat
      ihres Sonntags (bzw. des letzten Beschäftigungstags), wie im Konto. Für einen Monat gilt die
      Grenze der Fassung, die am Monatsende gilt (bei Austritt im Monat: am letzten
      Beschäftigungstag) – wechselt die Fassung im Monat, gilt deren Grenze für den ganzen Monat,
      auch im laufenden Monat schon die zum Monatsende eingetragene. Eine geänderte Grenze rechnet
      das Konto ab dem Monat des Stichtags neu; vorgelegte oder abgeschlossene Monate lassen sich
      so nicht mehr ändern. Korrekturbuchungen und „Überstunden auszahlen“ bleiben unberührt. Wo
      sie erscheint: „Aktuell gültig“ („Mit dem Gehalt abgegolten: bis … Std. Überstunden je
      Monat“), Reiter „Überstundenkonto“ („Davon abgegolten in diesem Monat: … von … Std.“),
      Monatsbericht/Monatsnachweis („davon abgegolten“ unter „Saldo im Monat“) und Lohn-Export.
    - „Schichtvorlage (Uhrzeiten, optional)“: feste Uhrzeiten aus einer Schichtvorlage, z. B.
      „Früh (06:00–14:30)“, für Schichtplan, Pünktlichkeit und Ruhezeit-Prüfung. Das Soll bleibt
      das des Arbeitszeitmodells.
    - „Pause“: „Wie Pausenregeln“ (Standard; mit Schichtvorlage, die eine eigene Pause hat, heißt
      der Knopf „Wie Schichtvorlage“), „Feste Minuten“ ab einer Arbeitszeit („… Minuten ab … Std.
      Arbeit“, leer = ab der ersten Minute; gestempelte Pausen zählen mit) oder „Feste Uhrzeit“
      (z. B. 12:00–12:30, abgezogen, soweit der Mitarbeiter da war). Mit „Weitere Pausenzeit“ gibt
      es bis zu vier feste Pausen (z. B. Frühstück 09:00–09:15 und Mittag 12:00–12:30), „Entfernen“
      löscht eine; sie dürfen sich nicht überschneiden. Die Pausenstaffel gilt immer mindestens.
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
  - „Genehmigt von“ (bei „Genehmigung nötig“): „Führungskraft (oder darüber) oder Admin/HR“
    (Standard: jede Führungskraft, in deren Bereich die Person liegt), „Führungskraft“ (genau die
    zuständigen Führungskräfte – die abweichend eingetragene oder alle Leitungen der Abteilung samt
    Stellvertretungen mit gleichen Rechten –, wenn sie eine Rolle und einen Zugang haben; jede darf
    entscheiden, alle werden benachrichtigt), „erst Führungskraft, dann Admin/HR“ (zwei Schritte) oder
    „nur Admin/HR“. Ist keine Leitung da (heute abwesend oder ohne Zugang), entscheiden die
    Stellvertretungen der Abteilung; fehlt eine abweichende Führungskraft, entscheidet die Abteilung.
    Ohne passende Führungskraft entscheiden Admin und HR. Admin und HR
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
  - Abwesenheitsquote: Monate „Von“ bis „bis“ (höchstens 24), Kategorien zum Anhaken (Standard
    Krankheit und Kind krank). Je Monat und gesamt, für die ganze Firma und je Abteilung:
    genehmigte Abwesenheitstage der Kategorien geteilt durch die Soll-Arbeitstage laut
    Arbeitszeitmodell ohne Feiertage (ohne Modell und bei flexiblem Modell Mo–Fr, „nach Aufwand“
    keine). Halbe Tage zählen halb, Stundenangaben nicht. Gezählt wird höchstens bis heute. Die Zahlen
    dahinter zeigt der Mauszeiger über einer Zelle.
  - Köpfe und FTE: Monate „Von“ bis „bis“ (höchstens 36). Je Monatsende die Beschäftigten laut Ein-
    und Austritt (Köpfe) und ihre Vollzeitstellen (FTE = Wochenstunden / Wochenstunden des
    Standard-Arbeitszeitmodells unter „Einstellungen“, ohne solches 40 Stunden). „Nach Aufwand“ zählt
    als Kopf mit 0 FTE, ohne Arbeitszeitmodell als volle Stelle. Dazu Zugänge (Eintritt im Monat)
    und Abgänge (Austritt im Monat) und eine Tabelle je Abteilung (Köpfe / FTE). Deaktivierte ohne
    Austrittsdatum und anonymisierte Mitarbeiter zählen nicht.
  - In beiden gilt die heutige Abteilung (Wechsel haben keinen Verlauf).
  - Eigene Berichte (nur mit dem Schalter „Eigene Berichte“, siehe unten)
  - Projektzeiten (nur mit dem Schalter „Projektzeiten“; auch für Führungskräfte, dann nur ihr
    Bereich): „Von“ und „Bis“ (Standard der laufende Monat, höchstens 366 Tage), „Gruppieren nach“
    Projekt, Kunde oder Mitarbeiter. Je Gruppe die Stunden und wie viel davon abrechenbar ist, oben
    „Gesamt“, „Abrechenbar“ und „Nicht abrechenbar“. Gezählt wird jede selbst eingetragene Arbeitszeit
    mit Projekt (Arbeitstag ihres Beginns) ohne die Pausen darin; die gesetzliche Mindestpause der
    Tagesberechnung wird nicht auf Projekte verteilt, die Summe kann deshalb über der Ist-Zeit liegen.
    Zeiten ohne Projekt erscheinen nicht.
  - jeweils „CSV exportieren“
- **„Eigene Berichte“** (Reiter unter „Analysen“, wenn unter „Einstellungen“ → „Allgemein“ „Eigene
  Berichte“ an ist; für Admin, HR und Führungskräfte):
  - Liste: eigene und geteilte Berichte mit Datenquelle und Besitzer. „Neuer Bericht“ öffnet den
    Baukasten, ein Klick auf den Namen öffnet einen gespeicherten Bericht.
  - „Datenquelle“: „Mitarbeitende“ (Stammdaten mit Abteilung, Führungskraft, Standort, Ein- und
    Austritt, Status, Arbeitszeitmodell, Wochenstunden, FTE; dazu Vertrag, persönliche Daten und
    eigene Felder der Personalakte), „Abwesenheiten“ (Von, Bis, Art, Kategorie, Tage im Zeitraum,
    Stunden, halber Tag, Status), „Zeit je Monat“ (Soll, Ist, Saldo, Kontostand zum Monatsende,
    Urlaub genommen, Resturlaub des Jahres) oder – mit eingeschalteten Projektzeiten – „Projektzeiten“
    (Projekt, Projektnummer, Kunde, Abrechenbar, Kostenstelle, Stunden je Mitarbeiter und Projekt).
  - „Spalten“ (höchstens 30) hinzufügen, mit ↑ ↓ ordnen, mit ✕ entfernen. „Filter hinzufügen“
    (höchstens 10): Spalte, Vergleich (z. B. „enthält“, „größer oder gleich“, „ist eines von“, „ist
    leer“) und Wert. Bis zu drei Sortierungen, „Gruppieren nach“ einer Spalte: Anzahl und Summen je
    Gruppe.
  - Abwesenheiten und Zeit je Monat brauchen einen „Zeitraum“ (höchstens 366 Tage; Zeit je Monat
    rechnet ganze Monate). Bei „Mitarbeitende“ gilt der heutige Stand.
  - „Vorschau“ zeigt 50 Zeilen je Seite mit Summen; „CSV exportieren“ liefert alle Zeilen (wie der
    Lohn-Export: Semikolon, Umlaute für Excel, Formeln entschärft; bei Gruppierung mit Summenblock).
    Ein Bericht hat höchstens 20.000 Zeilen, sonst bitte filtern.
  - „Speichern“ mit Name (und Beschreibung); „Mit allen Verwaltungskonten teilen“ macht den Bericht
    für alle Verwaltungskonten der Firma lesbar und ausführbar. Ändern und „Löschen“ dürfen nur der
    Besitzer und Admins; alle anderen können „Als neuen Bericht speichern“.
  - Rechte: Geteilt wird die Zusammenstellung, nicht das Ergebnis. Jede Person sieht nur, was sie
    sehen darf: Führungskräfte nur ihren Bereich; Geburtsdatum, Vertrag, persönliche Daten und eigene
    Felder nur Admin und HR; Bank, Steuer, Sozialversicherung und Vergütung nur mit „Vergütung &
    Lohn-Export“. Wer einen geteilten Bericht mit solchen Spalten ausführt, bekommt sie weggelassen
    (Hinweis über der Tabelle). Filtert, sortiert oder gruppiert der Bericht nach einer solchen
    Spalte, lässt er sich ohne die Berechtigung nicht ausführen.
  - Das Audit-Protokoll vermerkt jedes Ausführen und jeden Export (Quelle, Spalten- und Zeilenzahl,
    Zeitraum, ohne Inhalte), Ausgabe von Vergütung zusätzlich als „Vergütung eingesehen“.
- **„Lohn-Export“:** Monat (vorbelegt: Vormonat) und Standort wählen, CSV für das Lohnbüro.
  Exportiert werden alle, die im Monat beschäftigt waren – auch wer im Monat ausgetreten ist. Mit
  „Vergütung & Lohn-Export“ kommt je Zulage bzw. Einmalzahlung eine Spalte mit dem Betrag im Zeitraum
  dazu (z. B. „Zulage Fahrtkosten (€)“, „Einmalzahlung Weihnachtsgeld (€)“), sonst fehlen diese
  Spalten.
  „Ausgezahlte Überstunden (Std.)“ zeigt die Auszahlungen aus den „Korrekturbuchungen
  Überstundenkonto“ mit Datum im Zeitraum; gab es eine Auszahlung mit Faktor, kommt die Spalte
  „Ausgezahlte Überstunden gewichtet (Std.)“ dazu (DATEV: Stunden ungewichtet, mit Hinweis). Gilt
  für einen der Mitarbeiter im Zeitraum eine Grenze für abgegoltene Überstunden, kommt ganz hinten
  die Spalte „Abgegoltene Überstunden (Std.)“ dazu (die mit dem Gehalt abgegoltenen Stunden im
  Zeitraum; „Saldo (Std.)“ bleibt Ist − Soll). Über dem Export steht der Stand des „Monatsabschluss“
  (z. B. „1 von 2 abgeschlossen, 1 offen“ – solange nicht alles abgeschlossen ist, können sich die
  Werte noch ändern) und „Schon exportiert“ mit Zeitpunkt und Person (DATEV-Exporte nur mit
  „Vergütung & Lohn-Export“).
- **„Lohnbuchhaltung“** (vorbereitende Lohnbuchhaltung, mit „Vergütung & Lohn“; einschalten unter
  „Einstellungen“ → „Lohnbuchhaltung“, Standard aus): alles für den Lohnlauf eines Monats auf einer
  Seite, je Mitarbeiter, der im Monat beschäftigt war.
  - Angezeigt werden: „Neuzugang“ und „Austritt“, „Änderungen im Monat“ (neuer oder endender Vertrag,
    Vergütung ab, Zulage ab bzw. endet, Standortwechsel, eigene Felder mit „Gilt ab“ im Monat sowie im
    Monat geänderte persönliche Daten, Kostenstellen und Arbeitszeitmodell), „Vergütung“ (Gehalt bzw.
    Stundenlohn und die Zulagen und Einmalzahlungen des Monats), „Abwesenheiten“ (Tage je Art),
    „Stunden“ (Soll, Ist, Saldo, ausgezahlte Überstunden, Feiertage, offene Tage, Zuschläge – wie im
    Lohn-Export) und der Stand des „Monatsabschluss“.
  - „Freigeben“ friert den Monat ein: Die Übersicht und die Exportdateien (die CSV des Lohn-Exports
    und, wenn Berater- und Mandantennummer hinterlegt sind, die DATEV-LODAS-Datei) werden verschlüsselt
    gespeichert und bleiben danach unverändert abrufbar („CSV herunterladen“, „DATEV LODAS
    herunterladen“). Ist der Monatsabschluss noch nicht bei allen abgeschlossen, fragt „Freigeben“
    nach – freigeben geht trotzdem. Die Freigabe zählt beim „Lohn-Export“ unter „Schon exportiert“.
  - Ändert sich danach etwas, markiert die Seite die betroffenen Mitarbeiter mit „Seit der Freigabe
    geändert“; die freigegebenen Werte bleiben stehen.
  - „Freigabe zurücknehmen“ (nur Admins) löscht die eingefrorenen Daten; der Monat zeigt dann wieder
    den aktuellen Stand und lässt sich neu freigeben.
  - **Steuerberatung bzw. Lohnbüro:** unter „Einstellungen“ → „Rollen“ die Vorlage „Lohnbüro (nur
    lesen)“ anlegen und unter „Verwaltungskonten“ einen Zugang mit Rolle „HR“ und dieser eigenen Rolle
    einrichten. Das Lohnbüro sieht dann nur die „Lohnbuchhaltung“ mit den freigegebenen Monaten und
    deren Dateien, keinen aktuellen Stand. Jeder Abruf und jeder Download steht im „Audit-Protokoll“.
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
  - Mit dem Gehalt abgegoltene Überstunden (Grenze im Arbeitszeitmodell) lösen keine Zahlung aus und
    stehen nicht in der Datei. Die „Vorschau“ nennt sie je Mitarbeiter als Hinweis.
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
    Einstellungen). Mit „Rahmen je Wochentag unterschiedlich“ gilt je Tag ein eigener Rahmen (z. B.
    freitags 07:00–14:00); ein Tag ohne Häkchen hat keinen Rahmen, dort wird nichts geprüft. Die
    eigene Kernzeit muss an jedem Tag im Rahmen liegen. Ein neues Modell gilt von Anfang an, kann also auch rückwirkend zugewiesen
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
- **„Standorte“** (Admin und HR): Name, Zeitzone, Bundesland (Feiertage) und optional ein „Kreis für die
  Standortprüfung beim Stempeln“. In der Liste zeigt „Kreis“ den Radius.
- **Standort beim Stempeln** (nur Stempeln im Web-Login, nicht am Tablet und nicht für Nachträge
  durch HR):
  - Einrichten: unter „Standorte“ je Standort „Breite“ und „Länge“ des Mittelpunkts (in Grad, z. B.
    aus einem Kartendienst kopiert, Komma oder Punkt) und „Radius (m)“ (50–5000) eintragen. Vor Ort
    hilft „Aktuellen Standort übernehmen“ (fragt den Browser des eigenen Geräts). „Kreis entfernen“
    leert die drei Felder. Danach unter „Einstellungen“ → „Stempeln“ „Standort beim Stempeln prüfen
    (Web-Login)“ einschalten und wählen: „Nur vermerken“ (Standard; Stempeln ist immer möglich, die
    Buchung bekommt einen Vermerk) oder „Außerhalb nicht erlauben“ (außerhalb, ohne Standortfreigabe
    oder bei zu ungenauer Position wird das Stempeln mit einer Meldung abgelehnt).
  - Es zählen alle Standorte der Firma mit Kreis, nicht nur der des Mitarbeiters. Solange kein
    Standort einen Kreis hat, wird nicht geprüft (auch nichts abgelehnt); die Seite „Stempeln“ weist
    darauf hin.
  - Datenschutz: Der Browser schickt die Position nur im Moment des Klicks. Gespeichert wird nur das
    Ergebnis an der Buchung („innerhalb“ mit Standort, „außerhalb“ oder „Standort unbekannt“), keine
    Koordinaten – auch nicht in Protokollen oder Fehlermeldungen. Mitarbeiter sehen das im Handbuch
    und auf der Stempel-Karte.
  - Genauigkeit: Der Browser meldet, wie ungenau die Position ist. Ist sie ungenauer als der Radius,
    gilt die Buchung als „Standort unbekannt“ – außer die Position liegt selbst mit dieser
    Ungenauigkeit eindeutig außerhalb, dann „außerhalb“. Für Büros ohne GPS (WLAN-Ortung, oft
    50–150 m) einen Radius von mindestens 150–200 m wählen.
  - Anzeige: Im Reiter „Zeiterfassung“ des Mitarbeiters steht neben der Quelle „außerhalb“ bzw.
    „Standort unbekannt“ („innerhalb“ ohne Kennzeichen), im Monatsnachweis (PDF) unter „Bemerkung“,
    z. B. „außerhalb: Kommen 08:02“. Korrigiert HR die Buchung, bleibt der Vermerk.
- **„Kostenstellen“:** Nummer und Bezeichnung; benutzte archivieren statt löschen.
- **„Projekte & Kunden“** (Admin und HR; mit eigener Rolle „Stammdaten der Firma“):
  - Nur Admin: „Projektzeiten“ (Standard aus) schaltet die Projektzeiterfassung ein, „Projekt ist
    Pflicht“ verlangt bei jeder selbst eingetragenen Arbeitszeit ein Projekt. Projekte gibt es bisher
    nur beim Selbst-Eintragen (Stundenzettel, siehe „Stempeln“ → „Zeiten selbst eintragen“); am
    Tablet und beim Stempeln im Web-Login gibt es bewusst keine Projektauswahl.
  - „Kunden“: Name; „Deaktivieren“ nimmt die Projekte des Kunden aus der Auswahl. Löschen nur ohne
    Projekte.
  - „Projekte“: Name, „Nummer (optional)“ (eindeutig), „Kunde (optional)“, „Kostenstelle (optional)“
    (die Kostenstellen von oben), „Gültig von“/„Gültig bis“ (nur dann auswählbar), „Abrechenbar“.
    „Bearbeiten“, „Deaktivieren“; „Löschen“ nur, solange dem Projekt keine Zeiten zugeordnet sind.
  - Projekt und Tätigkeit einer Zeit ändert HR in der „Zeiterfassung“ des Mitarbeiters mit
    „Korrigieren“ am „Kommen“ (Felder „Projekt“ und „Tätigkeit“); dort steht das Projekt auch unter
    der Art.
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
- **„Abteilungen“:** die einzige Organisationsstruktur (Teams gibt es seit 09.11.2026 nicht mehr;
  bestehende Teams wurden zu Abteilungen, ihre Teamleitung zur Leitung). Abteilungen anlegen und
  verschachteln („Übergeordnete Abteilung“, z. B. Vertrieb → Innendienst) und unter „Leitung und
  Stellvertretung“ mit „Person hinzufügen“ eintragen, wer sie leitet (Spalte „Leitung und
  Stellvertretung“). Auch direkt im „Organigramm“. Die erste Person wird „Leitung“, weitere
  „Stellvertretung“; die Rolle lässt sich je Person umstellen.
  - **Leitungen** (beliebig viele, gleichberechtigt) sind die Führungskräfte aller in der Abteilung –
    auch in Unterabteilungen ohne eigene Leitung; eine Leitung selbst berichtet an die Leitungen
    darüber. Mit Login und Rolle „Führungskraft“ sehen sie das Tagesgeschäft ihres Bereichs und
    genehmigen dessen Anträge. Eine Leitung muss nicht selbst Mitglied der Abteilung sein.
  - **Stellvertretungen** sind keine Führungskräfte im Baum, sondern springen ein. Ihre Rechte wählt
    ihr je Person: „Sieht immer, entscheidet bei Abwesenheit“ (Standard: sieht den Bereich wie die
    Leitung, entscheidet und wird benachrichtigt, wenn keine Leitung da ist), „Gleiche Rechte wie die
    Leitung“ (sieht, entscheidet und wird benachrichtigt wie die Leitung) oder „Nur während
    Abwesenheit der Leitung“ (sieht und entscheidet nur dann). „Keine Leitung da“ heißt: alle
    Leitungen der Abteilung sind heute genehmigt abwesend, haben keinen Zugang oder es gibt keine.
    Auch Stellvertretungen brauchen Login und Rolle „Führungskraft“.
  Ausnahmen je Person: am Mitarbeiter „Abweichende Führungskraft“. Eine Änderung, durch die jemand
  (indirekt) die eigene Führungskraft würde, wird abgelehnt. Löschen geht nur bei leeren Abteilungen.
- **„Tablets“:**
  - „Neues Tablet“: Name, Standort, „Gerätename im MDM“ (optional, siehe Abschnitt 10 „Tablets per
    MDM verteilen“), Darstellung, Bildschirmzeiten
  - „QR-Code“: Mit der Kamera scannen öffnet die Tablet-App fertig eingerichtet. Ohne Kamera gibt
    es einen Kopplungscode zum Eintippen. Der Code gilt einmal und 15 Minuten. Ist der Eintrag schon
    mit einem Tablet verbunden (auch per MDM), fragt HR3000 erst nach: „Gerät tauschen – QR-Code
    erzeugen“ meldet das bisherige Tablet beim Koppeln ab. Das steht im Audit-Protokoll, Admins
    und HR bekommen eine Warnung. Für ein zusätzliches Tablet „Neues Tablet“ anlegen.
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
  Bereiche. HR sieht „Standorte“, „Abteilungen“, „Feiertagskalender“, „Schichtplanung“ (nur die Schichtvorlagen,
  wenn die Schichtplanung an ist), „Tablets“ und „Audit-Protokoll“, mit „Vergütung & Lohn-Export“ auch
  „Lohnarten“. Kann eine Änderung nicht gespeichert werden (z. B. weil ein Monat schon vorgelegt
  oder abgeschlossen ist), steht der Grund oben im Bereich.
  Mit eigener Rolle sieht HR nur die Bereiche, die zur Rolle passen (siehe Abschnitt 1).
- **Zugänge & Rechte** (nur Admin):
  - „Rollen“: eigene Rollen anlegen, bearbeiten und löschen (siehe Abschnitt 1).
  - „Verwaltungskonten“: Zugänge ohne Mitarbeiter, z. B. für die Steuerberatung. Anlegen mit E-Mail,
    Passwort (mindestens 8 Zeichen), Verwaltungsrolle (HR oder Admin) und bei HR optional eigener
    Rolle. „Zugang entfernen“ nimmt E-Mail-Login und Rolle weg; das Konto bleibt für den Verlauf
    bestehen.
- **Unternehmen:**
  - „Allgemein“: „Standard-Bundesland“, „Geburtstage im Kalender anzeigen“, „Firmenlogo“ (max.
    256 KB), „Erinnerungen an Admin und HR“ (Standard aus): einmal am Tag als Benachrichtigung und –
    mit Mailversand – per E-Mail: Probezeit endet in 14 Tagen, Befristung endet in 30 Tagen, Austritt
    in 14 Tagen, Resturlaub aus dem Vorjahr verfällt in 30 Tagen (das auch an die Person selbst),
    „Eigene Berichte“ (Standard aus): Reiter „Eigene Berichte“ unter „Analysen“, auch für
    Führungskräfte (siehe Abschnitt 7)
  - „Standorte“, „Abteilungen“, „Feiertagskalender“ (siehe Abschnitt 8)
  - „Hinweisgebersystem“ (nur Admin, Standard aus): siehe unten „Hinweisgebersystem“
  - „Recruiting“ (nur Admins): „Recruiting einschalten“ (Standard aus), „Löschfristen“ („Frist in
    Monaten“, Standard 6, und „Talentpool in Monaten“, Standard 12) und „Datenschutzhinweise für
    Bewerber“ (Text und/oder Link); siehe Abschnitt 12
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
      Gleitzeit-Rahmen (auch je Wochentag) und Toleranz lassen sich je Arbeitszeitmodell abweichend
      festlegen (Abschnitt 8), der Gleitzeit-Rahmen auch individuell am Mitarbeiter. Mit „Kernzeit je Wochentag unterschiedlich“ gilt je Tag eine eigene Kernzeit (z. B. freitags
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
    - „Mitarbeiter sehen den Kalender ihrer Abteilung“ (Standard aus): Reiter „Abteilungskalender“ in
      „Mein Bereich“. Die Art steht nur bei Abwesenheitsarten mit „Im Abteilungskalender: farbig (mit Art)“
      (unter „Abwesenheitsarten“, Standard „ausgegraut“), sonst nur, dass jemand fehlt; Homeoffice-
      Angaben erscheinen dort nicht.
    - „Mitarbeiter sehen beim Antrag, wer in ihrer Abteilung gleichzeitig abwesend ist“ (nur Name und Zeitraum,
      ohne Art; Standard aus). Im Antrag von HR steht der Hinweis immer, mit Art.
    - „Vier-Augen-Prinzip: eigene Anträge genehmigt jemand anderes“ (an: Admin, HR und
      Führungskräfte bekommen eigene genehmigungspflichtige Abwesenheiten nicht direkt
      genehmigt, eine andere Person entscheidet unter „Zu klären“ → „Urlaubsanträge“; Standard aus)
  - „Abwesenheitsarten“ (siehe Abschnitt 6)
- **Stempeln & Tablets:**
  - „Stempeln“:
    - „Stempeln über den Web-Login (Home-Office)“: Stempel-Karte in „Mein Bereich“, mit
      Serverzeit
    - „Standort beim Stempeln prüfen (Web-Login)“ (Standard aus) mit „Nur vermerken“ oder „Außerhalb
      nicht erlauben“: siehe Abschnitt 8 „Standort beim Stempeln“
    - „Zeiten selbst eintragen (Stundenzettel)“ (Standard aus): „Zeiten selbst eintragen erlauben“
      gibt Mitarbeitern in „Mein Bereich“ → „Zeiterfassung“ den Stundenzettel. „Genehmigung nötig“
      (Standard an): Einträge kommen unter „Zu klären“ → „Korrekturanträge“ und zählen erst nach
      „Übernehmen“; aus: sie zählen sofort (Audit-Protokoll „Zeiten selbst eingetragen“) und
      Mitarbeiter können sie im erlaubten Zeitraum selbst löschen. „Rückwirkend eintragen bis … Tage“
      (Standard 7, 0 = nur heute, höchstens 62). Gilt für die ganze Firma – eine Abweichung je
      Arbeitszeitmodell oder Mitarbeiter gibt es bewusst nicht.
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
       Status, Ein-/Austritt, Standort, Abteilung (`department_id`, Name), Position, Führungskräfte (wirksam: `supervisor_id` = die erste,
       `supervisor_ids` = alle)
     - `GET /api/v1/absence-types`
     - `GET /api/v1/absences?from=2026-01-01&to=2026-01-31&employee_id=…`: Zeitraum höchstens ein Jahr,
       mit Status (APPROVED, PENDING, REJECTED)
     - `GET /api/v1/punches?from=…&to=…&employee_id=…`: Stempelungen, Zeitpunkte in UTC; mit
       Projektzeiten `project_id`, `project_number`, `project_name`, mit Standortprüfung
       `location_check` (`INSIDE`, `OUTSIDE`, `UNKNOWN`), sonst jeweils `null`. Koordinaten gibt es
       nicht.
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

### Hinweisgebersystem

Interne Meldestelle für Hinweise auf Verstöße (z. B. nach dem Hinweisgeberschutzgesetz). HR3000
liefert das Werkzeug; wie die Meldestelle rechtlich ausgestaltet ist (wer sie besetzt, welche Fälle
sie annimmt, wie sie Folgemaßnahmen ergreift), verantwortet die Firma selbst. Externe Meldestellen
der Behörden bleiben davon unberührt; Beschäftigte dürfen sich weiterhin direkt an sie wenden.

- **Einrichten:** „Einstellungen“ → „Hinweisgebersystem“. Zuerst unter „Meldestellen-Beauftragte“
  ein oder mehrere Konten auswählen und „Benennen“, dann den Schalter „Hinweisgebersystem“
  einschalten. Benennbar ist jedes Konto der Firma mit Zugang, auch ein Mitarbeiter ohne
  Verwaltungsrolle. Ohne Beauftragte nimmt die Meldeseite keine Hinweise an. „Abberufen“ entzieht
  den Zugriff sofort. Benennen und Abberufen stehen im Audit-Protokoll.
- **Vertraulichkeit:** Hinweise sehen ausschließlich die Beauftragten – Admins, HR und
  Führungskräfte ohne Benennung sehen weder Inhalte noch die Liste noch die Anzahl; auch die
  Plattformverwaltung von HR3000 zeigt nichts davon. Wer einen Hinweis öffnet, bearbeitet oder einen Anhang lädt,
  steht im Protokoll des Vorgangs (nur für die Beauftragten sichtbar, ohne Inhalte); im allgemeinen
  Audit-Protokoll erscheinen diese Einträge nicht. Zur meldenden Person speichert HR3000 nur, was sie
  selbst angibt – keine IP-Adresse, kein Konto. Inhalte, Kontaktangaben und Anhänge liegen
  verschlüsselt.
- **Link bekannt geben:** Die Seite steht unter „Link zur Meldeseite“
  (`https://<firma>.hr3000.de/hinweis`), z. B. im Intranet oder als Aushang. In „Mein Bereich“ sehen
  alle Mitarbeiter den Link „Hinweis abgeben“. Melden kann jeder, der den Link kennt, auch ohne Konto.
- **Was die meldende Person bekommt:** nach dem Absenden einmalig eine Vorgangsnummer und einen
  Zugangscode. Geht der Code verloren, lässt er sich nicht wiederherstellen; dann hilft nur eine neue
  Meldung. Mit beiden Angaben sieht sie unter „Stand abfragen“ Status und Nachrichten der
  Meldestelle, antwortet und reicht Dateien nach (PDF, PNG, JPEG, DOCX, XLSX, je höchstens 10 MB,
  bis zu 10 je Vorgang). Interne Notizen und der Abschlussvermerk bleiben für sie unsichtbar.
- **Bearbeiten („Hinweise“):** Filter „Offen“ / „Abgeschlossen“ / „Alle“; „neu“ markiert Vorgänge
  mit Eingängen seit dem letzten Öffnen. Im Vorgang: Meldung mit Anhängen, „Verlauf“, darunter
  „Nachricht an die meldende Person“ oder „Interne Notiz“. Die meldende Person bekommt keine E-Mail;
  sie liest Nachrichten mit ihrem Zugangscode.
- **Fristen:** Rechts unter „Fristen“ und in der Liste. „Eingangsbestätigung bis“ = 7 Tage nach
  Eingang; „Als Eingangsbestätigung senden“ setzt das Datum und den Status „In Prüfung“.
  „Rückmeldung bis“ = drei Monate nach der Eingangsbestätigung (ohne Bestätigung drei Monate nach
  Ablauf der 7 Tage); „Als Rückmeldung senden“ setzt das Datum und den Status „Rückmeldung erteilt“.
  Überfällige Fristen stehen rot. Die Glocke erinnert die Beauftragten zwei Tage vor und nach Ablauf
  der Eingangsbestätigung sowie 14 Tage vor und nach Ablauf der Rückmeldung (die E-Mail dazu nennt
  keinen Vorgang). Das läuft unabhängig vom Schalter „Erinnerungen an Admin und HR“.
- **Status:** „Eingegangen“, „In Prüfung“, „Rückmeldung erteilt“, „Abgeschlossen“. Zum Abschließen
  ist ein „Abschlussvermerk“ nötig. Wird ein Vorgang wieder geöffnet, bleibt der bisherige Vermerk als
  interne Notiz erhalten.
- **Aufbewahrung und Löschen:** Mit dem Abschluss steht das „Löschdatum“ fest: drei Jahre nach
  Abschluss. Ab dann steht der Vorgang als „zur Löschung fällig“ in der Liste, die Glocke erinnert
  einmal, und im Vorgang gibt es „Vorgang löschen“ → „Endgültig löschen“. Gelöscht wird bewusst nicht
  automatisch: Ist eine längere Aufbewahrung erforderlich (z. B. wegen eines laufenden Verfahrens),
  bleibt der Vorgang einfach stehen. Vor dem Löschdatum lässt sich nichts löschen.
- **Ausschalten:** Der Schalter blendet Meldeseite und Menüpunkt aus; vorhandene Hinweise bleiben
  gespeichert und sind nach dem Einschalten wieder da.

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
- Tablet tauschen: „QR-Code“ des Eintrags, „Gerät tauschen – QR-Code erzeugen“, dann mit dem neuen
  Tablet scannen. Das alte ist damit abgemeldet. Ein per MDM verteiltes Tablet, das so abgemeldet
  wurde, fragt nach einem Neustart der Kiosk-App erneut an (Freigabe unter „Tablets“). Zeigt ein Tablet „Dieser Tablet-Zugang ist auf einem anderen Gerät gekoppelt“, nutzt
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

## 12. Recruiting

Eingeschaltet unter „Einstellungen“ → „Recruiting“ → „Recruiting einschalten“ (Standard aus). Aus
heißt: kein Menüpunkt, die Karriereseite und alle Recruiting-Adressen antworten mit „nicht gefunden“.
Gespeicherte Bewerbungen bleiben erhalten und werden weiter nach Frist gelöscht.

- **Wer sieht was:** Admin und HR sehen alle Stellen und Bewerbungen. Alle anderen Konten
  (Führungskräfte und Mitarbeitende ohne Verwaltungsrolle) sehen nur die Stellen, in deren „Hiring
  Team“ sie stehen, und deren Bewerbungen. Sie können Bewerbungen ansehen, Anhänge öffnen, die Phase
  wechseln, Notizen schreiben und bewerten. Mitarbeitende ohne Verwaltungsrolle finden das in „Mein
  Bereich“ → „Recruiting“. Die Gehaltsvorstellung sehen nur Konten mit „Vergütung & Lohn-Export“.
- **Reiter „Stellen“:** „Neue Stelle“ mit Titel, Abteilung, Standort, Anstellungsart, Status
  („Entwurf“, „Veröffentlicht“, „Geschlossen“), optional „Bewerbungsschluss“, „Beschreibung“ und
  „Hiring Team“. Die Beschreibung ist einfacher Text: Leerzeile = neuer Absatz, Zeilen mit „- “ werden
  zur Aufzählung. Eine Stelle mit Bewerbungen lässt sich nicht löschen, nur schließen. Die Spalte
  „Bewerbungen“ zeigt alle und die offenen; „Gelöscht“ zählt anonym, was schon gelöscht wurde.
- **Karriereseite:** `https://<firma>.hr3000.de/karriere` listet ohne Anmeldung die veröffentlichten
  Stellen bis einschließlich Bewerbungsschluss; „Ansehen“ öffnet die Anzeige mit Bewerbungsformular
  (Vorname, Nachname, E-Mail, optional Telefon, Anschreiben, Gehaltsvorstellung, Lebenslauf und weitere
  Anhänge). Erlaubt sind PDF, PNG und JPEG, höchstens 5 Dateien mit je höchstens 10 MB; die Dateien
  liegen verschlüsselt. Pflicht ist das Häkchen zu den Datenschutzhinweisen; optional „Meine
  Bewerbung darf auch für künftige Stellen aufbewahrt werden“ (Talentpool). Gegen Missbrauch gibt es
  eine Grenze je Anschluss (5 Bewerbungen pro Stunde) und ein verstecktes Feld gegen Bots, kein
  Captcha. Mit eingerichtetem Mailversand bekommt die Person eine Eingangsbestätigung; das Hiring Team
  (ohne Team: Admin und HR) bekommt eine Benachrichtigung in der Glocke.
- **Reiter „Bewerbungen“:** als „Spalten“ nach Phase („Neu“, „Sichtung“, „Interview“, „Angebot“,
  „Eingestellt“, „Abgelehnt“, „Zurückgezogen“) oder als „Liste“, filterbar nach Stelle. „Bewerbung
  erfassen“ (Admin, HR) legt eine Bewerbung von Hand an (Quelle „Manuell erfasst“), Anhänge kommen
  danach in der Bewerbung dazu. Ein Klick auf den Namen öffnet die Bewerbung:
  - „Phase“ mit „Phase speichern“; bei „Abgelehnt“ ist ein „Absagegrund“ Pflicht, bei „Abgelehnt“ und
    „Zurückgezogen“ gibt es eine optionale Begründung. Jeder Wechsel steht unter „Verlauf“.
  - „Anhänge“: ansehen (Auge) oder herunterladen; jeder Abruf steht im Audit-Protokoll.
  - „Bewertungen“: 1 bis 5 Sterne je Konto mit Kommentar; die Liste zeigt den Durchschnitt.
  - „Notizen“ mit Verfasser und Zeit; löschen kann der Verfasser sowie Admin und HR.
  - Admin und HR: „Für künftige Stellen aufbewahren“ und „Bewerbung jetzt löschen“.
- **„Als Mitarbeiter übernehmen“** (Admin, HR; in der Phase „Eingestellt“): fragt Vorname, Nachname,
  Personalnummer, Anstelldatum, E-Mail (privat), Position, Standort und Abteilung ab, welche Anhänge
  in die Personalakte kommen (mit Dokumentkategorie) und welche Onboarding-Checkliste starten soll.
  Der Mitarbeiter entsteht wie über „Mitarbeiter anlegen“ (inklusive Tarifgrenze); die Bewerbung bleibt
  mit ihm verknüpft und lässt sich nicht ein zweites Mal übernehmen.
- **Löschfristen:** Abgelehnte und zurückgezogene Bewerbungen löscht HR3000 nach der „Frist in
  Monaten“ ab dem Abschluss (im Talentpool nach „Talentpool in Monaten“) – mit Daten, Notizen,
  Bewertungen und Anhängen. Übrig bleibt nur die anonyme Zählung je Stelle und Phase. Was in den
  nächsten 30 Tagen fällig wird, zeigt der Kasten „Zur Löschung fällig“ über den Bewerbungen. Laufende
  und eingestellte Bewerbungen löscht HR3000 nicht von selbst; Admin und HR können jede Bewerbung
  jederzeit sofort löschen.
- **Bewusst nicht enthalten:** Ausschreiben auf Stellenbörsen, Anbindung eines E-Mail-Postfachs,
  Terminbuchung, Angebote und Verträge erstellen, ein Login für Bewerber.
