# AGENTS.md – Arbeitsanleitung für KI-Agenten

Der All-in-One Lab Assistant ist eine Streamlit-App, die den unveränderten
SDS-PAGE-Editor mit Laborrechnern, einem elektronischen Laborbuch, einem
Protokoll-Generator und einem lokalen Labor-Kalender verbindet. Diese Datei
fasst Architektur, Regeln und Fallstricke zusammen, damit Änderungen konsistent
bleiben.

## Schnellstart

```bash
./run.sh --server.port 8502            # App starten (legt .venv an, installiert requirements.txt)
pkill -f "streamlit run lab_assistant.py"  # App beenden

./.venv/bin/python -m unittest discover -s tests    # 172 Tests
./.venv/bin/ruff check . --exclude .venv            # Lint, muss fehlerfrei sein
```

Nach Änderungen an importierten Modulen (`locales.py`, `models.py`,
`workflow.py`, `canvas_renderer.py`, `editor_component.py`, `lab_*.py`) den
Streamlit-Server neu starten – der Hot-Reload greift nicht zuverlässig über
Modulgrenzen.

## Architektur

| Datei | Verantwortung |
|---|---|
| `lab_assistant.py` | Shell: Page-Config, Icon-Navigation, Theme, Routing, Dialoge |
| `lab_dashboard.py` | Startseite mit Ordnerkarten, To-dos, Projektübersicht, Kalender-UI inkl. To-do-Verknüpfung, Onboarding, Einstellungen, Hilfe |
| `lab_calendar.py` | Kalender-SQLite, ICS-Parser/-Export, Abo-Sync, Wichtigkeit und To-do-Ereignisse |
| `lab_pages.py` | Rechner (inkl. Einheiten und qPCR), Notizbuch-Tageskarten, Universal-Import und Gel-Brücken-UI |
| `lab_eln.py` | Notizbuch-SQLite (v3), Medien, CRUD, Suche, Protokolle, Ordnerfarben, To-dos |
| `lab_gel_bridge.py` | Deterministischer Parser für Spurtabellen/Pipettierschemata und Projektaufbau |
| `lab_synthesis.py` | Zero-Loss-Prompt, Fallback, Audit, OCR/Whisper |
| `lab_calculators.py` | Rechenlogik Neubauer, Molarität, Verdünnung, Mastermix, Einheiten, qPCR |
| `lab_exports.py` | Markdown-Subset nach PDF/DOCX |
| `lab_locales.py` | DE/EN-Texte der neuen Module, `tr()` |
| `lab_theme.py` | Hell-/Dunkel-CSS der Shell |
| `gel_app.py` | Gel-Editor: Tabs 1–5, CSS, Caches, Export-UI; `editor_options()` als Sidebar (einzeln) oder Editor-Panel (Shell) |
| `models.py` | Pydantic-v2-Modelle, Defaults, Bild-Base64, Migrationen |
| `locales.py` | Übersetzungstabellen DE/EN, `t()`, `translator()`, `missing_keys()` |
| `image_processing.py` | Laden, Perspektive, Justierung, Harmonisierung, Detektion |
| `canvas_renderer.py` | Layout und Rendering der Abbildung, Export-Bytes, CSV/JSON |
| `workflow.py` | Spuren-/Marker-Logik, Editor-Ereignisse (`apply_editor_event`) |
| `editor_component.py` | Brücke zur Canvas-Komponente (`gel_editor`) |
| `components/gel_editor/index.html` | Canvas-Editor (Ziehen, Zoom, Events) |
| `tests/` | Gel-, Workflow-, App- und Lab-Tests (siehe Abschnitt Tests) |
| `tools/source_pdf.py` | Quelldateien als PDF (reportlab, nur Werkzeug) |

Datenfluss Gel: Bild laden → `process_panel()` → `render_figure()` /
`render_working_view()` → Anzeige oder Export (`png_bytes`, `tiff_bytes`,
`pdf_bytes`, `metadata_csv`, `metadata_json`).

Datenfluss Shell: Dashboard → Modulwahl (`lab_module`) → Seite; Notizbuch und
Kalender öffnen jeweils eigene SQLite-Dateien im Datenordner. Die Shell startet
den Gel-Editor per `runpy.run_path("gel_app.py")` mit `lab_shell=True`; `gel_app.py`
überspringt dann `st.set_page_config` und fügt sich in die Shell ein. Die
globale Sidebar enthält nur Shell-Funktionen; `gel_app.py` rendert seine
gel-spezifischen Optionen in der Shell über `editor_options()` im Popover
**Editor-Optionen**, im eigenständigen Betrieb weiterhin in `st.sidebar`.

