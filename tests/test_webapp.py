"""Phone app: project manifests reach the server, and its API serves the model."""
import gzip
import json
import threading
import urllib.request

import numpy as np
import pytest

from hexcad import cache, model, webapp
from hexcad.server import Remote, serve

from test_cache import SRC, project


@pytest.fixture
def server(tmp_path):
    srv = serve(tmp_path / "store", "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url, gz=False):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"} if gz else {})
    with urllib.request.urlopen(req) as r:
        body = r.read()
        return (gzip.decompress(body) if r.headers.get("Content-Encoding") == "gzip" else body), r.headers


def test_full_build_publishes_the_project(tmp_path, server):
    lap = cache.Local(tmp_path / "laptop")
    feats = project(tmp_path)
    model.build(feats, local=lap, remote=Remote(server))
    ps = json.loads(get(server + "/api/projects")[0])
    assert len(ps) == 1 and ps[0]["title"] == "p" and ps[0]["features"] == 2
    m = json.loads(get(f"{server}/api/project/{ps[0]['name']}")[0])
    assert [f["name"] for f in m["features"]] == ["a", "b"]
    a = m["features"][0]
    assert a["parts"][0]["name"] == "A" and a["parts"][0]["color"] == [0, 0, 1, 1]
    assert a["key"] == cache.feature_key(feats["a"]) and a["parts"][0]["triangles"] > 10
    # the mesh is the stored float32 [x y z nx ny nz] array, gzipped on request, cached for good
    body, headers = get(f"{server}/api/mesh/{a['key']}/0", gz=True)
    data = np.frombuffer(body, np.float32).reshape(-1, 6)
    assert np.allclose(data, model.build(feats, local=lap, remote=Remote(""))[0].mesh[0])
    assert "immutable" in headers["Cache-Control"]


def test_partial_build_doesnt_publish(tmp_path, server):
    lap = cache.Local(tmp_path / "laptop")
    model.build(project(tmp_path), ["a"], local=lap, remote=Remote(server))
    assert json.loads(get(server + "/api/projects")[0]) == []


def test_manifest_only_changes_when_the_model_does(tmp_path, server):
    lap = cache.Local(tmp_path / "laptop")
    model.build(project(tmp_path), local=lap, remote=Remote(server))
    name = lap.project_names()[0]
    first = lap.get_project(name)
    model.build(project(tmp_path), local=lap, remote=Remote(server))
    assert lap.get_project(name) == first and lap.unsynced_projects() == []
    model.build(project(tmp_path, SRC.replace("H = 5", "H = 6")), local=lap, remote=Remote(server))
    m = json.loads(get(f"{server}/api/project/{name}")[0])
    assert m["features"][1]["key"] != json.loads(first)["features"][1]["key"]


def test_offline_build_publishes_later(tmp_path, server):
    lap = cache.Local(tmp_path / "laptop")
    model.build(project(tmp_path), local=lap, remote=Remote("http://127.0.0.1:9"))
    assert len(lap.unsynced_projects()) == 1
    Remote(server).sync(lap)
    assert lap.unsynced_projects() == [] and len(json.loads(get(server + "/api/projects")[0])) == 1


def test_app_files_and_bad_requests(server):
    html, h = get(server + "/")
    assert b"HexCAD" in html and h["Content-Type"].startswith("text/html")
    for f in ["app.js", "style.css", "sw.js", "manifest.webmanifest", "icon-192.png", "icon-maskable.png"]:
        assert get(f"{server}/{f}")[0]
    for bad in ["/../server.py", "/api/project/..%2Fx", "/api/project/nope", "/api/mesh/nope-1/0", "/nothing.txt"]:
        with pytest.raises(urllib.error.HTTPError) as e:
            get(server + bad)
        assert e.value.code == 404
    req = urllib.request.Request(server + "/project/x", data=b"not json", method="PUT")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 400


def test_npy_payload_matches_numpy(tmp_path):
    a = np.arange(36, dtype=np.float32).reshape(-1, 6)
    np.save(tmp_path / "a.npy", a)
    assert webapp.npy_payload((tmp_path / "a.npy").read_bytes()) == a.tobytes()
    np.save(tmp_path / "b.npy", a.astype(np.float64))
    with pytest.raises(ValueError):
        webapp.npy_payload((tmp_path / "b.npy").read_bytes())


def test_sync_all_fills_a_new_server(tmp_path, server):
    """Builds already marked synced (with another server) still reach a new one with sync(everything=True)."""
    lap = cache.Local(tmp_path / "laptop")
    other = serve(tmp_path / "other", "127.0.0.1", 0)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        model.build(project(tmp_path), local=lap, remote=Remote(f"http://127.0.0.1:{other.server_address[1]}"))
    finally:
        other.shutdown()
    assert lap.unsynced() == [] and Remote(server).sync(lap) == 0          # nothing looks new
    assert Remote(server).sync(lap, everything=True) == 2
    assert len(json.loads(get(server + "/api/projects")[0])) == 1
