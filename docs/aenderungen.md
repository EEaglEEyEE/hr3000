# HR3000 – Änderungen

Neueste zuerst. Bei jeder Änderung hier einen Eintrag ergänzen (Datum, was sich für Nutzer oder
Betrieb ändert). Einzelheiten stehen in der Git-Historie.

## 13.11.2026

- **„Zu klären“ und das Modell „Flexibel ohne feste Tage“:** Unter „Einstellungen“ → „Prüfungen“
  gibt es zwei neue Häkchen für Mitarbeiter mit diesem Arbeitszeitmodell.
  - „Tage dieser Mitarbeiter melden“ (Standard an, wie bisher). Aus: Tage dieser Mitarbeiter
    erscheinen nicht mehr unter „Zu klären“ – weder unvollständige oder widersprüchliche
    Stempelungen noch Sonderfälle (Feiertag, trotz Abwesenheit, mehr als 10 Std.). Sie gelten dann
    auch beim Monatsabschluss, im Monatsbericht und im Lohn-Export nicht als offen. Status und
    Zeiten bleiben am Tag sichtbar; ein Tag ohne auswertbare Stempelung zählt mit 0 Stunden.
  - „Wochen melden, in denen das Wochensoll nicht erreicht wurde“ (Standard aus). An: Bleibt eine
    abgerechnete Woche unter dem Wochensoll, steht am Sonntag der Woche (bei Austritt am letzten
    Beschäftigungstag) der Hinweis „Wochensoll nicht erreicht“ mit Ist und Soll der Woche. Gemeldet
    werden nur Wochen ab dem Tag des Einschaltens.
  - Wer beide Häkchen so setzt (erstes aus, zweites an), sieht flexible Mitarbeiter nur noch, wenn
    sie ihre Wochenstunden nicht erreichen.
- **Tablets, Verteilung per MDM – Freigabeliste:** „Neue Geräte warten auf Freigabe“ zeigt jetzt,
  welche Geräte wirklich warten („wartet gerade“ – sie melden sich jede Minute) und zählt nur diese.
  Anfragen, hinter denen kein wartendes Gerät mehr steht, stehen getrennt unter „Meldet sich nicht
  mehr“, lassen sich mit „Alle entfernen“ wegräumen und verfallen nach 24 Stunden von selbst. Jede
  Anfrage nennt Browser, System und IP-Adresse. Solche Anfragen entstehen, wenn die Start-URL
  irgendwo geöffnet wird – z. B. durch automatische Prüfgeräte des App-Stores nach dem
  Veröffentlichen einer Web-App. Zugriff entsteht daraus nicht. Verwaiste Anfragen blockieren die
  Obergrenze von 20 je Standort nicht mehr.
- **Monatsabschluss, Übersicht:** Die Spalte der offenen Tage rechnet veraltete Tage jetzt selbst
  nach. Bisher zeigte sie nach einer Änderung an Einstellungen oder Arbeitszeitmodellen den alten
  Stand, bis jemand „Zu klären“ geöffnet hatte.

## 12.11.2026

- **Unbekannte Adressen zeigen „Seite nicht gefunden“:** Wer in der Verwaltung eine veraltete oder
  vertippte Adresse aufruft, sieht jetzt einen Hinweis mit dem Link „Zur Startseite“ statt einer
  leeren Seite. Menü und Kopfzeile bleiben stehen.
- **Eigene Rolle mit „Ansehen“ im Reiter „Vertrag & Vergütung“:** Hat die Rolle bei „Vergütung & Lohn“
  nur „Ansehen“, zeigt das Profil Vergütung, Zulagen und Einmalzahlungen ohne die Schaltflächen zum
  Anlegen, Beenden und Löschen („Nur Ansicht – deine Rolle darf hier nichts ändern.“). Dasselbe gilt
  für die Vertragsdaten bei „Mitarbeiter & Stammdaten: Ansehen“. Bisher lehnte erst der Server das
  Speichern ab.
- **Öffentliche API, Stempelungen:** `GET /api/v1/punches` nennt je Stempelung zusätzlich
  `project_id`, `project_number`, `project_name` (Projektzeiten, sonst `null`) und `location_check`
  (`INSIDE`, `OUTSIDE`, `UNKNOWN`; `null` = nicht geprüft). Koordinaten und Tätigkeitsnotizen gibt die
  API nicht aus. Bestehende Felder sind unverändert.
- **DATEV LODAS:** Die „Vorschau“ nennt je Mitarbeiter die mit dem Gehalt abgegoltenen Überstunden
  des Monats als Hinweis („… Std. Überstunden mit dem Gehalt abgegolten – keine Buchung, nur zur
  Information.“). Sie lösen keine Zahlung aus und stehen deshalb nicht in der Datei.
- **Mitarbeiter-Import und „Neuer Mitarbeiter“:** Der CSV-Import kennt das mehrwöchige Modell
  (Spalten `tagesstunden_woche2` bis `tagesstunden_woche4` zusätzlich zu `tagesstunden` als Woche 1,
  optional `turnus_beginn`) und `abgegoltene_ueberstunden` (Stunden je Monat). Im Dialog „Neuer
  Mitarbeiter“ lässt sich bei „Stunden je Wochentag“ die Grenze „Mit dem Gehalt abgegoltene
  Überstunden je Monat“ gleich mit eintragen. Ein Turnus wird weiter im Reiter „Arbeitszeit“ oder
  über ein Arbeitszeitmodell eingerichtet.

## 11.11.2026

