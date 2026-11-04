"""Static preview server for generated web pages (HTML/CSS/JS) on its own localhost port.

A different port is a different browser origin: pages the agent wrote run with their own localStorage and
scripts, but cannot call the app API (the origin guard rejects them). Each folder gets a random token, so only
folders the app opened for preview are served."""
from __future__ import annotations

import mimetypes
import secrets
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

_ROOTS: dict[str, Path] = {}
_TOKENS: dict[str, str] = {}
_SERVER: ThreadingHTTPServer | None = None
_LOCK = threading.Lock()
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/wasm", ".wasm")


class _Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parts = unquote(urlsplit(path).path).lstrip("/").split("/", 1)
        root = _ROOTS.get(parts[0])
        if not root:
            return ""
        target = (root / (parts[1] if len(parts) > 1 else "")).resolve()
        if target != root and root not in target.parents:  # no ../ escapes out of the folder
            return ""
        return str(target)

    def send_head(self):
        if not self.translate_path(self.path):
            self.send_error(404)
            return None
        return super().send_head()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")  # edits show up on reload
        super().end_headers()

    def log_message(self, *args) -> None:  # keep the app console clean
        pass


def _start() -> ThreadingHTTPServer:
    global _SERVER
    if _SERVER is None:
        _SERVER = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, directory="."))
        _SERVER.daemon_threads = True
        threading.Thread(target=_SERVER.serve_forever, name="preview-server", daemon=True).start()
    return _SERVER


def url_for(root: Path, rel: str) -> str:
    """URL of a file inside root (the folder is served as a whole, so relative links and assets work)."""
    root = root.resolve()
    with _LOCK:
        server = _start()
        key = str(root)
        token = _TOKENS.get(key)
        if not token:
            token = _TOKENS[key] = secrets.token_urlsafe(9)
            _ROOTS[token] = root
    return f"http://127.0.0.1:{server.server_address[1]}/{token}/{rel.lstrip('/')}"
