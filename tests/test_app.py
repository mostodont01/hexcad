import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
EX = Path(__file__).parent.parent / "examples" / "bracket.py"


def test_tessellate():
    from hexcad.app import tessellate
    from hexcad.shapes import bx
    data, lo, hi = tessellate(bx([0, 0, 0], [10, 20, 30]).s)
    assert data.shape == (36, 6)                      # 12 triangles, flat shaded
    assert tuple(hi - lo) == pytest.approx((10, 20, 30))


def test_studio_builds_and_lists(qtbot):
    from hexcad.app import Studio
    s = Studio(EX)
    s.rebuild()
    qtbot.waitUntil(lambda: not s.busy and s.parts.rowCount() == 2, timeout=60000)
    assert s.features == ["All", "bracket", "washer"]
    names = [r["name"] for r in s.parts.rows]
    assert names == ["L bracket", "Rib"]
    s.setShown(0, False)
    assert s.parts.rows[0]["shown"] is False
    s.checkClashes()
    assert s.clashes == "no clashes"
    s.showFeature("washer")
    qtbot.waitUntil(lambda: not s.busy and s.parts.rowCount() == 1, timeout=60000)


def test_qml_loads(qtbot):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    import hexcad.app as app
    s = app.Studio(EX)
    eng = QQmlApplicationEngine()
    eng.rootContext().setContextProperty("studio", s)
    eng.load(QUrl.fromLocalFile(str(Path(app.__file__).with_name("main.qml"))))
    if not eng.rootObjects():
        pytest.skip("Qt Quick 3D unavailable on this platform")
    s.rebuild()
    qtbot.waitUntil(lambda: s.parts.rowCount() == 2, timeout=60000)


def test_workbench_send(monkeypatch, tmp_path):
    from hexcad import model, workbench
    parts = model.build(model.load(EX))
    seen = {}

    def fake_run(cmd, **kw):
        import json
        seen["args"] = json.loads(cmd[-1])
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(workbench, "python", lambda: Path("/usr/bin/python3"))
    msg = workbench.send(parts, "bracket", slice_now=True, run=fake_run)
    a = seen["args"]
    assert a["slice"] is True and len(a["files"]) == 2
    assert Path(a["files"][0][0]).stat().st_size > 1000
    assert a["settings"]["fill_pattern"] == "gyroid"
    assert "2 parts sliced" in msg