## Shell, Dashboard und Kalender

- `lab_module` ist die einzige Navigationsquelle. Die Icon-Leiste hat genau fünf
  Ziele (Übersicht, Notizen, Gel-Editor, Laborrechner, Kalender), setzt den Wert
  und ruft `st.rerun()`; aktive Schaltflächen erhalten `type="primary"`. Die
  Projektverwaltung (`projects`) bleibt als Route erreichbar, ist aber kein
  Seitenleisten-Ziel.
- `lab_lang` (`de`/`en`) und `lab_theme` (`light`/`dark`) liegen in
  `st.session_state`. Die Shell injiziert `lab_theme.shell_css()` nur außerhalb
  des Gel-Editors; `gel_app.py` behält sein eigenes `ui_theme` und wird vor dem
  Start auf `lab_theme` gesetzt, nach dem Lauf zurückgelesen.
- Die globale Sidebar ist in jedem Modul identisch: Marke, fünf Navigationsziele,
  Einstellungen, Hilfe und Datenschutzhinweis. Sie enthält **keine**
  gel-spezifischen Widgets. Einstellungen und Hilfe laufen als `st.popover` in
  dieser Sidebar. Popover-Inhalte gehören zum Hauptskript; Widget-Änderungen
  rerendern daher die ganze App und das CSS wird neu injiziert. `st.dialog`
  wäre ein Fragment und würde Theme-/Sprachwechsel nicht zuverlässig anwenden.
- `gel_app.py:editor_options()` kapselt Projekt, Export und Harmonisierung. Im
  Standalone-Betrieb wird die Funktion in `st.sidebar` gerendert; bei
  `lab_shell=True` erscheint sie im Popover **Editor-Optionen** oben rechts am
  Editor. Typografie und Spurnummern liegen in `typography_controls()` im
  Reiter **Typografie** von Tab 2 (Spuren & Labels); der Reiter zeigt zusätzlich
  die Vorschau der bearbeiteten Abbildung. In der Shell wird
  `project.theme`/`export.theme` aus `lab_theme` gesetzt; nur der Standalone-
  Editor behält den separaten Theme-Schalter.
- `lab_tour_done`, `lab_tour_step` und `lab_tour_open` steuern das Onboarding;
  die Einstellungen setzen sie zurück. Die Einführung liegt standardmäßig
  eingeklappt unter dem Titel, damit die Ordnerkarten sichtbar bleiben.
  Tourtexte liegen als `onboarding_1_*` … `onboarding_5_*` in `lab_locales.py`.
- Die Startseite nutzt `st.columns([2.35, 1])`: links Ordnerkarten und vier
  Schnellstart-Kacheln, rechts Kalender und To-dos. Ordnerkarten werden über
  `lab_theme.colored_cards_css()` und `.st-key-folder_open_<id>` eingefärbt.
- Ordnerfarben liegen als `#rrggbb` in `practica.color` (Palette
  `PRACTICUM_COLORS`, Validierung `normalize_color()`). To-dos liegen in der
  Tabelle `todos` derselben Notizbuch-Datenbank; Schema-Version ist 3.
- Notizbuch-Tageskarten heißen `V1`, `V2`, … und setzen `eln_day_id`. Die
  beiden Hauptaktionen sind Universal-Import (`_media_tab`) und Gel-Brücke
  (`_run_gel_bridge`); letztere schreibt `project`, leert die Render-Caches und
  wechselt zu `lab_module="gel"`. Bei `has_project_work()` ist die
  Bestätigungs-Checkbox Pflicht.
- `lab_gel_bridge.parse_notes()` verarbeitet Markdown-Tabellen,
  `Spur/Lane …:`-Zeilen und Bullet-Fallbacks; `build_project()` setzt Labels,
  Bedingungen, Marker-Spuren und Zielbanden. Der Ablauf bleibt deterministisch,
  es gibt keinen KI-Aufruf.
