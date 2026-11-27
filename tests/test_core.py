import math
from pathlib import Path

import pytest

from hexcad import cli, model
from hexcad.shapes import bx, cone, cut, cyl, prism, rbx, sph, unite, moveBodies, rotateBodies, filletAt

EX = Path(__file__).parent.parent / "examples" / "bracket.py"


def test_primitives():
    assert bx([0, 0, 0], [10, 20, 30]).volume == pytest.approx(6000)
    assert bx([10, 20, 30], [0, 0, 0]).volume == pytest.approx(6000)
    assert cyl([0, 0, 0], [0, 10, 0], 2).volume == pytest.approx(math.pi * 4 * 10)
    assert cone([0, 0, 0], [5, 0, 0], 2, 1).volume == pytest.approx(math.pi * 5 / 3 * (4 + 2 + 1))
    assert sph([1, 2, 3], 3).volume == pytest.approx(4 / 3 * math.pi * 27)
    tri = prism([0, 0, 5], [0, 0, 1], [1, 0, 0], [[0, 0], [10, 0], [0, 10]], 2)
    assert tri.volume == pytest.approx(100)
    assert tri.s.bounding_box().min.Z == pytest.approx(5)


def test_rounded_box():
    r = rbx([0, 0, 0], [20, 20, 10], [5, 0, 0, 0])
    assert r.volume == pytest.approx(4000 - (25 - math.pi * 25 / 4) * 10, rel=1e-6)


def test_booleans_in_place():
    a = bx([0, 0, 0], [10, 10, 10])
    u = unite([a, bx([10, 0, 0], [20, 10, 10])])
    assert u.volume == pytest.approx(2000)
    cut(u, [bx([0, 0, 0], [5, 10, 10])])
    assert u.volume == pytest.approx(1500)          # target changed in place


def test_move_rotate_fillet():
    b = bx([0, 0, 0], [10, 10, 10])
    moveBodies(b, [5, 0, 0])
    assert b.s.bounding_box().min.X == pytest.approx(5)
    rotateBodies([b], [0, 0, 0], [0, 0, 1], 90)
    assert b.s.bounding_box().max.Y == pytest.approx(15)
    f = filletAt(bx([0, 0, 0], [10, 10, 10]), [[10, 10, 5]], 2)
    assert f.volume == pytest.approx(1000 - (4 - math.pi) * 10, rel=1e-6)


def test_project_build_and_clash():
    feats = model.load(EX)
    assert list(feats) == ["bracket", "washer"]
    parts = model.build(feats)
    assert [p.name for p in parts] == ["L bracket", "Rib"]
    assert parts[0].feature == "bracket"
    assert model.clashes(parts) == []
    with pytest.raises(KeyError):
        model.build(feats, ["nope"])


def test_cli_build(tmp_path, capsys):
    assert cli.main(["build", str(EX), "-o", str(tmp_path), "--step"]) == 0
    assert (tmp_path / "l-bracket.stl").stat().st_size > 1000
    assert (tmp_path / "rib.step").exists()
    assert cli.main(["check", str(EX), "--strict"]) == 0
    assert "2 parts, 0 clashes" in capsys.readouterr().out


def test_empty_part_is_an_error(tmp_path):
    f = tmp_path / "p.py"
    f.write_text("from hexcad import feature\nfrom hexcad.shapes import bx, part, color\n"
                 "@feature\ndef f():\n    part('Gone', [bx([0,0,0],[1,1,1])], [bx([-1,-1,-1],[2,2,2])], color(1,0,0))\n")
    with pytest.raises(RuntimeError, match="came out empty"):
        model.build(model.load(f), cache=False)


def test_batch_fallback(monkeypatch):
    from build123d import Solid
    import hexcad.shapes as S
    a, b = bx([0, 0, 0], [10, 10, 10]), bx([10, 0, 0], [20, 10, 10])
    real = Solid.fuse

    def flaky(self, *others):                      # simulate the OCC multi-tool failure
        return Solid() if len(others) > 1 else real(self, *others)
    monkeypatch.setattr(Solid, "fuse", flaky)
    u = S.unite([a, b, bx([20, 0, 0], [30, 10, 10])])
    assert u.volume == pytest.approx(3000)


def test_step_import_filter_and_cache_key(tmp_path):
    """Bought parts from STEP: solids picked by bounding box, and the feature key follows the file's content."""
    from build123d import Box, Compound, Location, export_step
    from hexcad import cache, model
    body = Box(10, 10, 10)
    cable = Box(50, 2, 2).moved(Location((40, 0, 0)))
    export_step(Compound([body, cable]), str(tmp_path / "thing.step"))
    src = '''
from hexcad import feature
from hexcad.shapes import StepFile, step, name, moveBodies, color
THING = StepFile("thing.step")

@feature
def bought():
    b = step(THING, keep=lambda lo, hi: hi[0] < 10)       # drop the "cable"
    moveBodies(b, [0, 0, 5])
    name(b, "Thing", color(0.2, 0.2, 0.2))
'''
    (tmp_path / "p.py").write_text(src)
    feats = model.load(tmp_path / "p.py")
    [p] = model.build(feats, cache=False)
    assert p.volume == pytest.approx(1000) and p.bbox[0][2] == pytest.approx(0)
    k1 = cache.feature_key(feats["bought"])
    export_step(Compound([Box(10, 10, 12), cable]), str(tmp_path / "thing.step"))
    assert cache.feature_key(model.load(tmp_path / "p.py")["bought"]) != k1
