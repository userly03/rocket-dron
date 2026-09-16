/**
 * Render 3D del mapa táctico (Three.js). Reemplaza el canvas 2D.
 * Expone window.Render3D con una API mínima que consume script.js (script clásico).
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

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
  // Tono propio, distinto del ámbar de riesgoLatente: un dron puede estar
  // "dañado" (estado_salud persistente) Y en riesgo latente (transitorio,
  // ver entrar_en_riesgo_latente en drone.py) al mismo tiempo — con casi
  // el mismo hex que antes (0xd9a53d vs 0xe0a23d) el parpadeo ámbar de
  // riesgo era invisible sobre el color base. Ver --status-damaged en
  // style.css (mismo hex).
  danado: 0x9c6b3e,
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

// PRNG determinista chico (mulberry32) — el disperso de árboles necesita
// ser reproducible entre recargas de la página (misma semilla que los
// scripts de Blender, 2026) sin arrastrar una librería para esto.
function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Ruido "valor" 2D suave: grilla de valores pseudoaleatorios (mulberry32)
// interpolados con smoothstep — no es Perlin/simplex de verdad, pero para
// colinas suaves alcanza y evita sumar una librería externa solo para
// esto. Devuelve una función (u, v) -> [0,1] con u, v en [0,1).
// `periodico`: si es true, el borde derecho/inferior de la grilla se
// fuerza a repetir el izquierdo/superior (topología de toro) para que la
// función dé el MISMO valor en u=0 y u=1 — sin esto, alturaTerreno() no
// puede tilear esta función con "% 1" sin que quede una costura: los
// valores a ambos lados de un límite de tile vienen de celdas de grilla
// no relacionadas, y el salto ahí resulta ~10x más empinado que la
// pendiente típica del ruido (bug real, encontrado con una auditoría
// numérica antes de comitear, no a ojo — ver docs/SEGUIMIENTO_SESION.md
// §9.10).
function crearRuidoValor(seed, gridSize, periodico = false) {
  const rng = mulberry32(seed);
  const grid = [];
  for (let i = 0; i <= gridSize; i++) {
    const fila = [];
    for (let j = 0; j <= gridSize; j++) fila.push(rng());
    grid.push(fila);
  }
  if (periodico) {
    for (let j = 0; j <= gridSize; j++) grid[gridSize][j] = grid[0][j];
    for (let i = 0; i <= gridSize; i++) grid[i][gridSize] = grid[i][0];
  }
  const suavizar = (t) => t * t * (3 - 2 * t);
  return function (u, v) {
    const gx = Math.min(Math.max(u, 0), 0.999999) * gridSize;
    const gy = Math.min(Math.max(v, 0), 0.999999) * gridSize;
    const x0 = Math.floor(gx);
    const y0 = Math.floor(gy);
    const tx = suavizar(gx - x0);
    const ty = suavizar(gy - y0);
    const a = lerp(grid[x0][y0], grid[x0 + 1][y0], tx);
    const b = lerp(grid[x0][y0 + 1], grid[x0 + 1][y0 + 1], tx);
    return lerp(a, b, ty);
  };
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

  // Relieve del terreno (colinas suaves): dos octavas de ruido — una de
  // longitud de onda grande (colinas) y otra más fina encima (ondulación)
  // — generadas UNA vez con semillas fijas (reproducible entre recargas,
  // como el disperso de árboles). PURAMENTE VISUAL: la física del juego
  // (línea de vista, movimiento, radar) sigue siendo 2D sobre el plano
  // x/y — mismo criterio que la simplificación ya documentada en
  // hpm_engine.linea_de_vista_bloqueada (no modelar altura de obstáculo
  // porque no hay un dato medido para eso). Agregar relieve real a la
  // física del enjambre/vehículo no fue pedido y sería un cambio de
  // alcance mucho mayor (habría que decidir qué significa "línea de
  // vista bloqueada por una colina", pendiente ladeante, etc.).
  const ruidoColinas = crearRuidoValor(11, 6); // no se tilea, no hace falta periódico
  const ruidoOndulacion = crearRuidoValor(23, 17, /* periodico */ true); // sí se tilea ×3 (ver alturaTerreno)
  const ALTURA_COLINAS_M = 11;
  const ALTURA_ONDULACION_M = 2.5;

  // Altura del terreno (metros) en una coordenada del mundo (x, y del
  // backend, no coordenadas Three). Se usa tanto para deformar el plano
  // del piso como para "apoyar" sobre esa altura al vehículo, los
  // edificios, los árboles y la trinchera — sin esto quedarían flotando
  // o hundidos en las colinas.
  function alturaTerreno(wx, wy) {
    const u = wx / field.width;
    const v = wy / field.height;
    const uOnd = (u * 3) % 1;
    const vOnd = (v * 3) % 1;
    return ruidoColinas(u, v) * ALTURA_COLINAS_M + ruidoOndulacion(uOnd, vOnd) * ALTURA_ONDULACION_M;
  }
  // Dron real (tools/blender/generar_dron.py → frontend/models/dron.glb):
  // reemplaza el cono genérico. A diferencia del vehículo (un solo
  // modelo), acá hay hasta ~50 a la vez — droneTemplate es la escena
  // cargada UNA vez, nunca agregada a la escena en sí; cada dron vivo
  // clona su propia copia (con su propio material "Cuerpo" clonado
  // aparte, para poder teñirlo por estado sin afectar a los demás).
  let droneTemplate = null;
  let dronesGroup = null;
  const droneRecords = new Map(); // id -> { x,y,angulo,estado, target:{x,y,angulo}, fx }
  const missileObjects = new Map(); // id -> { mesh, trail, x, y, target:{x,y} }
  const detonations = []; // { mesh1, mesh2, start }
  const cannonPulses = []; // { ring, start }
  const particleBursts = []; // { points: THREE.Points, start, velocities }
  const lightningBolts = []; // { line, start }
  let hpmConeMesh = null;
  // Vehículo lanzador (tools/blender/generar_lanzador_hpm.py, exportado
  // a frontend/models/lanzador_hpm.glb): reemplaza la esfera+mástil
  // genéricos de antes. vehiculoGroup existe desde el arranque (para
  // poder posicionarlo ya mismo); torretaHpmNode se completa recién
  // cuando termina de cargar el .glb (carga async) — se rota según
  // hpm.direccion en cuanto está disponible.
  let vehiculoGroup = null;
  let torretaHpmNode = null;
  const lastHpmOrigin = { x: 0, y: 0, z: 0 };
  // Kamikaze (ver SimulationEngine.kamikaze_activo): plataformaDestruida
  // es el estado deseado (puede llegar ANTES de que termine de cargar
  // el .glb, por eso es una variable aparte, no algo que se aplica al
  // vuelo); coloresOriginalesVehiculo guarda el color de cada material
  // relevante la primera vez que se toca, para poder restaurarlo en un
  // reset sin tener que recordar los hex a mano acá.
  let plataformaDestruida = false;
  const coloresOriginalesVehiculo = new Map();
  // "Mover plataforma": mientras está armado, el próximo click en el
  // mapa se interpreta como destino (no como parte del control de
  // órbita de OrbitControls, que usa drag, no click suelto) — ver
  // configurarClickParaMover/activarModoMover.
  let modoMoverActivo = false;
  let callbackDestinoElegido = null;
  const _raycaster = new THREE.Raycaster();
  const _planoSuelo = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  // Suavizado de la posición del vehículo (mismo criterio que
  // droneRecords._smoothX/Y) — sin esto, cada snapshot nuevo movería el
  // modelo en saltos discretos en vez de un desplazamiento fluido.
  const _smoothVehiculo = { x: null, z: null };
  // Edificios atacables (tools/blender/generar_edificio.py →
  // frontend/models/edificio.glb, ver src/models/structure.py):
  // edificioTemplate es la escena cargada una vez; cada Estructura del
  // snapshot (posición FIJA, a diferencia de los drones) clona su propia
  // instancia la primera vez que aparece — nunca se recrea después,
  // salud/destruida se reflejan tiñendo esa misma instancia.
  let edificioTemplate = null;
  let estructurasGroup = null;
  const estructuraRecords = new Map(); // id -> { model, materiales, coloresOriginales, destruidaAntes }

  // Árboles (tools/blender/generar_arboles.py → frontend/models/
  // arboles.glb): puramente decorativos, sin entidad en el backend — no
  // hay snapshot que traiga posiciones, así que se dispersan UNA vez en
  // el cliente con una semilla fija (reproducible entre recargas), recién
  // cuando se conocen el tamaño del campo y las estructuras reales (para
  // no hacerlos brotar encima de un edificio o del vehículo).
  let arbolesTemplates = null; // [Object3D, Object3D, Object3D], una por variante
  let arbolesGroup = null;
  let arbolesDispersados = false;

  // Trinchera (tools/blender/generar_trinchera.py → frontend/models/
  // trinchera.glb): un único emplazamiento fijo, delante del vehículo en
  // su posición INICIAL (una trinchera se cava una vez, no sigue al
  // vehículo si este hace "shoot and scoot" después) — puramente
  // decorativa, sin salud ni bloqueo de línea de vista (ver 9.9 en
  // docs/SEGUIMIENTO_SESION.md: eso no se pidió para la trinchera).
  let trincheraTemplate = null;
  let trincheraColocada = false;

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
    // Antes maxDim*0.15 (150m con el campo default de 1000m): un piso
    // tan alto hacía IMPOSIBLE acercar la cámara a cualquier cosa,
    // incluido el vehículo lanzador (ver verPlataforma) — nadie podía
    // zoomear de cerca, ni con mouse real ni con automatización. 8m
    // sigue evitando atravesar geometría pero deja acercarse en serio.
    controls.minDistance = 8;
    controls.maxDistance = maxDim * 2.5;

    // Antes tenían tinte verde (0x445544/0xbfffcf) — se filtraba a CADA
    // material de la escena, no solo a los que ya son verdes a propósito
    // (activo/pasto). Neutro/frío en su lugar, consistente con el resto
    // de la migración de paleta.
    scene.add(new THREE.AmbientLight(0x454b54, 1.2));
    const sun = new THREE.DirectionalLight(0xdce8f2, 0.6);
    sun.position.set(field.width * 0.3, maxDim * 0.6, field.height * 0.2);
    scene.add(sun);
    // El hillshading del piso (ver aplicarRelieveTerreno) usa una luz
    // "de mentira" aparte porque el piso no reacciona a la luz real de
    // la escena (MeshBasicMaterial) — pero no hay razón para que las dos
    // luces apunten a lugares distintos: sincronizarla con el sol real
    // le da coherencia al conjunto (la sombra del relieve cae "del mismo
    // lado" que, en teoría, cualquier otra cosa que sí reaccionara a la
    // luz). sun.position está en coordenadas Three (X, Y=altura, Z); el
    // sombreado trabaja en (wx, wy, altura) — mismo cambio de eje que
    // worldToThree, por eso Y y Z se intercambian acá.
    _luzRelieve = normalizar3({ x: sun.position.x, y: sun.position.z, z: sun.position.y });

    buildGround();
    buildHeatmapPlane();
    buildHpmCone();
    buildDroneTemplate();
    buildEdificioTemplate();
    buildArbolesTemplate();
    buildTrincheraTemplate();
    configurarClickParaMover();

    resize();
    started = true;
    requestAnimationFrame(loop);
  }

  function buildDroneTemplate() {
    dronesGroup = new THREE.Group();
    scene.add(dronesGroup);
    new GLTFLoader().load(
      "models/dron.glb",
      (gltf) => {
        droneTemplate = gltf.scene;
      },
      undefined,
      (err) => {
        console.error("No se pudo cargar frontend/models/dron.glb:", err);
      },
    );
  }

  function buildEdificioTemplate() {
    estructurasGroup = new THREE.Group();
    scene.add(estructurasGroup);
    new GLTFLoader().load(
      "models/edificio.glb",
      (gltf) => {
        edificioTemplate = gltf.scene;
      },
      undefined,
      (err) => {
        console.error("No se pudo cargar frontend/models/edificio.glb:", err);
      },
    );
  }

  function buildArbolesTemplate() {
    arbolesGroup = new THREE.Group();
    scene.add(arbolesGroup);
    new GLTFLoader().load(
      "models/arboles.glb",
      (gltf) => {
        arbolesTemplates = ["Arbol_0", "Arbol_1", "Arbol_2"]
          .map((nombre) => gltf.scene.getObjectByName(nombre))
          .filter(Boolean);
      },
      undefined,
      (err) => {
        console.error("No se pudo cargar frontend/models/arboles.glb:", err);
      },
    );
  }

  function buildTrincheraTemplate() {
    new GLTFLoader().load(
      "models/trinchera.glb",
      (gltf) => {
        trincheraTemplate = gltf.scene;
      },
      undefined,
      (err) => {
        console.error("No se pudo cargar frontend/models/trinchera.glb:", err);
      },
    );
  }

  // Tamaño de un tile de la textura de tierra, en metros — determina
  // cuántas veces se repite crearTexturaTerreno() a lo largo del campo.
  const TERRENO_TILE_M = 45;

  // Textura de tierra procedural: mismo criterio que buildHeatmapPlane
  // (un canvas 2D como fuente, sin depender de ninguna imagen externa
  // descargada) — reemplaza el plano de color sólido de antes por un
  // piso con textura real: grano de tierra suelta, parches de pasto seco
  // y un par de rodadas de vehículo (detalle barato que lee como
  // "terreno usado", no un mapa recién pintado). Paleta emparentada con
  // la tierra de generar_trinchera.py/generar_edificio.py (rural,
  // terrosa) pero oscurecida para no romper el registro "sala de
  // operaciones" del resto de la escena (ver el comentario de COLOR
  // arriba).
  function crearTexturaTerreno() {
    // Base de baja frecuencia: un canvas CHICO con una mota de color por
    // celda (paleta de tierra/pasto seco/surco), escalado hacia arriba
    // con suavizado de imagen activado — el propio navegador interpola
    // linealmente entre celdas, dando manchas difusas orgánicas "gratis"
    // en vez de tener que dibujar a mano cientos de blobs superpuestos.
    // El intento anterior (blobs grandes con opacidad alta, o grano fino
    // per-píxel de alta frecuencia) o tapaba la base entera (se veía como
    // una alfombra caqui uniforme) o se leía como estática de TV — acá la
    // frecuencia baja de la base es lo que la hace leer como "tierra
    // vista de lejos", no ruido.
    const baseSize = 20;
    const base = document.createElement("canvas");
    base.width = base.height = baseSize;
    const bctx = base.getContext("2d");
    const rng = mulberry32(7);
    // Selección PESADA, no uniforme: el suavizado bilineal promedia
    // colores vecinos, así que si la base oscura y los parches claros
    // aparecen con la misma frecuencia, el promedio termina siendo un
    // caqui parejo (justo el problema del intento anterior) — acá la
    // base oscura domina (~78%) y los parches son la excepción, no la mitad.
    function colorCelda() {
      const t = rng();
      if (t < 0.78) return [14, 13, 11]; // tierra de base, oscura
      if (t < 0.9) return [34, 29, 18]; // parche de tierra removida
      if (t < 0.97) return [30, 33, 17]; // parche de pasto seco
      return [7, 6, 5]; // surco/sombra
    }
    for (let y = 0; y < baseSize; y++) {
      for (let x = 0; x < baseSize; x++) {
        const [r, g, b] = colorCelda();
        const j = (rng() - 0.5) * 6;
        bctx.fillStyle = `rgb(${r + j},${g + j},${b + j})`;
        bctx.fillRect(x, y, 1, 1);
      }
    }

    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(base, 0, 0, size, size);

    // Grano fino MUY sutil encima de las manchas — refuerza la sensación
    // de tierra suelta sin volver a leerse como estática (pocas motas,
    // alfa bajo, a diferencia del intento anterior con 3000-5000).
    for (let i = 0; i < 900; i++) {
      const v = rng();
      ctx.fillStyle = `rgba(${20 + v * 30},${17 + v * 26},${12 + v * 18},${0.12 + v * 0.15})`;
      ctx.fillRect(rng() * size, rng() * size, 2, 2);
    }

    // Rodadas de vehículo: un par de franjas oscuras curvas cruzando el tile.
    ctx.strokeStyle = "rgba(5,4,3,0.35)";
    ctx.lineWidth = 8;
    for (let i = 0; i < 2; i++) {
      const y0 = rng() * size;
      ctx.beginPath();
      ctx.moveTo(0, y0);
      ctx.bezierCurveTo(
        size * 0.3, y0 + (rng() - 0.5) * 80,
        size * 0.7, y0 + (rng() - 0.5) * 80,
        size, y0 + (rng() - 0.5) * 60,
      );
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  function normalizar3(v) {
    const len = Math.hypot(v.x, v.y, v.z) || 1;
    return { x: v.x / len, y: v.y / len, z: v.z / len };
  }

  // Dirección de luz para el hillshading del piso (ver aplicarRelieveTerreno
  // más abajo) — se sincroniza con la posición real del sol de la escena
  // recién en init() (ver ahí el porqué del intercambio de ejes); este
  // valor default solo cubre el caso raro de llamar a algo que la use
  // antes de que init() corra.
  let _luzRelieve = normalizar3({ x: 0.3, y: 0.2, z: 1 });

  // Para el toggle de UI "Relieve" (setRelieveVisible): terrenoMesh es el
  // piso ya creado, terrenoColoresRelieve el sombreado calculado una sola
  // vez en aplicarRelieveTerreno — togglear solo cambia qué colores están
  // activos en el BufferAttribute, no recalcula ni toca la geometría (las
  // colinas en sí siguen ahí, solo se apaga el sombreado que las hace
  // notarse).
  let terrenoMesh = null;
  let terrenoColoresRelieve = null;

  // Aplica el relieve (ver alturaTerreno más arriba) a los vértices de un
  // PlaneGeometry ya creado. La geometría vive en su plano local ANTES de
  // rotarla -90° en X para acostarla; esa rotación manda el eje local Z a
  // world Y (la altura) y el local Y a -world Z — por eso la conversión
  // de vértice local a coordenada de mundo (wx, wy) de acá abajo no es la
  // misma que worldToThree (esa ya asume la malla acostada).
  function aplicarRelieveTerreno(planeGeo) {
    const pos = planeGeo.attributes.position;
    const colores = new Float32Array(pos.count * 3);
    const eps = 4; // metros, ventana para estimar la pendiente local

    for (let i = 0; i < pos.count; i++) {
      const wx = pos.getX(i) + field.width / 2;
      const wy = field.height / 2 - pos.getY(i);
      pos.setZ(i, alturaTerreno(wx, wy));

      // Hillshading analítico por diferencias finitas: el piso usa
      // MeshBasicMaterial (ver por qué en buildGround), que NO se
      // oscurece con la luz de la escena — sin este color de vértice, el
      // relieve sería geométricamente real pero invisible a simple vista
      // desde arriba (la vista táctica por defecto), un material sin luz
      // no sombrea laderas solo. Técnica estándar de mapas de relieve
      // (hillshade), calculada a mano acá en vez de depender de
      // iluminación real de la escena para tener control total del
      // contraste.
      const hL = alturaTerreno(wx - eps, wy);
      const hR = alturaTerreno(wx + eps, wy);
      const hD = alturaTerreno(wx, wy - eps);
      const hU = alturaTerreno(wx, wy + eps);
      // Exageración SOLO para el sombreado (la geometría real usa la
      // altura sin exagerar, arriba) — colinas de 11m sobre celdas de
      // ~166m tienen una pendiente real de apenas ~6%, que da un dot
      // product casi constante (~0.97 vs ~0.74) y un brillo invisible a
      // ojo. Multiplicar la pendiente ×8 antes de armar la normal exagera
      // el CONTRASTE del sombreado sin tocar la altura real de la malla —
      // mismo truco que usan los generadores de hillshade de verdad
      // cuando el relieve de entrada es demasiado suave para leerse.
      const EXAGERACION_SOMBREADO = 10;
      const dx = ((hR - hL) / (2 * eps)) * EXAGERACION_SOMBREADO;
      const dy = ((hU - hD) / (2 * eps)) * EXAGERACION_SOMBREADO;
      const nLen = Math.hypot(dx, dy, 1);
      const nx = -dx / nLen;
      const ny = -dy / nLen;
      const nz = 1 / nLen;
      const dot = Math.max(-1, Math.min(1, nx * _luzRelieve.x + ny * _luzRelieve.y + nz * _luzRelieve.z));
      // Rango de brillo bien ancho (0.2x a 1.6x) a propósito: sobre una
      // textura tan oscura (valores ~10-40 de 255), un contraste sutil
      // tipo 0.55-1.1x se traduce en 2-3 unidades de diferencia — invisible
      // en la práctica (probado, no una sospecha). Este rango da hasta
      // ~20 unidades de diferencia entre ladera iluminada y sombra, que sí
      // se lee a simple vista sin dejar de ser oscuro en conjunto (las
      // sombras se ponen MÁS oscuras, no las laderas más claras que el
      // registro "sala de operaciones" del resto de la escena).
      const brillo = Math.max(0.2, Math.min(1.6, 0.35 + 1.25 * dot));
      colores[i * 3] = brillo;
      colores[i * 3 + 1] = brillo;
      colores[i * 3 + 2] = brillo;
    }
    // Se guarda aparte (no solo en el BufferAttribute) para que
    // setRelieveVisible() pueda restaurar el sombreado calculado sin
    // tener que recalcularlo — togglear el checkbox de "Relieve" no
    // vuelve a correr el hillshading, solo cambia qué array está activo.
    terrenoColoresRelieve = colores;
    planeGeo.setAttribute("color", new THREE.BufferAttribute(colores.slice(), 3));
    pos.needsUpdate = true;
    planeGeo.computeVertexNormals();
  }

  function buildGround() {
    // Suficientes segmentos para que las colinas se vean curvas y no
    // facetadas, sin pasarse de polígonos — a 20m por quad, un campo de
    // 1000m queda en ~2500 quads, nada para una GPU moderna.
    const segmentos = Math.max(24, Math.round(Math.max(field.width, field.height) / 20));
    const planeGeo = new THREE.PlaneGeometry(field.width, field.height, segmentos, segmentos);
    aplicarRelieveTerreno(planeGeo);

    const terrenoTexture = crearTexturaTerreno();
    const repeticiones = Math.max(4, Math.round(Math.max(field.width, field.height) / TERRENO_TILE_M));
    terrenoTexture.repeat.set(repeticiones, repeticiones);
    // Basic (sin luz): con la iluminación tan tenue de esta escena
    // (ambient+sol apagados a propósito para no lavar los colores de
    // estado de los drones), un material que sí reacciona a la luz
    // (Standard/Lambert) multiplicaba la textura por tan poca luz que el
    // patrón quedaba invisible, más oscuro que el plano de color
    // original. Con Basic, lo que se dibuja en crearTexturaTerreno() es
    // EXACTAMENTE lo que se ve en pantalla.
    const planeMat = new THREE.MeshBasicMaterial({ map: terrenoTexture, vertexColors: true });
    const plane = new THREE.Mesh(planeGeo, planeMat);
    plane.rotation.x = -Math.PI / 2;
    scene.add(plane);
    terrenoMesh = plane;

    // La grilla/el borde tácticos se quedan PLANOS a propósito (referencia
    // de coordenadas tipo HUD, no terreno físico) — quedan "enterrados"
    // bajo una colina donde el relieve sube por encima de y=0, lo cual es
    // el comportamiento esperado (mismo criterio que un mapa de arena con
    // líneas pintadas en el piso, no flotando sobre el relieve).
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

    // Vehículo lanzador (cañón + misil, comparten emplazamiento — ver
    // HPM_ORIGIN_X/Y/Z en src/config.py). Antes era una esfera+mástil
    // genéricos; ahora es el modelo real (ver tools/blender/
    // generar_lanzador_hpm.py para el porqué de cada pieza). El grupo
    // se agrega YA (para poder posicionarlo desde el primer snapshot);
    // el contenido visual aparece cuando termina de cargar el .glb —
    // carga asíncrona, no bloquea el resto de la escena.
    vehiculoGroup = new THREE.Group();
    scene.add(vehiculoGroup);
    const ESCALA_VEHICULO = 3; // el modelo mide ~6.5m real; a esta escala
    // se ve comparable al tamaño de los drones (ver generar_dron.py) —
    // mismo criterio de "exagerado para que se note a la distancia de
    // combate" que ya usa el resto del mapa.
    new GLTFLoader().load(
      "models/lanzador_hpm.glb",
      (gltf) => {
        const modelo = gltf.scene;
        modelo.scale.setScalar(ESCALA_VEHICULO);
        vehiculoGroup.add(modelo);
        torretaHpmNode = modelo.getObjectByName("Torreta_HPM");
        // Por si plataformaDestruida ya llegó True ANTES de que terminara
        // de cargar el modelo (snapshot procesado mientras el .glb
        // todavía viajaba por red) — sin esto quedaría con los colores
        // normales hasta el próximo cambio de estado.
        aplicarEstadoDestruccionVehiculo();
      },
      undefined,
      (err) => {
        console.error("No se pudo cargar frontend/models/lanzador_hpm.glb:", err);
      },
    );

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
    const origenX = hpm.origen_x ?? 0;
    const origenY = hpm.origen_y ?? 0;
    // Apoya el vehículo sobre el relieve real de su posición actual — sin
    // esto quedaría flotando sobre una colina o hundido en un valle.
    const suelo = alturaTerreno(origenX, origenY);
    const origin = worldToThree(field, origenX, origenY, suelo + 0.8);
    // Guardado para verPlataforma(): la vista por defecto siempre mira
    // al centro del mapa (donde nace el enjambre), pero el vehículo
    // suele estar lejos de ahí — sin esto no hay forma de acercar la
    // cámara al vehículo en sí.
    lastHpmOrigin.x = origin.x;
    lastHpmOrigin.y = suelo;
    lastHpmOrigin.z = origin.z;
    // Suavizado (mismo criterio que droneRecords._smoothX/Y): el
    // vehículo ahora puede moverse ("shoot and scoot"), sin esto cada
    // snapshot nuevo lo saltaría de golpe en vez de deslizarse.
    if (_smoothVehiculo.x === null) {
      _smoothVehiculo.x = origin.x;
      _smoothVehiculo.z = origin.z;
    } else {
      _smoothVehiculo.x = lerp(_smoothVehiculo.x, origin.x, 0.25);
      _smoothVehiculo.z = lerp(_smoothVehiculo.z, origin.z, 0.25);
    }
    if (vehiculoGroup) vehiculoGroup.position.set(_smoothVehiculo.x, suelo, _smoothVehiculo.z);
    if (radarRingMesh) radarRingMesh.position.set(_smoothVehiculo.x, suelo + 0.5, _smoothVehiculo.z);

    const dirDeg = hpm.direccion ?? 0;
    // Torreta_HPM mira +X en reposo, misma convención que este cono
    // (mundo: x=cos, z=sin — ver más abajo) — headingToRotationY ya
    // hace la conversión de signo correcta entre esa convención y el
    // rotation.y de Three (mismo helper que usan drones/misiles).
    if (torretaHpmNode) torretaHpmNode.rotation.y = headingToRotationY(dirDeg);
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
    hpmConeMesh.position.set(origin.x, origin.y, origin.z);
  }

  function updateRadarPing(radar) {
    if (!radar || !radarPingMesh) return;
    const origenX = radar.origen_x ?? 0;
    const origenY = radar.origen_y ?? 0;
    const origin = worldToThree(field, origenX, origenY, alturaTerreno(origenX, origenY) + 0.55);
    radarPingMesh.position.set(origin.x, origin.y, origin.z);
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

  // Toggle de UI ("Relieve"): apaga/prende el SOMBREADO de las colinas
  // sin tocar la geometría — las colinas reales siguen estando ahí
  // (física y colisión visual del vehículo/edificios/árboles no dependen
  // de esto), solo deja de notarse a simple vista. Pensado para
  // escenarios con mucha densidad de drones donde el contraste del
  // hillshading (ver aplicarRelieveTerreno) pueda competir con la
  // lectura de los estados de color.
  function setRelieveVisible(visible) {
    if (!terrenoMesh || !terrenoColoresRelieve) return;
    const colorAttr = terrenoMesh.geometry.attributes.color;
    if (visible) {
      colorAttr.array.set(terrenoColoresRelieve);
    } else {
      colorAttr.array.fill(1);
    }
    colorAttr.needsUpdate = true;
  }

  // Tinte de daño de los edificios: mismo color "quemado" que usa el
  // vehículo destruido (COLOR_QUEMADO más abajo), pero declarado acá
  // aparte porque los edificios lo aplican GRADUALMENTE (proporcional a
  // 1 - salud/salud_maxima), no como un interruptor todo-o-nada.
  const MATERIALES_EDIFICIO_DANIABLES = ["Pared", "Techo"];
  const _colorEdificioQuemado = new THREE.Color(0x14100c);

  function ensureEstructuraModel(estructura) {
    let rec = estructuraRecords.get(estructura.id);
    if (!rec) {
      rec = { model: null, destruidaAntes: false };
      estructuraRecords.set(estructura.id, rec);
    }
    if (rec.model || !edificioTemplate) return rec;

    const model = edificioTemplate.clone(true);
    // clone(true) no clona materiales (ver mismo comentario en
    // ensureDroneModel) — acá hace falta ADEMÁS porque "Pared" lo
    // comparten dos nodos DENTRO de un mismo edificio (Edificio y
    // Chimenea), así que un solo clone por nombre alcanza para toda la
    // instancia, no uno por mesh.
    const materiales = new Map();
    model.traverse((obj) => {
      if (!obj.isMesh || !obj.material) return;
      const nombre = obj.material.name;
      if (!materiales.has(nombre)) materiales.set(nombre, obj.material.clone());
      obj.material = materiales.get(nombre);
    });
    rec.materiales = materiales;
    rec.coloresOriginales = new Map(
      [...materiales.entries()].map(([nombre, mat]) => [nombre, mat.color.clone()])
    );

    const pos = worldToThree(field, estructura.x, estructura.y, alturaTerreno(estructura.x, estructura.y));
    model.position.set(pos.x, pos.y, pos.z);
    estructurasGroup.add(model);
    rec.model = model;
    return rec;
  }

  function actualizarEstructuras(estructuras) {
    if (!estructuras) return;
    for (const e of estructuras) {
      const rec = ensureEstructuraModel(e);
      if (!rec.model) continue; // template todavía no cargó

      if (!rec.destruidaAntes && e.destruida) {
        spawnParticleBurst(worldToThree(field, e.x, e.y, 4), COLOR.neutralizadoBlink);
      }
      rec.destruidaAntes = e.destruida;

      const fraccionDano = 1 - Math.max(0, Math.min(1, e.salud / (e.salud_maxima || 1)));
      const mezcla = e.destruida ? 0.85 : fraccionDano * 0.7;
      for (const nombre of MATERIALES_EDIFICIO_DANIABLES) {
        const mat = rec.materiales.get(nombre);
        if (!mat) continue;
        _color.copy(rec.coloresOriginales.get(nombre)).lerp(_colorEdificioQuemado, mezcla);
        mat.color.copy(_color);
      }
      // Un edificio caído se hunde/aplasta un poco — mismo criterio barato
      // que la caída de un dron: comunica "destruido" sin necesitar un
      // modelo de escombros aparte.
      const escalaObjetivo = e.destruida ? 0.25 : 1;
      rec.model.scale.y = lerp(rec.model.scale.y, escalaObjetivo, 0.1);
    }
  }

  const ARBOL_CANTIDAD = 55;
  const ARBOL_ESCALA = 2.2; // mismo criterio "exagerado a distancia de combate" que vehículo/dron
  const ARBOL_RADIO_EXCLUSION_ESTRUCTURA_M = 45;
  const ARBOL_RADIO_EXCLUSION_VEHICULO_M = 35;

  // Disperso decorativo de árboles: no hay posiciones en el backend (no
  // son una entidad simulada, ver 9.9 en docs/SEGUIMIENTO_SESION.md), así
  // que se generan acá con una semilla fija (misma semilla 2026 que los
  // scripts de Blender, por consistencia) — reproducible entre recargas,
  // no un disperso distinto cada vez que se refresca la página. Se corre
  // UNA sola vez, apenas se conocen el tamaño real del campo y las
  // posiciones reales de vehículo/estructuras (para no hacer brotar un
  // árbol encima de un edificio o del vehículo).
  function dispersarArboles(snap) {
    if (arbolesDispersados || !arbolesTemplates || !arbolesTemplates.length) return;
    arbolesDispersados = true;

    const exclusiones = [];
    if (snap.hpm) {
      exclusiones.push({
        x: snap.hpm.origen_x ?? 0,
        y: snap.hpm.origen_y ?? 0,
        r: ARBOL_RADIO_EXCLUSION_VEHICULO_M,
      });
    }
    for (const e of snap.estructuras ?? []) {
      exclusiones.push({ x: e.x, y: e.y, r: ARBOL_RADIO_EXCLUSION_ESTRUCTURA_M });
    }
    const posicionTrinchera = calcularPosicionTrinchera(snap);
    if (posicionTrinchera) {
      exclusiones.push({
        x: posicionTrinchera.wx,
        y: posicionTrinchera.wy,
        r: ARBOL_RADIO_EXCLUSION_TRINCHERA_M,
      });
    }

    const rng = mulberry32(2026);
    let colocados = 0;
    let intentos = 0;
    while (colocados < ARBOL_CANTIDAD && intentos < ARBOL_CANTIDAD * 20) {
      intentos++;
      const wx = rng() * field.width;
      const wy = rng() * field.height;
      if (exclusiones.some((z) => Math.hypot(wx - z.x, wy - z.y) < z.r)) continue;

      const variante = arbolesTemplates[Math.floor(rng() * arbolesTemplates.length)];
      const arbol = variante.clone(true);
      const pos = worldToThree(field, wx, wy, alturaTerreno(wx, wy));
      arbol.position.set(pos.x, pos.y, pos.z);
      arbol.rotation.y = rng() * Math.PI * 2;
      arbol.scale.setScalar(ARBOL_ESCALA * (0.85 + rng() * 0.3));
      arbolesGroup.add(arbol);
      colocados++;
    }
  }

  const TRINCHERA_DISTANCIA_M = 25; // metros por delante del vehículo, hacia el centro del campo
  const ARBOL_RADIO_EXCLUSION_TRINCHERA_M = 25;

  // Extraído de colocarTrinchera para que dispersarArboles pueda calcular
  // la MISMA posición sin duplicar la fórmula (antes los árboles no
  // excluían la trinchera — un árbol podía brotar atravesando los sacos,
  // ver docs/SEGUIMIENTO_SESION.md). Devuelve null si todavía no hay
  // snapshot de hpm.
  function calcularPosicionTrinchera(snap) {
    if (!snap.hpm) return null;
    const origenX = snap.hpm.origen_x ?? 0;
    const origenY = snap.hpm.origen_y ?? 0;
    const centroX = field.width / 2;
    const centroY = field.height / 2;
    const dx = centroX - origenX;
    const dy = centroY - origenY;
    const dist = Math.hypot(dx, dy) || 1;
    const dirX = dx / dist;
    const dirY = dy / dist;
    return {
      wx: origenX + dirX * TRINCHERA_DISTANCIA_M,
      wy: origenY + dirY * TRINCHERA_DISTANCIA_M,
      dirX,
      dirY,
    };
  }

  // Se coloca UNA vez, delante de la posición INICIAL del vehículo (una
  // trinchera es un emplazamiento cavado de antemano, no algo que se
  // reubica solo si el vehículo se mueve después — ver "shoot and scoot"
  // en 9.6). "Delante" = hacia el centro del campo, de donde viene el
  // enjambre en el layout por defecto.
  function colocarTrinchera(snap) {
    if (trincheraColocada || !trincheraTemplate) return;
    const posicion = calcularPosicionTrinchera(snap);
    if (!posicion) return;
    trincheraColocada = true;

    const { wx, wy, dirX, dirY } = posicion;
    const pos = worldToThree(field, wx, wy, alturaTerreno(wx, wy));
    const model = trincheraTemplate.clone(true);
    model.position.set(pos.x, pos.y, pos.z);
    // Mismo helper/convención que usan drones y misiles para pasar de un
    // ángulo "mundo" (atan2 estándar) a rotation.y de Three.
    model.rotation.y = headingToRotationY(THREE.MathUtils.radToDeg(Math.atan2(dirY, dirX)));
    scene.add(model);
  }

  function ensureDroneModel(rec) {
    // droneTemplate carga async — si todavía no está listo, el rec se
    // actualiza igual (estado/posición) y el modelo aparece recién
    // cuando ensureDroneModel se vuelve a llamar en un tick posterior
    // y ya está disponible (mismo patrón que vehiculoGroup).
    if (rec.model || !droneTemplate) return;
    const model = droneTemplate.clone(true);
    // clone(true) clona la jerarquía pero NO los materiales (los hijos
    // clonados siguen apuntando al MISMO material que el original) — si
    // no clonamos acá el material de "Cuerpo", teñir un dron por estado
    // teñiría a los 50 a la vez.
    const cuerpo = model.getObjectByName("Cuerpo");
    if (cuerpo) {
      cuerpo.material = cuerpo.material.clone();
      rec.cuerpoMaterial = cuerpo.material;
    }
    dronesGroup.add(model);
    rec.model = model;
  }

  const _euler = new THREE.Euler();
  const _color = new THREE.Color();
  const _riesgoColor = new THREE.Color(COLOR.riesgoLatente);
  const _missileQuatYaw = new THREE.Quaternion();
  const _missileQuatPitch = new THREE.Quaternion();
  const _yAxis = new THREE.Vector3(0, 1, 0);
  const _zAxis = new THREE.Vector3(0, 0, 1);

  function updateDrones(drones, now) {
    if (!drones) return;

    const seen = new Set();
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
      ensureDroneModel(rec);

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
    }
    for (const id of [...droneRecords.keys()]) {
      if (seen.has(id)) continue;
      const rec = droneRecords.get(id);
      if (rec.model) {
        dronesGroup.remove(rec.model);
        rec.cuerpoMaterial?.dispose();
      }
      droneRecords.delete(id);
    }

    for (const rec of droneRecords.values()) {
      if (!rec.model) continue; // template todavía no cargó — se pone al día solo

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

      rec.model.position.set(rec._smoothX - field.width / 2, altitude, rec._smoothY - field.height / 2);
      _euler.set(0, headingToRotationY(rec._smoothAngulo), 0);
      rec.model.quaternion.setFromEuler(_euler);
      rec.model.visible = visible;

      if (rec.cuerpoMaterial) {
        _color.setHex(colorHex);
        // Riesgo latente (P2-D): el dron impactado entró en una ventana de
        // vulnerabilidad transitoria — puede recuperarse o fallar más tarde.
        // Se comunica con un parpadeo ámbar superpuesto al color normal (no
        // lo reemplaza) cuya frecuencia escala con la severidad, en vez de
        // un estado discreto más — la muerte diferida deja de verse
        // instantánea e inexplicable. No se aplica mientras cae/ya cayó (ya
        // tiene su propio efecto) ni si está "no detectado" (ese color ya
        // domina).
        if (
          rec.riesgoSeveridad > 0 &&
          rec.fx.state !== "falling" && rec.fx.state !== "settled" &&
          rec.detectado !== false
        ) {
          const periodMs = lerp(1600, 400, rec.riesgoSeveridad);
          const wave = (Math.sin((now % periodMs) / periodMs * Math.PI * 2) + 1) / 2;
          _color.lerp(_riesgoColor, 0.15 + 0.55 * wave);
        }
        rec.cuerpoMaterial.color.copy(_color);
      }
    }
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
      // Antes el misil solo "aparecía" ya en vuelo, sin ninguna marca de
      // dónde salió — un estallido en su primera posición conocida (el
      // lanzador, mismo origen que el cañón) da esa referencia visual,
      // igual que ya se hace al neutralizar un dron o al llegar a la
      // misión (spawnParticleBurst).
      const launchPos = worldToThree(field, m.x, m.y, m.z ?? FALLBACK_MISSILE_ALTITUDE);
      spawnParticleBurst(launchPos, COLOR.missile);
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
    if (snap.estructuras) actualizarEstructuras(snap.estructuras);
    dispersarArboles(snap);
    colocarTrinchera(snap);
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

  // Materiales que se apagan cuando la plataforma queda destruida —
  // Chasis/Torreta (el cuerpo del vehículo) y EmisorHPM/AcentoEnergia
  // (el panel que el dron kamikaze impactó, ver el mensaje de rechazo en
  // src/models/hpm_weapon.py) — no Pista/Rueda/Detalle/Radar, que no
  // tienen nada que ver con por qué dejó de funcionar.
  const MATERIALES_DANIABLES = ["Chasis", "Torreta", "EmisorHPM", "AcentoEnergia"];
  const COLOR_QUEMADO = 0x0d0b0a;

  function setPlataformaDestruida(destruida) {
    destruida = !!destruida;
    if (destruida === plataformaDestruida) return;
    const primeraVez = destruida && !plataformaDestruida;
    plataformaDestruida = destruida;
    aplicarEstadoDestruccionVehiculo();
    if (primeraVez) {
      spawnParticleBurst(
        new THREE.Vector3(lastHpmOrigin.x, 8, lastHpmOrigin.z),
        COLOR.neutralizadoBlink,
      );
    }
  }

  function aplicarEstadoDestruccionVehiculo() {
    if (!vehiculoGroup) return;
    vehiculoGroup.traverse((obj) => {
      if (!obj.isMesh || !obj.material || !MATERIALES_DANIABLES.includes(obj.material.name)) return;
      if (!coloresOriginalesVehiculo.has(obj.material.name)) {
        coloresOriginalesVehiculo.set(obj.material.name, obj.material.color.clone());
      }
      if (plataformaDestruida) {
        obj.material.color.setHex(COLOR_QUEMADO);
      } else {
        obj.material.color.copy(coloresOriginalesVehiculo.get(obj.material.name));
      }
    });
  }

  function configurarClickParaMover() {
    renderer.domElement.addEventListener("click", (ev) => {
      if (!modoMoverActivo) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1,
      );
      _raycaster.setFromCamera(ndc, camera);
      const punto = new THREE.Vector3();
      if (_raycaster.ray.intersectPlane(_planoSuelo, punto)) {
        // Inversa de worldToThree: three x/z -> mundo x/y.
        const simX = punto.x + field.width / 2;
        const simY = punto.z + field.height / 2;
        const cb = callbackDestinoElegido;
        desactivarModoMover();
        cb?.(simX, simY);
      }
    });
  }

  function activarModoMover(callback) {
    modoMoverActivo = true;
    callbackDestinoElegido = callback;
    if (canvas) canvas.style.cursor = "crosshair";
  }

  function desactivarModoMover() {
    modoMoverActivo = false;
    callbackDestinoElegido = null;
    if (canvas) canvas.style.cursor = "";
  }

  function verPlataforma() {
    // A diferencia de resetCamera()/setDefaultView() (siempre miran al
    // centro del mapa, donde nace el enjambre), esta apunta y acerca la
    // cámara al vehículo lanzador — sin esto, el minDistance/target
    // fijos al centro nunca dejan verlo de cerca cuando el arma está
    // lejos del centro (caso por defecto: arma en la esquina del campo).
    const dist = 45; // suficiente para ver el vehículo completo, no solo una pieza
    const objetivoY = lastHpmOrigin.y + 6; // +6 relativo al PISO del vehículo, no un y absoluto — con colinas, el vehículo puede estar varios metros por encima de y=0
    camera.position.set(lastHpmOrigin.x + dist * 0.7, lastHpmOrigin.y + dist * 0.6, lastHpmOrigin.z + dist * 0.7);
    camera.lookAt(lastHpmOrigin.x, objetivoY, lastHpmOrigin.z);
    if (controls) {
      controls.target.set(lastHpmOrigin.x, objetivoY, lastHpmOrigin.z);
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

  return {
    init, updateSnapshot, setViewMode, resetCamera, verPlataforma, resize,
    triggerCannonPulse, flashHits, setShowTracks, setWtaPlan, setPlataformaDestruida,
    activarModoMover, desactivarModoMover, setRelieveVisible,
  };
})();

window.Render3D = Render3D;
window.addEventListener("resize", () => Render3D.resize());