- Kalender: `CalendarStore` nutzt `lab_data/lab_calendar.sqlite3`. ICS-Import ist
  idempotent über die UID; Abo-Sync ruft `fetch_ics()` nur auf Knopfdruck auf
  (http(s), max. 2 MB) und speichert keine Zugangsdaten. Wiederkehrende Termine
  werden mit der ersten Occurrence importiert. Termine tragen `kind` und
  `importance` (`low`/`normal`/`high`); die Farbe kommt aus
  `lab_theme._event_css()`. Datierte To-dos werden über
  `upsert_todo_event()`/`delete_todo_event()` als Ereignisse mit
  `kind="todo"`, `source="todo"` und der To-do-ID als `uid` geführt.
- Die Kalender-UI zeigt Datumsangaben über `_format_date()` als `TT.MM.JJJJ`
  (DE) bzw. `MM/DD/YYYY` (EN). Neben **Neuer Termin** liegt die To-do-Liste;
  Erledigen und Löschen synchronisieren den verknüpften Kalendereintrag.
- Das Demo-Projekt der Startseite setzt `project`, `demo_tracking`, Versions-
  zähler und leert die Render-Caches, bevor es in den Gel-Editor wechselt. Bei
  bearbeitetem Projekt ist die Checkbox-Bestätigung Pflicht.

## Datenmodell und Invarianten

- Koordinaten sind **relativ** (0.0–1.0) zu Breite/Höhe des Gelbilds, y von oben.
- Alle Modelle erben von `BaseModel` mit `extra="ignore"`; fehlende Felder werden
  über Defaults ergänzt. Neue Felder immer mit Default versehen, damit alte
  Projektdateien weiter laden.
- Spurnummern-Migration läuft über `model_validator(mode="before")`; bestehende
  Migrationen nicht entfernen.
- Zentrale Modelle: `Project`, `GelPanel`, `Lane`, `MarkerBand`, `TargetArrow`,
  `ConditionRow`, `GroupLabel`, `Transform`, `Adjustments`, `ExportSettings`.
- Defaults: `DEFAULT_LANE_COUNT = 10` (`default_lanes()`, `default_markers()`),
  `default_project()`.
- `Project` speichert Bilder als Base64-PNG (`encode_image_png_b64`,
  `decode_image_png_b64`). Das Originalbild wird **nie** verändert.
- `MarkerBand.unit` und `GelPanel.unit` werden gemeinsam gepflegt; die Einheit ist
  ein freies Textfeld, Grundeinstellung `kDa`.

## Rendering

- Zweistufig: Beschriftungsebene in Zielauflösung (Supersampling), danach
  herunterskalieren und das Gel pixelgenau per `paste()` einsetzen. Dadurch bleibt
  das Gel im Export unberührt.
- `supersample` beeinflusst nur die Beschriftungsebene, nicht das Layout.
- Hoch-/Tiefstellung: `parse_rich()` (Syntax `^{...}` / `_{...}`, kurz `^2` / `_2`),
  Breite über `rich_text_width()`, Zeichnen über `_label_image()` (Skriptschrift
  ca. 68 % der Grundgröße). Diese Syntax gilt in allen Label-Feldern, auch in der
  Spurtabelle.
- Vorschauen laufen mit `options.model_copy(update={"supersample": 1})`; Exporte
  nutzen die vollen `ExportSettings`.
- Spurnummern: Position oben/unten/aus, kleine Schrift an der Spur.
- Layout-Reihenfolge nicht ohne Not ändern: `compute_layout()` bestimmt Kopf,
  Skalen, Spuren, Gruppen, Bedingungen, Pfeile und Fuß; Tests prüfen die Maße.

## Editor-Komponente

- `gel_editor()` ist ein Streamlit-Custom-Component (`components.declare_component`
  mit `path=`), läuft also in einem iframe: Argumente als JSON, Ereignisse als
  Dict zurück (`apply_editor_event`).
- `MAX_EDITOR_WIDTH = 1000`: größere Bilder werden für die Bearbeitung verkleinert,
  Koordinaten bleiben relativ und damit auflösungsunabhängig.
- `_data_url()` cached das Base64-Bild über einen SHA1-Hash des Bildinhalts
  (`_DATA_URL_CACHE`, max. 12 Einträge), damit Reruns nicht neu kodieren.
- Neue Editor-Funktionen immer auch in `apply_editor_event()` und in
  `tests/test_workflow.py` abbilden.

## Oberfläche und CSS

