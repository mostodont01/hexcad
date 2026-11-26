"""Send parts to Prusa Workbench (github.com/mostodont01/prusa-workbench-mcp): new job, lay flat, arrange, slice.
Runs Workbench's own Python (its venv), so HexCAD does not depend on it."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

WORKBENCH = Path(os.environ.get("HEXCAD_WORKBENCH", "~/Programming/PrusaSlicer-mcp")).expanduser()
# the user's print preferences: gyroid infill, slow first layer (perimeters and its infill)
SETTINGS = {"fill_pattern": "gyroid", "first_layer_speed": 15, "first_layer_infill_speed": 15}

SCRIPT = r"""
import json, sys
from prusa_workbench import mcp_server as m
a = json.loads(sys.argv[1])
print(m.new_job(a["job"]))
print(m.set_bed("bed-1", settings=a["settings"]))
names = []
for f, n in a["files"]:
    m.add_model(f, name=n, arrange=False)
    names.append(n)
print(m.transform(names, lay_flat=True))
print(m.arrange())
if a["slice"]:
    print(m.slice_beds(open_viewer=True))
else:
    print(m.open_viewer())
"""


def python():
    py = WORKBENCH / ".venv" / "bin" / "python"
    if not py.exists():
        raise FileNotFoundError(f"Prusa Workbench not found at {WORKBENCH} (set HEXCAD_WORKBENCH)")
    return py


def send(parts, project="hexcad", slice_now=False, settings=None, run=subprocess.run):
    """Export parts as STL into a new Workbench job; slice it if asked. Returns Workbench's summary text."""
    from build123d import export_stl
    if not parts:
        raise ValueError("no parts chosen")
    out = Path(tempfile.mkdtemp(prefix="hexcad-"))
    files = []
    for p in parts:
        n = re.sub(r"[^A-Za-z0-9]+", "-", re.sub(r"\(.*?\)", "", p.name)).strip("-")
        f = out / f"{n}.stl"
        export_stl(p.shape, str(f), tolerance=0.01, angular_tolerance=0.1)
        files.append([str(f), n])
    job = f"{re.sub(r'[^a-z0-9]+', '-', project.lower())}-{len(parts)}-parts"
    args = {"job": job, "files": files, "slice": slice_now, "settings": settings or SETTINGS}
    r = run([str(python()), "-c", SCRIPT, json.dumps(args)], capture_output=True, text=True, timeout=1800)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1])
    return f"Workbench job {job}: {len(parts)} parts" + (" sliced" if slice_now else "") + "\n" + r.stdout[-1500:]
