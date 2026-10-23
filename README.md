# Lab Assistant

Vollständiger Lab Assistant mit Gel-Editor, elektronischem Laborbuch, Praktikumsordnern, Laborrechnern und Kalender. Dies ist die ursprüngliche Python-/Streamlit-Anwendung vor dem eigenständigen Vercel-Umbau.

## Einstiegspunkt

**`app.py` startet den gesamten Lab Assistant** mit Übersicht, Notizen,
Praktikumsordnern, Gel-Editor, Laborrechner und Kalender.
Für Streamlit-Hosting als Startdatei `app.py` auswählen.
Der einzelne Gel-Editor liegt in `gel_app.py`.
Das gesamte Repository einschließlich `assets/`, `components/` und `.streamlit/`
herunterladen; eine einzelne Python-Datei enthält nicht die gesamte Anwendung.

## Lokal starten

Python 3.12 wird empfohlen.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pwa_server.py --port 8502 --backend-port 8503
```

Danach http://127.0.0.1:8502 öffnen. Alternativ ohne PWA-Proxy:
`streamlit run app.py`. Unter Windows die virtuelle Umgebung mit `.venv\Scripts\activate` aktivieren.

## Daten

Notizen und Kalender liegen standardmäßig in `lab_data/`. Über `LAB_ASSISTANT_DATA_DIR` kann ein anderes Datenverzeichnis gewählt werden. Persönliche Daten, Bilder aus eigenen Versuchen, Zugangsdaten und fertige App-Pakete sind nicht Bestandteil dieses Quellcodepakets.

## Tests

```sh
LAB_ASSISTANT_DATA_DIR=/tmp/lab-assistant-test python -m unittest discover -s tests
```

## Bereitstellung

Die vollständige Streamlit-Anwendung benötigt einen laufenden Python-Server. `Dockerfile` und `docker-compose.yml` sind enthalten. Der separate, noch in Bearbeitung befindliche Vercel-Gel-Editor gehört nicht zu diesem Repository.

Weitere technische Hinweise stehen in `SPEC.md` und `AGENTS.md`.

## Geschwindigkeit des Gel-Editors

Exportbilder und PNG-/TIFF-/PDF-/ZIP-Dateien werden erst beim Öffnen des
Export-Reiters erzeugt. Die Bearbeitungsreiter teilen sich identische
Vorschaubilder. Exportauflösung und Bildqualität bleiben unverändert.
Streamlit 1.66 oder neuer ist erforderlich.

## Darstellung wie in der lokalen PWA

Für Streamlit-Hosting `app.py` als Startdatei und Python 3.12 wählen.
Die Zusatzdateien `.streamlit/static/pwa-ui.css` und `pwa-icons.js` werden
auch ohne PWA-Gateway eingebunden: Seitenleiste, Abstände, Unterstreichungen
und lokale SVG-Symbole entsprechen damit dem lokalen Browser.
Streamlit ist auf die lokal getestete Version 1.66.1 festgelegt.
Die Ladeoptimierung des Gel-Editors ist enthalten. Netzwerk und ein ruhender
Hosting-Server können die Online-Startzeit zusätzlich beeinflussen.

## Kleine Fenster

Die Seitenleiste lässt sich über den Pfeil oben ein- und ausklappen.
Bei schmalen Fenstern stehen Arbeitsbereiche untereinander; Reiter bleiben
horizontal scrollbar. Auf kleinen Bildschirmen startet die Seitenleiste automatisch eingeklappt.

## Bedingungsmatrix

Einzelne Plus- und Minuszeichen werden in Vorschau und Export unabhängig von
den auf dem Server installierten Schriften gezeichnet. Die gespeicherten
Bedingungswerte und frei eingegebene Texte bleiben unverändert.


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
