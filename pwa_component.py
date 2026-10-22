"""PWA-Integration für Streamlit – manifest.json, Service Worker, Offline-Support.

Dieses Modul injiziert das PWA-Manifest, registriert den Service Worker
und fügt Offline-Support hinzu. Es nutzt streamlit.components.v1 für
die HTML/JS-Injektion.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

@lru_cache(maxsize=1)
def standalone_ui_assets() -> tuple[str, str]:
    """Dieselben lokalen UI-Dateien wie beim PWA-Gateway, ohne Netzabruf."""
    root = Path(__file__).resolve().parent / ".streamlit" / "static"
    return (
        (root / "pwa-ui.css").read_text(encoding="utf-8"),
        (root / "pwa-icons.js").read_text(encoding="utf-8"),
    )


def inject_pwa(
    name: str = "Lab Assistant",
    short_name: str = "LabAssistant",
    theme_color: str = "#356b52",
    background_color: str = "#f7f7f7",
    icons: Optional[list[dict]] = None,
    shortcuts: Optional[list[dict]] = None,
) -> None:
    """
    Injiziert PWA-Manifest, Service Worker und Offline-Support in die Streamlit-App.

    Parameters
    ----------
    name : str
        Vollständiger App-Name (wird im Install-Dialog angezeigt).
    short_name : str
        Kurzer Name für Homescreen (max. 12 Zeichen empfohlen).
    theme_color : str
        Theme-Farbe für Statusleiste und Splash-Screen (Hex).
    background_color : str
        Hintergrundfarbe für Splash-Screen (Hex).
    icons : list[dict], optional
        Liste von Icon-Dicts mit Keys: src, sizes, type, purpose.
    shortcuts : list[dict], optional
        App-Shortcuts für Homescreen (max. 4).
    """
    if icons is None:
        icons = [
            {"src": "/static/assets/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/assets/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ]

    if shortcuts is None:
        shortcuts = [
            {"name": "Kalender", "short_name": "Kalender", "url": "/?module=calendar", "icons": [{"src": "/static/assets/icon-192.png", "sizes": "192x192"}]},
            {"name": "Rechner", "short_name": "Rechner", "url": "/?module=calculators", "icons": [{"src": "/static/assets/icon-192.png", "sizes": "192x192"}]},
            {"name": "Notizbuch", "short_name": "Notizen", "url": "/?module=notebook", "icons": [{"src": "/static/assets/icon-192.png", "sizes": "192x192"}]},
        ]

    # Manifest generieren
    manifest = {
        "name": name,
        "short_name": short_name,
        "description": "All-in-One Lab Assistant – Gel-Dokumentation, Laborrechner, Elektronisches Laborbuch, Kalender",
        "start_url": "/",
        "display": "standalone",
        "background_color": background_color,
        "theme_color": theme_color,
        "orientation": "portrait-primary",
        "scope": "/",
        "icons": icons,
        "categories": ["education", "productivity", "science"],
        "shortcuts": shortcuts,
    }
    manifest_json = json.dumps(manifest, ensure_ascii=False)
    manifest_b64 = base64.b64encode(manifest_json.encode()).decode()

    # Auch beim direkten Start (z. B. Streamlit Cloud) das Gateway-Layout laden.
    ui_css, icon_script = standalone_ui_assets()
    st.markdown("<style>" + ui_css + "</style>", unsafe_allow_html=True)
    icon_bootstrap = """
    <script>
    (() => {
      try {
        const document = window.parent.document;
        if (document.querySelector('script[src^="/pwa-icons.js"]') ||
            document.documentElement.dataset.labInlineIcons) return;
        document.documentElement.dataset.labInlineIcons = "ready";
        const MutationObserver = window.parent.MutationObserver;
        const requestAnimationFrame = window.parent.requestAnimationFrame.bind(window.parent);
    """ + icon_script + """
      } catch (error) { console.warn('[Lab UI] Symbole konnten nicht geladen werden:', error); }
    })();
    </script>
    """

    # HTML/JS Injection
    html_code = f"""
    <script>
    (function() {{
      // Das Gateway integriert die PWA bereits im Hauptdokument.
      try {{
        if (window.parent !== window && window.parent.document.querySelector('link[rel="manifest"]')) return;
      }} catch (error) {{ /* Ohne Parent-Zugriff bleibt die Standalone-Integration aktiv. */ }}
      // 1. Manifest injizieren (Data-URL für sofortige Verfügbarkeit)
      const manifestLink = document.createElement('link');
      manifestLink.rel = 'manifest';
      manifestLink.href = 'data:application/manifest+json;base64,{manifest_b64}';
      document.head.appendChild(manifestLink);

      // 2. Theme-Color Meta
      const themeMeta = document.createElement('meta');
      themeMeta.name = 'theme-color';
      themeMeta.content = '{theme_color}';
      document.head.appendChild(themeMeta);

      // 3. Apple PWA Meta Tags
      const appleCaps = document.createElement('meta');
      appleCaps.name = 'apple-mobile-web-app-capable';
      appleCaps.content = 'yes';
      document.head.appendChild(appleCaps);

      const appleStatus = document.createElement('meta');
      appleStatus.name = 'apple-mobile-web-app-status-bar-style';
      appleStatus.content = 'default';
      document.head.appendChild(appleStatus);

      const appleTitle = document.createElement('meta');
      appleTitle.name = 'apple-mobile-web-app-title';
      appleTitle.content = '{short_name}';
      document.head.appendChild(appleTitle);

      // 4. Service Worker registrieren
      if ('serviceWorker' in navigator) {{
        window.addEventListener('load', () => {{
          navigator.serviceWorker.register('/static/sw.js')
            .then(reg => {{
              console.log('[PWA] SW registered:', reg.scope);

              // Update-Check alle 30 Minuten
              setInterval(() => reg.update(), 30 * 60 * 1000);

              // Update-Benachrichtigung
              reg.addEventListener('updatefound', () => {{
                const newWorker = reg.installing;
                newWorker.addEventListener('statechange', () => {{
                  if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {{
                    if (confirm('Neue Version der Lab Assistant App verfügbar. Jetzt laden?')) {{
                      window.location.reload();
                    }}
                  }}
                }});
              }});
            }})
            .catch(err => console.warn('[PWA] SW registration failed:', err));
        }});
      }}

      // 5. Online/Offline Detection
      window.addEventListener('online', () => {{
        console.log('[PWA] Online');
        document.body.classList.remove('offline');
      }});
      window.addEventListener('offline', () => {{
        console.log('[PWA] Offline');
        document.body.classList.add('offline');
      }});

      // 6. Install Prompt Handling (optional)
      let deferredPrompt = null;
      window.addEventListener('beforeinstallprompt', (e) => {{
        e.preventDefault();
        deferredPrompt = e;
        console.log('[PWA] Install prompt available');
      }});

    }})();
    </script>
    """
    components.html(icon_bootstrap + html_code, height=0, width=0)


def inject_pwa_simple() -> None:
    """Vereinfachte Version für schnelle Integration ohne Parameter."""
    inject_pwa()
