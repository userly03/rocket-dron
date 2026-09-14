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

// Paleta de sala de operaciones (migrada desde el verde neón original —
// ver docs/propuesta_identidad_visual.html y frontend/css/style.css para
// el racional completo). Los estados del dron conservan el MISMO mapeo
// semántico de antes (activo=verde, neutralizado=rojo, riesgo=ámbar,
// interferido=violeta, misil/pista=verde azulado) — lo que cambia es que
// están desaturados/atenuados a un registro serio en vez de neón, y que
// hpmOrigin ya no comparte el verde de "activo": es NUESTRO sistema, así
// que usa el mismo azul de acento que la interfaz (nav, botones), no un
// color de estado del enjambre.
const COLOR = {
  activo: 0x4caf6e,
  activoBlindado: 0x5bb3c7,
  riesgoLatente: 0xe0a23d,
  track: 0x6f93b0,
  danado: 0xd9a53d,
  neutralizado: 0x8f3a34,
  neutralizadoBlink: 0xe0574f,
  interferido: 0x9a7fd1,
  noDetectado: 0x1c2128,
  missile: 0xd9573a,
  trailNear: 0x3fb8ae,
  trailFar: 0x0d2a2c,
  hpmCone: 0xd9772e,
  hpmOrigin: 0x4f8fc4,
  // Misión ofensiva: un dron que LLEGÓ al objetivo — brecha de la
  // defensa, no una baja (por eso no reusa neutralizado/rojo). Mismo
  // naranja que el cono/pulso del cañón: "esto detonó/impactó algo",
  // deliberadamente distinto del violeta de interferido y del rojo de
  // neutralizado para que las tres causas de "un dron dejó de volar" se
  // lean distintas de un vistazo.
  objetivoAlcanzado: 0xd9772e,
  detonationOuter: 0x9a7fd1,
  detonationInner: 0x3fb8ae,
  ground: 0x0a0d11,
  grid: 0x1c232b,
  gridCenter: 0x2d4a63,
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
  let radarPingMesh = null;
  let trackLinesMesh = null;
  let trackGhostMesh = null;
  let showTracks = false;
  let wtaMarkersGroup = null;
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

    // Antes tenían tinte verde (0x445544/0xbfffcf) — se filtraba a CADA
    // material de la escena, no solo a los que ya son verdes a propósito
    // (activo/pasto). Neutro/frío en su lugar, consistente con el resto
    // de la migración de paleta.
    scene.add(new THREE.AmbientLight(0x454b54, 1.2));
    const sun = new THREE.DirectionalLight(0xdce8f2, 0.6);
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

    // "Ping" de barrido (P2-G): el radar de este proyecto revisita TODO el
    // enjambre a la vez cada RADAR_REVISITA_S segundos (no un haz rotando
    // que barre en bearing) — un anillo giratorio sería más lindo pero
    // mentiría sobre el modelo. En cambio, un anillo que se EXPANDE desde
    // el origen y se desvanece durante cada ciclo comunica lo que
    // realmente pasa: qué tan viejo es el dato (recién refrescado = chico
    // y brillante; a punto de refrescar de nuevo = llega al borde y
    // desaparece). Geometría placeholder, real en updateRadarPing().
    const pingGeo = new THREE.RingGeometry(0.1, 0.2, 48);
    const pingMat = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.5,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    radarPingMesh = new THREE.Mesh(pingGeo, pingMat);
    radarPingMesh.rotation.x = -Math.PI / 2;
    radarPingMesh.position.y = 0.55;
    scene.add(radarPingMesh);

    // Tracks del radar (P2-G): línea entre la posición REAL de un dron
    // detectado y la posición ESTIMADA por el filtro (con la que apunta el
    // misil) — solo visible cuando se activa el toggle "Mostrar tracks", y
    // solo para drones donde la diferencia es apreciable.
    const trackGeo = new THREE.BufferGeometry();
    trackGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(0), 3));
    const trackMat = new THREE.LineBasicMaterial({
      color: COLOR.track, transparent: true, opacity: 0.7,
    });
    trackLinesMesh = new THREE.LineSegments(trackGeo, trackMat);
    trackLinesMesh.visible = false;
    scene.add(trackLinesMesh);

    const ghostGeo = new THREE.BufferGeometry();
    ghostGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(0), 3));
    const ghostMat = new THREE.PointsMaterial({ color: COLOR.track, size: 5, transparent: true, opacity: 0.9 });
    trackGhostMesh = new THREE.Points(ghostGeo, ghostMat);
    trackGhostMesh.visible = false;
    scene.add(trackGhostMesh);
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

  function updateRadarPing(radar) {
    if (!radar || !radarPingMesh) return;
    const origin = worldToThree(field, radar.origen_x ?? 0, radar.origen_y ?? 0, 0.55);
    radarPingMesh.position.set(origin.x, 0.55, origin.z);
    const fase = Math.max(0, Math.min(1, radar.fase_barrido ?? 0));
    const outer = Math.max(2, RADAR_RANGE_M * fase);
    const inner = Math.max(0.5, outer - 4);
    radarPingMesh.geometry.dispose();
    radarPingMesh.geometry = new THREE.RingGeometry(inner, outer, 48);
    // Se desvanece rápido (curva cuadrática, no lineal) para que se lea
    // como un pulso que muere, no como un anillo que se confunde con el
    // límite de alcance estático (mismo radio máximo, otro color/opacidad).
    radarPingMesh.material.opacity = 0.7 * Math.pow(1 - fase, 1.6);
  }

  const _trackA = new THREE.Vector3();
  const _trackB = new THREE.Vector3();
  const TRACK_ERROR_MIN_M = 2.0;

  function updateTracks(drones) {
    if (!trackLinesMesh || !trackGhostMesh) return;
    if (!showTracks || !drones) {
      trackLinesMesh.visible = false;
      trackGhostMesh.visible = false;
      return;
    }
    const linePositions = [];
    const ghostPositions = [];
    for (const d of drones) {
      if (d.track_x == null || d.estado === "neutralizado" || d.detectado === false) continue;
      const dx = d.track_x - d.x;
      const dy = d.track_y - d.y;
      if (Math.hypot(dx, dy) < TRACK_ERROR_MIN_M) continue;
      _trackA.copy(worldToThree(field, d.x, d.y, (d.z ?? FALLBACK_DRONE_ALTITUDE)));
      _trackB.copy(worldToThree(field, d.track_x, d.track_y, (d.track_z ?? d.z ?? FALLBACK_DRONE_ALTITUDE)));
      linePositions.push(_trackA.x, _trackA.y, _trackA.z, _trackB.x, _trackB.y, _trackB.z);
      ghostPositions.push(_trackB.x, _trackB.y, _trackB.z);
    }
    trackLinesMesh.geometry.dispose();
    trackLinesMesh.geometry = new THREE.BufferGeometry();
    trackLinesMesh.geometry.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
    trackGhostMesh.geometry.dispose();
    trackGhostMesh.geometry = new THREE.BufferGeometry();
    trackGhostMesh.geometry.setAttribute("position", new THREE.Float32BufferAttribute(ghostPositions, 3));
    trackLinesMesh.visible = linePositions.length > 0;
    trackGhostMesh.visible = ghostPositions.length > 0;
  }

  // Plan óptimo (P3-A, WTA): un anillo por cluster asignado, coloreado
  // según el arma sugerida — cañón (naranja, mismo tono que su cono de
  // efecto) o misil (cian, mismo tono que su marcador). Puramente
  // informativo hasta que el usuario confirma "Ejecutar plan" desde la UI.
  function setWtaPlan(plan) {
    if (wtaMarkersGroup) {
      scene.remove(wtaMarkersGroup);
      wtaMarkersGroup.traverse((obj) => { obj.geometry?.dispose?.(); obj.material?.dispose?.(); });
      wtaMarkersGroup = null;
    }
    if (!plan || !plan.asignacion?.length) return;
    wtaMarkersGroup = new THREE.Group();
    // Un anillo por (cluster, arma) — con presupuesto abundante y pocos
    // clusters, la asignación puede apilar muchos disparos del mismo tipo
    // sobre el mismo grupo; dibujarlos todos superpuestos no agrega nada.
    const dibujados = new Set();
    const anillosPorCluster = new Map();
    for (const a of plan.asignacion) {
      const key = `${a.cluster_id}:${a.tipo}`;
      if (dibujados.has(key)) continue;
      dibujados.add(key);
      const ringIdx = anillosPorCluster.get(a.cluster_id) ?? 0;
      anillosPorCluster.set(a.cluster_id, ringIdx + 1);
      const [cx, cy] = a.cluster_centroide;
      const pos = worldToThree(field, cx, cy, 1.2);
      const radioBase = Math.min(60, 16 + a.cluster_tamano * 4);
      // Si hay dos armas sobre el mismo cluster, el segundo anillo va un
      // poco más afuera para que ambos se vean (no uno tapando al otro).
      const radio = radioBase + ringIdx * 10;
      // COLOR.missile (el color del PROYECTIL en vuelo) es rojo-anaranjado,
      // casi idéntico a COLOR.hpmCone — inútil para distinguir en este
      // anillo. Se usa el cian de la leyenda ("Misil HPM" = activoBlindado)
      // en su lugar, que sí contrasta.
      const color = a.tipo === "canion" ? COLOR.hpmCone : COLOR.activoBlindado;
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(radio - 2, radio, 32),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }),
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(pos.x, 1.2, pos.z);
      wtaMarkersGroup.add(ring);
    }
    scene.add(wtaMarkersGroup);
  }

  function setShowTracks(value) {
    showTracks = !!value;
    if (!showTracks) {
      trackLinesMesh.visible = false;
      trackGhostMesh.visible = false;
    }
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
  const _riesgoColor = new THREE.Color(COLOR.riesgoLatente);
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
        spawnParticleBurst(worldToThree(field, d.x, d.y, d.z ?? FALLBACK_DRONE_ALTITUDE), COLOR.neutralizadoBlink);
      }
      // Misión ofensiva: transición única alive → reached, aunque el
      // snapshot siga trayendo objetivo_alcanzado=true en cada tick
      // subsiguiente (no queremos relanzar el estallido cada frame).
      if (!rec.objetivoAlcanzado && d.objetivo_alcanzado) {
        rec.fx = { state: "reached" };
        spawnParticleBurst(worldToThree(field, d.x, d.y, d.z ?? FALLBACK_DRONE_ALTITUDE), COLOR.objetivoAlcanzado);
      }
      rec.objetivoAlcanzado = d.objetivo_alcanzado === true;
      rec.estado = d.estado;
      rec.blindaje = d.blindaje;
      rec.detectado = d.detectado !== false;
      rec.riesgoSeveridad = d.riesgo_latente_severidad ?? 0;
      rec.subsistemaEnRiesgo = d.subsistema_en_riesgo ?? null;
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
      } else if (rec.fx.state === "reached") {
        // Se queda exactamente donde llegó — a diferencia de "falling"
        // (neutralizado) no cae al piso: cumplió su misión, no lo
        // derribaron. La altura/posición ya dejaron de actualizarse
        // (Swarm excluye a los drones con objetivo_alcanzado del loop de
        // movimiento), así que esto solo fija el color.
        colorHex = COLOR.objetivoAlcanzado;
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
      // Riesgo latente (P2-D): el dron impactado entró en una ventana de
      // vulnerabilidad transitoria — puede recuperarse o fallar más tarde.
      // Se comunica con un parpadeo ámbar superpuesto al color normal (no lo
      // reemplaza) cuya frecuencia escala con la severidad, en vez de un
      // estado discreto más — la muerte diferida deja de verse instantánea
      // e inexplicable. No se aplica mientras cae/ya cayó (ya tiene su
      // propio efecto) ni si está "no detectado" (ese color ya domina).
      if (
        rec.riesgoSeveridad > 0 &&
        rec.fx.state !== "falling" && rec.fx.state !== "settled" &&
        rec.detectado !== false
      ) {
        const periodMs = lerp(1600, 400, rec.riesgoSeveridad);
        const wave = (Math.sin((now % periodMs) / periodMs * Math.PI * 2) + 1) / 2;
        _color.lerp(_riesgoColor, 0.15 + 0.55 * wave);
      }
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
      new THREE.MeshBasicMaterial({ color: COLOR.hpmCone, transparent: true, opacity: 0.75, side: THREE.DoubleSide, depthWrite: false })
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
    if (snap.drones) updateTracks(snap.drones);
    if (snap.missiles) updateMissiles(snap.missiles.misiles);
    if (snap.hpm) updateHpmCone(snap.hpm);
    if (snap.radar) updateRadarPing(snap.radar);
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

  return { init, updateSnapshot, setViewMode, resetCamera, resize, triggerCannonPulse, flashHits, setShowTracks, setWtaPlan };
})();

window.Render3D = Render3D;
window.addEventListener("resize", () => Render3D.resize());
