"""hexcad CLI: hexcad {list,build,check,info,view} project.py"""
import argparse
import re
import sys
from pathlib import Path



class _LazyModel:
    """`model` is imported on first use, so `hexcad serve` / `sync` run without the CAD kernel (no libGL on servers)."""
    def __getattr__(self, name):
        from . import model as m
        return getattr(m, name)


model = _LazyModel()


def slug(n):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"\(.*?\)", "", n.lower())).strip("-")


def _parts(a):
    feats = model.load(a.project)
    parts = model.build(feats, a.feature or None, cache=not a.no_cache,
                        log=lambda m: print(m, file=sys.stderr) if a.verbose else None)
    if a.part:
        parts = [p for p in parts if any(q.lower() in p.name.lower() for q in a.part)]
        if not parts:
            raise SystemExit(f"no part matches {a.part}")
    return parts


def cmd_list(a):
    for n in model.load(a.project):
        print(n)


def cmd_build(a):
    from build123d import export_step, export_stl
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for p in _parts(a):
        (lo, hi) = p.bbox
        f = out / slug(p.name)
        if not a.no_stl:
            export_stl(p.shape, str(f.with_suffix(".stl")), tolerance=a.tolerance, angular_tolerance=0.1)
        if a.step:
            export_step(p.shape, str(f.with_suffix(".step")))
        dims = " x ".join(f"{hi[i] - lo[i]:.1f}" for i in range(3))
        print(f"{p.name}: {dims} mm, {p.volume / 1000:.2f} cm3 -> {f.name}")


def cmd_info(a):
    for p in _parts(a):
        (lo, hi) = p.bbox
        dims = " x ".join(f"{hi[i] - lo[i]:.1f}" for i in range(3))
        print(f"{p.feature:16} {p.name:50} {dims:>22} mm  {p.volume / 1000:8.2f} cm3")


def cmd_check(a):
    parts = _parts(a)
    cl = model.clashes(parts, a.min)
    for x, y, v in cl:
        print(f"{v:8.1f} mm3  {x.feature}: {x.name}  x  {y.feature}: {y.name}")
    print(f"{len(parts)} parts, {len(cl)} clashes")
    return 1 if cl and a.strict else 0


def cmd_slice(a):
    from . import workbench
    print(workbench.send(_parts(a), Path(a.project).stem, slice_now=not a.no_slice))


def cmd_serve(a):
    from .server import serve
    serve(Path(a.dir).expanduser(), a.host, a.port).serve_forever()


def cmd_sync(a):
    from .cache import Local
    from .server import Remote
    r = Remote()
    if not r.url:
        print("no server set (~/.config/hexcad/config.json {\"server\": \"http://host:8770\"} or HEXCAD_SERVER)")
        return 1
    n = r.sync(Local())
    print(f"{r.url}: offline" if n is None else f"{r.url}: pushed {n} builds")
    return 1 if n is None else 0


def cmd_view(a):
    from .app import main
    return main(a.project)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hexcad", description="Code-first CAD on build123d / OpenCascade")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n, f, h in [("list", cmd_list, "list features"), ("build", cmd_build, "export parts (STL, optional STEP)"),
                    ("info", cmd_info, "sizes and volumes"), ("check", cmd_check, "clash check"),
                    ("slice", cmd_slice, "send parts to Prusa Workbench and slice"), ("view", cmd_view, "open the viewer")]:
        p = sub.add_parser(n, help=h)
        p.add_argument("project", nargs="?" if n == "view" else None, help="project .py file"
                       + (" (default: the last one opened)" if n == "view" else ""))
        p.set_defaults(fn=f)
        if n in ("build", "info", "check", "slice"):
            p.add_argument("-f", "--feature", action="append", help="feature to build (repeatable; default all)")
            p.add_argument("-v", "--verbose", action="store_true")
            p.add_argument("--no-cache", action="store_true", help="always build (no cache, no server)")
            p.add_argument("-p", "--part", action="append", help="only parts whose name contains this (repeatable)")
    sub.choices["build"].add_argument("-o", "--out", default="out")
    sub.choices["build"].add_argument("--step", action="store_true", help="also write STEP")
    sub.choices["build"].add_argument("--no-stl", action="store_true")
    sub.choices["build"].add_argument("--tolerance", type=float, default=0.01, help="STL chord tolerance (mm)")
    sub.choices["check"].add_argument("--min", type=float, default=1.0, help="ignore overlaps below this (mm3)")
    sub.choices["check"].add_argument("--strict", action="store_true", help="exit 1 on clashes")
    sv = sub.add_parser("serve", help="run the build store (e.g. on the home server)")
    sv.add_argument("--dir", default="~/hexcad-store")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8770)
    sv.set_defaults(fn=cmd_serve)
    sub.add_parser("sync", help="push local builds the server is missing").set_defaults(fn=cmd_sync)
    sub.choices["slice"].add_argument("--no-slice", action="store_true", help="only make the job")
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
