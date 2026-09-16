# Simulador de Guerra Electromagnética (EW)

Simulador de contramedidas de microondas de alta potencia (HPM) contra
enjambres de drones, con motor de física en tiempo real, planificación
de tiro optimizada y una suite de validación científica integrada.

No es una demo visual con números decorativos: cada resultado que el
motor produce está trazado hasta una fórmula, cada fórmula está
identificada como física real, calibración contra literatura publicada
o aproximación de diseño explícita, y esa clasificación está documentada
y auditada (ver [Documentación e investigación](#documentación-e-investigación)).
La calibración del modelo de daño principal (`friis`) está verificada
contra los datos publicados en [arXiv:2602.08477](https://arxiv.org/abs/2602.08477),
incluyendo una inconsistencia interna del propio paper que este proyecto
detectó, aisló y documentó de forma independiente.

## Qué hace

- **Motor de simulación en tiempo real** — enjambre con dinámica de
  boids (separación/alineación/cohesión + evasión de amenaza), física
  de propagación electromagnética (Friis), guiado de misil por
  navegación proporcional, y un modelo de daño por subsistema basado en
  la Tabla 1 del paper de referencia.
- **Radar con seguimiento real, no omnisciencia** — el arma no conoce la
  posición verdadera del enjambre: un `TrackManager` con barrido
  periódico y filtro α-β-γ estima posición y velocidad de cada blanco, y
  puede perder el track por rango, maniobra evasiva o línea de vista
  bloqueada (obstáculos o relieve real del terreno).
- **Sensor RF pasivo** — complementa al radar con un enlace
  unidireccional (ecuación de Friis, no la ecuación de radar) sobre la
  emisión de control/telemetría del propio dron — mayor alcance que el
  radar a igual potencia, doctrina real de ESM/RWR.
- **Defensa multi-nodo con cesión de blanco** — dos emplazamientos de
  cañón HPM fijos; el optimizador de asignación arma-blanco (WTA) reparte
  disparos entre ambos para maximizar las bajas esperadas totales.
- **Planificación de tiro optimizada (WTA)** — clustering de blancos
  detectados + asignación greedy con búsqueda local, validada contra
  fuerza bruta exacta en instancias pequeñas.
- **Economía de la defensa** — cada plan de tiro y cada experimento
  reportan el costo en USD por baja esperada y su razón contra el costo
  de un dron hostil, sin alterar qué optimiza el planificador.
- **Experimentación Monte Carlo y coevolución genética** — réplicas
  headless en background vía API, con estadística agregada (medias,
  intervalos, percentiles) y una corrida de coevolución arma↔enjambre
  (algoritmo genético) que busca la frontera de Pareto entre ambos
  bandos.
- **Auditoría científica autocontenida** — análisis de sensibilidad
  global (Morris + Sobol) para identificar qué parámetro no calibrado
  domina la varianza del resultado, recuperación de la curva
  dosis-respuesta real del motor por máxima verosimilitud (contrastada
  contra la configuración), y una verificación en caliente de que la
  calibración contra el paper de referencia sigue vigente.
- **Panel táctico web con mapa 3D** — Three.js, cuatro pestañas
  (Operación, Planificación, Laboratorio, Análisis), WebSocket a 60 FPS,
  reproducción de réplicas de experimentos.

## Arquitectura

```
simulador-ew/
├── src/
│   ├── main.py                 # Servidor FastAPI + uvicorn
│   ├── config.py                # Variables de entorno (~130 parámetros)
│   ├── models/
│   │   ├── drone.py              # Dron individual: estado, susceptibilidad, riesgo latente
│   │   ├── swarm.py               # Enjambre: formaciones, boids, avance de misión
│   │   ├── hpm_weapon.py           # Cañón HPM estático (cono direccional)
│   │   ├── hpm_missile.py           # Misil HPM guiado (efecto de área)
│   │   ├── hpm_system.py             # Lanzador y munición de misiles
│   │   ├── jammer.py                  # Jammer de enlace (negación continua)
│   │   └── structure.py                # Estructuras atacables / obstáculos de línea de vista
│   ├── engine/
│   │   ├── simulation.py         # Bucle de simulación (60 FPS), orquestación
│   │   ├── physics.py             # Colisiones, reflexión de bordes
│   │   ├── flocking.py             # Boids + propagación de alarma entre drones
│   │   ├── hpm_engine.py            # Modelo de daño (Friis + sigmoide), línea de vista
│   │   ├── radar_engine.py           # Ecuación de radar, TrackManager (filtro α-β-γ)
│   │   ├── rf_sensor.py               # Sensor RF pasivo (enlace de Friis unidireccional)
│   │   ├── terreno.py                  # Relieve del terreno (puerto exacto del frontend)
│   │   ├── targeting.py                 # Optimización arma-blanco (WTA) + costo-intercambio
│   │   ├── experiments.py                # Motor Monte Carlo (réplicas headless)
│   │   ├── coevolution.py                 # Algoritmo genético arma↔enjambre
│   │   ├── sensitivity.py                  # Análisis de sensibilidad global (Morris + Sobol)
│   │   ├── validation.py                    # Verificación en caliente de la calibración
│   │   ├── propagation.py                    # Curva dosis-respuesta (MLE + bootstrap)
│   │   └── parametros.py                      # Espacio de parámetros para experimentos/coevolución
│   ├── api/
│   │   ├── routes.py              # Endpoints REST
│   │   ├── websocket.py            # Snapshots en tiempo real
│   │   └── coevolucion_jobs.py      # Jobs de coevolución en background
│   └── utils/                    # Helpers geométricos, reproducibilidad (semillas/RNG)
├── frontend/
│   ├── index.html             # Panel táctico: Operación, Planificación, Laboratorio, Análisis
│   ├── css/style.css           # Tema táctico
│   └── js/
│       ├── render3d.js          # Escena Three.js: drones, HPM, misiles, terreno, efectos
│       ├── script.js             # Orquestación principal, estado, controles
│       ├── websocket.js           # Cliente WS con reconexión automática
│       ├── charts.js               # Gráficos analíticos (efectividad, heatmap, espectro)
│       ├── replay2d.js              # Reproducción 2D de réplicas de experimentos
│       ├── icons.js                  # Iconografía SVG en línea (sprite único, sin dependencias)
│       └── vendor/three/              # Three.js + OrbitControls vendorizados (sin bundler)
├── data/scenarios/           # Escenarios JSON predefinidos (cargables desde la API)
├── tests/                    # 25 módulos de prueba, cobertura de motor, física y API
├── docs/                     # Física, estado del arte, arquitectura, auditorías, glosario
├── research/                 # Notas de investigación independientes (hallazgos, metodología)
├── requirements.txt
└── .env
```

> Nota de diseño: `src/engine/__init__.py` y `src/models/__init__.py` no reexportan símbolos a nivel de paquete a propósito (evita un ciclo de imports entre ambos paquetes). Importá siempre desde el submódulo concreto, p. ej. `from src.engine.simulation import SimulationEngine`.

## Modelo HPM

Hay dos modelos de probabilidad de neutralización, seleccionables con `HPM_MODEL`:

- **`friis` (por defecto)** — física real: densidad de potencia en espacio libre
  (ecuación de Friis, `S = P·G/4πr²`) → campo eléctrico (`E = √(S·377)`) →
  sigmoide sobre un umbral de susceptibilidad. Calibrado numéricamente contra
  los datos publicados en [arXiv:2602.08477](https://arxiv.org/abs/2602.08477)
  ("A Multi-physics Simulation Framework for High-power Microwave
  Counter-unmanned Aerial System Design and Performance Evaluation").
- **`legacy`** — exponencial ad-hoc, `P = 1 - exp(-k · potencia / distancia²)`,
  con atenuación angular en los bordes del cono. Se conserva por compatibilidad;
  *no* está basada en el paper (una versión previa de este README lo atribuía
  incorrectamente — ver auditoría en `docs/FISICA_Y_MATEMATICA.md`).

El cañón (cono direccional) y el misil (efecto de área circular) usan
umbrales de calibración **distintos** dentro del modelo `friis`, porque son
arquetipos de antena distintos (plato de alta ganancia vs. radiador de área).
El desarrollo completo — de dónde sale cada constante, qué está verificado
contra literatura real y qué es una aproximación de diseño — está en
[`docs/FISICA_Y_MATEMATICA.md`](docs/FISICA_Y_MATEMATICA.md). Para el
panorama real de la tecnología (programas militares activos, comparación
con láser/jamming/cinético, mercado, investigación académica), ver
[`docs/ESTADO_DEL_ARTE_HPM.md`](docs/ESTADO_DEL_ARTE_HPM.md). Para la
arquitectura completa de este proyecto, todas las fórmulas en un solo
lugar, qué puede y no puede derribar (con números), qué falta para ser una
investigación completa, y una sección sobre aplicación en el contexto del
Perú, ver [`docs/PROYECTO_Y_CAPACIDADES.md`](docs/PROYECTO_Y_CAPACIDADES.md).
Si algún término técnico no queda claro, [`docs/GLOSARIO.md`](docs/GLOSARIO.md)
explica cada concepto (electromagnetismo, probabilidad, guiado, drones) en
lenguaje simple. Si necesitás explicar el proyecto de cero (para una
exposición), [`docs/EXPLICACION_PARA_EXPOSICION.md`](docs/EXPLICACION_PARA_EXPOSICION.md)
lo recorre en orden, paso a paso, sin asumir conocimiento previo.

> **Calibración de `HPM_K_CONSTANT`**: el default es `250` (no el `0.015` de versiones anteriores). Con `0.015`, la probabilidad de neutralización a las distancias típicas del campo (500–900 m) era prácticamente nula — un misil detonando justo en su distancia de diseño (80 m) tenía ~0.01% de chance de derribo. Con `250`: un misil dentro de su radio de efecto (100 m default) neutraliza con 71–100% de probabilidad según la distancia al centro de la detonación, y el cañón estático (más débil, pensado para rango corto o potencia alta) neutraliza ocasionalmente a distancia y de forma consistente si se dispara de cerca o a máxima potencia. Es un valor de configuración, no un cambio a la fórmula del modelo.

## Instalación

Backend:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Frontend (necesario para tener `three` en `node_modules/` si vas a re-vendorizarlo; el panel en sí corre sirviendo `frontend/` como archivos estáticos, sin build step):

```bash
cd frontend
npm install
```

El mapa 3D usa [Three.js](https://threejs.org/) cargado como módulo ES nativo del navegador (sin bundler), vía un `<script type="importmap">` en `index.html` que apunta a los archivos vendorizados en `frontend/js/vendor/three/`:
- `three.module.js` + `three.core.min.js` (build modular de Three.js)
- `OrbitControls.js` (control de cámara orbital)

Si necesitás actualizar la versión de Three.js:
```bash
cd frontend
npm install three@<version>
cp node_modules/three/build/three.module.min.js js/vendor/three/three.module.js
cp node_modules/three/build/three.core.min.js js/vendor/three/three.core.min.js
cp node_modules/three/examples/jsm/controls/OrbitControls.js js/vendor/three/OrbitControls.js
```

## Configuración

Edita `.env`. La tabla siguiente cubre los parámetros de uso más frecuente;
`src/config.py` es la referencia completa (alrededor de 130 variables, cada
una con su ancla física o de diseño documentada en el propio código).

| Variable | Descripción | Default |
|----------|-------------|---------|
| `SIMULATION_FPS` | Frames por segundo del motor | 60 |
| `HOST` / `PORT` | Bind del servidor | `0.0.0.0` / `8000` |
| `CORS_ORIGINS` | Orígenes permitidos, separados por coma (`*` = todos) | `*` |
| `SWARM_SIZE` | Drones iniciales | 50 |
| `FIELD_WIDTH` / `FIELD_HEIGHT` | Dimensiones del campo (m) | 1000 / 1000 |
| `HPM_DEFAULT_POWER` | Potencia del cañón HPM (kW) | 25 |
| `HPM_DEFAULT_ANGLE` | Dirección inicial del cañón (°) | 45 |
| `HPM_CONE_APERTURE` | Apertura del cono de efecto (°) — 15° ≈ 20.6 dBi, del orden de un plato real | 15 |
| `HPM_K_CONSTANT` | Constante del modelo exponencial `legacy` | 250 |
| `HPM_MODEL` | `friis` (física real) o `legacy` (exponencial ad-hoc) | `friis` |
| `HPM_E_THRESHOLD_V_M` / `HPM_SIGMOID_STEEPNESS` | Umbral de susceptibilidad (V/m) y pendiente de la sigmoide del **cañón**, ajustados contra arXiv:2602.08477 | 500 / 0.0075 |
| `HPM_MISSILE_E_THRESHOLD_V_M` / `HPM_MISSILE_SIGMOID_STEEPNESS` | Ídem para el **misil** (arquetipo de área, no plato) | 30 / 0.15 |
| `HPM_ORIGIN_X` / `HPM_ORIGIN_Y` / `HPM_ORIGIN_Z` | Posición del cañón HPM (nodo A) | 0 / 0 / 8 |
| `HPM_NODO_B_ORIGIN_X` / `HPM_NODO_B_ORIGIN_Y` | Posición del segundo nodo de defensa (cañón fijo, `nodo_b_activo`) | 1000 / 1000 |
| `HPM_FREQUENCY_GHZ`, `HPM_PULSE_DURATION_NS` | Frecuencia de operación del arma y duración de referencia del pulso — entran al modelo de daño `friis` | 2.45, 100 |
| `HPM_COUPLING_K`, `HPM_BEAM_SIGMA` | Parámetros **solo del mapa de calor** (`gaussian_neutralization_prob`): pintan dónde el haz es más intenso. **No deciden ninguna baja** y ya no se publican en el panel físico — ver hallazgo 8 de `docs/FISICA_Y_MATEMATICA.md` | 0.42, 50 |
| `RADAR_FREQUENCY_GHZ` | Frecuencia del radar de detección, **independiente** de la del arma: la ecuación de radar lleva λ², así que compartirlas hacía que barrer la frecuencia del arma cambiara el alcance de detección y confundiera el experimento de resonancia | 2.45 |
| `RADAR_REVISITA_S` | Periodo de barrido del radar dinámico (`TrackManager`) — entre revisitas, el track se propaga por dead-reckoning, no por medición fresca | 1.0 |
| `DRONE_TX_POWER_W` / `RF_SENSOR_GAIN_DBI` | Potencia de emisión del dron y ganancia del sensor RF pasivo — enlace unidireccional, independiente del radar | 0.025 / 6.0 |
| `COSTO_DISPARO_CANION_USD` / `COSTO_MISIL_USD` / `COSTO_DRON_HOSTIL_USD` | Anclas de costo (USD) para el reporte de costo-intercambio del plan de tiro y de los experimentos | 25 / 50000 / 1000 |
| `MISSILE_SPEED` | Velocidad del misil HPM (m/s) | 400 |
| `MISSILE_DEFAULT_POWER` / `MISSILE_DEFAULT_RADIUS` | Potencia/radio de efecto por defecto | 50 / 100 |
| `MISSILE_MUNITION_TOTAL` | Munición máxima | 10 |
| `MISSILE_DETONATION_DISTANCE` | Distancia de detonación óptima (m) | 80 |
| `MISSILE_MAX_TURN_RATE_DEG_S` / `MISSILE_PN_GAIN` | Guiado por navegación proporcional: límite de giro (°/s) y ganancia N | 180 / 4.0 |
| `DRONE_ALTITUD_MIN` / `DRONE_ALTITUD_MAX` | Rango de altitud de crucero de los drones (m) | 40 / 160 |
| `MISSILE_LAUNCH_ALTITUDE_M` / `MISSILE_CRUISE_ALTITUDE_M` | Perfil de vuelo del misil (m) | 5 / 220 |
| `AUTO_DEMO_ENABLED` | Autoarranque de demo al cargar el panel | `true` |
| `DEMO_FORMATION`, `DEMO_SWARM_SIZE`, `DEMO_MISSILE_DELAY_S` | Parámetros de la demo automática | `circular`, 50, 3 |

> `CORS_ORIGINS=*` deshabilita `allow_credentials` automáticamente (un origen comodín con credenciales es una combinación inválida según el spec CORS). Para credenciales, configurá orígenes explícitos.

## Ejecución

```bash
python -m src.main
```

O con uvicorn directamente:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Documentación interactiva: http://localhost:8000/docs

Panel táctico (frontend): servilo como archivos estáticos, por ejemplo:

```bash
cd frontend
python3 -m http.server 5500
```

y abrí `http://localhost:5500/index.html` (el frontend asume el backend en `localhost:8000`).

Para apuntar el frontend a un backend en otro host/puerto (útil en desarrollo), usá el query param `?api=`:
```
http://localhost:5500/index.html?api=http://localhost:8001
```

## API REST

### Simulación y control

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/health` | Liveness check |
| GET | `/api/status` | Snapshot completo de la simulación (drones, HPM, misiles, analíticas, logs) |
| POST | `/api/start` | Inicia la simulación (opcionalmente reconfigura `formacion`/`cantidad`) |
| POST | `/api/stop` | Pausa la simulación |
| POST | `/api/reset` | Reinicia la simulación al estado inicial |
| POST | `/api/speed` | Ajusta el multiplicador de velocidad (`{"escala": 1\|2\|5\|10}`, rango 0.1–10) |
| GET | `/api/logs` | Últimos eventos registrados |
| GET | `/api/manifest` | Semilla activa y snapshot de la configuración relevante, para reproducibilidad |

### Armamento y sensores

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/drones` | Lista de drones con posición, estado y fuente de detección (radar/RF) |
| POST | `/api/fire` | Dispara el cañón HPM del nodo A (cono direccional) |
| POST | `/api/fire_b` | Dispara el cañón del nodo B, si está activo (`nodo_b_activo`) |
| POST | `/api/hpm/mover` | Reposiciona el vehículo (cañón + misil + jammer comparten emplazamiento) |
| POST | `/api/missile/launch` | Lanza un misil HPM (apunta automático al centroide detectado si no se indica ángulo) |
| GET | `/api/missile/status` | Estado y lista de misiles activos |
| GET | `/api/missile/munition` | Munición restante |
| POST | `/api/missile/reload` | Recarga munición |
| POST | `/api/jam/start` / `/api/jam/stop` | Activa/desactiva el jammer de enlace (negación continua) |

### Planificación y economía

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/targeting/plan` | Plan de asignación arma-blanco optimizado (WTA), con costo-intercambio |

### Analítica en vivo

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/analytics` | Panel físico, métricas de energía, curva de efectividad, heatmap y espectro |
| GET | `/api/analytics/effectiveness` | Curva de efectividad por distancia |
| GET | `/api/analytics/heatmap` | Mapa de calor de intensidad HPM |
| GET | `/api/analytics/shots` | Historial de disparos |
| GET | `/api/export` | Exporta disparos o eventos del log en CSV |

### Validación científica

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/calibracion` | Verifica en caliente que la calibración contra arXiv:2602.08477 sigue vigente |
| GET | `/api/sensibilidad` | Análisis de sensibilidad global (Morris + Sobol) — qué parámetro no calibrado domina la varianza |
| GET | `/api/dosis-respuesta` | Recupera por máxima verosimilitud la curva dosis-respuesta real del motor y la contrasta contra la configuración |
| GET | `/api/subsistemas` | Desglose de probabilidad de daño por subsistema (Tabla 1 del paper) a una distancia dada |

### Experimentación (Monte Carlo y coevolución)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/experiments` | Lanza un experimento Monte Carlo en background (réplicas headless) |
| GET | `/api/experiments` | Lista los experimentos registrados con su estado y progreso |
| GET | `/api/experiments/{id}` | Estado, progreso y estadística agregada de un experimento |
| GET | `/api/experiments/{id}/preview` | Fotogramas de la réplica 0, si se lanzó con `con_preview=true` |
| POST | `/api/coevolucion/start` | Arranca una corrida de coevolución genética arma↔enjambre |
| GET | `/api/coevolucion/status/{id}` | Progreso y, al completar, la frontera de Pareto |
| GET | `/api/coevolucion/preview/{id}` | Fotogramas del enfrentamiento final campeón vs. campeón |

### Escenarios y demo

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/scenarios` | Lista los escenarios predefinidos de `data/scenarios/` |
| POST | `/api/scenarios/{id}/load` | Carga un escenario: formación, cantidad y parámetros HPM |
| GET | `/api/demo/config` | Configuración de la demo automática |
| POST | `/api/demo/start` | Inicia la demo automática (enjambre + misil tras un delay) |

Formaciones soportadas (`formacion` en `/api/start`, escenarios y el selector del panel): `cuadrada`, `circular`, `aleatoria`, `linea`, `v`.

### Ejemplos

```bash
# Iniciar simulación con formación en V
curl -X POST http://localhost:8000/api/start \
  -H "Content-Type: application/json" \
  -d '{"formacion": "v", "cantidad": 20}'

# Disparar HPM
curl -X POST http://localhost:8000/api/fire \
  -H "Content-Type: application/json" \
  -d '{"potencia": 50, "direccion": 90}'

# Acelerar la simulación a 10x
curl -X POST http://localhost:8000/api/speed -H "Content-Type: application/json" -d '{"escala": 10}'

# Cargar un escenario predefinido
curl -X POST http://localhost:8000/api/scenarios/ataque_circular/load

# Consultar drones
curl http://localhost:8000/api/drones

# Plan de tiro optimizado (WTA) con costo-intercambio
curl http://localhost:8000/api/targeting/plan

# Lanzar un experimento Monte Carlo de 50 réplicas
curl -X POST http://localhost:8000/api/experiments \
  -H "Content-Type: application/json" \
  -d '{"n_replicas": 50}'
```

## WebSocket

Conecta a `ws://localhost:8000/ws` para recibir snapshots de la simulación en tiempo real (60 FPS cuando está activa).

Mensajes soportados del cliente:
- `ping` → respuesta `pong`
- `status` → snapshot inmediato

## Panel táctico (frontend)

El panel se organiza en cuatro pestañas:

- **Operación** — mapa 3D (Three.js, cámara orbital libre y vista superior),
  drones representados como conos que cambian de color según estado
  (activo, dañado, neutralizado), estela y onda de choque del misil,
  pulso del cañón al disparar, controles de armamento y formación,
  control de velocidad de simulación (1x/2x/5x/10x) y métricas en vivo
  (drones activos/neutralizados, tasa de éxito, energía, munición).
  Incluye la tarjeta "Validez del modelo": distancia del vehículo al
  dron activo más cercano comparada contra el rango calibrado real, para
  saber en todo momento si la simulación está operando dentro de su
  rango validado.
- **Planificación** — plan de asignación arma-blanco (WTA) con
  costo-intercambio por baja esperada, ejecutable directamente desde el
  panel (incluye la cesión de blanco entre los dos nodos de defensa).
- **Laboratorio** — experimentos Monte Carlo y coevolución genética
  arma↔enjambre en background, con reproducción 2D de réplicas,
  análisis de sensibilidad global (Morris + Sobol), curva
  dosis-respuesta recuperada del motor real y desglose de daño por
  subsistema (modelo de 5 subsistemas de la Tabla 1 del paper).
- **Análisis** — historial de disparos, curva de efectividad por
  distancia, mapa de calor de intensidad HPM y espectro de frecuencias.

Todos los iconos de la interfaz son SVG en línea (`frontend/js/icons.js`,
un único sprite compartido), sin dependencias externas ni fuentes de
iconos de terceros.

## Pruebas

```bash
pytest tests/ -v
```

25 módulos de prueba cubren el motor de simulación, la física de daño y
detección, el optimizador de asignación arma-blanco, el motor de
experimentos y coevolución, y la API REST. Cada feature del proyecto
incorpora sus propios tests de regresión al implementarse — no hay una
fase de "escribir tests después" separada.

## Escenarios

En `data/scenarios/` hay escenarios JSON predefinidos, cargables desde la API (`GET /api/scenarios`, `POST /api/scenarios/{id}/load`) o desde el selector "Escenario predefinido" del panel:
- `enjambre_cuadrado` — formación cuadrada de 50 drones
- `ataque_circular` — 100 drones en círculo
- `dispersion_aleatoria` — 30 drones aleatorios

## Documentación e investigación

Este proyecto mantiene su propio registro de auditoría científica: qué
está verificado contra literatura publicada, qué es una aproximación de
diseño declarada, y qué inconsistencias se encontraron (incluida una en
el propio paper de referencia).

| Documento | Contenido |
|---|---|
| [`docs/FISICA_Y_MATEMATICA.md`](docs/FISICA_Y_MATEMATICA.md) | Cada fórmula del simulador, su procedencia y su estado de calibración |
| [`docs/PROYECTO_Y_CAPACIDADES.md`](docs/PROYECTO_Y_CAPACIDADES.md) | Arquitectura completa, qué puede y no puede derribar el sistema (con números), aplicación en contexto |
| [`docs/ESTADO_DEL_ARTE_HPM.md`](docs/ESTADO_DEL_ARTE_HPM.md) | Panorama real de programas militares, mercado e investigación académica en HPM |
| [`docs/ESTADO_DEL_ARTE_BIOMIMESIS.md`](docs/ESTADO_DEL_ARTE_BIOMIMESIS.md) | Respaldo biológico/dinámico del modelo de comportamiento del enjambre |
| [`docs/GLOSARIO.md`](docs/GLOSARIO.md) | Cada término técnico explicado en lenguaje simple |
| [`docs/EXPLICACION_PARA_EXPOSICION.md`](docs/EXPLICACION_PARA_EXPOSICION.md) | El proyecto explicado de cero, en orden, para exponer |
| [`docs/ROADMAP_CIENTIFICO.md`](docs/ROADMAP_CIENTIFICO.md) | Por qué y en qué orden se abordó cada mejora |
| [`docs/REFERENCIA_PAPER_2602.08477.md`](docs/REFERENCIA_PAPER_2602.08477.md) | Parámetros de referencia extraídos del paper, con procedencia verificada |
| [`docs/HALLAZGO_TABLA1_VS_TABLA3.md`](docs/HALLAZGO_TABLA1_VS_TABLA3.md) | Inconsistencia interna detectada en el paper de referencia, aislada y documentada |
| [`research/`](research/) | Notas de investigación independientes (barrido depredador-presa, sesgos de estimación en Monte Carlo) |

## Licencia

MIT
