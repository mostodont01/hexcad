"""HexCAD viewer: live 3D view of a project file, rebuilt on every save."""
import os
import sys
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import (Property, QAbstractListModel, QByteArray, QFileSystemWatcher, QModelIndex, QObject, Qt,
                            QThread, QTimer, QUrl, Signal, Slot)
from PySide6.QtGui import QColor, QGuiApplication, QVector3D
from PySide6.QtQml import QmlElement, QQmlApplicationEngine
from PySide6.QtQuick3D import QQuick3DGeometry

from .. import model
from .. import workbench

QML_IMPORT_NAME = "HexCAD"
QML_IMPORT_MAJOR_VERSION = 1


def tessellate(shape, tol=0.05):
    """Flat-shaded triangle soup: float32 [x y z nx ny nz] per vertex, plus bounds."""
    verts, tris = shape.tessellate(tol, 0.2)
    if not tris:
        return np.zeros((0, 6), np.float32), (0, 0, 0), (0, 0, 0)
    v = np.array([(p.X, p.Y, p.Z) for p in verts], np.float32)
    t = np.array(tris, np.int64)
    p = v[t]                                            # (n, 3, 3)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    data = np.concatenate([p, np.repeat(n[:, None, :], 3, axis=1)], axis=2).reshape(-1, 6)
    return data.astype(np.float32), v.min(0), v.max(0)


@QmlElement
class MeshGeometry(QQuick3DGeometry):
    def set_mesh(self, data, lo, hi):
        self.clear()
        self.setStride(24)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(QQuick3DGeometry.Attribute.PositionSemantic, 0, QQuick3DGeometry.Attribute.F32Type)
        self.addAttribute(QQuick3DGeometry.Attribute.NormalSemantic, 12, QQuick3DGeometry.Attribute.F32Type)
        self.setVertexData(QByteArray(data.tobytes()))
        self.setBounds(QVector3D(*map(float, lo)), QVector3D(*map(float, hi)))
        self.update()


class Builder(QThread):
    done = Signal(object, str)

    def __init__(self, path, features):
        super().__init__()
        self.path, self.features = path, features

    def run(self):
        try:
            feats = model.load(self.path)
            parts = model.build(feats, self.features or None)
            meshes = [tessellate(p.shape) for p in parts]
            self.done.emit((list(feats), parts, meshes), "")
        except Exception:  # noqa: BLE001 - show any project error in the UI
            self.done.emit(None, traceback.format_exc(limit=6))


