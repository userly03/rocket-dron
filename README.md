# Simulador de Guerra Electromagnética (EW)

Simulador en Python de contramedidas HPM (High Power Microwave) contra enjambres de drones. Incluye motor de simulación a 60 FPS, API REST con FastAPI, transmisión en tiempo real por WebSocket y un panel táctico web con **mapa 3D (Three.js)** para operarlo visualmente.

## Arquitectura

```
simulador-ew/
├── src/
│   ├── main.py              # Servidor FastAPI + uvicorn
│   ├── config.py            # Variables de entorno
│   ├── models/              # Drone, Swarm, HPMWeapon, HPMissile, HPMissileSystem
│   ├── engine/               # Simulación (bucle 60 FPS), física, motor HPM, analíticas
│   ├── api/                  # REST (routes.py) + WebSocket (websocket.py)
│   └── utils/                 # Helpers geométricos
├── frontend/
│   ├── index.html            # Panel táctico (mapa 3D, controles, métricas, gráficos)
│   ├── css/style.css         # Tema táctico militar
│   └── js/
│       ├── render3d.js       # Escena Three.js: drones, HPM, misiles, efectos (módulo ES)
│       ├── script.js         # Orquestación principal, estado, demo, controles
│       ├── websocket.js      # Cliente WS con reconexión automática
│       ├── charts.js         # Gráficos 2D de efectividad/heatmap/espectro (analítica, no espacial)
│       └── vendor/three/     # Three.js + OrbitControls vendorizados (sin bundler)
├── data/scenarios/           # Escenarios JSON predefinidos (cargables desde la API)
├── tests/
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

Edita `.env`:

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
| `HPM_ORIGIN_X` / `HPM_ORIGIN_Y` / `HPM_ORIGIN_Z` | Posición del cañón HPM | 0 / 0 / 8 |
| `HPM_FREQUENCY_GHZ`, `HPM_COUPLING_K`, `HPM_PULSE_DURATION_NS`, `HPM_BEAM_SIGMA` | Parámetros del panel físico/analíticas (modelo gaussiano de referencia, no el `friis`/`legacy` de arriba) | 2.45, 0.42, 100, 50 |
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
python3 -m http.server 5501
```

y abrí `http://localhost:5500/index.html` (el frontend asume el backend en `localhost:8000`).

Para apuntar el frontend a un backend en otro host/puerto (útil en desarrollo), usá el query param `?api=`:
```
http://localhost:5500/index.html?api=http://localhost:8001
```

## API REST

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/health` | Liveness check |
| GET | `/api/status` | Snapshot completo de la simulación (drones, HPM, misiles, analíticas, logs) |
| POST | `/api/start` | Inicia la simulación (opcionalmente reconfigura `formacion`/`cantidad`, cada uno independiente) |
| POST | `/api/stop` | Pausa la simulación |
| POST | `/api/reset` | Reinicia la simulación al estado inicial |
| POST | `/api/speed` | Ajusta el multiplicador de velocidad de la simulación (`{"escala": 1\|2\|5\|10}`, rango 0.1–10) |
| POST | `/api/fire` | Dispara el cañón HPM estático (cono direccional) |
| GET | `/api/drones` | Lista de drones con posición y estado |
| GET | `/api/logs` | Últimos eventos registrados |
| POST | `/api/missile/launch` | Lanza un misil HPM (apunta automático al centroide del enjambre si no se indica ángulo) |
| GET | `/api/missile/status` | Estado y lista de misiles activos |
| GET | `/api/missile/munition` | Munición restante |
| POST | `/api/missile/reload` | Recarga munición |
| GET | `/api/analytics` | Panel físico, métricas de energía, curva de efectividad, heatmap y espectro |
| GET | `/api/analytics/effectiveness` | Curva de efectividad por distancia |
| GET | `/api/analytics/heatmap` | Mapa de calor de intensidad HPM |
| GET | `/api/analytics/shots` | Historial de disparos |
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
```

## WebSocket

Conecta a `ws://localhost:8000/ws` para recibir snapshots de la simulación en tiempo real (60 FPS cuando está activa).