- **Neue Funktionen greifen ineinander:** Das mehrwöchige Arbeitszeitmodell zählt jetzt auch in den
  Analysen richtig: „Abwesenheitsquote“ und „Urlaub genommen“ in eigenen Berichten rechnen die
  Soll-Arbeitstage nach der jeweiligen Turnus-Woche, „Köpfe und FTE“ und die Spalte „Wochenstunden“
  nach dem Durchschnitt über den Turnus. Mit dem Gehalt abgegoltene Überstunden stehen in der
  „Lohnbuchhaltung“ je Person („Mit dem Gehalt abgegolten“, auch im freigegebenen Schnappschuss) und
  als Spalte „Davon mit dem Gehalt abgegolten (Std.)“ in eigenen Berichten („Zeit je Monat“).
- **Eigene Rollen kennen die neuen Module:** Neuer Bereich „Recruiting“ in der Rollen-Matrix. Ohne
  diesen Bereich sieht ein Konto mit eigener Rolle nur die Stellen, in deren Hiring Team es steht.
  Eigene Berichte und die neuen Analysen gehören zum Bereich „Auswertungen“ (Vorschau und Export ab
  „Ansehen“, Speichern ab „Bearbeiten“). Hinweise sieht weiterhin nur, wer als
  Meldestellen-Beauftragte:r benannt ist – unabhängig von der Rolle.
- **Datum mit Uhrzeit wurde als „Invalid Date“ angezeigt:** betroffen waren das Ablaufdatum bei
  „Tablets per MDM verteilen“ und das Eingangsdatum von Bewerbungen. Behoben.
- **Standort beim Stempeln (Web-Login, Standard aus):** Unter „Einstellungen“ → „Stempeln“ lässt sich
  „Standort beim Stempeln prüfen (Web-Login)“ einschalten, mit „Nur vermerken“ (Standard) oder
  „Außerhalb nicht erlauben“. Je Standort trägt man unter „Einstellungen“ → „Standorte“ optional einen
  Kreis ein („Breite“, „Länge“, „Radius (m)“ 50–5000, Hilfe „Aktuellen Standort übernehmen“). Beim
  Stempeln im Web-Login fragt der Browser dann einmalig nach dem Standort; gespeichert wird nur, ob die
  Buchung innerhalb oder außerhalb eines Standorts der Firma war (oder „Standort unbekannt“, wenn die
  Freigabe fehlt oder die Position zu ungenau ist) – keine Koordinaten. „Außerhalb nicht erlauben“
  lehnt das Stempeln außerhalb, ohne Freigabe oder bei zu ungenauer Position mit einer Meldung ab.
  Kennzeichen „außerhalb“/„Standort unbekannt“ im Reiter „Zeiterfassung“ (für HR, Führungskräfte und
  die Mitarbeiter selbst) und im Monatsnachweis unter „Bemerkung“. Tablets und Nachträge durch HR sind
  nicht betroffen. Neu in der API: `position` bei `POST /me/punches`, `location_check` an Stempelungen,
  Kreis-Felder an `/locations`.
- **Projektzeiten (Schalter, Standard aus):** Neuer Bereich „Einstellungen“ → „Projekte & Kunden“.
  Admins schalten dort „Projektzeiten“ ein und optional „Projekt ist Pflicht“; Admin und HR pflegen
  Kunden (Name, aktiv) und Projekte (Name, Nummer, Kunde, Kostenstelle, abrechenbar, aktiv, gültig
  von/bis). Projekte mit zugeordneten Zeiten und Kunden mit Projekten lassen sich nur deaktivieren.
  Im Stundenzettel („Mein Bereich“ → „Zeiterfassung“) wählt man je Arbeitszeit ein Projekt (nur
  aktive und am Tag gültige) und optional eine Tätigkeit. Am Tablet und beim Stempeln gibt es bewusst
  keine Projektauswahl. HR ändert Projekt und Tätigkeit beim „Korrigieren“ eines „Kommen“. Neue
  Auswertung „Analysen“ → „Projektzeiten“: Zeitraum, Summe je Projekt, Kunde oder Mitarbeiter,
  abrechenbar getrennt, „CSV exportieren“; Führungskräfte sehen sie für ihren Bereich. Im
  Berichts-Builder gibt es die Datenquelle „Projektzeiten“ (Projekt, Projektnummer, Kunde,
  Abrechenbar, Kostenstelle, Stunden). Neu in der API: `/customers`, `/projects`,
  `GET /reports/project-times`.
- **Zeiten selbst eintragen (Stundenzettel, Schalter, Standard aus):** Unter „Einstellungen“ →
  „Stempeln“ → „Zeiten selbst eintragen (Stundenzettel)“ eingeschaltet, gibt es in „Mein Bereich“ →
  „Zeiterfassung“ die Karte „Stundenzettel“: eine Woche Mo–So, je Tag die Zeiten mit Quelle und die
  Ist-Zeit; mit „Eintragen“ trägt man für einen Tag eine oder mehrere Arbeitszeiten ein, auch mit
  Pausen, über Mitternacht („Folgetag“) und für Tage ohne Stempelung. „Genehmigung nötig“ (Standard
  an): Die Zeiten landen unter „Zu klären“ → „Korrekturanträge“ (Art „Zeiten eingetragen“) und zählen
  erst nach „Übernehmen“; HR wird über die Glocke benachrichtigt, der Mitarbeiter über das Ergebnis.
  Ohne Genehmigung zählen sie sofort, stehen im Audit-Protokoll und lassen sich im erlaubten Zeitraum
  selbst wieder löschen. „Rückwirkend eintragen bis … Tage“ (Standard 7, 0 = nur heute, höchstens 62).
  Abgelehnt werden Tage in der Zukunft und Zeiten, die noch nicht vorbei sind, Überschneidungen mit
  vorhandenen Zeiten oder offenen Anträgen, Tage außerhalb der Beschäftigung und abgeschlossene Monate.
  In der Zeiterfassung des Mitarbeiters steht die Quelle „Selbst eingetragen“. Die API
  (`GET /v1/punches`) liefert genehmigte Zeiten mit `source` `SELF_ENTRY`, beantragte nicht.
