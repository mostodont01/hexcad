"""HexCAD build store: `hexcad serve` keeps built features for every machine; clients sync with it.
Config (client): ~/.config/hexcad/config.json {"server": "http://192.168.1.143:8770"} or HEXCAD_SERVER (empty = off)."""
import json
import os
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import webapp
from .cache import Local

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "hexcad" / "config.json"
KEY = re.compile(r"^[A-Za-z0-9_]+-[0-9a-f]{24}$")


def server_url():
    if "HEXCAD_SERVER" in os.environ:
        return os.environ["HEXCAD_SERVER"].rstrip("/") or None
    try:
        return json.loads(CONFIG.read_text()).get("server", "").rstrip("/") or None
    except (OSError, ValueError):
        return None


class Remote:
    """Client for the build store. Every call fails fast (offline = None / False, never an exception)."""

    def __init__(self, url=None, timeout=1.5):
        self.url = url if url is not None else server_url()
        self.timeout = timeout
        self.down = False                       # don't retry an unreachable server within one session
        self._up = None

    def reachable(self):
        """Quick TCP probe (0.5 s): a home-network server answers in milliseconds; offline costs half a second once."""
        if self._up is None:
            u = urllib.parse.urlsplit(self.url)
            try:
                socket.create_connection((u.hostname, u.port or 80), timeout=0.5).close()
                self._up = True
            except OSError:
                self._up = False
        return self._up

    def _req(self, method, path, data=None):
        if not self.url or self.down or not self.reachable():
            return None
        try:
            r = urllib.request.Request(self.url + path, data=data, method=method)
            with urllib.request.urlopen(r, timeout=self.timeout if method != "PUT" else 30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            return b"" if e.code == 404 else None
        except (OSError, ValueError):
            self.down = True
            return None

    def get(self, key):
        b = self._req("GET", f"/entry/{key}")
        return b or None

    def put(self, key, blob):
        return self._req("PUT", f"/entry/{key}", blob) is not None

    def have(self, keys):
        b = self._req("POST", "/have", json.dumps(keys).encode())
        return set(json.loads(b)) if b else None

    def sync(self, local, everything=False):
        """Push every local entry the server is missing (and changed project manifests).
        everything: check all local entries and projects, not only the ones not marked synced (a "synced" mark
        doesn't say which server; use it after changing servers). Returns the number of entries pushed (None = offline)."""
        n = self._sync_entries(local, everything)
        if n is not None:
            for name in (local.project_names() if everything else local.unsynced_projects()):
                data = local.get_project(name)
                if data is not None and self._req("PUT", f"/project/{name}", data) is not None:
                    local.mark_project_synced(name, data)
        return n

    def _sync_entries(self, local, everything=False):
        todo = local.keys() if everything else local.unsynced()
        if not todo:
            return 0
        there = self.have(todo)
        if there is None:
            return None
        n = 0
        for k in todo:
            if k not in there:
                blob = local.get(k)
                if blob is None or not self.put(k, blob):
                    continue
                n += 1
            local.mark_synced(k)
        return n


def serve(root, host="0.0.0.0", port=8770):
    store = Local(root, keep=None)     # the server is the archive: never prunes
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body=b"", ctype="application/octet-stream"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _key(self):
            k = self.path.rsplit("/", 1)[-1]
            return k if self.path.startswith("/entry/") and KEY.match(k) else None

        def do_GET(self):
            if self.path == "/keys":
                return self._send(200, json.dumps(store.keys()).encode(), "application/json")
            if self.path.startswith("/entry/"):
                k = self._key()
                blob = store.get(k) if k else None
                return self._send(200, blob) if blob else self._send(404)
            if not webapp.handle_get(self, store, KEY):        # the phone app and its API
                self._send(404)

        def do_PUT(self):
            if self.path.startswith("/project/"):
                name = self.path.rsplit("/", 1)[-1]
                n = int(self.headers.get("Content-Length", 0))
                if not webapp.NAME.match(name) or not 0 < n < 1_000_000:
                    return self._send(400)
                data = self.rfile.read(n)
                try:
                    m = json.loads(data)
                    assert m["name"] == name and isinstance(m["features"], list)
                except (ValueError, KeyError, AssertionError, TypeError):
                    return self._send(400)
                with lock:
                    store.put_project(name, data)
                return self._send(201)
            k = self._key()
            n = int(self.headers.get("Content-Length", 0))
            if not k or not 0 < n < 200_000_000:
                return self._send(400)
            blob = self.rfile.read(n)
            with lock:
                store.put(k, blob)
            self._send(201)

        def do_POST(self):
            if self.path != "/have":
                return self._send(404)
            keys = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
            have = [k for k in keys if isinstance(k, str) and KEY.match(k) and store.path(k).exists()]
            self._send(200, json.dumps(have).encode(), "application/json")

        def log_message(self, fmt, *a):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    print(f"HexCAD build store on http://{host}:{port}, {len(store.keys())} entries in {store.root}", flush=True)
    return srv
