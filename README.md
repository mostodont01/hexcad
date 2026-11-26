# ⬡ HexCAD

Code-first CAD with a live 3D viewer. Parts are Python functions on [build123d](https://github.com/gumyr/build123d)
(OpenCascade kernel: real booleans, fillets, STEP), so models live in git, build offline, and have no API limits.

```python
from hexcad import feature
from hexcad.shapes import bx, cyl, rbx, part, color

@feature
def bracket():
    base = rbx([0, 0, 0], [40, 20, 4], [3, 3, 3, 3])          # box with rounded vertical corners
    hole = cyl([15, 10, -1], [15, 10, 5], 1.6)                 # cylinder between two points
    part("Bracket", [base], [hole], color(0.12, 0.30, 0.75))   # name = adds - subs
```

## Use

```
hexcad view project.py          # viewer: rebuilds on every save, show/hide, clash check, Workbench buttons
hexcad list project.py          # features
hexcad info project.py          # sizes + volumes of every part
hexcad build project.py -o out --step     # STL (+ STEP) per part
hexcad check project.py --strict          # clash check (overlap volumes)
hexcad slice project.py -f bracket        # new Prusa Workbench job: lay flat, arrange, slice, open the viewer
```

- **Helpers** (`hexcad.shapes`, mm): `bx`, `rbx`, `cyl`, `cone`, `sph`, `prism` (polygon on any plane, extruded),
  `engrave` (text), `unite`, `cut` (changes the target in place), `part`, `name`, `mirrorX`, `moveBodies`,
  `rotateBodies`, `filletAt` (fillet the edges through given points). Anything else from build123d works too:
  wrap a build123d shape in `Body(shape)`.
- **Features** group parts; `@feature(hidden=True)` keeps reference geometry, test prints or alternative versions
  hidden in the viewer until you pick that feature.
- **Prusa Workbench** ([prusa-workbench-mcp](https://github.com/mostodont01/prusa-workbench-mcp)): "To Workbench" /
  "Slice" export the selected parts (none selected = all shown) into a new job with gyroid infill and a 15 mm/s first
  layer, using Workbench's own Python (`HEXCAD_WORKBENCH`, default `~/Programming/PrusaSlicer-mcp`).

## Install

```
uv tool install --editable .     # puts `hexcad` on the PATH
```

Tests: `QT_QPA_PLATFORM=offscreen uv run pytest`.

Planned: run builds on a small home server (old tablet) and view from anywhere; STEP import of bought parts.

MIT licence.
