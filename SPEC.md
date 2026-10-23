# Spezifikation – All-in-One Lab Assistant

Status: umgesetzt, Stand 2026-10-21.

Dieses Dokument beschreibt zuerst die gemeinsame Shell und die neuen Module.
Teil B enthält unverändert die Anforderungen des bestehenden SDS-PAGE-Editors.

## Teil A – Arbeitsbereich, Notizbuch, Rechner und Kalender

### A.1 Zweck

Ein lokaler Arbeitsbereich führt Gel-Dokumentation, Laborberechnungen,
Praktikumsnotizen und Protokollerstellung zusammen. Die Anwendung muss ohne
Cloud-Konto nutzbar sein, offline arbeiten und alle Daten in einem sicherbaren
Ordner ablegen. Der Gel-Editor bleibt funktional und visuell unverändert.

### A.2 Gestaltungsprinzipien

1. **Lokal zuerst.** Notizbuch, Kalender und Medien liegen im Datenordner.
   Cloud-Dienste werden nur nach ausdrücklicher Auswahl und Bestätigung
   kontaktiert.
2. **Kein Datenverlust beim Wechsel.** Navigation zwischen Modulen darf weder
   Gel-Projekt noch Notizentwürfe, Rechnerzustände oder Kalenderfilter verlieren.
3. **Zweisprachigkeit.** Jeder sichtbare Text existiert in Deutsch und Englisch.
   Keine hartkodierten UI-Texte; neue Schlüssel werden in beiden Tabellen geführt.
4. **Ruhige, wissenschaftliche Oberfläche.** Keine Emojis; typografische Pfeile
   und Material-Icons sind zulässig.
5. **Nachvollziehbarkeit.** Protokolle führen ihre Quellen mit; Anhänge tragen
   Prüfsummen; KI-Ausgaben werden vor der Anzeige geprüft.

### A.3 Shell, Dashboard und Navigation (FR-A1)

- **Dashboard:** großzügiger Titel **Lab Assistant** sowie eine rechte Leiste
  mit kompaktem Monatskalender und dauerhafter Laboraufgaben-Checkliste.
- **Globale Haupt-Sidebar:** schlank und in jedem Modul identisch. Sie enthält
  ausschließlich die fünf Navigationsziele, globale Einstellungen (Sprache,
  System-Theme, Datenordner, Kalender-Konten, Einführung) und die allgemeine
  Hilfe. Gel- oder bildspezifische Parameter sind dort nicht zulässig.
- **Praktikumsordner:** farbige, klickbare Karten für jedes Praktikum mit
  Fachbereich, Anzahl der Versuchstage und Farbwahl. Ein Klick öffnet direkt
  die Tageskarten des Praktikums im Notizbuch.
- **Schnellstart:** vier Kacheln für Notizen, Gel-Editor, Laborrechner und
  Kalender mit Material-Icon und Kurzbeschreibung.
- **Icon-Leiste:** genau fünf Ziele – Übersicht, Notizen, Gel-Editor (Pipette),
  Laborrechner, Kalender. Der aktive Eintrag ist hervorgehoben. Ein Klick
  wechselt die Ansicht ohne Zustandsverlust.
- **Einstellungen (Popover in der Haupt-Sidebar):** Sprache
  (Deutsch/Englisch), Hell-/Dunkelmodus, Datenordner, Kalender-Konten und
  Neustart der Einführung. Änderungen wirken sofort und lösen einen
  vollständigen Rerun aus.
- **Schnellhilfe (Popover in der Haupt-Sidebar):** zweisprachige Hilfe zu
  Navigation, Gel-Editor, Notizformatierung, Rechnern, Kalender und Datenschutz.
