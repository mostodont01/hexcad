import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick3D
import QtQuick3D.Helpers
import QtQuick.Dialogs
import HexCAD

ApplicationWindow {
    id: win
    width: 1400; height: 900; visible: true
    title: "HexCAD — " + studio.path
    color: "#1d1f24"
    readonly property color panel: "#26292f"
    readonly property color text: "#d8dbe0"
    readonly property color dim: "#8a8f98"
    readonly property color accent: "#d9a521"

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---------- side panel ----------
        Rectangle {
            Layout.preferredWidth: 380; Layout.fillHeight: true; color: win.panel
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 10; spacing: 8
                Label { text: "⬡ HexCAD"; color: win.accent; font.pixelSize: 20; font.bold: true }
                RowLayout {
                    Label { text: studio.path; color: win.dim; elide: Text.ElideMiddle; Layout.fillWidth: true }
                    Button { text: "Open…"; onClicked: openDlg.active = true }
                }
                ComboBox {
                    // recent projects (newest first): pick one to open it
                    Layout.fillWidth: true; model: studio.recent; displayText: "Recent projects…"
                    enabled: studio.recent.length > 1
                    delegate: ItemDelegate {
                        width: ListView.view.width; text: modelData.split("/").slice(-3).join("/")
                        onClicked: studio.open(modelData)
                    }
                }
                // created only when needed: a FileDialog made at start-up blocks rendering on Wayland
                Loader {
                    id: openDlg; active: false
                    sourceComponent: FileDialog {
                        visible: true; nameFilters: ["HexCAD project or mesh (*.py *.stl)", "HexCAD project (*.py)", "STL mesh (*.stl)"]
                        onAccepted: { studio.open(selectedFile); openDlg.active = false }
                        onRejected: openDlg.active = false
                    }
                }
                RowLayout {
                    ComboBox { id: feat; model: studio.features; Layout.fillWidth: true; onActivated: studio.showFeature(currentText) }
                    Button { text: studio.busy ? "…" : "Rebuild"; enabled: !studio.busy; onClicked: studio.rebuild() }
                }
                RowLayout {
                    Button { text: "Show default"; onClicked: studio.showAll(true) }
                    Button { text: "Hide all"; onClicked: studio.showAll(false) }
                    Button { text: "Clash check"; onClicked: studio.checkClashes() }
                }
                ListView {
                    id: list
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: studio.partsModel
                    ScrollBar.vertical: ScrollBar {}
                    // folders = features: a header per feature, ▸/▾ collapses it, its checkbox shows/hides all its parts
                    property var collapsed: ({})
                    function toggleCollapsed(f) { var c = Object.assign({}, collapsed); c[f] = !c[f]; collapsed = c }
                    section.property: "feature"
                    section.delegate: Rectangle {
                        required property string section
                        width: list.width; height: 34; color: "#22252b"
                        MouseArea { anchors.fill: parent; onClicked: list.toggleCollapsed(section) }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 6; anchors.rightMargin: 4
                            Label { text: list.collapsed[section] ? "▸" : "▾"; color: win.accent; font.pixelSize: 14 }
                            Label { text: section; color: win.text; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            Button { text: "show / hide"; font.pixelSize: 11; onClicked: studio.toggleFeature(section) }
                        }
                    }
                    delegate: Rectangle {
                        width: list.width; height: list.collapsed[feature] ? 0 : 44
                        visible: !list.collapsed[feature]
                        color: selected ? "#3a3420" : (index % 2 ? "#2a2d33" : "transparent")
                        MouseArea { anchors.fill: parent; onClicked: studio.setSelected(index, !selected) }
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 4
                            CheckBox { checked: shown; onToggled: studio.setShown(index, checked) }
                            Rectangle { width: 14; height: 14; radius: 3; color: model.color }
                            ColumnLayout {
                                spacing: 0; Layout.fillWidth: true
                                Label { text: name; color: win.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: feature + " · " + info; color: win.dim; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                        }
                    }
                }
                Label { text: "Click parts to select them for printing (none selected = all shown parts)."; color: win.dim; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 11 }
                RowLayout {
                    Button { text: "To Workbench"; onClicked: studio.sendToWorkbench(false) }
                    Button { text: "Slice"; onClicked: studio.sendToWorkbench(true) }
                }
                ScrollView {
                    Layout.fillWidth: true; Layout.preferredHeight: 130
                    TextArea {
                        readOnly: true; wrapMode: Text.Wrap; color: win.text; font.family: "monospace"; font.pixelSize: 11
                        text: studio.status + (studio.clashes ? "\n\nClashes:\n" + studio.clashes : "")
                        background: Rectangle { color: "#1d1f24" }
                    }
                }
            }
        }

        // ---------- 3D view ----------
        View3D {
            id: view
            Layout.fillWidth: true; Layout.fillHeight: true
            environment: SceneEnvironment {
                clearColor: "#1d1f24"; backgroundMode: SceneEnvironment.Color
                antialiasingMode: SceneEnvironment.MSAA; antialiasingQuality: SceneEnvironment.High
            }
            Node {
                id: orbit
                position: Qt.vector3d(studio.center.x, studio.center.z, -studio.center.y)
                eulerRotation: Qt.vector3d(-30, 35, 0)
                PerspectiveCamera {
                    id: cam
                    z: studio.radius * 1.9
                    clipNear: 1; clipFar: studio.radius * 20
                }
            }
            DirectionalLight { eulerRotation: Qt.vector3d(-45, 30, 0); brightness: 1.2 }
            DirectionalLight { eulerRotation: Qt.vector3d(-20, 210, 0); brightness: 0.5 }
            // robot frame is z up: turn it so z points up in the y-up scene
            Node {
                eulerRotation.x: -90
                Repeater3D {
                    model: studio.partsModel
                    Model {
                        geometry: model.geometry
                        visible: shown
                        materials: PrincipledMaterial {
                            baseColor: selected ? win.accent : model.color
                            roughness: 0.6; metalness: 0
                            opacity: model.opacity
                            alphaMode: model.opacity < 1 ? PrincipledMaterial.Blend : PrincipledMaterial.Opaque
                            cullMode: Material.NoCulling
                        }
                    }
                }
            }
            OrbitCameraController { origin: orbit; camera: cam; anchors.fill: parent }
            Label {
                anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 8
                color: win.dim; text: "drag: orbit · right-drag: pan · wheel: zoom · saves rebuild automatically"
            }
        }
    }
}