- **Gleichzeitige Stempelungen:** Liegen ein „Gehen“ und ein „Kommen“ auf derselben Minute (z. B.
  08:00–12:00 und 12:00–16:00), zählt jetzt immer erst das Ende, dann der Beginn – auch wenn die
  spätere Zeit zuerst erfasst wurde. Bisher wurde so ein Tag als widersprüchlich gemeldet.

## 10.11.2026

- **Hinweisgebersystem (interne Meldestelle):** Neuer Schalter unter „Einstellungen“ →
  „Hinweisgebersystem“ (Standard aus). Eingeschaltet gibt es die Seite `https://<firma>.hr3000.de/hinweis`:
  Beschäftigte und Dritte geben dort ohne Anmeldung einen Hinweis ab – Kategorie, Beschreibung,
  freiwillig Zeitpunkt, Ort und Anhänge, anonym oder mit Kontaktangabe. Danach erscheinen einmalig
  eine Vorgangsnummer und ein Zugangscode; damit sieht die meldende Person unter „Stand abfragen“ den
  Bearbeitungsstand, liest Nachrichten der Meldestelle, antwortet und reicht Dateien nach. Gespeichert
  werden weder IP-Adresse noch eine Verbindung zum Konto, auch nicht, wenn die Person angemeldet ist;
  Inhalte, Kontaktangaben und Anhänge liegen verschlüsselt. Hinweise sehen nur die vom Admin benannten
  „Meldestellen-Beauftragten“ (nicht automatisch Admins oder HR) unter dem neuen Menüpunkt
  „Hinweise“: Liste mit Status und Fristen (Eingangsbestätigung nach 7 Tagen, Rückmeldung nach drei
  Monaten, Überfälliges rot, Erinnerung über die Glocke), Nachrichten an die meldende Person
  („Als Eingangsbestätigung senden“, „Als Rückmeldung senden“), interne Notizen, Status mit
  Abschlussvermerk und Löschdatum drei Jahre nach Abschluss. Ab dem Löschdatum steht der Vorgang
  als „zur Löschung fällig“ in der Liste und lässt sich löschen. „Mein Bereich“ verlinkt die
  Meldeseite. Neu in der API: `/public/whistle/…` (Meldeseite) und `/whistle/…` (Meldestelle,
  Beauftragte).
- **Neue Analysen „Abwesenheitsquote“ und „Köpfe und FTE“:** Unter „Analysen“ (Admin und HR) zeigt
  „Abwesenheitsquote“ je Monat die Abwesenheitstage geteilt durch die Soll-Arbeitstage, gesamt und je
  Abteilung. Die Kategorien sind wählbar, Standard ist Krankheit und Kind krank. „Köpfe und FTE“ zeigt
  je Monatsende die Zahl der Beschäftigten und ihre Vollzeitstellen (Wochenstunden geteilt durch die
  Standard-Arbeitszeit der Firma), dazu Zu- und Abgänge im Monat, gesamt und je Abteilung. Beide mit
  „CSV exportieren“. Neu in der API: `GET /reports/absence-rate` und `GET /reports/headcount`.
- **Eigene Berichte (Schalter, Standard aus):** Unter „Einstellungen“ → „Allgemein“ → „Eigene
  Berichte“ eingeschaltet, gibt es unter „Analysen“ den Reiter „Eigene Berichte“. Dort stellt ihr
  Auswertungen aus „Mitarbeitende“, „Abwesenheiten“ oder „Zeit je Monat“ zusammen: Spalten wählen und
  ordnen, Filter, Sortierung, Gruppierung mit Summen, Vorschau, „CSV exportieren“. Berichte lassen sich
  speichern und mit allen Verwaltungskonten teilen; ändern und löschen dürfen nur Besitzer und Admins.
  Führungskräfte bekommen mit dem Schalter den Menüpunkt „Analysen“ mit nur diesem Reiter und sehen
  in jedem Bericht nur ihren Bereich. Vergütung, Bank, Steuer und Sozialversicherung brauchen
  „Vergütung & Lohn-Export“, persönliche Daten und eigene Felder Admin oder HR. Jeder Lauf und jeder
  Export steht im Audit-Protokoll (ohne Inhalte). Neu in der API: `/report-builder/…`.

- **Recruiting (neu, Standard aus):** Unter „Einstellungen“ → „Recruiting“ schalten Admins Stellen,
  Bewerbungen und eine Karriereseite ein. Stellen mit Abteilung, Standort, Anstellungsart,
  Bewerbungsschluss und „Hiring Team“; veröffentlichte Stellen stehen ohne Anmeldung unter
  `/karriere` mit Bewerbungsformular (Lebenslauf und Anhänge als PDF/Bild, verschlüsselt abgelegt,
  Pflicht-Häkchen zu den Datenschutzhinweisen, Grenze je Anschluss und Schutz gegen Bots). Im
  neuen Menüpunkt „Recruiting“ laufen die Bewerbungen als Spalten nach Phase oder als Liste, mit
  Notizen, Sternen je Person, Verlauf, Absagegrund und Anhängen; das Hiring Team sieht nur seine
  Stellen (Mitarbeitende ohne Verwaltungsrolle in „Mein Bereich“ → „Recruiting“). „Als Mitarbeiter
  übernehmen“ legt aus einer eingestellten Bewerbung den Mitarbeiter an, übernimmt gewählte Anhänge in
  die Personalakte und startet auf Wunsch das Onboarding. Abgelehnte und zurückgezogene Bewerbungen
  werden nach einer einstellbaren Frist (Standard 6 Monate, im Talentpool 12) automatisch gelöscht;
  übrig bleibt nur eine anonyme Zählung je Stelle.