- **Gel-Editor-Bereich:** Bei aktivem Gel-Editor öffnet **Editor-Optionen** ein
  eigenes Panel direkt am Editor. Es bündelt GelDoc Studio, Projektverwaltung,
  Export und Harmonisierung. Typografie und Spurnummern liegen im Reiter
  **Typografie** von **Spuren & Labels**; dieser zeigt zusätzlich eine Vorschau
  der bearbeiteten Abbildung. Die globale Sidebar bleibt unverändert; in der
  Shell folgt das Abbildungs-Farbschema dem globalen Hell-/Dunkelmodus. Im
  eigenständigen Betrieb von `app.py` bleiben Projekt-, Theme- und Exportoptionen
  in der Editor-Seitenleiste.
- **Onboarding:** fünfteilige, standardmäßig eingeklappte Einführung (Module,
  Praktika, Quellen, Synthese, Rechnen/Planen) mit Zurück, Weiter,
  Überspringen und Abschluss. Der Status bleibt in der Sitzung erhalten und ist
  über die Einstellungen zurücksetzbar.
- **Demo:** ein Klick lädt das vorhandene SDS-PAGE-Demo und wechselt in den
  Gel-Editor. Bei bereits bearbeitetem Projekt ist eine Bestätigung erforderlich.

### A.4 Praktika, Tageskarten und Aufgaben (FR-A2)

- Hierarchie: `Praktikum / Fachbereich` → `Versuchstag / Datum` →
  `Versuchseinheit / Notiz`.
- Jedes Praktikum besitzt eine lokal gespeicherte Ordnerfarbe aus einer Palette
  oder über den Color-Picker. Die Startseite zeigt farbige Ordnerkarten, das
  Notizbuch klickbare Tageskarten `V1`, `V2`, ….
- Projektübersicht listet alle Praktika mit Tagen, Quellen, Anhängen und
  Protokollzahlen; ein Tag öffnet direkt das Notizbuch.
- Persistente To-do-Checkliste für Laboraufgaben mit Offen/Erledigt-Status,
  optionalem Fälligkeitsdatum und Löschen; die Aufgaben liegen in derselben
  SQLite-Datenbank wie das Notizbuch. Datierte To-dos werden mit dem Kalender
  synchronisiert.
- Anlegen, Bearbeiten, kaskadierendes Löschen und Suche über Titel und Volltext.
- Persistenz in SQLite; Originalmedien als Dateien mit SHA-256-Prüfsumme.
  `LAB_ASSISTANT_DATA_DIR` verlegt den gesamten Datenordner.

### A.5 Multimodales Notizbuch und Gel-Brücke (FR-A3)

- Markdown-Text mit Tabellen; Autosave beim Verlassen eines Eingabefelds.
- **Universal-Import:** beliebig viele Dateien gleichzeitig, jedes Format bis
  50 MB pro Datei; ausführbare Formate werden abgewiesen. Bilder und PDFs
  unterstützen zusätzlich optionale Tesseract-OCR.
- Audioaufnahme oder Upload mit optionaler lokaler `faster-whisper`-
  Transkription oder bestätigter OpenAI-Verarbeitung.
- Originaldateien bleiben unverändert als Anhang; extrahierter Text ist vor dem
  Speichern editierbar.
- **Gel-Brücke:** liest Spurtabellen, Zeilen wie `Spur 1: Marker` und
  Pipettierschemata, übernimmt das Gelbild des Versuchs, erkennt Spuren im Bild
  und erzeugt ein Gel-Projekt mit Probenlabels, Bedingungen, Marker-Spuren und
  Zielbanden aus kDa-Angaben. Der Ablauf ist deterministisch und öffnet direkt
  den Gel-Editor. Bei vorhandener Gel-Arbeit ist eine Bestätigung erforderlich.
- Reduzierte Oberfläche: prominente Aktionen **Dokumente / Dateien
  hinzufügen** und **Gel automatisch mit Notizen annotieren**, darunter nur
  die Bereiche Notizen/Quellen und Zusammenfassung.
- Medienprüfung erkennt fehlende oder veränderte Anhänge.

### A.6 Zero-Loss-Protokollsynthese (FR-A4)

- Sechs feste Abschnitte: Kopfdaten; Ziel und Fragestellung; Material und
  Methoden; Rohdaten und Beobachtungen; Ergebnisse und Auswertung; Diskussion
  und Fehleranalyse.
