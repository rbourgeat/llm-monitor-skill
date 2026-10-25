"""Local HTTP server, static UI host and daemon lifecycle for llm-monitor."""
from __future__ import annotations

import http.server
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from urllib.parse import quote, urlparse

from . import api, attachments
from .model import now_iso
from .store import Store

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(SKILL_ROOT, "ui")
HOST = "127.0.0.1"
MAX_BODY = 8_000_000
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _content_disposition(filename, inline):
    """ASCII-safe Content-Disposition carrying the exact UTF-8 filename."""
    name = str(filename or "file").replace('"', "").replace("\\", "")
    fallback = name.encode("ascii", "replace").decode("ascii")
    encoded = quote(name, safe="")
    return ("inline" if inline else "attachment") + \
        '; filename="' + fallback + '"; filename*=UTF-8\'\'' + encoded


def _health(url, timeout=1.0):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


class KanbanServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, store, port):
        super().__init__(address, handler)
        self.store = store
        self.cache = {}
        self.port = port


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "LLMMonitor/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _write(self, status, payload, content_type, extra=None):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        self._write(status, payload, "application/json; charset=utf-8")

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            raise ValueError("invalid Content-Length")
        if length > MAX_BODY:
            raise ValueError("request body too large")
        if not length:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid JSON body: %s" % error)

    def _handle_api(self, method):
        try:
            body = self._read_body() if method in ("POST", "PATCH", "DELETE") else None
        except ValueError as error:
            self._json(400, {"error": str(error)})
            return
        status, payload = api.handle(method, self.path, body,
                                     self.server.store, self.server.cache, self.server.port)
        self._json(status, payload)

    def _serve_static(self):
        parsed = urlparse(self.path)
        relative = parsed.path.lstrip("/") or "index.html"
        root = os.path.realpath(UI_DIR)
        candidate = os.path.realpath(os.path.join(root, relative))
        if candidate != root and not candidate.startswith(root + os.sep):
            self._write(404, b"Not found", "text/plain; charset=utf-8")
            return
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, "index.html")
        if not os.path.isfile(candidate):
            self._write(404, b"Not found", "text/plain; charset=utf-8")
            return
        extension = os.path.splitext(candidate)[1].lower()
        with open(candidate, "rb") as handle:
            blob = handle.read()
        self._write(200, blob, MIME.get(extension, "application/octet-stream"))

    def _serve_attachment(self):
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) != 3:
            self._write(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            attachment, blob = attachments.read(
                self.server.store, parts[1], parts[2])
        except (LookupError, ValueError, OSError):
            self._write(404, b"Not found", "text/plain; charset=utf-8")
            return
        mime = attachment.get("mime") or "application/octet-stream"
        inline = mime.startswith("image/") or mime in ("application/pdf", "text/plain")
        if not inline:
            mime = "application/octet-stream"
        self._write(200, blob, mime, {
            "Content-Disposition": _content_disposition(attachment.get("name"), inline),
            "X-Content-Type-Options": "nosniff",
        })

    def do_GET(self):
        if self.path.startswith("/attachments/"):
            self._serve_attachment()
        elif self.path.startswith("/api/"):
            self._handle_api("GET")
        else:
            self._serve_static()

    def do_POST(self):
        self._handle_api("POST")

    def do_PATCH(self):
        self._handle_api("PATCH")

    def do_DELETE(self):
        self._handle_api("DELETE")


def _make_server(store, start_port):
    if start_port == 0:
        return KanbanServer((HOST, 0), Handler, store, 0), 0
    last = None
    for candidate in range(start_port, start_port + 10):
        try:
            server = KanbanServer((HOST, candidate), Handler, store, candidate)
            return server, candidate
        except OSError as error:
            last = error
    raise OSError("no free port in %d..%d: %s" % (start_port, start_port + 9, last))


def _write_info(store, server, port):
    url = "http://%s:%d" % (HOST, port)
    store.write_server_info({
        "pid": os.getpid(),
        "host": HOST,
        "port": port,
        "url": url,
        "home": store.home,
        "version": api.SKILL_VERSION,
        "started_at": now_iso(),
    })
    return url


def run_server(store, port, open_browser=False):
    store.initialize()
    server, actual = _make_server(store, port)
    url = _write_info(store, server, actual)
    print("Kanban web app: %s" % url, flush=True)
    print("Data: %s" % store.data_path, flush=True)
    if open_browser:
        webbrowser.open(url)

    def _request_stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        store.clear_server_info()
        print("Kanban server stopped.", flush=True)


def start_daemon(store, port, open_browser=False):
    store.initialize()
    info = store.read_server_info()
    if info:
        existing = info.get("url") or "http://%s:%s" % (HOST, info.get("port"))
        if _health(existing):
            print(existing, flush=True)
            if open_browser:
                webbrowser.open(existing)
            return existing
    entry = os.path.join(SKILL_ROOT, "kanban.py")
    command = [sys.executable, entry, "--home", store.home, "serve", "--port", str(port)]
    with open(store.log_path, "ab") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("server exited early; see %s" % store.log_path)
        info = store.read_server_info()
        if info and info.get("pid") == process.pid:
            url = info.get("url") or "http://%s:%s" % (HOST, info.get("port"))
            if _health(url):
                print(url, flush=True)
                if open_browser:
                    webbrowser.open(url)
                return url
        time.sleep(0.1)
    raise RuntimeError("server did not start within 8s; see %s" % store.log_path)


def stop_server(store):
    info = store.read_server_info()
    if not info:
        return {"stopped": False, "message": "server is not running"}
    url = info.get("url") or "http://%s:%s" % (HOST, info.get("port"))
    health = _health(url)
    if not health:
        store.clear_server_info()
        return {"stopped": False, "message": "server not responding; stale server.json cleared"}
    if health.get("pid") != info.get("pid"):
        store.clear_server_info()
        return {"stopped": False, "message": "pid mismatch; stale server.json cleared"}
    pid = info.get("pid")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        store.clear_server_info()
        return {"stopped": False, "message": "process already gone"}
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not _health(url):
            store.clear_server_info()
            return {"stopped": True, "message": "server stopped", "url": url}
        time.sleep(0.15)
    raise RuntimeError("server did not stop within 5s (pid %s)" % pid)


def status_server(store):
    info = store.read_server_info()
    if not info:
        return {"running": False, "message": "server is not running"}
    url = info.get("url") or "http://%s:%s" % (HOST, info.get("port"))
    health = _health(url)
    return {"running": bool(health), "url": url, "info": info, "health": health}


def cli_serve(args, store):
    if args.stop:
        result = stop_server(store)
        print(json.dumps(result) if args.json else result.get("message", ""))
        return
    if args.status:
        result = status_server(store)
        print(json.dumps(result, indent=2, ensure_ascii=False) if args.json
              else ("Running: %s" % result["url"] if result["running"]
                    else result.get("message", "server is not running")))
        return
    if args.daemon:
        url = start_daemon(store, args.port, args.open)
        print("URL: %s" % url) if not args.json else print(json.dumps({"url": url}))
        return
    run_server(store, args.port, args.open)
