"""Shape -> triangle mesh for the viewer (no Qt here, so caches can store meshes headless)."""
import numpy as np


def _triangles(shape, tol):
    """(verts, tris) of the whole shape; vendor STEP models can have a face OpenCascade can't triangulate, which makes
    the one-call tessellation fail, so then it goes face by face and skips the faces that fail."""
    try:
        return shape.tessellate(tol, 0.2)
    except AttributeError:
        verts, tris = [], []
        for f in shape.faces():
            try:
                v, t = f.tessellate(tol, 0.2)
            except AttributeError:
                continue
            n = len(verts)
            verts += v
            tris += [(a + n, b + n, c + n) for a, b, c in t]
        return verts, tris


def tessellate(shape, tol=0.05):
    """Flat-shaded triangle soup: float32 [x y z nx ny nz] per vertex, plus bounds (lo, hi)."""
    verts, tris = _triangles(shape, tol)
    if not tris:
        return np.zeros((0, 6), np.float32), np.zeros(3), np.zeros(3)
    v = np.array([(p.X, p.Y, p.Z) for p in verts], np.float32)
    p = v[np.array(tris, np.int64)]                     # (n, 3, 3)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    data = np.concatenate([p, np.repeat(n[:, None, :], 3, axis=1)], axis=2).reshape(-1, 6)
    return data.astype(np.float32), v.min(0), v.max(0)
