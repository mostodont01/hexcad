"""Projects: a Python file whose functions decorated with @feature build named parts."""
import importlib.util
import itertools
import sys
import time
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
    body: object
    color: tuple = (0.6, 0.6, 0.6, 1.0)
    hidden: bool = False
    _clean: object = field(default=None, repr=False)

    @property
    def shape(self):
        if self._clean is None:
            s = self.body.s
            try:
                s = s.clean()
            except Exception:  # noqa: BLE001 - clean is cosmetic
                pass
            self._clean = s
        return self._clean

    @property
    def volume(self):
        return self.shape.volume

    @property
    def bbox(self):
        b = self.shape.bounding_box()
        return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)


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
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(path.parent))
    return dict(FEATURES)


def build(features, names=None, log=None):
    """Run features (all by default) and return their parts."""
    global _parts, _feature, _hidden
    out = []
    for n in names or list(features):
        if n not in features:
            raise KeyError(f"no feature {n!r}; have {', '.join(features)}")
        _parts, _feature, _hidden = [], n, getattr(features[n], "hexcad_hidden", False)
        t = time.time()
        try:
            features[n]()
            out += _parts
        finally:
            _parts = None
        if log:
            log(f"{n}: {time.time() - t:.1f} s")
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
        v = v.volume if v is not None else 0
        if v > min_volume:
            res.append((parts[i], parts[j], v))
    return res
