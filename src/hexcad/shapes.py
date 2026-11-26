"""Solid-building helpers (mm). Every helper returns a Body: a mutable handle on an OpenCascade shape, so
cut(target, ...) changes the target in place and registered parts see later moves (like Onshape bodies)."""
import math

from build123d import Align, Axis, Face, FontStyle, Location, Plane, Solid, Text, Vector, Wire, extrude

from . import model

degree = math.pi / 180
sin, cos, tan, sqrt, floor = math.sin, math.cos, math.tan, math.sqrt, math.floor


class Body:
    __slots__ = ("s",)

    def __init__(self, s):
        self.s = s

    @property
    def volume(self):
        return self.s.volume


def _s(x):
    return x.s if isinstance(x, Body) else x


def color(r, g, b, a=1.0):
    return (r, g, b, a)


# small list helpers (FeatureScript style, kept for ported code)
def append(a, x):
    return [*a, x]


def concatenateArrays(arrs):
    return [x for a in arrs for x in a]


def size(a):
    return len(a)


def bx(a, b):
    """Axis-aligned box between two corners."""
    lo = [min(a[i], b[i]) for i in range(3)]
    hi = [max(a[i], b[i]) for i in range(3)]
    return Body(Solid.make_box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], Plane(origin=lo)))


def rbx(a, b, r):
    """Box with rounded vertical edges; r = radii at corners (x0,y0), (x1,y0), (x1,y1), (x0,y1)."""
    body = bx(a, b)
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    s = body.s
    for (x, y), rr in zip([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], r):
        if rr > 0:
            e = [e for e in s.edges().filter_by(Axis.Z) if abs(e.center().X - x) < 1e-6 and abs(e.center().Y - y) < 1e-6]
            s = s.fillet(rr, e)
    body.s = s
    return body


def cone(p0, p1, r0, r1):
    d = Vector(*p1) - Vector(*p0)
    return Body(Solid.make_cone(r0, r1, d.length, Plane(origin=p0, z_dir=d)))


def cyl(p0, p1, r):
    d = Vector(*p1) - Vector(*p0)
    return Body(Solid.make_cylinder(r, d.length, Plane(origin=p0, z_dir=d)))


def sph(c, r):
    return Body(Solid.make_sphere(r, Plane(origin=c)))


def prism(c, n, xd, pts, depth):
    """Closed polygon (points [u, v]) on the plane (origin c, normal n, x direction xd), extruded by depth along n."""
    pl = Plane(origin=c, x_dir=xd, z_dir=n)
    w = Wire.make_polygon([pl.from_local_coords(Vector(u, v, 0)) for u, v in pts], close=True)
    return Body(Solid.extrude(Face(w), pl.z_dir * depth))


def engrave(txt, cx, cy, h, z, d):
    """Text tool body: bold text of height ~h centred on (cx, cy) on the plane z, going d down."""
    t = Text(txt, font_size=h, font="Open Sans", font_style=FontStyle.BOLD, align=(Align.CENTER, Align.CENTER))
    return Body(extrude(t, amount=d, dir=(0, 0, -1)).moved(Location((cx, cy, z))))


def _vol(s):
    try:
        return s.volume
    except Exception:  # noqa: BLE001 - a broken result counts as empty
        return 0.0


def unite(adds):
    """Union of the bodies (into adds[0]). OpenCascade's one-call union of many tools sometimes fails and returns an
    empty shape; a union can never be smaller than its biggest piece, so then it is redone one piece at a time."""
    if len(adds) > 1:
        shapes = [_s(a) for a in adds]
        r = shapes[0].fuse(*shapes[1:])
        if _vol(r) < max(_vol(x) for x in shapes) - 1e-6:
            r = shapes[0]
            for x in shapes[1:]:
                r = r.fuse(x)
        adds[0].s = r
    return adds[0]


def cut(target, subs):
    """Subtract the bodies from target (in place). If the one-call cut wipes out the target (OpenCascade failure),
    it is redone one tool at a time."""
    if subs:
        tools = [_s(x) for x in subs]
        v0 = _vol(target.s)
        r = target.s.cut(*tools)
        if v0 > 0 and _vol(r) <= 1e-6:
            r = target.s
            for x in tools:
                r = r.cut(x)
        target.s = r
    return target


def name(q, n, c):
    model.register(q, n, c)
    return q


def part(n, adds, subs, c):
    return name(cut(unite(adds), subs), n, c)


def mirrorX(body, n, c):
    return name(Body(body.s.mirror(Plane.YZ)), n, c)


def moveBodies(q, d):
    for b in q if isinstance(q, list) else [q]:
        b.s = b.s.moved(Location(tuple(d)))


def rotateBodies(q, origin, axis, deg):
    for b in q if isinstance(q, list) else [q]:
        b.s = b.s.rotate(Axis(tuple(origin), tuple(axis)), deg)


def filletAt(q, points, r):
    """Fillet the edges passing through the given points (tangent chains follow automatically)."""
    edges = [e for e in q.s.edges() if any(e.distance_to(Vector(*p)) < 1e-4 for p in points)]
    q.s = q.s.fillet(r, edges)
    return q