- **Monatlich abgegoltene Überstunden:** Im Arbeitszeitmodell (am Mitarbeiter und in den
  Arbeitszeitmodellen) gibt es das Feld „Mit dem Gehalt abgegoltene Überstunden je Monat (Stunden)“.
  Mehrarbeit eines Kalendermonats bis zu dieser Grenze kommt nicht aufs Überstundenkonto, erst der
  Teil darüber; maßgeblich ist der Saldo des ganzen Monats, Minusstunden bleiben unverändert. Im
  laufenden Monat wirkt die Abgeltung fortlaufend. Der Reiter „Überstundenkonto“ zeigt „Davon
  abgegolten in diesem Monat“, der Monatsnachweis eine Zeile „davon abgegolten“, der Lohn-Export die
  Spalte „Abgegoltene Überstunden (Std.)“ ganz hinten (nur wenn eine Grenze gilt). Ohne Eintrag
  ändert sich nichts. Neu in der API: `settled_overtime_hours` in der Eingabe,
  `settled_overtime_minutes` in der Antwort, `settled_limit_minutes`/`settled_month_minutes` am
  Überstundenkonto, `settled_minutes` am Monatsabschluss.
- **Mehrwöchiges Arbeitszeitmodell (Turnus):** Unter „Soll“ gibt es neben „Wochenstunden“ und
  „Monatsstunden (fest)“ die Variante „Mehrwöchig (Turnus)“ – am Mitarbeiter und in den
  Arbeitszeitmodellen. Je Woche eines Rhythmus über 2 bis 4 Wochen werden die Stunden je Wochentag
  eingetragen (z. B. Woche 1 Mo–Mi, Woche 2 Do–Fr); der Dialog zeigt die durchschnittlichen
  Wochenstunden und Arbeitstage. Woche 1 beginnt in der Woche des „Gültig ab“-Datums oder am
  optionalen „Turnus beginnt am“, danach wiederholt sich der Turnus fortlaufend. Tagessoll,
  Gleitzeitkonto, „Zu klären“, Urlaubs- und Feiertage, Monatsbericht und Lohn-Export folgen der
  jeweiligen Woche; der berechnete Urlaubsanspruch nutzt die durchschnittlichen Arbeitstage (z. B.
  2,5). Bestehende Modelle ändern sich nicht. Neu in der API: `rotation_weeks`/`rotation_start` in
  der Eingabe, `rotation_minutes`/`rotation_start` in der Antwort.
- **Vorbereitende Lohnbuchhaltung:** Neue Seite „Lohnbuchhaltung“ (einschalten unter „Einstellungen“
  → „Lohnbuchhaltung“, Standard aus) für alle mit „Vergütung & Lohn“: je Monat Neuzugänge, Austritte,
  Änderungen im Monat, Vergütung und Zulagen, Abwesenheiten je Art, Stunden und Zuschläge wie im
  Lohn-Export und der Stand des Monatsabschlusses. „Freigeben“ friert den Monat samt CSV und – wenn
  eingerichtet – DATEV-LODAS-Datei verschlüsselt ein; spätere Änderungen werden als „Seit der Freigabe
  geändert“ markiert. „Freigabe zurücknehmen“ nur für Admins. Mit der Rolle „Lohnbüro (nur lesen)“
  sieht die Steuerberatung nur die freigegebenen Monate und lädt deren Dateien; jeder Abruf steht im
  Audit-Protokoll. Die Seite „Lohn-Export“ bleibt unverändert.
- **Eigene Rollen:** Unter „Einstellungen“ → „Rollen“ legen Admins Rollen mit Rechten je Bereich an
  („Kein Zugriff“, „Ansehen“, „Bearbeiten“) – etwa für ein externes Lohnbüro (Vorlage „Lohnbüro (nur
  lesen)“) oder eine Person, die nur Abwesenheiten pflegt. Eine eigene Rolle schränkt die
  Verwaltungsrolle „HR“ ein, sie erweitert sie nie; Admin-Funktionen bleiben bei Admins. Zuweisen beim
  Mitarbeiter unter „HR-Berechtigung“ oder bei den neuen „Verwaltungskonten“ (Zugänge ohne
  Mitarbeiter, z. B. für die Steuerberatung). Menü, Seiten und Reiter zeigen nur die freigegebenen
  Bereiche, der Server prüft jede Anfrage. Für bestehende Konten ändert sich nichts.
- **Abwesenheiten mit Benachrichtigung wieder löschbar:** Eine Abwesenheit ließ sich nicht löschen,
  sobald es eine Benachrichtigung zu ihr gab – nach jeder Entscheidung über einen Antrag (wenn die
  Person einen Zugang hat) und wenn eine Vertretung benachrichtigt wurde. Die Web-App zeigte dann
  einen Serverfehler. Dasselbe galt, wenn eine Krankmeldung einen solchen Urlaub ganz ersetzte. Jetzt
  wird die Abwesenheit gelöscht, die Benachrichtigung bleibt in der Glocke stehen. Der Fehler bestand
  seit Einführung der Benachrichtigungen.

