// HexCAD phone app: projects on the build store and their current model in 3D.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const $ = id => document.getElementById(id);
const api = path => fetch(path, { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });

if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});

// ---------------------------------------------------------------- project list

function ago(t) {
  const s = Date.now() / 1000 - t;
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${Math.round(s / 3600)} h ago`;
  return new Date(t * 1000).toLocaleDateString();
}

async function showList() {
  $('model').hidden = true;
  $('list').hidden = false;
  const box = $('projects');
  try {
    const ps = await api('/api/projects');
    box.replaceChildren();
    if (!ps.length) box.innerHTML = '<p class="hint">No projects yet. Build one on the laptop (<code>hexcad view</code> or <code>hexcad build</code>) and it shows up here.</p>';
    for (const p of ps) {
      const b = document.createElement('button');
      b.className = 'card';
      const fresh = Date.now() / 1000 - p.updated < 86400 ? ' class="new"' : '';
      b.innerHTML = `<b></b><div class="file"></div><div class="meta">${p.features} features · <span${fresh}>changed ${ago(p.updated)}</span></div>`;
      b.querySelector('b').textContent = p.title;
      b.querySelector('.file').textContent = p.file;
      b.onclick = () => { location.hash = p.name; };
      box.append(b);
    }
  } catch (e) {
    box.innerHTML = '<p class="hint">Can\'t reach the build store. Are you on Tailscale?</p>';
  }
}
$('refresh').onclick = showList;

// ---------------------------------------------------------------- 3D view

const renderer = new THREE.WebGLRenderer({ canvas: $('canvas'), antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x101418);
const camera = new THREE.PerspectiveCamera(40, 1, 1, 100000);
camera.up.set(0, 0, 1);                                     // CAD: Z is up
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x334050, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
camera.add(sun);
sun.position.set(0.5, 1, 1);
scene.add(camera);
const grid = new THREE.GridHelper(400, 40, 0x2a333c, 0x1d242b);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
const model = new THREE.Group();
scene.add(model);

let current = null;                 // {manifest, groups: {feature: THREE.Group}}
let selected = null;

function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();
renderer.setAnimationLoop(() => { if (!$('model').hidden) { controls.update(); renderer.render(scene, camera); } });

function status(text) { $('status').hidden = !text; $('status').textContent = text || ''; }

async function loadPart(key, i, part) {
  const r = await fetch(`/api/mesh/${key}/${i}`);           // immutable: the phone keeps it after the first time
  if (!r.ok) throw new Error(`mesh ${key}/${i}: ${r.status}`);
  const data = new Float32Array(await r.arrayBuffer());
  const buf = new THREE.InterleavedBuffer(data, 6);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.InterleavedBufferAttribute(buf, 3, 0));
  g.setAttribute('normal', new THREE.InterleavedBufferAttribute(buf, 3, 3));
  const [r_, g_, b_, a] = part.color;
  const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(r_, g_, b_), roughness: 0.6, metalness: 0.05,
    transparent: a < 1, opacity: a, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(g, mat);
  mesh.userData.part = part;
  return mesh;
}

async function loadFeature(f) {
  if (current.groups[f.name] || f.missing) return current.groups[f.name];
  const grp = new THREE.Group();
  grp.userData.feature = f.name;
  current.groups[f.name] = grp;
  const meshes = await Promise.all(f.parts.map((p, i) => loadPart(f.key, i, p)));
  meshes.forEach((m, i) => { m.visible = !f.parts[i].hidden || f.showHidden; grp.add(m); });
  model.add(grp);
  return grp;
}

function fit(view = 'iso') {
  const box = new THREE.Box3();
  model.traverse(o => { if (o.isMesh && o.visible && o.parent.visible) box.expandByObject(o); });
  if (box.isEmpty()) box.set(new THREE.Vector3(-50, -50, 0), new THREE.Vector3(50, 50, 50));
  const c = box.getCenter(new THREE.Vector3()), r = box.getSize(new THREE.Vector3()).length() / 2;
  const dir = { iso: [1, -1.2, 0.9], top: [0, -0.0001, 1], front: [0, -1, 0.0001] }[view];
  const d = r / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * (camera.aspect < 1 ? 1.25 / camera.aspect ** 0.5 : 1.1);
  camera.position.copy(c).add(new THREE.Vector3(...dir).normalize().multiplyScalar(d));
  camera.near = d / 100; camera.far = d * 100; camera.updateProjectionMatrix();
  controls.target.copy(c);
  controls.update();
}
$('fit').onclick = () => fit();
document.querySelectorAll('#views button').forEach(b => b.onclick = () => fit(b.dataset.view));

function select(mesh) {
  if (selected) selected.material.emissive.setHex(0);
  selected = mesh;
  if (!mesh) { $('info').hidden = true; return; }
  mesh.material.emissive.setHex(0x553300);
  const p = mesh.userData.part, [lo, hi] = p.bbox;
  const size = hi.map((v, k) => (v - lo[k]).toFixed(1)).join(' × ');
  $('info').innerHTML = '<b></b> <span class="dim"></span><br>' +
    `${size} mm · ${(p.volume / 1000).toFixed(2)} cm³ · ${p.triangles.toLocaleString()} triangles`;
  $('info').querySelector('b').textContent = p.name;
  $('info').querySelector('.dim').textContent = `(${mesh.parent.userData.feature})`;
  $('info').hidden = false;
}

// tap (not drag) selects the part under the finger
let down = null;
renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', e => {
  if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 8) return;
  const ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(e.clientX / innerWidth * 2 - 1, -e.clientY / innerHeight * 2 + 1), camera);
  const hit = ray.intersectObjects(model.children, true).find(h => h.object.visible && h.object.parent.visible);
  select(hit ? hit.object : null);
});

function featureList() {
  const ul = $('features');
  ul.replaceChildren();
  const fs = current.manifest.features;
  $('count').textContent = fs.length;
  for (const f of fs) {
    const li = document.createElement('li');
    const color = f.parts[0] ? `rgb(${f.parts[0].color.slice(0, 3).map(v => Math.round(v * 255))})` : 'transparent';
    li.innerHTML = `<span class="sw" style="background:${color}"></span><span class="nm"></span><input type="checkbox">`;
    li.querySelector('.nm').textContent = f.name;
    const small = document.createElement('small');
    small.textContent = f.missing ? 'not on the store' : `${f.parts.length} part${f.parts.length === 1 ? '' : 's'}`;
    li.querySelector('.nm').append(small);
    li.classList.toggle('missing', !!f.missing);
    const box = li.querySelector('input');
    box.checked = !f.hidden && !f.missing;
    box.disabled = !!f.missing;
    li.classList.toggle('off', !box.checked);
    box.onchange = async () => {
      li.classList.toggle('off', !box.checked);
      if (box.checked) {
        f.showHidden = true;                                 // a feature switched on shows all its parts
        status('Loading…');
        try {
          const g = await loadFeature(f);
          g.visible = true;
          g.children.forEach(m => { m.visible = true; });
        } finally { status(''); }
      } else if (current.groups[f.name]) {
        current.groups[f.name].visible = false;
        if (selected && selected.parent === current.groups[f.name]) select(null);
      }
    };
    ul.append(li);
  }
}
$('handle').onclick = () => $('sheet').classList.toggle('collapsed');

async function showModel(name) {
  $('list').hidden = true;
  $('model').hidden = false;
  $('sheet').classList.add('collapsed');
  select(null);
  model.clear();
  $('features').replaceChildren();
  $('title').textContent = '';
  $('sub').textContent = '';
  resize();
  status('Loading…');
  try {
    const m = await api(`/api/project/${encodeURIComponent(name)}`);
    current = { manifest: m, groups: {} };
    $('title').textContent = m.title;
    $('sub').textContent = `${m.file} · changed ${ago(m.updated)}`;
    featureList();
    const shown = m.features.filter(f => !f.hidden && !f.missing);
    let done = 0;
    await Promise.all(shown.map(async f => {
      await loadFeature(f);
      status(`Loading… ${++done}/${shown.length}`);
    }));
    status('');
    fit();
  } catch (e) {
    status(`Couldn't load the model (${e.message})`);
  }
}

// ---------------------------------------------------------------- routing: #<project> = model, nothing = list

function route() {
  const name = decodeURIComponent(location.hash.slice(1));
  name ? showModel(name) : showList();
}
$('back').onclick = () => { history.length > 1 && location.hash ? history.back() : (location.hash = ''); };
addEventListener('hashchange', route);
route();
