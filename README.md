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
hexcad slice project.py -f bracket -p "L bracket"   # new Prusa Workbench job (lay flat, arrange, slice, open the viewer)
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

## Build cache + server

Nothing is built twice. Every feature gets a key from its own code plus the functions and constants it uses (and the
HexCAD / build123d version), so editing one part rebuilds only that feature. Built features (exact BREP shapes, viewer
meshes, sizes) are kept

- **locally** in `~/.cache/hexcad` (works offline), and
- **on a server** (keeps every build; clients keep their 400 most recently used) (`hexcad serve`, e.g. an old tablet at home): a missing feature is fetched from the server before it
  is built; new builds are pushed right away, or on the next contact after working offline (`hexcad sync` forces it;
  `hexcad sync --all` checks every local build, e.g. after changing servers).

Client config: `~/.config/hexcad/config.json` → `{"server": "http://100.97.75.22:8770"}` (the `server` tablet over
Tailscale, works away from home too) (or `HEXCAD_SERVER`).
Server setup over SSH, no root: `server/install-server.sh <ssh-host>` (uv + HexCAD, `hexcad serve` with a crontab
`@reboot` line). Offline costs one 0.5 s connection probe. `--no-cache` builds without either.

## Phone app

`hexcad serve` also serves an installable web app (PWA) with your models in 3D: the project list (newest change
first), then the model; drag to orbit, pinch to zoom, tap a part for its name, size and volume, and the features
sheet at the bottom shows / hides features (hidden ones, like test prints, start off).

Whenever a client builds a **whole** project (the viewer, `hexcad info`, `build`, `check`, ...), it also stores
which build each feature uses now and pushes that to the server with the builds, so the phone always shows the
latest model. Meshes are cached on the phone (a build's key changes when it changes), so a model downloads once.

Installing it needs HTTPS: on the server, `sudo tailscale serve --bg 8770` gives
`https://<server>.<tailnet>.ts.net`; open that in Chrome on the phone and use **Install app**. The server itself has
no CAD kernel (stdlib + the stored meshes); three.js loads from a CDN.

## Install

```
uv tool install --editable .     # puts `hexcad` on the PATH
```

Tests: `QT_QPA_PLATFORM=offscreen uv run pytest`.

Planned: STEP import of bought parts; builds on the server for weak clients.

MIT licence.
