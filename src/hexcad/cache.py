"""Build cache: every feature's parts are stored under a key that changes only when the feature's own code, the
functions and constants it uses, or HexCAD / build123d change. Entries live in a local folder (works offline) and are
synced with a HexCAD server (`hexcad serve`), so a model is built once and then only loaded."""
import hashlib
import inspect
import io
import json
import os
import tempfile
import time
import types
import functools
import zipfile
from pathlib import Path

LOCAL = Path(os.environ.get("HEXCAD_CACHE", Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "hexcad"))
KEEP = 400          # local entries kept (least recently used ones are removed)


@functools.cache
def _tool():
    """Hash of HexCAD's shape helpers + the build123d version (imported here, so `hexcad serve` needs no CAD kernel)."""
    import build123d
    here = Path(__file__).parent              # shape helpers + the mesher (entries hold meshes) + build123d's version
    return hashlib.sha256(here.joinpath("shapes.py").read_bytes() + here.joinpath("mesh.py").read_bytes()
                          + build123d.__version__.encode()).hexdigest()


def feature_key(fn):
    """Hash of everything a feature function depends on inside its project file."""
    g, seen, h = fn.__globals__, set(), hashlib.sha256(_tool().encode())

    def names(co):
        out = set(co.co_names)
        for c in co.co_consts:
            if isinstance(c, types.CodeType):
                out |= names(c)
        return out

    def visit(f):
        if f in seen:
            return
        seen.add(f)
        try:
            h.update(inspect.getsource(f).encode())
        except (OSError, TypeError):
            h.update(f.__code__.co_code)
        for n in sorted(names(f.__code__)):
            v = g.get(n)
            if isinstance(v, types.FunctionType) and v.__module__ == fn.__module__:
                visit(v)
            elif v is not None and not isinstance(v, (types.ModuleType, type, types.FunctionType, types.BuiltinFunctionType)):
                h.update(f"{n}={v!r}".encode())

    visit(fn)
    return f"{fn.__name__}-{h.hexdigest()[:24]}"


# ---------------------------------------------------------------- entry = zip: parts.json + i.brep + i.mesh

def pack(parts, mesher):
    """Parts of one feature -> zip bytes (exact shapes as BREP, viewer meshes, sizes, volumes)."""
    import build123d
    import numpy as np
    buf = io.BytesIO()
    meta = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, tempfile.TemporaryDirectory() as td:
        for i, p in enumerate(parts):
            f = Path(td) / f"{i}.brep"
            build123d.export_brep(p.shape, str(f))
            z.write(f, f"{i}.brep")
            data, lo, hi = p.mesh if p.mesh is not None else mesher(p.shape)
            p.mesh = (data, lo, hi)
            mb = io.BytesIO()
            np.save(mb, data)
            z.writestr(f"{i}.mesh.npy", mb.getvalue())
            meta.append({"name": p.name, "color": list(p.color), "hidden": p.hidden, "volume": p.volume,
                         "bbox": [list(x) for x in p.bbox], "mesh_bounds": [list(map(float, lo)), list(map(float, hi))]})
        z.writestr("parts.json", json.dumps(meta))
    return buf.getvalue()


def unpack(blob, feature):
    """zip bytes -> Parts (shapes load lazily from BREP, meshes are ready for the viewer)."""
    import numpy as np
    from .model import Part
    z = zipfile.ZipFile(io.BytesIO(blob))
    out = []
    for i, m in enumerate(json.loads(z.read("parts.json"))):
        data = np.load(io.BytesIO(z.read(f"{i}.mesh.npy")))
        p = Part(m["name"], feature, None, tuple(m["color"]), m["hidden"])
        p.brep = z.read(f"{i}.brep")
        p._volume, p._bbox = m["volume"], tuple(tuple(x) for x in m["bbox"])
        p.mesh = (data, np.array(m["mesh_bounds"][0]), np.array(m["mesh_bounds"][1]))
        out.append(p)
    return out


class Local:
    """Folder of entries. keep = how many recently used entries survive pruning; None keeps everything (the server)."""
    def __init__(self, root=LOCAL, keep=KEEP):
        self.root = Path(root)
        self.keep = keep

    def path(self, key):
        return self.root / f"{key}.zip"

    def get(self, key):
        f = self.path(key)
        if f.exists():
            os.utime(f)                     # recently used
            return f.read_bytes()
        return None

    def put(self, key, blob):
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path(key).with_suffix(".tmp")
        tmp.write_bytes(blob)
        tmp.replace(self.path(key))
        self.prune()

    def keys(self):
        return [f.stem for f in self.root.glob("*.zip")] if self.root.exists() else []

    def unsynced(self):
        return [k for k in self.keys() if not (self.root / f"{k}.synced").exists()]

    def mark_synced(self, key):
        (self.root / f"{key}.synced").touch()

    def prune(self):
        if self.keep is None:
            return
        files = sorted(self.root.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[self.keep:]:
            f.unlink(missing_ok=True)
            f.with_suffix(".synced").unlink(missing_ok=True)

    # Projects: which entry each feature of a project file uses right now (the phone app shows these).
    # projects/<name>.json; a `.synced` file next to it holds the content's hash once the server has it.

    def put_project(self, name, data):
        d = self.root / "projects"
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{name}.tmp"
        tmp.write_bytes(data)
        tmp.replace(d / f"{name}.json")

    def get_project(self, name):
        f = self.root / "projects" / f"{name}.json"
        return f.read_bytes() if f.exists() else None

    def project_names(self):
        d = self.root / "projects"
        return sorted(f.stem for f in d.glob("*.json")) if d.exists() else []

    def unsynced_projects(self):
        out = []
        for n in self.project_names():
            mark = self.root / "projects" / f"{n}.synced"
            if not mark.exists() or mark.read_text() != _digest(self.get_project(n)):
                out.append(n)
        return out

    def mark_project_synced(self, name, data):
        (self.root / "projects" / f"{name}.synced").write_text(_digest(data))


def _digest(data):
    return hashlib.sha256(data or b"").hexdigest()


def project_name(path):
    """Store name of a project file: its stem + a short hash of where it lives (two robot.py files don't clash)."""
    path = Path(path).resolve()
    stem = "".join(c if c.isalnum() or c in "_-" else "_" for c in path.stem)
    return f"{stem}-{hashlib.sha1(str(path).encode()).hexdigest()[:6]}"


def project_manifest(path, features):
    """JSON bytes: project title/file + [{name, key, hidden}] per feature, in the file's order."""
    path = Path(path).resolve()
    home = Path.home()
    shown = f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)
    return json.dumps({"name": project_name(path), "title": path.stem, "file": shown, "updated": time.time(),
                       "features": [{"name": n, "key": feature_key(f), "hidden": getattr(f, "hexcad_hidden", False)}
                                    for n, f in features.items()]}).encode()