- Zwei Ausgabestile als kurzer Umschalter: Stichpunkte und akademischer
  Fließtext. Provider und Modell liegen eingeklappt unter Synthese-Optionen.
- **Zero-Loss-Regel:** Kein Messwert, keine Auffälligkeit und keine Randnotiz
  darf ausgelassen oder gekürzt werden. Jede Quelle wird zusätzlich unverändert
  als Quellenanhang angefügt.
- Quellengetreue Vorlage funktioniert ohne KI. Optional lokales Ollama oder
  OpenAI nach Auswahl und Bestätigung; API-Schlüssel werden nicht gespeichert.
- Audit auf Abschnitte, Quellenverweise und Zahlen. Bei Lücken wird der
  vollständige quellengetreue Text verwendet und die Lücken werden benannt.
- Versionierte Speicherung, erneutes Laden, Bearbeiten und Export als Markdown,
  PDF und DOCX.

### A.7 Laborrechner (FR-A5)

- **Neubauer:** `C = (Zellen gesamt / Quadrate) × Verdünnung × 10⁴ Zellen/mL`;
  Gesamtzellzahl, Viabilität `Lebend / Gesamt × 100`, benötigte Suspension und
  Mediumsvolumen für Zielzahl beziehungsweise Zielkonzentration.
- **Molarität:** `m = c × V × M`, nach jeder Variablen auflösbar, mit
  Einheitenkonvertierung für Masse, Konzentration, Volumen und molare Masse.
- **Verdünnung:** `C₁ × V₁ = C₂ × V₂`, nach jeder Variablen auflösbar;
  Aufkonzentrieren wird abgelehnt.
- **Mastermix:** Reagenzien und Volumen pro Reaktion, Skalierung auf `N`
  Reaktionen plus Pipettierüberschuss (0–500 %, Standard 10 %), CSV-Export.
- **Einheiten:** Umrechnung von Masse, Volumen, Konzentration, molarer Masse,
  Zeit und Temperatur mit passenden Einheiten und Validierung.
- **qPCR-Auswertung:** ΔCt für Probe und Kontrolle, ΔΔCt sowie relative
  Expression nach der ΔΔCt-Methode mit einstellbarer Primer-Effizienz.
- Ungültige, negative oder unvollständige Eingaben erzeugen eine lokalisierte
  Fehlermeldung statt einer Ausnahme in der Oberfläche.

### A.8 Labor-Kalender (FR-A6)

- Monatsraster mit heutigem Tag, Terminen und Navigation vor/zurück;
  Datumsangaben erscheinen auf Deutsch als `TT.MM.JJJJ`.
- Termine: Titel, Datum, optionale Uhrzeit, Kategorie (Praktikumstag, Frist,
  Inkubation, Abgabe, To-do, Sonstiges), Wichtigkeit und Notiz.
- Kategorien bestimmen die Farbe; hohe Wichtigkeit wird kräftig hervorgehoben.
- Dashboard zeigt die nächsten Termine; der Kalenderbereich erlaubt Anlegen,
  Löschen, Import und Export.
- Neben **Neuer Termin** führt eine To-do-Liste offene und erledigte Aufgaben.
  Ein To-do mit Fälligkeitsdatum wird automatisch als Kalendereintrag angelegt
  und beim Erledigen oder Löschen wieder entfernt.
- ICS-Import per Datei, ICS-Export als Download.
- Kalender-Konten für Google, Apple/iCloud, Outlook, CalDAV und generisches
  iCal mit veröffentlichter http(s)-Abo-Adresse. Synchronisation nur auf
  Knopfdruck; Status und Zeitpunkt werden gespeichert. Keine OAuth-Token,
  keine Passwörter, keine Hintergrundabfragen.
- Feeds maximal 2 MB; wiederkehrende Termine werden mit der ersten Occurrence
  importiert. Import ist idempotent über die iCalendar-UID.

### A.9 Nicht-funktionale Anforderungen

