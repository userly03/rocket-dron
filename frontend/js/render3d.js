/**
 * Render 3D del mapa táctico (Three.js). Reemplaza el canvas 2D.
 * Expone window.Render3D con una API mínima que consume script.js (script clásico).
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const FALLBACK_DRONE_ALTITUDE = 100;
const FALLBACK_MISSILE_ALTITUDE = 100;
// 150 puntos ≈ 2.5s de historial a 60Hz — cubre el vuelo completo de un
// misil típico (suele detonar en 1-1.5s); con menos historial, el rastro
// solo mostraba la fase final del guiado (donde la corrección es más
// brusca por diseño de la navegación proporcional), haciendo ver como un
// "codo" lo que en realidad es una curva suave de principio a fin.
const TRAIL_MAX_POINTS = 150;
const FALL_DURATION_MS = 1100;
const BLINK_PERIOD_MS = 140;
const DETONATION_DURATION_MS = 1500;
const PARTICLE_DURATION_MS = 700;
const LIGHTNING_DURATION_MS = 220;
const LIGHTNING_BOLT_COUNT = 10;
const LIGHTNING_FLICKER_COUNT = 3;
// Radio de referencia donde el SNR cruza el umbral de detección (ver
// RADAR_SNR_THRESHOLD_DB en config.py / docs/FISICA_Y_MATEMATICA.md) —
// puramente visual, no recalcula la ecuación de radar en el cliente.
const RADAR_RANGE_M = 600;

const COLOR = {
  activo: 0x00ff41,
  activoBlindado: 0x00c8ff,
  danado: 0xffd000,
  neutralizado: 0x992222,
  neutralizadoBlink: 0xff3333,
  interferido: 0x9955ff,
  noDetectado: 0x1a3d24,
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
  const lightningBolts = []; // { line, start }
  let hpmConeMesh = null;
  let hpmOriginMesh = null;
  let radarRingMesh = null;
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

    const radarGeo = new THREE.RingGeometry(RADAR_RANGE_M - 3, RADAR_RANGE_M, 64);
    const radarMat = new THREE.MeshBasicMaterial({
      color: COLOR.activoBlindado,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    radarRingMesh = new THREE.Mesh(radarGeo, radarMat);
    radarRingMesh.rotation.x = -Math.PI / 2;
    radarRingMesh.position.y = 0.5;
    scene.add(radarRingMesh);
  }

  function updateHpmCone(hpm) {
    if (!hpm) return;
    const origin = worldToThree(field, hpm.origen_x ?? 0, hpm.origen_y ?? 0, 0.8);
    hpmOriginMesh.position.set(origin.x, 6, origin.z);
    if (radarRingMesh) radarRingMesh.position.set(origin.x, 0.5, origin.z);

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
  const _missileQuatYaw = new THREE.Quaternion();
  const _missileQuatPitch = new THREE.Quaternion();
  const _yAxis = new THREE.Vector3(0, 1, 0);
  const _zAxis = new THREE.Vector3(0, 0, 1);

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
          z: d.z ?? FALLBACK_DRONE_ALTITUDE,
          angulo: d.angulo,
          estado: d.estado,
          fx: { state: "alive" },
        };
        droneRecords.set(d.id, rec);
      }

      if (rec.estado !== "neutralizado" && d.estado === "neutralizado") {
        rec.fx = { state: "falling", start: now, fallFromZ: rec._smoothZ ?? d.z ?? FALLBACK_DRONE_ALTITUDE };
        spawnParticleBurst(worldToThree(field, d.x, d.y, d.z ?? FALLBACK_DRONE_ALTITUDE), 0xff3333);
      }
      rec.estado = d.estado;
      rec.blindaje = d.blindaje;
      rec.detectado = d.detectado !== false;
      rec.target = { x: d.x, y: d.y, z: d.z ?? FALLBACK_DRONE_ALTITUDE, angulo: d.angulo };
      if (rec._smoothX === undefined) {
        rec._smoothX = d.x;
        rec._smoothY = d.y;
        rec._smoothZ = d.z ?? FALLBACK_DRONE_ALTITUDE;
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
      rec._smoothZ = lerp(rec._smoothZ, rec.target.z, smoothing);
      rec._smoothAngulo = rec.target.angulo;

      let altitude = rec._smoothZ;
      let colorHex = COLOR[rec.estado] ?? COLOR.activo;
      if (rec.estado === "activo" && rec.blindaje === "blindado") colorHex = COLOR.activoBlindado;
      if (rec.detectado === false) colorHex = COLOR.noDetectado;
      let visible = true;

      if (rec.fx.state === "falling") {
        const t = Math.min(1, (now - rec.fx.start) / FALL_DURATION_MS);
        altitude = lerp(rec.fx.fallFromZ, 0.6, t);
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
          triggerDetonation(m.x, m.y, m.radio_efecto || 100, m.z ?? FALLBACK_MISSILE_ALTITUDE);
          obj.trail.dispose(scene);
          scene.remove(obj.mesh);
        }
        continue;
      }

      const pos = worldToThree(field, m.x, m.y, m.z ?? FALLBACK_MISSILE_ALTITUDE);

      let pitch = 0;
      if (obj.prevPos) {
        const dz = pos.y - obj.prevPos.y;
        const dHoriz = Math.hypot(pos.x - obj.prevPos.x, pos.z - obj.prevPos.z);
        pitch = Math.atan2(dz, Math.max(dHoriz, 1e-6));
      }
      obj.prevPos = pos.clone();

      _missileQuatYaw.setFromAxisAngle(_yAxis, headingToRotationY(m.angulo || 0));
      _missileQuatPitch.setFromAxisAngle(_zAxis, pitch);
      obj.mesh.quaternion.copy(_missileQuatYaw).multiply(_missileQuatPitch);
      obj.mesh.position.copy(pos);
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

  // Rayo de plasma/EMP: una polilínea quebrada (jitter aleatorio) desde el
  // centro de detonación hacia afuera — representa visualmente la descarga
  // eléctrica del pulso, no tiene significado físico propio (el campo E real
  // ya está representado por la esfera; esto es puramente estético).
  function makeLightningBolt(center, length, colorHex) {
    const segments = 5 + Math.floor(Math.random() * 3);
    const dir = new THREE.Vector3(Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random() * 2 - 1).normalize();
    const points = [center.clone()];
    let current = center.clone();
    for (let i = 0; i < segments; i++) {
      const step = dir.clone().multiplyScalar(length / segments);
      const jitter = new THREE.Vector3(
        (Math.random() - 0.5) * length * 0.35,
        (Math.random() - 0.5) * length * 0.35,
        (Math.random() - 0.5) * length * 0.35
      );
      current = current.clone().add(step).add(jitter);
      points.push(current);
    }
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 1 });
    const line = new THREE.Line(geo, mat);
    line.frustumCulled = false;
    return line;
  }

  function spawnLightningFlicker(center, radius) {
    const now = performance.now();
    const colors = [0xffffff, COLOR.trailNear, COLOR.detonationInner];
    for (let i = 0; i < LIGHTNING_BOLT_COUNT; i++) {
      const colorHex = colors[i % colors.length];
      const length = radius * (0.4 + Math.random() * 0.5);
      const line = makeLightningBolt(center, length, colorHex);
      scene.add(line);
      lightningBolts.push({ line, start: now });
    }
  }

  function triggerDetonation(wx, wy, radius, altitude = 1.2) {
    // El pulso HPM del misil se propaga isotrópicamente en 3D (ver el término
    // 4πr² del modelo Friis en power_density()) — el volumen afectado es una
    // esfera centrada en el punto real de detonación (con su altitud), no un
    // disco apoyado en el suelo.
    const center = worldToThree(field, wx, wy, altitude);
    spawnLightningFlicker(center, radius);

    const sphereOuter = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 16),
      new THREE.MeshBasicMaterial({ color: COLOR.detonationOuter, transparent: true, opacity: 0.28, depthWrite: false })
    );
    sphereOuter.position.copy(center);
    scene.add(sphereOuter);

    const sphereWire = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 16),
      new THREE.MeshBasicMaterial({ color: COLOR.detonationInner, wireframe: true, transparent: true, opacity: 0.5, depthWrite: false })
    );
    sphereWire.position.copy(center);
    scene.add(sphereWire);

    // Anillo de choque proyectado sobre el terreno (huella visual del punto
    // de detonación en el suelo), independiente de la esfera del campo real.
    const groundPos = worldToThree(field, wx, wy, 1.0);
    const groundRing = new THREE.Mesh(
      new THREE.RingGeometry(0.1, radius, 40),
      new THREE.MeshBasicMaterial({ color: COLOR.detonationOuter, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false })
    );
    groundRing.rotation.x = -Math.PI / 2;
    groundRing.position.copy(groundPos);
    scene.add(groundRing);

    const start = performance.now();
    detonations.push({
      sphereOuter,
      sphereWire,
      groundRing,
      start,
      radius,
      center,
      flickersLeft: LIGHTNING_FLICKER_COUNT - 1,
      nextFlickerAt: start + 150,
    });
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

  // Confirmación visual de impacto: el motor evalúa la probabilidad de daño
  // para cada dron dentro del radio de efecto, pero la mayoría de esos
  // "afectados" sobreviven (soft-kill probabilístico, no una zona de muerte
  // garantizada) — sin esto, un impacto que no derriba a nadie no se ve en
  // pantalla, y parece que la explosión "no hizo nada" aunque sí se evaluó.
  // Los neutralizados ya tienen su propia animación de caída; esto es solo
  // para los que sobrevivieron al pulso.
  function flashHits(impactos) {
    if (!impactos) return;
    for (const imp of impactos) {
      if (imp.neutralizado) continue;
      const rec = droneRecords.get(imp.drone_id);
      if (!rec) continue;
      const pos = new THREE.Vector3(
        rec._smoothX - field.width / 2,
        rec._smoothZ ?? FALLBACK_DRONE_ALTITUDE,
        rec._smoothY - field.height / 2
      );
      spawnParticleBurst(pos, 0xffffff);
    }
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
        scene.remove(d.sphereOuter);
        scene.remove(d.sphereWire);
        scene.remove(d.groundRing);
        d.sphereOuter.geometry.dispose();
        d.sphereWire.geometry.dispose();
        d.groundRing.geometry.dispose();
        detonations.splice(i, 1);
        continue;
      }
      const sphereScale = lerp(0.05, 1, t) * d.radius;
      d.sphereOuter.scale.setScalar(sphereScale);
      d.sphereWire.scale.setScalar(sphereScale * 0.97);
      d.sphereOuter.material.opacity = 0.28 * (1 - t);
      d.sphereWire.material.opacity = 0.5 * (1 - t);

      const ringScale = lerp(0.05, 1, t);
      d.groundRing.scale.setScalar(ringScale);
      d.groundRing.material.opacity = 0.35 * (1 - t);

      if (d.flickersLeft > 0 && now >= d.nextFlickerAt) {
        spawnLightningFlicker(d.center, d.radius);
        d.flickersLeft -= 1;
        d.nextFlickerAt = now + 150;
      }
    }

    for (let i = lightningBolts.length - 1; i >= 0; i--) {
      const b = lightningBolts[i];
      const t = (now - b.start) / LIGHTNING_DURATION_MS;
      if (t >= 1) {
        scene.remove(b.line);
        b.line.geometry.dispose();
        b.line.material.dispose();
        lightningBolts.splice(i, 1);
        continue;
      }
      b.line.material.opacity = 1 - t;
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

  return { init, updateSnapshot, setViewMode, resetCamera, resize, triggerCannonPulse, flashHits };
})();

window.Render3D = Render3D;
window.addEventListener("resize", () => Render3D.resize());