## 09.11.2026

- **Mitarbeiter im Organigramm einer Abteilung hinzufügen:** An jeder Abteilungskarte gibt es für
  Admin und HR das Personen-Symbol „Mitarbeiter hinzufügen“. Der Dialog listet zuerst alle ohne
  Abteilung, dann alle aus anderen Abteilungen (mit ihrer bisherigen Abteilung), mit Suche und „Alle
  auswählen“. Mehrere lassen sich auf einmal aufnehmen; wer aus einer anderen Abteilung kommt,
  wechselt. Entstünde dadurch ein Kreis in den Führungskräften, ändert sich keiner. Das Protokoll
  vermerkt, wer aus welcher Abteilung kam. Neu in der API: `POST /departments/{id}/members`.
- **Mehrere Leitungen und Stellvertretungen, Organigramm direkt bearbeiten:** Eine Abteilung kann
  mehrere gleichberechtigte Leitungen und beliebig viele Stellvertretungen haben. Je Stellvertretung
  wählt ihr die Rechte: „Sieht immer, entscheidet bei Abwesenheit“ (Standard), „Gleiche Rechte wie die
  Leitung“ oder „Nur während Abwesenheit der Leitung“. Anträge gehen an alle Leitungen (und an
  Stellvertretungen mit gleichen Rechten), jede darf entscheiden. Ist keine Leitung da – heute
  abwesend oder ohne Zugang –, entscheiden die Stellvertretungen. Die „Vertretung bei Genehmigungen“
  am Mitarbeiter entfällt: Wer eine Abteilung leitete und eine Vertretung hatte, hat sie jetzt dort als
  Stellvertretung. Fehlt eine abweichende Führungskraft, entscheidet die Abteilung. Admin und HR
  bearbeiten Abteilungen jetzt direkt im Organigramm: an jeder Karte „Bearbeiten“, „Unterabteilung
  anlegen“ und „Löschen“, an jeder Person „Verschieben“; am Computer lassen sich Personen und
  Abteilungen auch mit der Maus auf eine andere Abteilung ziehen. Die API liefert zusätzlich
  `supervisor_ids` (alle Führungskräfte).
- **Abteilungen statt Teams:** Teams gibt es nicht mehr – die Abteilungen sind die einzige
  Struktur. Jede Abteilung bekommt unter „Einstellungen“ → „Abteilungen“ eine „Leitung“; sie ist
  die Führungskraft aller in der Abteilung (auch in Unterabteilungen ohne eigene Leitung). Mit der
  Rolle „Führungskraft“ sieht sie das Tagesgeschäft ihres Bereichs und genehmigt dessen Anträge.
  Am Mitarbeiter heißt das Feld jetzt „Abweichende Führungskraft“ und zeigt, wer automatisch gilt.
  Bestehende Teams wurden zu Abteilungen, die Teamleitung zur Leitung; wer schon in einer anderen
  Abteilung war, behält sie und bekommt die bisherige Teamleitung als abweichende Führungskraft.
  Kalender-Filter, „Abteilungskalender“ (früher Teamkalender), Überschneidungen beim Antrag, CSV-Import
  (Spalte „abteilung“, „team“ geht weiter) und API (`department_id` statt `team_id`) folgen der
  Abteilung. Das **Organigramm** zeigt jetzt den Abteilungsbaum mit Leitung und Mitarbeitern von oben nach
  unten mit Verbindungslinien; „Liste“ ist die eingerückte Ansicht (am Handy Standard).
- **Mitarbeiterliste mit Abteilung:** Die Liste hat eine Spalte „Abteilung“ und einen Filter
  „Alle Abteilungen“ / „Ohne Abteilung“ / je Abteilung. Eine Abteilung zeigt auch die Mitarbeiter
  ihrer Unterabteilungen.
- **Mehrere Pausenzeiten je Arbeitszeitmodell:** Unter „Pause“ → „Feste Uhrzeit“ lassen sich mit
  „Weitere Pausenzeit“ bis zu vier feste Pausen eintragen, z. B. Frühstück 09:00–09:15 und Mittag
  12:00–12:30. Jede wird abgezogen, soweit der Mitarbeiter in ihr da war; die gesetzliche
  Pausenstaffel gilt weiter mindestens. Gilt im Arbeitszeitmodell und individuell am Mitarbeiter.
- **Tablets: kein unbemerkter Tausch per QR-Code mehr:** Für ein Tablet, das schon mit einem Gerät
  verbunden ist (auch per MDM), erzeugt „QR-Code“ erst nach der Rückfrage „Gerät tauschen – QR-Code
  erzeugen“ einen Code. Bisher konnte ein zweites Gerät so den Eintrag übernehmen und das verbundene
  Tablet ohne Hinweis abmelden. Koppeln per QR-Code steht jetzt im Audit-Protokoll, ein Tausch
  meldet zusätzlich eine Warnung an Admins und HR. Ein per MDM verteiltes Tablet, das abgemeldet
  wurde, nennt am Bildschirm den Neustart der Kiosk-App als Weg zur neuen Anfrage.