- **Persistenz:** SQLite mit WAL, kurzen Verbindungen und Fremdschlüsseln;
  keine offenen Dateihandles über Reruns.
- **Sicherheit:** Universal-Import akzeptiert beliebige Dateitypen außer
  ausführbaren Formaten; die Größe ist auf 50 MB pro Datei begrenzt. Anhänge
  werden unter UUID-Namen gespeichert; Pfade aus Uploads werden nicht übernommen.
- **Datenschutz:** keine Telemetrie; Cloud nur nach Consent; Schlüssel nur im
  Speicher.
- **Bedienbarkeit:** Deutsch und Englisch, Hell und Dunkel, verständliche
  Fehlermeldungen, kein Emoji-Einsatz.
- **Testbarkeit:** Domänenlogik in reinen Modulen; Streamlit-Smoke-Tests nur in
  `tests/test_lab_ui.py`.

### A.10 Abnahmekriterien

1. `lab_assistant.py` startet ohne Bild und ohne Fehlermeldung.
2. Alle fünf Navigationsziele sind erreichbar; Modulwechsel erhält Eingaben.
   Die globale Sidebar bleibt in jedem Modul identisch und enthält keine
   gel- oder abbildungsspezifischen Optionen; diese liegen unter
   **Editor-Optionen**.
3. Sprache und Theme wechseln sofort und vollständig.
4. Ein Praktikum mit Farbe, Tag, Textquelle und Anhang lässt sich anlegen,
   suchen, sichern und kaskadierend löschen; Tageskarten und To-dos bleiben
   nach einem Neustart erhalten.
5. Universal-Import nimmt mehrere Dateien unterschiedlicher Formate auf;
   ausführbare Dateien werden abgewiesen.
6. Die Gel-Brücke erzeugt aus einer Spurtabelle und einem angehängten Gelbild
   ein Projekt mit Labels, Bedingungen und Zielbande und öffnet den Editor.
7. Protokoll in Fließtext und Stichpunkten erzeugbar; Audit und Quellenanhang
   vorhanden; PDF, DOCX und Markdown herunterladbar.
8. Alle Rechner liefern die dokumentierten Formeln und Fehlerfälle.
9. Kalendertermin anlegen, als ICS exportieren, wieder importieren und über
   eine gemockte Abo-Adresse synchronisieren; ein datiertes To-do erscheint im
   Kalender und verschwindet beim Erledigen.
10. `python -m unittest discover -s tests` und `ruff check` sind fehlerfrei.
11. Der Gel-Editor bleibt einzeln und in der Shell startbar; Gel-Tests bleiben grün.

---

# Teil B – GelDoc Studio (unverändert)

Anforderungs- und Briefing-Dokument für die Anwendung zur wissenschaftlichen
Dokumentation, geometrischen Entzerrung und publikationsfertigen Annotation von
SDS-PAGE-Gelbildern.

Status: umgesetzt (v1), Stand 2026-10-20.

## 1. Zweck und Zielgruppe

GelDoc Studio erzeugt aus einem oder mehreren Gel-Scans eine publikationsfertige
Abbildung mit Beschriftungsebene: Panel-Buchstabe, Gruppenüberschriften,
Bedingungszeilen, Spurlabels, kalibrierte kDa-Leiter und Pfeile zu Zielbanden.

Zielgruppe sind Laborwissenschaftlerinnen und Laborwissenschaftler, die Abbildungen
für Manuskripte, Abschlussarbeiten, Poster und Supplemente benötigen, ohne dafür
Grafiksoftware zu bedienen.

**Bewusste Begrenzung:** Das Programm deckt ausschließlich die Dokumentation von
SDS-PAGE-Gelbildern ab – Import, Perspektiv-Entzerrung, Beschriftung,
Leiter-Kalibrierung, Zielbanden und Export. Densitometrische Quantifizierung,
Kalibrierkurven und Statistik sind nicht Teil des Funktionsumfangs.

## 2. Gestaltungsprinzipien

