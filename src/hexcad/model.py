"""Projects: a Python file whose functions decorated with @feature build named parts."""
import itertools
import linecache
import sys
import tempfile
import time
import types
from dataclasses import dataclass, field
from pathlib import Path

FEATURES: dict = {}
_parts: list | None = None
_feature: str = ""
_hidden: bool = False


@dataclass
class Part:
    name: str
    feature: str
    body: object                     # Body while building; None when loaded from the cache (shape comes from brep)
    color: tuple = (0.6, 0.6, 0.6, 1.0)
    hidden: bool = False
    brep: bytes | None = field(default=None, repr=False)
    mesh: tuple | None = field(default=None, repr=False)       # (data, lo, hi) for the viewer
    _clean: object = field(default=None, repr=False)
    _volume: float | None = field(default=None, repr=False)
    _bbox: tuple | None = field(default=None, repr=False)

    @property
    def shape(self):
        if self._clean is None:
            if self.body is None:
                from build123d import import_brep
                with tempfile.NamedTemporaryFile(suffix=".brep") as f:
                    f.write(self.brep)
                    f.flush()
                    self._clean = import_brep(f.name)
            else:
                s = self.body.s
                try:
                    s = s.clean()
                except Exception:  # noqa: BLE001 - clean is cosmetic
                    pass
                self._clean = s
        return self._clean

    @property
    def volume(self):
        if self._volume is None:
            self._volume = self.shape.volume
        return self._volume

    @property
    def bbox(self):
        if self._bbox is None:
            b = self.shape.bounding_box()
            self._bbox = (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)
        return self._bbox


def feature(fn=None, *, name=None, hidden=False):
    """Mark a function as a feature (a group of parts built together). hidden: not shown by default in the viewer
    (reference geometry, test prints, alternative versions)."""
    def deco(f):
        f.hexcad_hidden = hidden
        FEATURES[name or f.__name__] = f
        return f
    return deco(fn) if fn else deco


def register(body, name, color):
    if _parts is None:
        raise RuntimeError("parts can only be named inside a feature build")
    _parts.append(Part(name, _feature, body, tuple(color), _hidden))


_counter = itertools.count()


def load(path):
    """Import a project file and return its features {name: function}."""
    path = Path(path).resolve()
    FEATURES.clear()
    modname = f"hexcad_project_{next(_counter)}"
    # compiled from the source every time: the import system's .pyc cache is keyed on mtime + size and can miss
    # quick same-size edits
    mod = types.ModuleType(modname)
    mod.__file__ = str(path)
    sys.modules[modname] = mod                     # inspect.getsource needs it (cache keys)
    linecache.checkcache(str(path))
    sys.path.insert(0, str(path.parent))
    try:
        exec(compile(path.read_text(), str(path), "exec"), mod.__dict__)
    finally:
        sys.path.remove(str(path.parent))
    return dict(FEATURES)


def _run(features, n):
    global _parts, _feature, _hidden
    _parts, _feature, _hidden = [], n, getattr(features[n], "hexcad_hidden", False)
    try:
        features[n]()
        return _parts
    finally:
        _parts = None


def build(features, names=None, log=None, cache=True, local=None, remote=None):
    """Parts of the features (all by default). With cache: load from the local cache, else from the server, else
    build (and store locally + push to the server). Offline just means local only; entries sync later."""
    from . import cache as C
    from .mesh import tessellate
    from .server import Remote
    local = local or C.Local()
    remote = remote if remote is not None else Remote()
    out = []
    for n in names or list(features):
        if n not in features:
            raise KeyError(f"no feature {n!r}; have {', '.join(features)}")
        t = time.time()
        if not cache:
            out += _run(features, n)
            continue
        key = C.feature_key(features[n])
        blob, src = local.get(key), "cache"
        if blob is None:
            blob, src = remote.get(key), "server"
            if blob is not None:
                local.put(key, blob)
                local.mark_synced(key)
        if blob is None:
            parts, src = _run(features, n), "built"
            blob = C.pack(parts, tessellate)
            local.put(key, blob)
            out += parts
        else:
            out += C.unpack(blob, n)
        if log:
            log(f"{n}: {src} in {time.time() - t:.1f} s")
    if cache:
        pushed = remote.sync(local)
        if log and pushed:
            log(f"pushed {pushed} new builds to the server")
    return out


def clashes(parts, min_volume=1.0):
    """Pairs of parts that overlap by more than min_volume mm3: [(a, b, volume)]."""
    res = []
    boxes = [p.bbox for p in parts]
    for i, j in itertools.combinations(range(len(parts)), 2):
        (a0, a1), (b0, b1) = boxes[i], boxes[j]
        if any(a1[k] < b0[k] or b1[k] < a0[k] for k in range(3)):
            continue
        v = parts[i].shape.intersect(parts[j].shape)
        v = 0 if v is None else (sum(x.volume for x in v) if isinstance(v, list) else v.volume)
        if v > min_volume:
            res.append((parts[i], parts[j], v))
    return res