- **Gleitzeit-Rahmen je Wochentag:** Im Arbeitszeitmodell gibt es unter „Gleitzeit-Rahmen“ →
  „Eigener Rahmen“ das Häkchen „Rahmen je Wochentag unterschiedlich“, z. B. freitags 07:00–14:00
  oder an einzelnen Tagen gar kein Rahmen. Den Gleitzeit-Rahmen gibt es jetzt auch individuell am
  Mitarbeiter (Reiter „Arbeitszeit“). Bestehende Modelle und Mitarbeiter ändern sich nicht.
- **Einstellungen am Tablet:** Die Einstellungsseiten lassen sich bei Tablet-Breite nicht mehr seitlich
  verschieben (betraf u. a. Felder der Personalakte, Feiertagskalender, Pausenregeln, Lohnarten und API &
  Webhooks). Eingabefelder werden schmaler, lange Knöpfe brechen um. Zu lange Werte in Auswahlfeldern
  enden überall mit „…“, statt aus dem Feld zu laufen; geöffnet zeigt die Auswahl den vollen Text.

## 08.11.2026

- **Zwei-Faktor-Pflicht je Gruppe:** Unter „Einstellungen“ → „Allgemein“ → „Zwei-Faktor-Anmeldung
  verpflichtend für“ lassen sich Admin, HR, Führungskräfte und Mitarbeiter ohne Rolle einzeln
  ankreuzen, „Alle“ kreuzt alle an. War die Pflicht bisher eingeschaltet, gilt sie weiter für
  Admin, HR und Führungskräfte. Das Stempeln am Tablet ist nicht betroffen.
- **Tablets per MDM verteilen:** Unter „Tablets“ → „Verteilung per MDM“ gibt es je Standort einen
  Registrierungsschlüssel. Eine Geräteverwaltung (Intune, Endpoint Central, Jamf …) startet die
  Kiosk-App mit dieser Adresse, die Geräte richten sich ohne QR-Code selbst ein. Vorbereitete Einträge
  mit „Gerätename im MDM“ werden direkt verbunden, alle anderen Geräte warten mit Prüfcode auf
  Freigabe. Anleitung im Admin-Handbuch, Abschnitt 10.
- **Mitarbeiter bearbeiten im Reiter „Einstellungen“:** Auf der Mitarbeiterseite gibt es statt des
  Knopfs „Bearbeiten“ den Reiter „Einstellungen“ mit Grunddaten, Login, PIN, Chip und
  HR-Berechtigung. „Bearbeiten“ in der Mitarbeiterliste führt direkt dorthin; neue Mitarbeiter legt
  man weiter mit „Neuer Mitarbeiter“ an.

## 07.11.2026

- **API und Webhooks:** Unter „Einstellungen“ → „API & Webhooks“ legen Admins API-Zugänge mit
  Leserechten an (Mitarbeiter, Abwesenheiten, Stempelungen) und Webhooks für Änderungen an
  Mitarbeitern und Abwesenheiten (signiert, mit Wiederholung). Beschreibung im Admin-Handbuch.
- **Onboarding mit Aufgaben für die neue Person:** On-/Offboarding-Aufgaben können jetzt eine Aktion
  haben: Dokument hochladen oder Daten eintragen (erledigt die Person selbst unter „Meine Aufgaben“)
  und E-Mail beim Start senden.
- **Dokumentvorlagen:** Admins legen unter „Einstellungen“ → „Dokumentvorlagen“ Texte mit Platzhaltern
  an (z. B. Arbeitsbescheinigung). Am Mitarbeiter entsteht daraus mit „Aus Vorlage erstellen“ ein PDF in
  der Personalakte.
- **Eigene Dokumentkategorien:** Unter „Einstellungen“ → „Dokumentkategorien“ legen Admins eigene
  Kategorien mit Rechten an. In freigegebene Kategorien laden Mitarbeiter in „Mein Bereich“ →
  „Dokumente“ selbst hoch.
- **Änderungen vorschlagen:** Mitarbeiter schlagen in „Mein Bereich“ → „Meine Daten“ neue Angaben vor
  (Adresse, Bank, Steuer, freigegebene eigene Felder). Admin und HR übernehmen sie unter „Zu klären“ →
  „Datenänderungen“.
- **Eigene Felder und Verlauf in der Personalakte:** Admins legen unter „Einstellungen“ → „Felder der
  Personalakte“ eigene Abschnitte und Felder an (Text, Zahl, Datum, Auswahl, Ja/Nein, Person), auf
  Wunsch mit Verlauf und „Gültig ab“. Gepflegt wird am Mitarbeiter unter „Weitere Angaben“; der neue
  Unterreiter „Verlauf“ zeigt alle Änderungen am Mitarbeiter.
- **Genehmigung über die Führungskraft:** Je Abwesenheitsart lässt sich wählen, wer genehmigt:
  Teamleitung oder Admin/HR (wie bisher), die Führungskraft, erst Führungskraft dann Admin/HR oder
  nur Admin/HR. Ist die Führungskraft abwesend, entscheidet ihre „Vertretung bei Genehmigungen“.
  Anträge zeigen, bei wem sie gerade liegen.
- **Stammdaten in der Personalakte:** Neuer Unterreiter „Stammdaten“ mit Status (Onboarding, Aktiv,
  Auszeit, Inaktiv), Kostenstellen (auch anteilig), Adresse, Familie und – mit „Vergütung &
  Lohn-Export“ – Bank, Steuer und Sozialversicherung. Kostenstellen pflegt ihr unter „Einstellungen“
  → „Kostenstellen“. Mitarbeiter sehen ihre Angaben in „Mein Bereich“ → „Meine Daten“.