1. **Das Originalgel bleibt unberührt.** Kein Pixel des Gelbildes wird überzeichnet,
   beschriftet oder skaliert. Beschriftungen liegen ausschließlich im Canvas-Rahmen.
2. **Strikte Trennung von Bild und Text.** Texte, Ticks und Pfeile docken an der
   Gelkante an, dringen aber nie in die Gelmatrix ein.
3. **Zweisprachigkeit.** Alle sichtbaren Texte, Tooltips und Fehlermeldungen liegen
   in Deutsch und Englisch vor. Freie Texteingaben sind sprachunabhängig.
4. **Ruhige Oberfläche.** Keine Emojis in UI, Export und Dokumentation. Erlaubt sind
   reine typografische Richtungspfeile (zum Beispiel `↻`, `↺`, `⇋`, `⇅`, `↔`, `→`).
5. **Nicht-destruktive Bearbeitung.** Geometrie, Filter und Harmonisierung werden
   jederzeit aus dem Quellbild neu berechnet; der Projektstand ist vollständig
   rekonstruierbar.

## 3. Funktionale Anforderungen

### FR-1 Import und Geometrie

- **Start ohne Bild:** Eine neue Sitzung enthält kein Beispielbild. Die Arbeit beginnt
  mit dem Upload oder über die Schaltfläche „Referenzgel laden“.
- Upload von PNG, JPEG und TIFF inklusive EXIF-Drehung, Transparenz und Mehrfach-TIFF.
- Automatischer Zuschnitt einfarbiger Ränder sowie interaktiver Bounding-Box-Zuschnitt
  über zwei Bereichsregler (X und Y in Prozent).
- **Bildseite:** *Original* und *Verarbeitet* stehen untereinander; direkt anschließend
  an das verarbeitete Bild folgt die Perspektiv-Entzerrung mit den vier Eckpunkten.
  Alle Blöcke aktualisieren sich live und die Spalte bleibt beim Scrollen sichtbar.
- **Bedienseite:** Zuschnitt, Drehen/Spiegeln, Feinrotation und Filter. Eine eigene
  Zuschnitt-Vorschau entfällt, weil das *Verarbeitet*-Bild bereits das Ergebnis zeigt.
- Perspektiv-Entzerrung über vier interaktiv ziehbare Eckpunkte.
- 90-Grad-Drehung links und rechts, Spiegeln horizontal und vertikal, Feinrotation
  von -45 bis +45 Grad in 0,1-Grad-Schritten.
- Live-Filter: Helligkeit, Kontrast, Gamma, Invertieren, optional CLAHE.
- Gegenüberstellung Original und Verarbeitet.

### FR-2 Spuren und Labels

- Automatische Spurenschätzung und manuelles Verschieben, Einfügen und Löschen.
- **Anzahl direkt vorgeben:** Ein Zahlenfeld setzt die Spurenanzahl; die Spuren werden
  gleichmäßig verteilt und lassen sich anschließend frei verschieben.
- Pro Spur: Probenbezeichnung oben, unteres Label, X-Position, Rolle (Marker oder Probe).
- **Hoch- und Tiefstellung** in Proben- und Unterlabels über Markup: `^{...}` für
  Hochstellung, `_{...}` für Tiefstellung, wahlweise mit einzelnes Zeichen (`^2`, `_2`).
  Breite und Umbruch berücksichtigen die kleinere Skriptschrift.
- Spurlabels wahlweise 0, 45 oder 90 Grad gedreht, kollisionsfrei aus der
  Texthöhe berechnet.
- **Spurnummern:** kleine aufsteigende Zahlen direkt an der Spur. Die Position ist
  wählbar zwischen **oben** (unmittelbar über der Gelkante, im Kopfbereich),
  **unten** (unter der Gelkante) und **aus**. Es wird immer nur eine Position
  gleichzeitig verwendet. Der Umschalter liegt in der Seitenleiste und in Tab 2
  (beide synchron); bei *aus* werden auch die Nummern-Badges im Editor ausgeblendet.
