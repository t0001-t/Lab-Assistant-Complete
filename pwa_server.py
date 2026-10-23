"""Same-Origin-PWA-Gateway mit HTTP- und WebSocket-Weiterleitung an Streamlit.

Start: python pwa_server.py (http://localhost:8502)
Der Python-Server bleibt für Streamlit-Funktionen erforderlich. Offline wird
die in der Vorlage enthaltene App-Shell zwischengespeichert.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import ssl
import sys
from pathlib import Path

import tornado.httpclient
import tornado.httpserver
import tornado.iostream
import tornado.web
import tornado.websocket
from tornado.httputil import HTTPHeaders

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / ".streamlit" / "static"
HEAD_TAGS = (
    '<link rel="manifest" href="/static/manifest.json">'
    '<meta name="theme-color" content="#60a5fa">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-title" content="LabAssistant">'
    '<link rel="apple-touch-icon" href="/static/assets/icon-192.png">'
    '<link rel="stylesheet" href="/pwa-ui.css?v=1.0.9">'
    '<script src="/pwa-icons.js?v=1.0.9" defer></script>'
    '<script src="/pwa-runtime.js?v=1.0.9" defer></script>'
)
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "upgrade", "proxy-authenticate",
               "proxy-authorization", "te", "trailer", "content-length", "content-encoding"}


class PWAStaticHandler(tornado.web.StaticFileHandler):
    """Richtiger MIME-Typ und Root-Scope; keine Streamlit-Static-Overrides."""

    def set_extra_headers(self, path: str) -> None:
        self.set_header("X-Content-Type-Options", "nosniff")
        if path.endswith("sw.js"):
            self.set_header("Content-Type", "application/javascript; charset=utf-8")
            self.set_header("Service-Worker-Allowed", "/")
            self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        elif path.endswith(".js"):
            self.set_header("Content-Type", "application/javascript; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
        elif path.endswith("manifest.json"):
            self.set_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
        else:
            self.set_header("Cache-Control", "no-cache")


class ProxyHandler(tornado.web.RequestHandler):
    def initialize(self, backend: str) -> None:
        self.backend = backend

    async def forward(self) -> None:
        headers = HTTPHeaders()
        for name, value in self.request.headers.get_all():
            if name.lower() not in HOP_HEADERS | {"accept-encoding"}:
                headers.add(name, value)
        headers["Accept-Encoding"] = "identity"
        request = tornado.httpclient.HTTPRequest(
            self.backend + self.request.uri, method=self.request.method, headers=headers,
            body=self.request.body if self.request.method not in {"GET", "HEAD"} else None,
            follow_redirects=False, request_timeout=180, decompress_response=True,
        )
        try:
            response = await tornado.httpclient.AsyncHTTPClient().fetch(request, raise_error=False)
        except (OSError, tornado.httpclient.HTTPClientError):
            self.set_status(503)
            self.write("Lab Assistant startet. Bitte in wenigen Sekunden erneut laden.")
            return
        self.set_status(response.code)
        for name, value in response.headers.get_all():
            if name.lower() not in HOP_HEADERS:
                self.add_header(name, value)
        body = response.body or b""
        if "text/html" in response.headers.get("Content-Type", "") and response.code == 200:
            body = body.replace(b"</head>", HEAD_TAGS.encode() + b"</head>", 1)
            self.clear_header("Etag")
        self.finish(body)

    get = post = put = patch = delete = head = options = forward


class StreamlitSocket(tornado.websocket.WebSocketHandler):
    def initialize(self, backend: str) -> None:
        self.backend = backend
        self.upstream = None
        self.reader = None

    def check_origin(self, origin: str) -> bool:
        # Tornados Standardprüfung akzeptiert nur dieselbe Origin/Host-Kombination.
        return super().check_origin(origin)

    def select_subprotocol(self, subprotocols: list[str]) -> str | None:
        return "streamlit" if "streamlit" in subprotocols else None

    async def open(self) -> None:
        headers = HTTPHeaders()
        for name in ("Origin", "Cookie", "Host"):
            if name in self.request.headers:
                headers[name] = self.request.headers[name]
        protocols = [p.strip() for p in self.request.headers.get("Sec-WebSocket-Protocol", "").split(",") if p.strip()]
        try:
            request = tornado.httpclient.HTTPRequest(
                self.backend.replace("http://", "ws://") + self.request.uri, headers=headers,
            )
            self.upstream = await tornado.websocket.websocket_connect(
                request, subprotocols=protocols, max_message_size=200 * 1024 * 1024,
            )
            self.reader = asyncio.create_task(self.relay())
        except (OSError, tornado.httpclient.HTTPClientError, tornado.websocket.WebSocketError):
            self.close(code=1011, reason="Streamlit-Verbindung nicht verfügbar")

    async def relay(self) -> None:
        try:
            while self.upstream:
                message = await self.upstream.read_message()
                if message is None:
                    break
                await self.write_message(message, binary=isinstance(message, bytes))
        except (tornado.websocket.WebSocketClosedError, tornado.iostream.StreamClosedError):
            pass
        finally:
            self.close()

    async def on_message(self, message: str | bytes) -> None:
        if self.upstream:
            await self.upstream.write_message(message, binary=isinstance(message, bytes))

    def on_close(self) -> None:
        if self.upstream:
            self.upstream.close()
        if self.reader:
            self.reader.cancel()


def make_app(backend: str) -> tornado.web.Application:
    return tornado.web.Application([
        (r"/static/(sw\.js|manifest\.json|offline\.html)", PWAStaticHandler, {"path": str(STATIC)}),
        (r"/(pwa-runtime\.js|pwa-icons\.js|pwa-ui\.css)", PWAStaticHandler, {"path": str(STATIC)}),
        (r"/static/assets/(.*)", PWAStaticHandler, {"path": str(STATIC / "assets")}),
        (r"/_stcore/stream", StreamlitSocket, {"backend": backend}),
        (r"/.*", ProxyHandler, {"backend": backend}),
    ], websocket_max_message_size=200 * 1024 * 1024)


async def serve(args: argparse.Namespace) -> None:
    command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "pwa_entrypoint.py"),
               "--server.port", str(args.backend_port), "--server.address", "127.0.0.1",
               "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    process = await asyncio.create_subprocess_exec(*command, cwd=ROOT, env=os.environ.copy())
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stopped.set)
    backend = f"http://127.0.0.1:{args.backend_port}"
    server = None
    try:
        for _ in range(120):
            if process.returncode is not None:
                raise RuntimeError("Streamlit konnte nicht gestartet werden.")
            try:
                await tornado.httpclient.AsyncHTTPClient().fetch(backend + "/_stcore/health")
                break
            except (OSError, tornado.httpclient.HTTPClientError):
                await asyncio.sleep(0.25)
        else:
            raise RuntimeError("Streamlit wurde nicht rechtzeitig bereit.")
        tls = None
        if args.cert and args.key:
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(args.cert, args.key)
        server = tornado.httpserver.HTTPServer(make_app(backend), ssl_options=tls, max_buffer_size=210 * 1024 * 1024)
        server.listen(args.port, address=args.host)
        print(f"Lab Assistant PWA: {'https' if tls else 'http'}://{args.host}:{args.port}", flush=True)
        while not stopped.is_set():
            if process.returncode is not None:
                raise RuntimeError("Streamlit wurde unerwartet beendet.")
            try:
                await asyncio.wait_for(stopped.wait(), timeout=1)
            except TimeoutError:
                pass
    finally:
        if server:
            server.stop()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except TimeoutError:
                process.kill()
                await process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--backend-port", type=int, default=8503)
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error("--cert und --key müssen gemeinsam angegeben werden.")
    if args.port == args.backend_port:
        parser.error("PWA- und Backend-Port müssen verschieden sein.")
    asyncio.run(serve(args))


if __name__ == "__main__":
    main()
