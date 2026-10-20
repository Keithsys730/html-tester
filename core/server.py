import functools
import http.server
import socket
import threading
from pathlib import Path
from typing import Optional


class EphemeralLocalServer:
    """A thread-safe, ephemeral local HTTP server to bypass file:/// CORS and ESM limits."""

    def __init__(self, serve_dir: Path, host: str = "127.0.0.1", port: Optional[int] = None):
        self.serve_dir = serve_dir.resolve()
        self.host = host
        self.requested_port = port or 0
        self.port = self.requested_port
        self.httpd: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(self.serve_dir))
        self.httpd = http.server.ThreadingHTTPServer((self.host, self.requested_port), handler)
        self.port = int(self.httpd.server_address[1])
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
