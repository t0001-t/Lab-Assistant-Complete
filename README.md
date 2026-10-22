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