Mensajes soportados del cliente:
- `ping` → respuesta `pong`
- `status` → snapshot inmediato

## Panel táctico (frontend)

- **Mapa 3D**: escena Three.js con cámara orbital libre (arrastrar para rotar/zoom) y un botón **"Vista superior"** para volver a una vista cenital. Drones como conos verdes (amarillo si están dañados — parpadean —, rojo si son neutralizados: parpadean, caen y quedan marcados en el suelo). El misil HPM se ve como un cono con estela cian que se desvanece; al detonar genera una onda de choque expansiva (anillos morado/cian) y activa una breve cámara lenta local. El cañón HPM dispara un pulso expansivo naranja en su origen.
- **Modos de vista**: Táctico, Físico (superpone el mapa de calor de intensidad HPM como textura sobre el terreno 3D) y Espectro (gráfico de perfil de frecuencia).
- **Controles**: cañón HPM (potencia/dirección), misil HPM (potencia/radio/dirección o auto-apuntado), formación (cuadrada/circular/aleatoria/línea/V) y cantidad de drones, carga de escenarios predefinidos, **control de velocidad de simulación (1x/2x/5x/10x)**, iniciar/pausar/reiniciar.
- **UI organizada**: las métricas clave (drones activos, tasa de éxito, munición) están siempre visibles arriba; el panel "Modelo Físico" (frecuencia, sigma, k de acoplamiento) y el panel "Analítica" (gráficos e historial) son **colapsables** para no saturar la pantalla. Los botones y métricas tienen tooltips explicativos.
- **Métricas en vivo**: drones activos/neutralizados, tasa de éxito, energía acumulada, pico de potencia, munición restante (con aviso visual cuando queda poca o se agota).
- **Demo automática**: al cargar la página arranca un enjambre circular y lanza un misil tras un conteo regresivo visible en el banner superior (configurable con `AUTO_DEMO_ENABLED` / `DEMO_MISSILE_DELAY_S`).

### Cómo probar cada mejora

| Mejora | Cómo verla |
|---|---|
| Mapa 3D | Cargar el panel — el mapa táctico ya es una escena 3D. Arrastrar con el mouse para rotar/zoom. |
| Vista superior | Click en "🎥 Vista superior" en el header del mapa — cámara cenital real. |
| Velocidad de drones realista | Iniciar la simulación y observar el movimiento (10–30 m/s en vez de 3–8). |
| Formaciones nuevas | Elegir "Línea" o "V" en el selector de Formación y presionar "Iniciar simulación". |
| Control de velocidad | Botones 1x/2x/5x/10x en la sección Simulación — el tiempo simulado avanza más rápido. |
| Misil visible + estela | Lanzar un misil (auto-apuntado o manual) — se ve el cono rojo con estela cian. |
| Detonación / onda de choque | Esperar a que el misil llegue al enjambre (o a los ~30s de tiempo de vuelo máximo) — anillos morado/cian expansivos + cámara lenta breve. |
| Neutralización (parpadeo + caída) | Requiere que un impacto realmente neutralice un dron (ver nota de balance del modelo HPM arriba); al ocurrir, el dron parpadea rojo, cae y queda marcado en el suelo. |
| Paneles colapsables | Click en "⚛️ Modelo Físico" o "📈 Analítica" para expandir/contraer. |
| Escenarios predefinidos | Elegir uno en "Escenario predefinido" y click en "📂 Cargar escenario". |
| Reinicio | Click en "♻️ Reiniciar" (pide confirmación). |

## Pruebas

```bash
pytest tests/ -v
```

## Escenarios

En `data/scenarios/` hay escenarios JSON predefinidos, cargables desde la API (`GET /api/scenarios`, `POST /api/scenarios/{id}/load`) o desde el selector "Escenario predefinido" del panel:
- `enjambre_cuadrado` — formación cuadrada de 50 drones
- `ataque_circular` — 100 drones en círculo
- `dispersion_aleatoria` — 30 drones aleatorios

## Licencia

MIT