- Jeder Tab: Bild links, Bedienung rechts in scrollbarem Container; das Bild bleibt
  sichtbar. CSS-Klassen/Tokens: `gd-sticky-*`, `gd-scroll-*`, `gd-fixed-import`.
- Farben der Tabellen laufen über `--gdg-*`-Variablen (`!important`), damit
  Streamlit-Interna überschrieben werden.
- Dunkelmodus der App ist **unabhängig** vom Farbschema der Abbildung:
  `ss.ui_theme` (`"light"`/`"dark"`), `_LIGHT_CSS`/`_DARK_CSS`, `app_css(dark)`.
  Das CSS wird vor der Sidebar emittiert, deshalb muss der Toggle `st.rerun()`
  auslösen.
- Streamlit-1.66-Selektoren (nicht raten, sonst greift das CSS nicht):
  Tabs `[data-testid="stTabs"] [role="tab"]`, Texteingaben
  `[data-testid="stTextInputRootElement"]`, Zahlenfelder
  `[data-testid="stNumberInputContainer"]`, Selectbox
  `[data-testid="stSelectbox"] [role="group"]`, Dropdown
  `[data-testid="stSelectboxVirtualDropdown"]`, Checkbox/Radio mit
  `div:first-of-type` (davor liegt der versteckte Input).
- Bestätigungen als `st.toast` (`show_flash()`), keine `st.success`-Kaskaden.
- Haupt-Tabs mit `on_change="rerun"` und ohne `key` verwenden. Den Export nur
  innerhalb von `if tab_export.open` berechnen; Bearbeitungsreiter teilen identische
  Vorschaubilder. Die Tab-Reihenfolge ist
  Import, Spuren, Marker, Zielbanden, Export.
- Shell-CSS nur in `lab_theme.py` pflegen (`.la-*`, Kalender, Kennzahlen). Es
  wird für den Gel-Editor bewusst nicht injiziert, damit dessen Layout und
  Farben unberührt bleiben. `.streamlit/config.toml` setzt ein helles
  Basis-Theme; der Dunkelmodus braucht deshalb die Widget-Overrides in
  `_dark_widget_css()` (Buttons, Inputs, Selects, Expander, Popover).
  Material-Icons (`:material/...:`) sind in Schaltflächen zulässig; in
  `st.markdown` werden sie als Text gerendert und dürfen dort nicht verwendet
  werden.

## Zweisprachigkeit

- **Kein hartkodierter UI-Text.** Immer `L("key")` (in `gel_app.py`, nutzt
  `ss.project.lang`), `T("key")` (in `lab_dashboard.py`/`lab_pages.py`, nutzt
  `lab_lang`) bzw. `tr("key", lang)` in reinen Modulen.
- Neue Schlüssel in `locales.py` (Gel) und `lab_locales.py` (Shell) jeweils in
  **beiden** Sprachen anlegen; `missing_keys()` und die Locale-Tests decken
  Lücken auf. Kalender-Monatsnamen und Wochentage liegen als Konstanten in
  `lab_dashboard.py`, alle übrigen Texte in `lab_locales.py`.