- **Abteilungen, Position, Führungskraft und Organigramm:** Unter „Einstellungen“ → „Abteilungen“
  lassen sich Abteilungen verschachtelt anlegen. Am Mitarbeiter gibt es „Abteilung“, „Position“ und
  „Führungskraft“. Daraus entsteht das neue „Organigramm“ im Menü; Mitarbeiter sehen es in „Mein
  Bereich“, wenn die Firma es freigibt (Standard aus).
- **Zwei-Faktor-Anmeldung:** Jedes Konto kann sie unter „Zwei-Faktor-Anmeldung“ mit einer
  Authenticator-App einrichten; danach fragt die Anmeldung zusätzlich nach einem Code. Dazu gibt es
  10 Wiederherstellungscodes. Admins können sie unter „Einstellungen“ → „Allgemein“ für Admin, HR und
  Führungskräfte verpflichtend machen und im Mitarbeiter-Dialog zurücksetzen.
- **Ein Konto je Person:** Admins, HR, Führungskräfte und Mitarbeiter melden sich über dasselbe
  Konto an; jede E-Mail-Adresse gibt es in der Firma nur einmal. War eine Adresse bisher als
  Verwaltungskonto und als Mitarbeiter-Login vorhanden, ist daraus ein Konto mit Rolle und
  „Mein Bereich“ geworden (Rolle und Passwort des Verwaltungskontos gelten). **Nach dem Update
  meldet sich jeder einmal neu an**; Passwörter bleiben, Tablets sind nicht betroffen.
- **Ein Tablet je Zugang:** Ein Tablet-Eintrag gilt jetzt für genau ein Gerät. Meldet sich ein
  weiteres Gerät mit demselben Zugang an, wird es abgewiesen; Admins und HR bekommen eine Warnung
  (Glocke und E-Mail), die Tablet-Liste zeigt den Versuch, das Audit-Protokoll ebenso. Der QR-Code
  enthält nur noch einen einmaligen Kopplungscode (15 Minuten), „Token kopieren“ entfällt.
  „Kopplung aufheben“ meldet ein verlorenes Tablet sofort ab. Bestehende Tablets laufen weiter und
  werden bei der nächsten Anmeldung an ihr Gerät gebunden. Teilen sich bisher mehrere Tablets einen
  Eintrag, braucht jedes weitere einen eigenen.
- **Kalender abonnieren (iCal):** Im „Kalender“ (und in „Mein Bereich“) erzeugt „Kalender abonnieren
  (iCal)“ einen privaten Abo-Link für Outlook, Google oder Apple Kalender – mit denselben Abwesenheiten,
  die man in HR3000 sieht, und den Feiertagen.
- **Teamkalender für Mitarbeiter:** Mit der neuen Einstellung sehen Mitarbeiter in „Mein Bereich“
  den Reiter „Teamkalender“ ihres Teams. Je Abwesenheitsart lässt sich festlegen, ob Kollegen die Art
  sehen („farbig“) oder nur, dass jemand fehlt („ausgegraut“, Standard). Standard aus.
- **Urlaubskonto korrigieren:** Am „Urlaubsanspruch“ lassen sich Tage gutschreiben oder abziehen
  („Urlaubskonto korrigieren (± Tage)“, mit Begründung), auf Wunsch mit Verfallsdatum – z. B. 2 Tage,
  die bis 31.03. genommen werden müssen. Verbraucht wird zuerst, was am frühesten verfällt.
- **Zusatzurlaub nach Betriebszugehörigkeit:** Unter „Urlaub & Anträge“ lassen sich Stufen anlegen
  (z. B. ab 5 Jahren + 1 Tag, ab 10 Jahren + 2 Tage). Sie zählen ab dem Kalenderjahr, in dem die Jahre
  vollendet werden, und fließen in den berechneten Urlaubsanspruch ein.
- **Urlaub bei Elternzeit kürzen:** Neue Einstellung unter „Urlaub & Anträge“: Je vollem
  Kalendermonat Elternzeit (Kategorie „Mutterschutz/Elternzeit“) wird der Jahresurlaub um 1/12
  gekürzt (§ 17 BEEG). Standard aus.
- **Sonderzahlungen:** Einmalzahlungen lassen sich „in % des Monatsgehalts“ anlegen (z. B. Urlaubsgeld
  50 %, 13. Monatsgehalt 100 %) und „jährlich wiederholen“ – bis sie beendet werden. Lohn-Export, DATEV
  und Lohnkosten rechnen sie zum jeweiligen Zahltag.
- **QR-Code statt Chip:** Am Mitarbeiter erzeugt „QR-Code fürs Tablet“ einen QR-Code (zum Ausdrucken
  oder fürs Handy). Am Tablet steht dafür „QR-Code scannen“ (Frontkamera, Chrome/Android); der Code
  gilt wie der Chip. Ohne Chip vergibt HR3000 eine zufällige Chip-UID.
- **Aufbewahrungsfristen:** Dokumente, deren „Aufbewahren bis“ abgelaufen ist, stehen unter
  „Analysen“ → „Handlungsbedarf“ zur Prüfung. Gelöscht wird weiterhin nichts automatisch.
- **E-Mails selbst abbestellen:** In der Glocke legt jede Person fest, ob sie Benachrichtigungen
  auch per E-Mail bekommt („Benachrichtigungen auch per E-Mail“, Standard an). In der Glocke bleiben
  sie immer.
- **Mein Bereich als App:** Die HR-Webapp lässt sich auf dem Handy mit „Zum Startbildschirm
  hinzufügen“ wie eine App ablegen (eigenes Symbol, ohne Browserleiste).
