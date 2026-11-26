"""Open plain mesh files (STL) in the viewer: no build, the triangles are shown as they are."""
from pathlib import Path

import numpy as np

from .model import Part

EXTS = (".stl",)


def read_stl(path):
    """Triangles (n, 3, 3) float32 from a binary or ASCII STL."""
    b = Path(path).read_bytes()
    if len(b) >= 84:
        n = int.from_bytes(b[80:84], "little")
        if len(b) == 84 + 50 * n:
            rec = np.frombuffer(b, np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), n, 84)
            return rec["v"].astype(np.float32)
    nums = [float(x) for line in b.decode(errors="ignore").splitlines()
            if (s := line.strip()).startswith("vertex") for x in s.split()[1:4]]
    return np.array(nums, np.float32).reshape(-1, 3, 3)


def stl_part(path, color=(0.12, 0.30, 0.75, 1.0)):
    p = read_stl(path)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    vol = float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    data = np.concatenate([p, np.repeat(n[:, None, :], 3, axis=1)], axis=2).reshape(-1, 6).astype(np.float32)
    flat = p.reshape(-1, 3)
    lo, hi = (flat.min(0), flat.max(0)) if len(flat) else (np.zeros(3), np.zeros(3))
    part = Part(Path(path).stem, "file", None, color)
    part.mesh, part._volume = (data, lo, hi), abs(vol)
    part.source = str(Path(path).resolve())             # Workbench takes the file as it is
    part._bbox = (tuple(map(float, lo)), tuple(map(float, hi)))
    return part
