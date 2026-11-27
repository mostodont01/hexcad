"""Shape -> triangle mesh for the viewer (no Qt here, so caches can store meshes headless)."""
import numpy as np


def _triangles(shape, tol):
    """(verts, tris) of the whole shape; vendor STEP models can have a face OpenCascade can't triangulate, which makes
    the one-call tessellation fail, so then it goes face by face and skips the faces that fail."""
    ang = 0.2 if tol <= 0.05 else 0.5                  # coarser retries also take bigger angles on curves
    try:
        return shape.tessellate(tol, ang)
    except AttributeError:
        verts, tris = [], []
        for f in shape.faces():
            try:
                v, t = f.tessellate(tol, ang)
            except AttributeError:
                continue
            n = len(verts)
            verts += v
            tris += [(a + n, b + n, c + n) for a, b, c in t]
        return verts, tris


MAX_TRIANGLES = 60_000      # more is detail nobody sees (vendor STEP models: threads, text) and slow on a phone


def tessellate(shape, tol=0.05):
    """Flat-shaded triangle soup: float32 [x y z nx ny nz] per vertex, plus bounds (lo, hi). Very detailed shapes
    are meshed again, coarser, until they fit in MAX_TRIANGLES (or the tolerance gets silly)."""
    verts, tris = _triangles(shape, tol)
    while len(tris) > MAX_TRIANGLES and tol < 1.0:
        from OCP.BRepTools import BRepTools
        BRepTools.Clean_s(shape.wrapped)               # OpenCascade keeps the finer mesh on the shape otherwise
        tol *= 4
        verts, tris = _triangles(shape, tol)
    if not tris:
        return np.zeros((0, 6), np.float32), np.zeros(3), np.zeros(3)
    v = np.array([(p.X, p.Y, p.Z) for p in verts], np.float32)
    p = v[np.array(tris, np.int64)]                     # (n, 3, 3)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    data = np.concatenate([p, np.repeat(n[:, None, :], 3, axis=1)], axis=2).reshape(-1, 6)
    return data.astype(np.float32), v.min(0), v.max(0)