- Gruppenüberschriften über mehreren Spuren mit optionaler Trennlinie.
- Bedingungsmatrix mit beliebig vielen Zeilen und Werten je Spur.
- **Zweispaltige Arbeitsfläche in allen Tabs:** links das Bild, rechts die scrollbare
  Bedienung. Das Bild bleibt beim Scrollen sichtbar (sticky). In Tab 2 ist die Seite
  des Bedienfelds zusätzlich umschaltbar (links/rechts).
- **Stabile Ansicht:** Aktionen dürfen weder den aktiven Tab noch die Scrollposition
  verändern. Bestätigungen werden daher als kurze Einblendung angezeigt und nicht als
  Block oberhalb der Tabs, der das Layout verschieben würde.

### FR-3 Marker und Leiter

- Voreingestellte Referenzleiter mit den Molmassen 170, 130, 100, 70, 55, 40, 35,
  25 und 10 kDa sowie vermessenen Y-Positionen.
- **Anzahl direkt vorgeben:** Ein Zahlenfeld erzeugt genau so viele Marker, verteilt sie
  gleichmäßig über die Leiter und vergibt log-interpolierte Werte; danach sind Position
  und Wert jedes Markers einzeln editierbar.
- Banden ergänzen, verschieben und löschen; Vorschlag per log-linearer
  Interpolation.
- **Einheit der Markerwerte frei wählbar** (Textfeld, Standard `kDa`, z. B. auch
  `Da`, `bp`, `kb`, `ng`); sie erscheint in Skala, Tabelle, Etiketten und Metadaten.
- Automatische Bandenerkennung links und rechts, Ausschluss der Laufmittelfront.
- Skalenseite links, rechts oder beidseitig.

### FR-4 Zielbanden

- Horizontale Pfeile, die an der Gelkante andocken und in den Außenrand laufen.
- **Interaktion:** Klick in den Außenrand legt einen Pfeil an, Ziehen am Pfeil verschiebt
  ihn, Doppelklick entfernt ihn. Zusätzlich Regler, Textfeld und Tabelle in der
  Bedienspalte. Eine Verschiebung im Editor bleibt erhalten und wird nicht durch den
  Y-Regler überschrieben.
- Beschriftung frei wählbar, zum Beispiel `37 kDa` oder `GFP-Fusion`.
- Pfeile links oder rechts; bei Konflikt mit der kDa-Skala hat der Pfeil Vorrang und
  die Skala wird auf der betroffenen Seite ausgeblendet (mit UI-Hinweis).

### FR-5 Multi-Gel und Export

- Harmonisierung A: alle Gele auf gleiche Pixelhöhe skalieren.
- Harmonisierung B: zwei Referenzbanden vertikal affin ausrichten, Annotationen
  werden mit abgebildet.
- Einzel-Export je Panel und kombinierte Figur aller Panels mit einheitlichen
  Kopf- und Fußbereichen.
- PNG, TIFF und PDF in 300 DPI (alternativ 150 oder 600 DPI) mit einstellbarer
  Kantenglättung.
- Metadaten als CSV und JSON sowie ZIP-Bundle aus Einzelpanels, Gesamtfigur und
  Projektdatei.
- Arbeitsansicht mit Hilfslinien, die nie im Publikations-Export erscheint.

### FR-6 Persistenz

- Projektstand als JSON inklusive aller Panels, Geometrie, Filter, Spuren, Gruppen,
  Bedingungen, Marker, Zielbanden, Sprache, Theme und Exporteinstellungen.
- Serverseitige Ablage in `projects/`, Download und Upload der JSON-Datei.
- Gelbilder optional als Base64-PNG eingebettet, damit die Datei dauerhaft
  reproduzierbar bleibt.
- Tolerantes Laden älterer Projektdateien; unbekannte Felder werden ignoriert.
  Das frühere Feld `show_lane_numbers_bottom` wird auf `lane_numbers_position`
  abgebildet.

## 4. Nicht-funktionale Anforderungen