class PartsModel(QAbstractListModel):
    ROLES = [b"name", b"feature", b"color", b"shown", b"info", b"geometry", b"selected", b"opacity"]

    def __init__(self):
        super().__init__()
        self.rows = []

    def roleNames(self):
        return {Qt.UserRole + i: r for i, r in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def data(self, index, role):
        return self.rows[index.row()].get(self.ROLES[role - Qt.UserRole].decode())

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def set(self, row, key, value):
        self.rows[row][key] = value
        i = self.index(row)
        self.dataChanged.emit(i, i, [Qt.UserRole + self.ROLES.index(key.encode())])


class Studio(QObject):
    changed = Signal()

    def __init__(self, path):
        super().__init__()
        self._path = str(Path(path).resolve())
        self._status, self._busy, self._features, self._feature = "", False, [], ""
        self._clashes, self._radius, self._center = "", 300.0, QVector3D()
        self.parts = PartsModel()
        self._parts = []
        self._geoms = []
        self._builder = None
        self._again = False
        self.watch = QFileSystemWatcher([self._path])
        self.watch.fileChanged.connect(self._on_file)
        self._debounce = QTimer(singleShot=True, interval=300, timeout=self.rebuild)

    def _on_file(self, p):
        if p not in self.watch.files():      # editors replace the file on save
            self.watch.addPath(p)
        self._debounce.start()

    def _prop(name, kind=str, changed=changed):
        return Property(kind, lambda s: getattr(s, "_" + name), notify=changed)

    path = _prop("path")
    status = _prop("status")
    busy = _prop("busy", bool)
    features = _prop("features", list)
    feature = _prop("feature")
    clashes = _prop("clashes")
    radius = _prop("radius", float)
    center = _prop("center", QVector3D)

    @Property(QObject, constant=True)
    def partsModel(self):
        return self.parts

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, "_" + k, v)
        self.changed.emit()

    @Slot(str)
    def open(self, url):
        path = QUrl(url).toLocalFile() or url
        self.watch.removePaths(self.watch.files())
        self._path = str(Path(path).resolve())
        self.watch.addPath(self._path)
        self.parts.set_rows([])
        remember(self._path)
        self._set(feature="", clashes="")
        self.rebuild()

    @Slot()
    def rebuild(self):
        if self._builder and self._builder.isRunning():
            self._again = True
            return
        self._set(busy=True, status="building…")
        self._builder = Builder(self._path, [self._feature] if self._feature else None)
        self._builder.done.connect(self._built)
        self._builder.start()

    @Slot(str)
    def showFeature(self, f):
        self._set(feature="" if f == "All" else f)
        self.rebuild()

    def _built(self, res, err):
        if err:
            self._set(busy=False, status=err)
        else:
            feats, parts, meshes = res
            shown = {r["name"]: r["shown"] for r in self.parts.rows}
            rows, self._geoms = [], []
            lo, hi = np.full(3, 1e9), np.full(3, -1e9)
            for p, (data, a, b) in zip(parts, meshes):
                g = MeshGeometry()
                g.set_mesh(data, a, b)
                self._geoms.append(g)
                if len(data) and (not p.hidden or self._feature):
                    lo, hi = np.minimum(lo, a), np.maximum(hi, b)
                (pl, ph) = p.bbox
                size = " × ".join(f"{ph[i] - pl[i]:.1f}" for i in range(3))
                rows.append({"name": p.name, "feature": p.feature, "color": QColor.fromRgbF(*p.color[:3]), "opacity": float(p.color[3]),
                             "shown": shown.get(p.name, not p.hidden or bool(self._feature)),
                             "info": f"{size} mm · {p.volume / 1000:.1f} cm³", "geometry": g, "selected": False})
            self._parts = parts
            self.parts.set_rows(rows)
            if lo[0] > hi[0]:                      # everything hidden: frame it all
                lo, hi = np.zeros(3), np.full(3, 100.0)
            c = (lo + hi) / 2
            self._set(busy=False, features=["All"] + feats, status=f"{len(parts)} parts",
                      radius=float(max(np.linalg.norm(hi - lo) / 2, 10)),
                      center=QVector3D(*map(float, c)))
        if self._again:
            self._again = False
            self.rebuild()

    @Slot(int, bool)
    def setShown(self, row, v):
        self.parts.set(row, "shown", v)

    @Slot(int, bool)
    def setSelected(self, row, v):
        self.parts.set(row, "selected", v)

    @Slot(bool)
    def showAll(self, v):
        for i in range(len(self.parts.rows)):
            self.parts.set(i, "shown", v)

    def _chosen(self):
        sel = [p for p, r in zip(self._parts, self.parts.rows) if r["selected"]]
        return sel or [p for p, r in zip(self._parts, self.parts.rows) if r["shown"]]

    @Slot()
    def checkClashes(self):
        parts = [p for p, r in zip(self._parts, self.parts.rows) if r["shown"]]
        cl = model.clashes(parts)
        self._set(clashes="\n".join(f"{v:.1f} mm³  {a.name}  ×  {b.name}" for a, b, v in cl) or "no clashes")

    @Slot(bool)
    def sendToWorkbench(self, slice_now):
        parts = self._chosen()
        try:
            msg = workbench.send(parts, Path(self._path).stem, slice_now=slice_now)
        except Exception as e:  # noqa: BLE001
            msg = f"Workbench: {e}"
        self._set(status=msg)


LAST = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "hexcad" / "last-project"


def remember(path):
    try:
        LAST.parent.mkdir(parents=True, exist_ok=True)
        LAST.write_text(str(path))
    except OSError:
        pass


def main(path=None):
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("HexCAD")
    if not path and LAST.exists():
        path = LAST.read_text().strip()
    if not path or not Path(path).exists():
        print("usage: hexcad view project.py", file=sys.stderr)
        return 2
    remember(Path(path).resolve())
    studio = Studio(path)
    eng = QQmlApplicationEngine()
    eng.rootContext().setContextProperty("studio", studio)
    eng.load(QUrl.fromLocalFile(str(Path(__file__).with_name("main.qml"))))
    if not eng.rootObjects():
        return 1
    shot = os.environ.get("HEXCAD_SCREENSHOT")    # save one screenshot after the first build, then quit
    if shot:
        def grab():
            if studio.busy or not studio.parts.rowCount():
                return QTimer.singleShot(500, grab)
            QTimer.singleShot(2000, lambda: (eng.rootObjects()[0].grabWindow().save(shot), app.quit()))
        QTimer.singleShot(1000, grab)
    studio.rebuild()
    app._keep = (studio, eng)
    return app.exec()