- **Erinnerungen:** Unter „Einstellungen“ → „Allgemein“ lassen sich „Erinnerungen an Admin und HR“
  einschalten: Probezeitende, Befristungsende, bevorstehender Austritt und verfallender Resturlaub
  (den bekommt auch die Person selbst) – als Benachrichtigung und mit Mailversand per E-Mail.
  Standard aus.
- **Audit-Protokoll:** Erfolgreiche Anmeldungen in der Webapp werden protokolliert (ohne
  IP-Adresse), und die angezeigten Einträge lassen sich mit „CSV exportieren“ speichern.
- **Grenzen fürs Überstundenkonto:** Unter „Einstellungen“ → „Arbeitszeit“ lassen sich eine
  Ober- und eine Untergrenze einstellen. Wer ab 90 % der Obergrenze steht oder unter der Untergrenze
  liegt, erscheint unter „Zu klären“ im Reiter „Grenzen“ (früher „Monatsgrenzen“). Ohne Einstellung
  ändert sich nichts.
- **Überstundenkonto buchen:** Unter „Korrekturbuchungen Überstundenkonto“ gibt es
  die Aktionen „Kontostand anpassen“, „Neuen Kontostand festlegen“ (bucht die Differenz),
  „Überstunden auszahlen“ mit „Faktor“ (z. B. 1,5) und „Anfangskontostand“. Auszahlungen mit Faktor
  erscheinen im Lohn-Export zusätzlich gewichtet in einer eigenen Spalte.
- **Kommentar und Nachweis bei Abwesenheiten:** Je Abwesenheitsart lässt sich „Kommentar
  erforderlich“ einschalten (nicht bei Krankheit). Bei Arten mit „Nachweis ab Tag“ können Mitarbeiter
  und HR den Nachweis direkt am Eintrag hochladen („Nachweis hochladen“); er landet verschlüsselt in
  der Personalakte unter „Dokumente“.
- **Überschneidungen im Team:** Beim Eintragen einer Abwesenheit und unter „Zu klären“ →
  „Urlaubsanträge“ steht, wer aus demselben Team im Zeitraum ebenfalls fehlt (oder es beantragt hat);
  bei Urlaubsanträgen zusätzlich der Resturlaub. Mitarbeiter sehen den Hinweis im eigenen Antrag nur
  mit der neuen Einstellung (Standard aus) und ohne Art der Abwesenheit.
- **Vertretung bei Abwesenheiten:** Je Abwesenheitsart lässt sich einstellen, ob eine
  „Vertretung“ abgefragt wird („optional“ oder „Pflicht beim Antrag“). Die Vertretung wird
  benachrichtigt, sobald die Abwesenheit gilt, und steht in der Liste und bei den Urlaubsanträgen.
  Standard: nicht abfragen – für bestehende Arten ändert sich nichts.
- **Halbe Feiertage:** Im „Feiertagskalender“ lässt sich ein eigener Feiertag als „Halber Tag“
  anlegen (z. B. Heiligabend, Silvester). An dem Tag gilt das halbe Soll, ein Urlaubstag zählt halb.
  Ganze Feiertage bleiben, wie sie sind.
- **Neue Abwesenheitskategorien:** „Mutterschutz/Elternzeit“, „Kurzarbeit“, „Unentschuldigt“ und
  „Pflege von Angehörigen“ (unter „Einstellungen“ → „Abwesenheitsarten“ als Kategorie wählbar). Sie
  rechnen wie „Unbezahlt“ – das Soll entfällt –, erscheinen im „Lohn-Export“ aber als eigene Spalte
  (z. B. „Kurzarbeit-Tage“), sobald sie im Monat vorkommen. Ohne solche Einträge bleibt der Export
  wie bisher.
- **Neue Begriffe:** Die Oberfläche nutzt jetzt durchgehend dieselben Begriffe wie andere verbreitete
  HR-Programme: „Überstundenkonto“ statt „Gleitzeitkonto“/„Gleitzeitsaldo“ (Reiter „Überstundenkonto“
  statt „Saldenübersicht“, „Überstundenkonten führen ab“), „Führungskraft“ statt „Teamleiter/in“,
  „Anstelldatum“ statt „Eintrittsdatum“, „Analysen“ statt „Auswertungen“, „Audit-Protokoll“ statt
  „Audit-Log“, „On- & Offboarding“ statt „Checklisten“ (eine Vorlage wird am Mitarbeiter
  „zugewiesen“) und „Feiertagskalender“ statt „Feiertage“. Berechnungen, Rechte und Einstellungen
  bleiben unverändert; Spalten und Werte der Exporte (Lohn-Export, CSV, DATEV) ebenso.
- **Arbeitszeitmodelle:** Unter „Einstellungen“ → „Arbeitszeitmodelle“ lassen sich Modelle wie
  „Vollzeit Büro“ anlegen – mit Soll, Arbeitstagen, Pause, Kernzeit und neu je Modell eigenem
  **Gleitzeit-Rahmen** und eigener **Toleranz der Pünktlichkeitsprüfung**. Zugewiesen wird am
  Mitarbeiter (Reiter „Arbeitszeit“ → „Arbeitszeitmodell zuweisen“) oder schon beim Anlegen. Ändert
  sich ein Modell ab einem Stichtag („Ändern ab Stichtag“), gilt das für alle zugewiesenen
  Mitarbeiter; die Zeit davor bleibt, abgeschlossene Monate werden nicht angetastet. Je Mitarbeiter
  gilt entweder ein Modell oder wie bisher die individuelle Eingabe – bestehende Mitarbeiter bleiben
  individuell.
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