- Bedienung im Browser über Streamlit, ohne Build-Schritt.
- **Oberflächen-Darstellung:** Die App bietet in der Seitenleiste einen Dunkelmodus für
  die gesamte Bedienoberfläche (inklusive Tabellen und Auswahllisten). Das Farbschema
  der erzeugten Abbildung (hell/dunkel) ist davon unabhängig einstellbar; die
  Einstellung gilt je Sitzung und wird nicht im Projekt gespeichert.
- OpenCV optional; ohne OpenCV greift ein Pillow/NumPy-Fallback.
- Supersampling der Beschriftungsebene (1-fach bis 3-fach) mit anschließendem
  Herunterskalieren; das Gel selbst wird nie skaliert.
- Vorschauen in den Editoren werden mit 1-fachem Supersampling und maximal
  1000 px Breite gerendert; der Export nutzt weiterhin die volle Einstellung.
- Gerenderte Vorschauen, Anzeige-PNGs und Exportdateien werden über Signaturen
  zwischengespeichert, damit ein Rerun nur das tatsächlich Geänderte neu
  berechnet. Die Zwischenspeicher werden bei Bild- oder Projektwechsel geleert.
- Automatisierte Tests für Rendering, i18n, Bildanalyse, Persistenz und Workflow.
- Lint ohne Befunde.

## 5. Abnahmekriterien

1. Ein Export enthält keine Hilfslinien und keine Beschriftung innerhalb der
   Gelmatrix; ein Pixelvergleich bestätigt das unveränderte Gel.
2. Spurnummern lassen sich zwischen oben, unten und aus umschalten; die jeweilige
   Variante reserviert genau den benötigten Rand und erzeugt keine Kollision mit
   Kopf- oder Fußinhalt.
3. Nach dem Verstellen der Zuschnitt-Regler ist das Ergebnis direkt darunter
   sichtbar.
4. Die Oberfläche enthält keine Emojis.
5. Alle UI-Texte existieren in Deutsch und Englisch.
6. Projekt-JSON-Roundtrip inklusive eingebetteter Bilder ist verlustfrei.

## 6. Ausbaustufen

- Vektor-basierte PDF-Ausgabe mit getrennten Text- und Bildobjekten.
- Weitere Leiter-Presets und benutzerdefinierte Marker-Sets.
- Automatische Bandenquantifizierung mit Densitometrie.
- Mehrsprachige Metadatenfelder.


## PWA-Referenznachbau

Die vorgegebenen PWA-Dateien werden unverändert übernommen. Siehe PWA_VORLAGE.md, VORLAGEN_DATEIEN.json und START_HIER.md für Dateivergleich, Auslieferung und dokumentierte Grenzen der Vorlage.


## Private Kalenderdaten pro Browser
Standardmäßig erhält jeder Browser einen eigenen Datenbereich für Kalender,
Kalenderfeeds, Aufgaben und Notizbuch. Ein zufälliger 256-Bit-Zugangsschlüssel
liegt im Browser-Speicher, nie im Link. Der Server leitet daraus den Datenordner
ab. Ohne gültigen Schlüssel wird keine gemeinsame Datenbank geöffnet.
Ein weitergegebener normaler Link teilt keine Termine. Derselbe Browser bzw.
dasselbe Profil verwendet denselben Bereich; ein anderes Gerät/Privatfenster
oder gelöschter Browser-Speicher bedeutet einen neuen Bereich. Dies ersetzt
keine Kontenanmeldung auf gemeinsam genutzten Geräten.
Alte gemeinsame Daten werden nicht automatisch Besuchern zugeteilt oder kopiert.
`LAB_ASSISTANT_DATA_DIR` bleibt das Stammverzeichnis; Hosting benötigt dauerhaften
Speicher für Wiederherstellung nach Server-Neustarts. ICS-Export als Sicherung nutzen.
Nur für eine vertrauenswürdige lokale Einzelplatzinstallation kann ausdrücklich
`LAB_ASSISTANT_STORAGE_MODE=local` die bisherige lokale Ablage öffnen. Diesen
Modus niemals für eine öffentlich geteilte Website setzen.
