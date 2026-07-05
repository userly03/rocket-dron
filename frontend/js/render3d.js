/**
 * Render 3D del mapa táctico (Three.js). Reemplaza el canvas 2D.
 * Expone window.Render3D con una API mínima que consume script.js (script clásico).
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const DRONE_ALTITUDE = 14;
const MISSILE_ALTITUDE = 22;
const TRAIL_MAX_POINTS = 30;
const FALL_DURATION_MS = 1100;
const BLINK_PERIOD_MS = 140;
const DETONATION_DURATION_MS = 1500;
const PARTICLE_DURATION_MS = 700;

const COLOR = {
  activo: 0x00ff41,
  danado: 0xffd000,
  neutralizado: 0x992222,
  neutralizadoBlink: 0xff3333,
  missile: 0xff3b1f,
  trailNear: 0x00d4ff,
  trailFar: 0x063542,
  hpmCone: 0xff6600,
  hpmOrigin: 0x00ff41,
  detonationOuter: 0xaa66ff,
  detonationInner: 0x00d4ff,
  ground: 0x020804,
  grid: 0x0c3d18,
  gridCenter: 0x18a24a,
};

function worldToThree(field, wx, wy, altitude = 0) {
  return new THREE.Vector3(wx - field.width / 2, altitude, wy - field.height / 2);
}

function headingToRotationY(thetaDeg) {
  return -THREE.MathUtils.degToRad(thetaDeg);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function makeDroneGeometry() {
  const geo = new THREE.ConeGeometry(4, 12, 6);
  geo.rotateZ(-Math.PI / 2); // el cono apunta a lo largo de +X (rumbo 0)
  return geo;
}

function makeMissileGeometry() {
  const geo = new THREE.ConeGeometry(3, 16, 8);
  geo.rotateZ(-Math.PI / 2);
  return geo;
}

class TrailRibbon {
  constructor(scene) {
    this.points = [];
    this.geometry = new THREE.BufferGeometry();
    this.material = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9 });
    this.line = new THREE.Line(this.geometry, this.material);
    this.line.frustumCulled = false;
    scene.add(this.line);
  }

  push(vec3) {
    this.points.push(vec3.clone());
    if (this.points.length > TRAIL_MAX_POINTS) this.points.shift();
    this._rebuild();
  }

  _rebuild() {
    const n = this.points.length;
    if (n < 2) {
      this.geometry.setFromPoints([]);
      return;
    }
    const positions = new Float32Array(n * 3);
    const colors = new Float32Array(n * 3);
    const near = new THREE.Color(COLOR.trailNear);
    const far = new THREE.Color(COLOR.trailFar);
    for (let i = 0; i < n; i++) {
      const p = this.points[i];
      positions[i * 3] = p.x;
      positions[i * 3 + 1] = p.y;
      positions[i * 3 + 2] = p.z;
      const t = i / (n - 1); // 0 = más viejo, 1 = más nuevo
      const c = far.clone().lerp(near, t);
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }
    this.geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    this.geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  }

  dispose(scene) {
    scene.remove(this.line);
    this.geometry.dispose();
    this.material.dispose();
  }
}

const Render3D = (() => {
  let renderer, scene, camera, controls, canvas;
  let field = { width: 1000, height: 1000 };
  let droneMesh = null;
  let droneCapacity = 0;
  const droneRecords = new Map(); // id -> { x,y,angulo,estado, target:{x,y,angulo}, fx }
  const missileObjects = new Map(); // id -> { mesh, trail, x, y, target:{x,y} }
  const detonations = []; // { mesh1, mesh2, start }
  const cannonPulses = []; // { ring, start }
  const particleBursts = []; // { points: THREE.Points, start, velocities }
  let hpmConeMesh = null;
  let hpmOriginMesh = null;
  let heatmapPlane = null;
  let heatmapCanvas = null;
  let heatmapCtx = null;
  let heatmapTexture = null;
  let viewMode = "tactical";
  let slowMoUntil = 0;
  let lastTime = performance.now();
  let started = false;

  function init(canvasEl, initialField) {
    canvas = canvasEl;
    field = { ...initialField };

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    scene = new THREE.Scene();
    scene.background = new THREE.Color(COLOR.ground);
    scene.fog = new THREE.Fog(COLOR.ground, field.width * 0.9, field.width * 2.2);

    const maxDim = Math.max(field.width, field.height);
    camera = new THREE.PerspectiveCamera(50, 1, 1, maxDim * 6);
    setDefaultView();

    controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minDistance = maxDim * 0.15;
    controls.maxDistance = maxDim * 2.5;

    scene.add(new THREE.AmbientLight(0x445544, 1.2));
    const sun = new THREE.DirectionalLight(0xbfffcf, 0.6);
    sun.position.set(field.width * 0.3, maxDim * 0.6, field.height * 0.2);
    scene.add(sun);

    buildGround();
    buildHeatmapPlane();
    buildHpmCone();

    resize();
    started = true;
    requestAnimationFrame(loop);
  }

  function buildGround() {
    const planeGeo = new THREE.PlaneGeometry(field.width, field.height);
    const planeMat = new THREE.MeshBasicMaterial({ color: COLOR.ground });
    const plane = new THREE.Mesh(planeGeo, planeMat);
    plane.rotation.x = -Math.PI / 2;
    scene.add(plane);

    const divisions = Math.max(4, Math.round(field.width / 50));
    const grid = new THREE.GridHelper(field.width, divisions, COLOR.gridCenter, COLOR.grid);
    grid.material.transparent = true;
    grid.material.opacity = 0.55;
    scene.add(grid);

    const borderGeo = new THREE.EdgesGeometry(new THREE.PlaneGeometry(field.width, field.height));
    const border = new THREE.LineSegments(
      borderGeo,
      new THREE.LineBasicMaterial({ color: COLOR.gridCenter, transparent: true, opacity: 0.5 })
    );
    border.rotation.x = -Math.PI / 2;
    border.position.y = 0.2;
    scene.add(border);
  }

  function buildHeatmapPlane() {
    heatmapCanvas = document.createElement("canvas");
    heatmapCanvas.width = 128;
    heatmapCanvas.height = 128;
    heatmapCtx = heatmapCanvas.getContext("2d");
    heatmapTexture = new THREE.CanvasTexture(heatmapCanvas);
    heatmapTexture.colorSpace = THREE.SRGBColorSpace;

    const geo = new THREE.PlaneGeometry(field.width, field.height);
    const mat = new THREE.MeshBasicMaterial({
      map: heatmapTexture,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
    });
    heatmapPlane = new THREE.Mesh(geo, mat);
    heatmapPlane.rotation.x = -Math.PI / 2;
    heatmapPlane.position.y = 0.6;
    heatmapPlane.visible = false;
    scene.add(heatmapPlane);
  }

  function buildHpmCone() {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3 * 22), 3));
    const mat = new THREE.MeshBasicMaterial({
      color: COLOR.hpmCone,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    hpmConeMesh = new THREE.Mesh(geo, mat);
    hpmConeMesh.position.y = 0.8;
    scene.add(hpmConeMesh);

    const originGeo = new THREE.SphereGeometry(6, 12, 12);
    const originMat = new THREE.MeshBasicMaterial({ color: COLOR.hpmOrigin });
    hpmOriginMesh = new THREE.Mesh(originGeo, originMat);
    scene.add(hpmOriginMesh);
  }

  function updateHpmCone(hpm) {
    if (!hpm) return;
    const origin = worldToThree(field, hpm.origen_x ?? 0, hpm.origen_y ?? 0, 0.8);
    hpmOriginMesh.position.set(origin.x, 6, origin.z);

    const dirDeg = hpm.direccion ?? 0;
    const aperture = hpm.apertura_cono ?? 30;
    const half = THREE.MathUtils.degToRad(aperture / 2);
    const dirRad = THREE.MathUtils.degToRad(dirDeg);
    const radius = Math.max(field.width, field.height) * 0.6;
    const segments = 20;

    const positions = [0, 0, 0];
    for (let i = 0; i <= segments; i++) {
      const a = -half + (2 * half * i) / segments;
      const worldAngle = dirRad + a;
      // mundo: x = cos, y = sin (convención matemática estándar) -> three: x = cos, z = sin
      positions.push(radius * Math.cos(worldAngle), 0, radius * Math.sin(worldAngle));
    }
    const flat = new Float32Array(positions);
    hpmConeMesh.geometry.setAttribute("position", new THREE.BufferAttribute(flat, 3));
    hpmConeMesh.geometry.computeVertexNormals();
    hpmConeMesh.position.set(origin.x, 0.8, origin.z);
  }

  function ensureDroneCapacity(n) {
    if (droneMesh && droneCapacity >= n) return;
    if (droneMesh) scene.remove(droneMesh);
    droneCapacity = Math.max(n, 64);
    const geo = makeDroneGeometry();
    const mat = new THREE.MeshStandardMaterial({ vertexColors: false, roughness: 0.6, metalness: 0.1 });
    droneMesh = new THREE.InstancedMesh(geo, mat, droneCapacity);
    droneMesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(droneCapacity * 3), 3);
    droneMesh.frustumCulled = false;
    scene.add(droneMesh);
  }

  const _matrix = new THREE.Matrix4();
  const _quat = new THREE.Quaternion();
  const _euler = new THREE.Euler();
  const _scale = new THREE.Vector3(1, 1, 1);
  const _pos = new THREE.Vector3();
  const _color = new THREE.Color();

  function updateDrones(drones, now) {
    if (!drones) return;
    ensureDroneCapacity(drones.length);

    const seen = new Set();
    let idx = 0;
    for (const d of drones) {
      seen.add(d.id);
      let rec = droneRecords.get(d.id);
      if (!rec) {
        rec = {
          x: d.x,
          y: d.y,
          angulo: d.angulo,
          estado: d.estado,
          fx: { state: "alive" },
        };
        droneRecords.set(d.id, rec);
      }

      if (rec.estado !== "neutralizado" && d.estado === "neutralizado") {
        rec.fx = { state: "falling", start: now };
        spawnParticleBurst(worldToThree(field, d.x, d.y, DRONE_ALTITUDE), 0xff3333);
      }
      rec.estado = d.estado;
      rec.target = { x: d.x, y: d.y, angulo: d.angulo };
      if (rec._smoothX === undefined) {
        rec._smoothX = d.x;
        rec._smoothY = d.y;
        rec._smoothAngulo = d.angulo;
      }

      idx += 1;
    }
    for (const id of [...droneRecords.keys()]) {
      if (!seen.has(id)) droneRecords.delete(id);
    }

    let i = 0;
    for (const rec of droneRecords.values()) {
      const smoothing = 0.25;
      rec._smoothX = lerp(rec._smoothX, rec.target.x, smoothing);
      rec._smoothY = lerp(rec._smoothY, rec.target.y, smoothing);
      rec._smoothAngulo = rec.target.angulo;

      let altitude = DRONE_ALTITUDE;
      let colorHex = COLOR[rec.estado] ?? COLOR.activo;
      let visible = true;

      if (rec.fx.state === "falling") {
        const t = Math.min(1, (now - rec.fx.start) / FALL_DURATION_MS);
        altitude = lerp(DRONE_ALTITUDE, 0.6, t);
        const blinkOn = Math.floor((now - rec.fx.start) / BLINK_PERIOD_MS) % 2 === 0;
        colorHex = blinkOn ? COLOR.neutralizadoBlink : COLOR.neutralizado;
        if (t >= 1) rec.fx.state = "settled";
      } else if (rec.fx.state === "settled") {
        altitude = 0.6;
        colorHex = COLOR.neutralizado;
      } else if (rec.estado === "danado") {
        const blinkOn = Math.floor(now / 220) % 2 === 0;
        visible = blinkOn;
      }

      _pos.set(rec._smoothX - field.width / 2, altitude, rec._smoothY - field.height / 2);
      _euler.set(0, headingToRotationY(rec._smoothAngulo), 0);
      _quat.setFromEuler(_euler);
      _scale.setScalar(visible ? 1 : 0.001);
      _matrix.compose(_pos, _quat, _scale);
      droneMesh.setMatrixAt(i, _matrix);

      _color.setHex(colorHex);
      droneMesh.setColorAt(i, _color);
      i += 1;
    }
    droneMesh.count = i;
    droneMesh.instanceMatrix.needsUpdate = true;
    if (droneMesh.instanceColor) droneMesh.instanceColor.needsUpdate = true;
  }

  function ensureMissile(m) {
    let obj = missileObjects.get(m.id);
    if (!obj) {
      const geo = makeMissileGeometry();
      const mat = new THREE.MeshBasicMaterial({ color: COLOR.missile });
      const mesh = new THREE.Mesh(geo, mat);
      scene.add(mesh);
      obj = { mesh, trail: new TrailRibbon(scene), x: m.x, y: m.y };
      missileObjects.set(m.id, obj);
    }
    return obj;
  }

  function updateMissiles(missiles) {
    if (!missiles) return;
    const seen = new Set();

    for (const m of missiles) {
      seen.add(m.id);

      if (m.estado === "destruido") continue;

      const obj = ensureMissile(m);
      obj.x = m.x;
      obj.y = m.y;

      if (m.estado === "detonado") {
        if (!obj.detonated) {
          obj.detonated = true;
          triggerDetonation(m.x, m.y, m.radio_efecto || 100);
          obj.trail.dispose(scene);
          scene.remove(obj.mesh);
        }
        continue;
      }

      const pos = worldToThree(field, m.x, m.y, MISSILE_ALTITUDE);
      obj.mesh.position.copy(pos);
      obj.mesh.rotation.y = headingToRotationY(m.angulo || 0);
      obj.trail.push(pos);
    }

    for (const [id, obj] of [...missileObjects.entries()]) {
      const stillActive = seen.has(id);
      const wasDetonating = obj.detonated;
      if (!stillActive || (wasDetonating && !obj.mesh.parent)) {
        if (obj.mesh.parent) scene.remove(obj.mesh);
        obj.trail.dispose(scene);
        missileObjects.delete(id);
      }
    }
  }

  function triggerDetonation(wx, wy, radius) {
    const pos = worldToThree(field, wx, wy, 1.2);
    const ring1 = new THREE.Mesh(
      new THREE.RingGeometry(0.1, radius, 40),
      new THREE.MeshBasicMaterial({ color: COLOR.detonationOuter, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false })
    );
    ring1.rotation.x = -Math.PI / 2;
    ring1.position.copy(pos);
    scene.add(ring1);

    const ring2 = new THREE.Mesh(
      new THREE.RingGeometry(0.1, radius * 0.7, 40),
      new THREE.MeshBasicMaterial({ color: COLOR.detonationInner, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false })
    );
    ring2.rotation.x = -Math.PI / 2;
    ring2.position.copy(pos).setY(pos.y + 0.3);
    scene.add(ring2);

    detonations.push({ ring1, ring2, start: performance.now(), radius });
    slowMoUntil = performance.now() + 900;
  }

  const CANNON_PULSE_DURATION_MS = 900;

  function triggerCannonPulse(wx, wy) {
    const pos = worldToThree(field, wx, wy, 1.0);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.1, 55, 32),
      new THREE.MeshBasicMaterial({ color: 0xff8800, transparent: true, opacity: 0.75, side: THREE.DoubleSide, depthWrite: false })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.copy(pos);
    scene.add(ring);
    cannonPulses.push({ ring, start: performance.now() });
  }

  function spawnParticleBurst(originVec3, colorHex) {
    const count = 18;
    const positions = new Float32Array(count * 3);
    const velocities = [];
    for (let i = 0; i < count; i++) {
      positions[i * 3] = originVec3.x;
      positions[i * 3 + 1] = originVec3.y;
      positions[i * 3 + 2] = originVec3.z;
      const theta = Math.random() * Math.PI * 2;
      const speed = 20 + Math.random() * 40;
      velocities.push(new THREE.Vector3(Math.cos(theta) * speed, 20 + Math.random() * 30, Math.sin(theta) * speed));
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.PointsMaterial({ color: colorHex, size: 3, transparent: true, opacity: 1 });
    const points = new THREE.Points(geo, mat);
    scene.add(points);
    particleBursts.push({ points, velocities, start: performance.now(), origin: originVec3.clone() });
  }

  function updateEffects(now, dtSec) {
    for (let i = detonations.length - 1; i >= 0; i--) {
      const d = detonations[i];
      const t = (now - d.start) / DETONATION_DURATION_MS;
      if (t >= 1) {
        scene.remove(d.ring1);
        scene.remove(d.ring2);
        d.ring1.geometry.dispose();
        d.ring2.geometry.dispose();
        detonations.splice(i, 1);
        continue;
      }
      const scale = lerp(0.05, 1, t);
      d.ring1.scale.setScalar(scale);
      d.ring2.scale.setScalar(scale * 0.85);
      d.ring1.material.opacity = 0.55 * (1 - t);
      d.ring2.material.opacity = 0.6 * (1 - t);
    }

    for (let i = cannonPulses.length - 1; i >= 0; i--) {
      const p = cannonPulses[i];
      const t = (now - p.start) / CANNON_PULSE_DURATION_MS;
      if (t >= 1) {
        scene.remove(p.ring);
        p.ring.geometry.dispose();
        p.ring.material.dispose();
        cannonPulses.splice(i, 1);
        continue;
      }
      p.ring.scale.setScalar(lerp(0.05, 1, t));
      p.ring.material.opacity = 0.75 * (1 - t);
    }

    for (let i = particleBursts.length - 1; i >= 0; i--) {
      const p = particleBursts[i];
      const t = (now - p.start) / PARTICLE_DURATION_MS;
      if (t >= 1) {
        scene.remove(p.points);
        p.points.geometry.dispose();
        particleBursts.splice(i, 1);
        continue;
      }
      const posAttr = p.points.geometry.getAttribute("position");
      for (let j = 0; j < p.velocities.length; j++) {
        const v = p.velocities[j];
        posAttr.array[j * 3] = p.origin.x + v.x * t;
        posAttr.array[j * 3 + 1] = p.origin.y + v.y * t - 40 * t * t;
        posAttr.array[j * 3 + 2] = p.origin.z + v.z * t;
      }
      posAttr.needsUpdate = true;
      p.points.material.opacity = 1 - t;
    }
  }

  function updateHeatmap(heatmap) {
    if (!heatmapCtx || !heatmap?.values?.length) return;
    const grid = heatmap.values;
    const rows = grid.length;
    const cols = grid[0].length;
    const max = heatmap.max || 1;
    heatmapCanvas.width = cols;
    heatmapCanvas.height = rows;
    const img = heatmapCtx.createImageData(cols, rows);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = grid[r][c] / max;
        const i = (r * cols + c) * 4;
        img.data[i] = Math.floor(v * 255);
        img.data[i + 1] = Math.floor(v * 160);
        img.data[i + 2] = 20;
        img.data[i + 3] = Math.floor(60 + v * 195);
      }
    }
    heatmapCtx.putImageData(img, 0, 0);
    heatmapTexture.needsUpdate = true;
  }

  function updateSnapshot(snap) {
    if (!started) return;
    if (snap.field && (snap.field.width !== field.width || snap.field.height !== field.height)) {
      field = { ...snap.field };
    }
    const now = performance.now();
    if (snap.drones) updateDrones(snap.drones, now);
    if (snap.missiles) updateMissiles(snap.missiles.misiles);
    if (snap.hpm) updateHpmCone(snap.hpm);
    if (viewMode === "physical" && snap.analytics?.heatmap) updateHeatmap(snap.analytics.heatmap);
  }

  function setViewMode(mode) {
    viewMode = mode;
    if (heatmapPlane) heatmapPlane.visible = mode === "physical";
  }

  function setDefaultView() {
    const maxDim = Math.max(field.width, field.height);
    camera.position.set(0, maxDim * 0.85, maxDim * 0.65);
    camera.lookAt(0, 0, 0);
    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }

  function resetCamera() {
    // Vista cenital real (top-down), distinta de la vista 3/4 por defecto.
    // Offset en Z (~2% de la altura) para evitar el gimbal-lock de lookAt
    // cuando la cámara queda exactamente sobre el eje Y (roll indefinido).
    const maxDim = Math.max(field.width, field.height);
    const height = maxDim * 1.3;
    camera.position.set(0, height, height * 0.02);
    camera.up.set(0, 0, -1);
    camera.lookAt(0, 0, 0);
    camera.up.set(0, 1, 0);
    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }

  function resize() {
    if (!renderer || !canvas) return;
    const wrapper = canvas.parentElement;
    const width = wrapper.clientWidth || 800;
    const height = Math.round(width / (4 / 3));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function loop() {
    requestAnimationFrame(loop);
    const now = performance.now();
    let dtSec = (now - lastTime) / 1000;
    lastTime = now;
    if (now < slowMoUntil) dtSec *= 0.15; // cámara lenta local tras una detonación

    updateEffects(now, dtSec);
    controls.update();
    renderer.render(scene, camera);
  }

  return { init, updateSnapshot, setViewMode, resetCamera, resize, triggerCannonPulse };
})();

window.Render3D = Render3D;
window.addEventListener("resize", () => Render3D.resize());