- Platzhalter über `**kwargs` formatieren, nicht per f-String in der Tabelle.
- Sprache wechseln setzt den aktiven Tab auf Tab 1 zurück (bestehendes Verhalten,
  nicht „fixen").

## Performance und Caches

- Kein `st.cache_data`; alles über `st.session_state`:
  `ss.preview_cache`, `ss.display_cache`, `ss.export_cache` (je max. 12 Einträge,
  danach `clear()`).
- Cache-Schlüssel enthalten `project_signature()`: SHA1 aus
  `project.model_dump_json()` + `options` + `id(p.source_image)` je Panel. Wer ein
  Feld hinzufügt, das die Darstellung ändert, muss es in die Signatur aufnehmen.
- Bei Bild-/Projektwechsel werden die Caches geleert (`ss.*_cache.clear()`).
- Teure Schritte (Perspektive, CLAHE, Rendering) nie im UI-Pfad ohne Cache
  aufrufen.

## Stilregeln

- **Keine Emojis** in UI, Doku und Commits. Typografische Pfeile sind erlaubt:
  `↻ ↺ ⇋ ⇅ ↔ →`.
- Deutsch als Projektsprache (UI zweisprachig, Code/Kommentare deutsch oder
  englisch, aber konsistent je Datei).
- Ruff: `line-length = 120`, `ISC004` ist bewusst ignoriert (mehrzeilige
  Übersetzungsstrings).
- Typannotationen nutzen, `from __future__ import annotations` beibehalten.
- Bestehende Namensschemata nicht umbenennen (Locales-Keys, Modellfelder,
  CSS-Tokens) – sie sind Teil des Projektdateiformats bzw. der Tests.

## Tests

- 172 Tests:
  - Gel: `test_engine.py` (Rendering, Gel-Unberührtheit, Themes, Layout, Pfeile,
    Verarbeitung, Harmonisierung, Komposition, Export, Persistenz, Analyse,
    Zähleingaben, Locales, Rich-Labels), `test_workflow.py`, `test_gel_app.py`.
  - Neue Module: `test_lab_calculators.py` (inkl. Einheiten und qPCR),
    `test_lab_eln.py` (inkl. Ordnerfarben, To-dos, Universal-Import),
    `test_lab_exports.py`, `test_lab_synthesis.py`, `test_lab_locales.py`,
    `test_lab_calendar.py` (ICS-Parsing, CRUD, Wichtigkeit, To-do-Ereignisse,
    Migration, Abo-Sync), `test_lab_gel_bridge.py` (Spurtabellen, Fallback,
    Projektaufbau), `test_lab_ui.py` (AppTest: Navigation, Dashboard, Ordner,
    Kalender inkl. To-do- und Farbprüfung, Notizbuch, Trennung von globaler
    Sidebar und Editor-Optionen).
- Neue Logik zuerst im Modul implementieren, dann Test ergänzen; Tests dürfen
  keine Streamlit-Session voraussetzen (reine Modul-Tests bevorzugen).
  `test_lab_ui.py` ist die einzige Ausnahme und bleibt auf Smoke-Tests begrenzt.

## Export

- Formate: PNG, TIFF, PDF (300 DPI), Metadaten CSV/JSON, Projekt-JSON inkl.
  Base64-Bildern, ZIP-Paket.
- `base_name` enthält einen Zeitstempel (`%Y%m%d_%H%M`), dadurch wird das ZIP
  spätestens jede Minute neu gepackt – unkritisch, aber beim Cachen beachten.
- Quelldateien als PDF: `./.venv/bin/python tools/source_pdf.py gel_app.py exports/app_py.pdf "Titel"`
  (benötigt `reportlab` in der venv, nicht Teil der App-Abhängigkeiten).

## Fallstricke

- `st.session_state`-Caches überleben Codeänderungen; bei merkwürdigen
  Darstellungen zuerst Cache leeren bzw. Server neu starten.
- Versteckte Browser-Tabs liefern `width/height = 0` und verzögerte
  `requestAnimationFrame`-Callbacks; Drag-Tests nur im fokussierten Tab.
- `browser.screenshot` schlägt fehl; Verifikation über DOM-Werte und
  `getComputedStyle`, nicht über Screenshots.
- `.venv` (ca. 539 MB) gehört nie in ein ZIP oder Commit; `.gitignore` deckt
  `exports/` und `projects/` ab.
- Beim Umbenennen von Locale-Keys bricht `missing_keys()` – Schlüssel nur
  ergänzen, nicht löschen, oder alle Verwendungen mitziehen.
- `st.dialog`-Inhalte sind Fragmente: `st.rerun()` ohne `scope="app"` rerendert
  nur den Dialog. Für Einstellungen deshalb `st.popover` verwenden, nicht
  `st.dialog`.
- Der Kalender importiert wiederkehrende ICS-Termine nur einmal; keine
  Erwartung an RRULE-Expansion.
- `lab_data/` ist gitignored und enthält echte Nutzerdaten. Nie in ZIPs oder
  Commits aufnehmen; Testläufe stattdessen gegen `LAB_ASSISTANT_DATA_DIR` in
  einem temporären Ordner ausführen.

## Definition of Done

1. `./.venv/bin/python -m unittest discover -s tests` grün (161+ Tests).
2. `./.venv/bin/ruff check . --exclude .venv` ohne Befund.
3. UI-Änderung im Browser auf Port 8502 geprüft (beide Sprachen, hell und
   dunkel, ohne Exception im Log). Bei Gel-Änderungen zusätzlich `gel_app.py`
   einzeln starten.
4. Doku aktualisiert, wenn sich Verhalten oder Bedienung ändert
   (`README.md` für Nutzer, `SPEC.md` für Anforderungen).
