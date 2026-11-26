import threading
from pathlib import Path

import pytest

from hexcad import cache, model
from hexcad.server import Remote, serve

SRC = '''
from hexcad import feature
from hexcad.shapes import bx, cyl, part, color
W = 10
H = 5

def plate(w):
    return bx([0, 0, 0], [w, w, 2])

@feature
def a():
    part("A", [plate(W)], [cyl([5, 5, -1], [5, 5, 3], 1)], color(0, 0, 1))

@feature
def b():
    part("B", [bx([20, 0, 0], [30, 10, H])], [], color(1, 0, 0))
'''


def project(tmp_path, src=SRC):
    f = tmp_path / "p.py"
    f.write_text(src)
    return model.load(f)


def keys(tmp_path, src):
    return {n: cache.feature_key(f) for n, f in project(tmp_path, src).items()}


def test_keys_follow_dependencies(tmp_path):
    k0 = keys(tmp_path, SRC)
    assert keys(tmp_path, SRC) == k0                                   # stable across loads
    k1 = keys(tmp_path, SRC.replace("H = 5", "H = 6"))                 # constant only b uses
    assert k1["a"] == k0["a"] and k1["b"] != k0["b"]
    k2 = keys(tmp_path, SRC.replace("[w, w, 2]", "[w, w, 3]"))         # helper only a uses
    assert k2["a"] != k0["a"] and k2["b"] == k0["b"]
    k3 = keys(tmp_path, SRC + "\n# comment\n")                         # unrelated edit
    assert k3 == k0


def test_second_build_comes_from_cache(tmp_path):
    local = cache.Local(tmp_path / "c")
    log = []
    p1 = model.build(project(tmp_path), local=local, remote=Remote(""), log=log.append)
    p2 = model.build(project(tmp_path), local=local, remote=Remote(""), log=log.append)
    assert [x.split(":")[1].split()[0] for x in log] == ["built", "built", "cache", "cache"]
    assert [p.name for p in p2] == ["A", "B"]
    assert p2[0].body is None and p2[0].volume == pytest.approx(p1[0].volume)
    assert p2[0].shape.volume == pytest.approx(p1[0].volume)          # exact shape back from BREP
    assert p2[0].mesh[0].shape[1] == 6 and p2[1].color == (1, 0, 0, 1)


def test_server_sync_and_offline(tmp_path):
    srv = serve(tmp_path / "store", "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        # laptop offline: builds locally, nothing pushed
        lap = cache.Local(tmp_path / "laptop")
        model.build(project(tmp_path), local=lap, remote=Remote("http://127.0.0.1:9"))
        assert len(lap.unsynced()) == 2
        # back online: the next build syncs everything up
        log = []
        model.build(project(tmp_path), local=lap, remote=Remote(url), log=log.append)
        assert "pushed 2 new builds to the server" in log and lap.unsynced() == []
        # another machine gets the builds from the server instead of building
        desk = cache.Local(tmp_path / "desktop")
        log = []
        parts = model.build(project(tmp_path), local=desk, remote=Remote(url), log=log.append)
        assert all(": server" in x for x in log) and [p.name for p in parts] == ["A", "B"]
        assert desk.unsynced() == []
    finally:
        srv.shutdown()


def test_client_prunes_but_server_store_keeps_everything(tmp_path):
    client = cache.Local(tmp_path / "client", keep=3)
    store = cache.Local(tmp_path / "store", keep=None)
    for i in range(6):
        client.put(f"k{i}", b"x")
        store.put(f"k{i}", b"x")
    assert len(client.keys()) == 3
    assert sorted(store.keys()) == [f"k{i}" for i in range(6)]
