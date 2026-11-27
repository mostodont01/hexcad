"""Phone app of the build store (`hexcad serve`): an installable web app that shows the projects' current models.

Routes (GET):  /  and the app's files (web/)  ·  /api/projects  ·  /api/project/<name>  ·  /api/mesh/<key>/<i>
Stdlib only: the server (an old tablet) has no CAD kernel. Meshes are sent as they are stored (float32
[x y z nx ny nz] per vertex), gzipped, and cached by the phone forever (an entry's key changes when it changes)."""
import gzip
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

WEB = Path(__file__).with_name("web")
NAME = re.compile(r"^[A-Za-z0-9_-]+$")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css",
         ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml"}


def npy_payload(b):
    """Raw float32 bytes of a C-order '<f4' .npy array (header checked, numpy not needed)."""
    if b[:6] != b"\x93NUMPY":
        raise ValueError("not a .npy file")
    hlen, start = (int.from_bytes(b[8:10], "little"), 10) if b[6] == 1 else (int.from_bytes(b[8:12], "little"), 12)
    header = b[start:start + hlen].decode("latin1")
    if "'<f4'" not in header or "'fortran_order': True" in header:
        raise ValueError(f"unexpected mesh array: {header.strip()}")
    return b[start + hlen:]


def projects(store):
    out = []
    for n in store.project_names():
        m = json.loads(store.get_project(n))
        out.append({"name": n, "title": m["title"], "file": m["file"], "updated": m["updated"],
                    "features": len(m["features"])})
    return sorted(out, key=lambda p: -p["updated"])


def project(store, name):
    """Manifest + the parts of every feature (name, color, size, triangles); None if there is no such project."""
    data = store.get_project(name) if NAME.match(name) else None
    if data is None:
        return None
    m = json.loads(data)
    for f in m["features"]:
        blob = store.get(f["key"])
        if blob is None:
            f["parts"], f["missing"] = [], True
            continue
        z = zipfile.ZipFile(BytesIO(blob))
        meta = json.loads(z.read("parts.json"))
        for i, p in enumerate(meta):
            p["triangles"] = (z.getinfo(f"{i}.mesh.npy").file_size // 4 // 6) // 3      # about (header is small)
            p.pop("mesh_bounds", None)
        f["parts"] = meta
    return m


def mesh(store, key, i):
    blob = store.get(key)
    if blob is None:
        return None
    try:
        return npy_payload(zipfile.ZipFile(BytesIO(blob)).read(f"{int(i)}.mesh.npy"))
    except (KeyError, ValueError):
        return None


def handle_get(handler, store, key_re):
    """Answer a GET for the phone app. Returns False when the path isn't the app's (the caller answers 404)."""
    path = handler.path.split("?", 1)[0]
    if path == "/api/projects":
        return _json(handler, projects(store))
    if path.startswith("/api/project/"):
        m = project(store, path.rsplit("/", 1)[-1])
        return _json(handler, m) if m is not None else _send(handler, 404, b"")
    if path.startswith("/api/mesh/"):
        parts = path.split("/")                         # ['', 'api', 'mesh', key, i]
        if len(parts) == 5 and key_re.match(parts[3]) and parts[4].isdigit():
            forever = {"Cache-Control": "public, max-age=31536000, immutable"}
            gz = store.root / "meshgz" / f"{parts[3]}-{int(parts[4])}.gz"     # compressed once (slow server CPU)
            wants_gz = "gzip" in handler.headers.get("Accept-Encoding", "")
            if wants_gz and gz.exists():
                return _raw(handler, gz.read_bytes(), dict(forever, **{"Content-Encoding": "gzip"}))
            body = mesh(store, parts[3], parts[4])
            if body is not None:
                if wants_gz:
                    data = gzip.compress(body, 6)
                    gz.parent.mkdir(exist_ok=True)
                    tmp = gz.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    tmp.replace(gz)
                    return _raw(handler, data, dict(forever, **{"Content-Encoding": "gzip"}))
                return _send(handler, 200, body, "application/octet-stream", forever)
        return _send(handler, 404, b"")
    f = WEB / ("index.html" if path == "/" else path.lstrip("/"))
    if f.parent == WEB and f.suffix in TYPES and f.is_file():
        extra = {"Cache-Control": "no-cache"}
        if f.name == "sw.js":
            extra["Service-Worker-Allowed"] = "/"
        return _send(handler, 200, f.read_bytes(), TYPES[f.suffix], extra)
    return False


def _json(handler, obj):
    return _send(handler, 200, json.dumps(obj).encode(), "application/json", {"Cache-Control": "no-cache"})


def _raw(handler, body, headers):
    """An already gzipped mesh."""
    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Vary", "Accept-Encoding")
    for k, v in headers.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _send(handler, code, body, ctype="application/octet-stream", headers=None):
    if len(body) > 1024 and "gzip" in handler.headers.get("Accept-Encoding", ""):
        body = gzip.compress(body, 5)
        headers = dict(headers or {}, **{"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)
    return True
