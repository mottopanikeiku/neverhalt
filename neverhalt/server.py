"""In-memory run state plus the read-only JSON API the gallery polls."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

WEB = Path(__file__).resolve().parent.parent / "web"
IDLE = {"problem": None, "phase": "idle", "round": 0, "model": None, "counts": {}, "by_kind": {}, "champion": None,
        "history": [], "theorem": None,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "seconds": 0.0, "calls": 0}}


class Store:
    """Event-sourced: a live hunt and a replayed journal drive the page through the same apply()."""

    def __init__(self):
        self.lock = threading.Lock()
        self.version, self.state, self.machines, self.log = 0, dict(IDLE), {}, []

    def apply(self, event: dict):
        with self.lock:
            kind = event["type"]
            if kind == "reset":  # version and log restart from zero: the page notices and clears itself
                self.version, self.state, self.machines, self.log = 0, {**IDLE, **event["state"]}, {}, []
            elif kind == "state":
                self.state.update(event["patch"])
                self.version += 1
            elif kind == "machines":
                self.version += 1
                for m in event["items"]:
                    self.machines[m["id"]] = {**self.machines.get(m["id"], {}), **m, "v": self.version}
            elif kind == "log":
                self.log.append({"i": len(self.log), "kind": event["kind"], "text": event["text"],
                                 "stream": event.get("stream")})

    def get(self, path: str, since: int):
        with self.lock:
            if path == "/api/state":
                return {"version": self.version, **self.state, "log_next": len(self.log)}
            if path == "/api/machines":
                return {"version": self.version,
                        "machines": [{k: v for k, v in m.items() if k != "v"} for m in self.machines.values() if m["v"] > since]}
            if path == "/api/log":
                return {"next": len(self.log), "events": self.log[max(since, 0):]}
        return None


def replay(store: Store, journal: Path, speed: float = 1.0, max_gap: float = 4.0, loop: bool = False):
    """Feed a recorded run back with its original pacing (gaps capped at max_gap seconds)."""
    while True:
        last = 0.0
        with journal.open() as lines:
            for line in lines:
                event = json.loads(line)
                time.sleep(min(max(event["t"] - last, 0.0), max_gap) / speed)
                last = event["t"]
                store.apply(event)
        if not loop:
            return
        time.sleep(12)


def serve(store: Store, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                page = WEB / "index.html"
                body = page.read_bytes() if page.exists() else b"web/index.html is missing"
                ctype = "text/html; charset=utf-8"
            else:
                try:
                    since = int(parse_qs(url.query).get("since", ["0"])[0])
                except ValueError:
                    since = 0
                data = store.get(url.path, since)
                if data is None:
                    self.send_error(404)
                    return
                body, ctype = json.dumps(data, separators=(",", ":")).encode(), "application/json"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
