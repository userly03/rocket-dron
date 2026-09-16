# Seguimiento: papers, hallazgos y frontend pendiente

Documento único para no perder el hilo. Se actualiza cada vez que algo
cambia de estado. Todo lo de acá tiene el detalle completo en
`ESTADO_DEL_ARTE_HPM.md`, `ESTADO_DEL_ARTE_BIOMIMESIS.md` y
`research/NOTA_ESTIMADOR_CIEGO.md` — esto es el mapa corto para ubicarse.

---

## 1. Papers — estado y para qué sirve cada uno

### 1.1 HPM / daño en drones — verificados, usables

| Paper | Qué aporta | Sirve para |
|---|---|---|
| Mao et al. (2023), IEEE Trans. Plasma Science | Hardware real: drones irradiados, fallan ESC y motor de rotor | Validar cualitativamente el subsistema ESC. **Falta el PDF completo** (paywall IEEE) |
| Xing et al. (2025), Micromachines | GaN HEMT (componente del ESC): sobrevive 800 pulsos a 42.5 dBm, falla en 10 a 43 dBm | Calibración de componente para ESC — transición abrupta real |
| Zhao, J. et al. (2025), Scientific Reports | GaN HEMT: quemado catastrófico a ~53 dBm (~200W), mecanismo de avalancha | Segundo punto de calibración de ESC, mecanismo distinto al de Xing |
| Zhao, J. et al. (2022), Scientific Reports | GaN HEMT: interferencia/corrimiento de umbral, NO destructivo | Contexto del mecanismo previo al quemado; no es específico de drones |
| Khalil, Wang, Choi, arXiv:2510.16495 (v2) | Framework independiente, umbrales en energía de pulso (J), sensibilidad: alcance domina | Contraste metodológico — otra forma de medir lo mismo |
| Lee et al. (2026), Drones (MDPI) | Mecanismo "soft-kill": corrupción de PWM, 55 kV/m, RECUPERABLE con reinicio | Confirma que existe un mecanismo distinto al térmico — pero a un campo 2 órdenes de magnitud arriba del umbral de daño del proyecto (487 V/m). **No aplica al rango de operación del arma modelada** |
| Kubacki et al. (2025), Electronics (MDPI) | Umbrales EMC reales: 10 V/m (estándar), 15-30 V/m (disrupción), 200 V/m (militar) | Chequeo de orden de magnitud del umbral de *upset* ya calibrado del proyecto (154 V/m) — no lo recalibra con precisión, pero confirma que no es descabellado |
| Yang et al. (2024), J. Electromagnetic Eng. and Science | Cámara CMOS: 40.4 kV/m para 95% interrupción funcional, pulso corto | Mismo patrón que Lee et al. — mecanismo real, campo muy por encima del rango del proyecto |
| Micromachines 17(9):1054 (2025) | LNA de RF (GaAs pHEMT, no específico de GPS): quemado a 45 dBm/2GHz/43ns | Componente análogo al de GPS/GNSS LNA, mecanismo similar al de ESC |
| Du, Xia, Huang, Mao, Cui, Fang, Nie (2022), Energies | LNA de RF bajo inyección de corriente HEMP: umbral de daño por norma vectorial, validado con microscopía óptica | Tercer punto de calibración para la línea GPS/GNSS LNA — metodología de equivalencia entre pulso de inyección y HEMP real |

### 1.2 Descartados o marcados como alerta

- **"GPS LNA burnout ≈ 150 V/m"** (de una búsqueda web): es el mismo número de la Tabla 1 del paper cuestionado (arXiv:2602.08477) reapareciendo en el resumen de búsqueda — **circular, no es fuente independiente**. Descartado.
- **Revista *Iranian Journal of Chemical and Chemical Engineering*** publicando sobre EMP en drones — revista fuera de campo, señal de bajo estándar. Descartado.
- **arXiv:2306.05111** ("AutoCharge") — el usuario lo encontró pero es sobre estaciones de carga autónoma para drones, sin relación con HPM/EMP. Descartado.

### 1.3 Encontrados, no verificados (paywall/bloqueo)

- *"Investigation on Falling and Damage Mechanisms of UAV Illuminated by HPM Pulses"* (ResearchGate).

### 1.4 Huecos reales — todavía sin buen paper

- **BMS/MOSFET**: sigue sin cerrar tras una segunda ronda. El usuario bajó 5
  PDFs candidatos; ninguno sirve como umbral de calibración:
  - `energies-15-01409.pdf` (Du et al. 2022) — real, pero es sobre un LNA de
    RF, no un MOSFET de potencia. Se suma a la línea de GPS/GNSS (§1.1) en
    vez de a BMS.
  - `electronics-13-01414-v3.pdf` (Grome & Ji, RPI/LLNL) — MOSFET de
    potencia SiC, pero el mecanismo de falla es radiación espacial (rayos
    cósmicos), no campo electromagnético. Mismo componente, amenaza
    distinta — no calibra nada, pero da contexto de la física de
    avalancha/quemado si algún día se modela.
  - `energies-18-05915.pdf`, `irps_full_length.pdf`, `P2_2.pdf` —
    descartados: clasificación de baterías con IA, recuperación inversa
    bajo conmutación normal, y caracterización RF de MOSFET para modelado
    de circuitos, respectivamente. Ninguno mide daño por HPM/EMP.
  - **Conclusión**: dos rondas de búsqueda (web + PDFs bajados a mano) no
    encontraron literatura de daño por HPM/EMP específica para MOSFET de
    BMS. Es un hueco de la literatura en sí, no de la búsqueda — se declara
    como límite conocido y no bloquea nada del trabajo de frontend.
- **Flight controller** bajo onda continua: nada más allá del mecanismo de Lee et al. (pulsado).
- **Mao et al. 2023 completo**: seguimos sin el PDF (paywall IEEE Xplore).

### 1.5 Biomimesis — verificados

| Paper | Qué aporta | Estado de aplicación |
|---|---|---|
| Chen & Kolokolnikov (2014), arXiv:1403.3250 | Régimen no monótono: fuerza del depredador determina escape/confusión/persecución/captura | Barrido corrido — ver §6. No apareció la curva de 4 regímenes (el arma no persigue, a diferencia del modelo del paper), pero sí una transición real de meseta baja→alta en formación compacta |
| Olson et al. (2013), arXiv:1209.3330 | Confusión del depredador basta para evolucionar enjambramiento (algoritmo evolutivo) | Anclaje teórico para P3-B (coevolución), ya implementado — no cambia código |
| Attanasi et al., Nature Physics / arXiv:1303.7097 | Ondas de agitación en bandadas: la alarma se propaga más rápido que el grupo | **Implementado** — ver §6, `flocking.propagate_alarm` (P2-E, Parte 4) |
| Nature Communications (raptores, PMC9399121) | Rapaces reales apuntan a un punto fijo del enjambre, no persiguen individuos | Valida una decisión ya tomada: `HPMissileSystem.lanzar` ya apunta al centroide — no requiere cambio |

---

## 2. Qué hicimos esta sesión (para no repetirlo)

1. Cerramos las 5 piezas del audit de frontend (riesgo latente, radar/tracks,
   WTA, laboratorio, coevolución genética) — todo commiteado y verificado
   en vivo en el navegador.
2. Escribimos `research/NOTA_ESTIMADOR_CIEGO.md` (+ traducción al inglés,
   sin publicar) — el hallazgo del estimador Monte Carlo ciego,
   autocontenido, no depende de ninguna fuente externa.
3. Catalogamos y verificamos 9 papers de HPM/daño en drones (con texto
   completo de 10 de los ~11 PDFs que el usuario descargó).
4. **Nos corregimos dos veces en el camino** (parte del método, no un
   error a esconder): primero, un análisis apurado que decía que el
   "soft-kill" era una brecha del proyecto — resultó ser el ítem `P2-D`,
   ya cerrado. Segundo, una comparación de escalas de campo mal hecha
   (55 kV/m de Lee et al. contra 487 V/m del proyecto, dos órdenes de
   magnitud de diferencia, no "el mismo patrón").
5. Barrimos literatura para los 4 subsistemas restantes del modelo de
   daño (GPS, cámara, flight controller, BMS) — 2 confirmaciones nuevas,
   1 alerta de circularidad descartada, 2 huecos honestos.
6. Catalogamos 4 papers de biomimesis/dinámica de enjambres, con
   distinción clara entre lo que ya está implementado, lo que es solo
   anclaje teórico, y una brecha real encontrada (propagación de alarma).

**Nada de la investigación de papers tocó código todavía** — todo quedó en
`docs/` y `research/`, documentado y citable, a la espera de decidir qué
vale la pena portar.

---

## 3. Frontend — qué falta exponer

- **Panel "Experimentos Monte Carlo"** — **CERRADO.** Expone
  `/api/experiments` (el estimador corregido: `fraccion_media` + IC por
  bootstrap, CV, percentiles, con la métrica vieja `aniquilación total` al
  lado para que se vea la diferencia). Backend sin cambios, solo UI nueva
  (`.lab-block` en el panel Laboratorio + polling cada 1s, mismo patrón que
  la coevolución). Verificado en vivo en el navegador: 20 réplicas con
  misil dieron `fraccion_media=0.0233` (IC 0.0133-0.0333) mientras la
  métrica vieja seguía en `0.0000` (IC Wilson 0-0.1611) — la misma corrida,
  la diferencia es solo qué se decide medir.

Nada de lo investigado sobre papers (HPM de otras fuentes, biomimesis)
tiene todavía una pieza de código que mostrar en el frontend — son
hallazgos de literatura, no features implementadas. El único candidato de
esa línea que SÍ tocaría código (y por lo tanto eventualmente el frontend)
es la propagación de alarma entre drones (§1.5, brecha real de
`P2-E`) — pero no está implementado, es una idea evaluada, no una función
existente sin exponer.

**Pendiente de decisión, no de investigación**: BMS/MOSFET y Mao et al.
siguen abiertos (§1.4), sin bloquear nada — quedan a la espera de que el
usuario consiga algo nuevo.

---

## 4. Reordenamiento UI/UX — CERRADO

Auditoría, propuesta y navegación real en 4 vistas
(Operación/Planificación/Análisis Físico/Laboratorio), todo implementado.
Detalle completo en `docs/PROPUESTA_UI_REORDENAMIENTO.html` (la propuesta
original) y el commit `c767a73` (la implementación).

Dos bugs reales aparecieron al reorganizar y se corrigieron en el camino,
ninguno estaba en el plan original:
- `charts.js::resizeCanvas` daba ancho negativo cuando la pestaña de
  Análisis Físico estaba oculta (los charts se actualizan en vivo sin
  importar qué tab está activo).
- `drawHeatmap` no distinguía "sin datos todavía" de datos reales — ahora
  muestra un mensaje explícito.

Y una consecuencia de UX detectada y resuelta: mover el plan WTA a
Planificación significaba que "Ejecutar Plan" (dispara tiros reales) ya
no estaba en la misma pantalla que la animación del cañón — se agregó un
salto automático a Operación al ejecutar.

Verificado en vivo en el navegador: consola limpia en las 4 vistas, todas
las transiciones de tab, el toggle Táctico/Calor 3D, y un disparo de
cañón real de punta a punta.

---

## 5. Reproducción visual de una réplica (Monte Carlo + coevolución) — CERRADO

Pedido del usuario: que Laboratorio no se sienta "una terminal" — no solo
números, sino ver drones/misiles/cañón moviéndose, igual que en Operación,
pero de una corrida ya calculada (Monte Carlo P1-A o el enfrentamiento
final de la coevolución P3-B).

**Backend** (`src/engine/experiments.py::run_replica`): flag opcional
`frames_out` — cada `frame_stride` ticks agrega un `_build_snapshot()` (el
mismo formato que ya usa `/ws` en vivo) a la lista. Efecto puramente
aditivo: no toca el generador aleatorio ni el resultado numérico de la
réplica (verificado con test: misma semilla, con y sin captura, resultado
idéntico byte a byte). Se aplica SOLO a la réplica 0 de cada corrida, el
resto sigue corriendo exactamente igual de rápido que antes.

- Monte Carlo (`ExperimentManager`): nuevo flag `con_preview` en
  `POST /api/experiments`, nuevo `GET /api/experiments/{id}/preview`.
- Coevolución (`coevolucion_jobs.py`): apenas el job marca "completado",
  se dispara UNA réplica extra (mejor arma vs. mejor defensa encontradas)
  con captura — "así pelea lo que el GA encontró", no una de las réplicas
  de fitness internas. Nuevo `GET /api/coevolucion/preview/{job_id}`.
  Puede tardar unos segundos más en estar `disponible` que el job en sí
  (es una corrida posterior, no bloquea el resultado).

**Frontend**: `frontend/js/replay2d.js`, nuevo — canvas 2D liviano
(fábrica, no singleton: dos instancias independientes, una por motor).
Deliberadamente NO reusa el motor 3D de Operación (`render3d.js`): ese es
un singleton de Three.js atado a un solo canvas — reusarlo exigiría
refactorizarlo primero a algo instanciable. Colores calcados de
`render3d.js::COLOR` para consistencia visual con el mapa en vivo actual;
se migran juntos si más adelante cambia la paleta de la app. Reproductor
con play/pausa + slider, recorre fotogramas ya calculados (no simula nada
en el cliente).

Verificado en vivo en el navegador de punta a punta para AMBOS motores:
Monte Carlo (cañón, formación circular, se ve el cono naranja del disparo)
y coevolución (formación evolucionada, marcador de origen HPM) — consola
sin errores en ninguno de los dos. Tests nuevos:
`tests/test_experiments.py::TestReplica::test_captura_de_frames_no_altera_el_resultado`,
`TestExperimentManager::test_con_preview_captura_solo_la_replica_0`,
`tests/test_coevolution.py::TestJobDeCoevolucionEnBackground::test_status_no_arrastra_frames_pero_preview_si`.

Pendiente, no bloqueante: si más adelante el 2D se siente pobre al lado
del mapa 3D real, evaluar refactorizar `render3d.js` a instanciable y
reusarlo acá — decisión que se dejó para después de verlo andar, tal como
se planteó.

---

## 6. Migración de paleta — CERRADO

Implementación de `docs/propuesta_identidad_visual.html` (la propuesta que
ya se le había mostrado al usuario). Separa dos roles que antes competían
por el mismo verde neón:

- **Acento de interfaz** (`--accent`, azul #4F8FC4): navegación, botones
  de sistema, foco, sliders — "esto es lo que opero yo".
- **Colores de ESTADO** (`--status-*`): activo=verde `#4CAF6E`,
  neutralizado=rojo `#E0574F`, riesgo/dañado/pausado=ámbar `#E0A23D`,
  misil/pista/física=verde azulado `#3FB8AE` — mismo mapeo semántico de
  antes (no se tocó qué significa cada color de dron), solo desaturado de
  neón a un registro serio.

Se migró TODO junto, no solo `style.css` — si no, hubiera quedado una
mezcla rara (chrome nuevo, mapa 3D viejo):
- `frontend/css/style.css` — tokens de `:root` renombrados/redefinidos,
  cada uso de `var(--accent-green)` reclasificado a mano como interfaz o
  estado (no fue un find-replace ciego).
- `frontend/js/render3d.js` — paleta `COLOR` del mapa táctico 3D (lo que
  el usuario más tiempo mira). Además: `hpmOrigin` pasó de verde-estado a
  azul-interfaz (es NUESTRO sistema, no un estado del enjambre).
- `frontend/js/charts.js` y `frontend/js/replay2d.js` — mismos tokens.

**Bugs/inconsistencias reales encontrados en la auditoría (no en el plan
original), corregidos en el camino:**
- La luz ambiental y direccional de la escena 3D (`AmbientLight`/
  `DirectionalLight`) tenían tinte verde (`0x445544`/`0xbfffcf`) — se
  filtraba a CADA material de la escena, no solo a los que son verdes a
  propósito. Neutralizado.
- `.metric-energy` tenía un color hardcodeado (`#ffaa00`) que no usaba
  ninguna variable — habría quedado desincronizado del resto de la
  paleta. Ahora usa `var(--accent-orange)`.
- Dos tokens casi duplicados para "advertencia" (`--accent-yellow` y
  `--accent-amber`, dos amarillos casi idénticos para conceptos distintos
  pero nunca mostrados en conflicto) — unificados en un solo
  `--status-warn`.
- Tres lugares con `rgba(42, 74, 42, 0.3)` hardcodeado (el equivalente
  RGB del viejo `--border-color`, no una referencia a la variable) que
  habrían quedado con un borde verde fantasma tras la migración.
- Dos partículas/efectos del mapa 3D (quemado de dron, pulso del cañón)
  usaban hex sueltos en vez de referenciar `COLOR.*` — ahora apuntan a
  `COLOR.neutralizadoBlink`/`COLOR.hpmCone`, una sola fuente de verdad.

Verificado en vivo en el navegador: Operación (mapa 3D, panel de
control completo, botones cañón/misil/recarga/start/stop con
`getComputedStyle` confirmando cada color nuevo), Análisis Físico (los 3
charts), Laboratorio (paneles + reproductor de réplica con la paleta
nueva) — consola limpia en las tres pestañas.

No incluido en este alcance (el usuario pidió específicamente la paleta):
la iconografía sigue en emoji — esa es una pieza más grande (20+ lugares)
que se evaluó por separado en la propuesta original, pendiente de que el
usuario la pida.

---

## 7. Iconografía — CERRADO

Reemplazo de los ~28 emoji distintos de la UI por un set propio de
iconos de línea (24×24, trazo, sin relleno salvo acentos puntuales) —
la otra mitad de `docs/propuesta_identidad_visual.html`.

**Arquitectura**: un solo sprite (`<svg><defs><symbol id="i-nombre">`) al
principio de `frontend/index.html` — una sola fuente de verdad para la
forma de cada ícono. Se consume con `<use href="#i-nombre">` tanto desde
HTML estático como desde HTML generado en JS (nuevo
`frontend/js/icons.js`, expone `Icon(nombre)`); ningún ícono está
duplicado en dos lugares. `.icon`/`.icon-fill` en `style.css` gobiernan
tamaño (1em, escala con el texto) y si es trazo o relleno.

**Bug real encontrado y corregido en el camino**: varios botones
(`runLabButton`, el botón de plan WTA, el de reproducción de réplica)
guardaban y restauraban su texto con `btn.textContent` para mostrar
"CALCULANDO..." durante una espera. Con el ícono ahora dentro del botón
como HTML, `textContent` lo habría descartado silenciosamente — el botón
habría perdido su ícono para siempre después del primer uso. Se cambiaron
esos 3 lugares a `.innerHTML` antes de que el bug llegara a verse.

**Segundo problema encontrado (de diseño, no de código)**: los íconos de
llama y misil, dibujados como un único contorno cerrado "de silueta",
casi no se veían al quedar sin relleno (el resto del set usa trazo, sin
relleno, por diseño). Se rediseñaron: la llama como dos curvas anidadas
(mismo patrón que usa Lucide), el misil como líneas separadas (cono +
guías + ventana) en vez de un cuerpo cerrado — ambos verificados de nuevo
en el navegador después del cambio.

Verificado en vivo: sprite carga sin roture, los 48 `<use>` del HTML
estático resuelven contra un símbolo real (0 faltantes), los íconos
generados dinámicamente (dado/ADN en la lista de corridas, cañón/misil en
el historial de disparos, reloj de arena/check/alerta en badges de
estado, play/pausa en el reproductor) probados disparando corridas reales
— consola limpia en todo el recorrido.

---

## 8. Biomimesis — de literatura a código: propagación de alarma + barrido

Las dos piezas de investigación biomimética que quedaban abiertas (§1.5),
ambas cerradas.

### 8.1 Propagación de alarma entre vecinos — CERRADO

Brecha real de literatura (Attanasi et al., ondas de agitación en
bandadas de estorninos) implementada: `src/engine/flocking.py::
propagate_alarm` (P2-E, Parte 4), nueva constante `BOIDS_ALARM_
PROPAGATION_GAIN=0.7` en `src/config.py`. Un dron sin amenaza propia
adopta la del vecino más alarmado dentro de `BOIDS_NEIGHBOR_RADIUS`,
atenuada por la ganancia — reusa la misma red de vecinos que ya usan
separación/alineación/cohesión, sin topología nueva. Actualización
SINCRÓNICA (snapshot de intensidades antes de propagar, no valores ya
actualizados en la misma llamada): la onda avanza un salto por tick, no
varios de golpe según el orden de iteración.

`compute_headings` sigue siendo de solo lectura — la mutación de
`amenaza_*` vive en `propagate_alarm`, llamada desde `Swarm.
actualizar_amenazas` (mismo método que ya hacía decaer la memoria; orden:
decaer primero, propagar después, para no "revivir" una amenaza vieja al
contagiarla a un valor más alto del que le queda a ella misma).

5 tests nuevos en `tests/test_opfor.py::TestPropagacionDeAlarma`,
incluyendo el central: un dron que **nunca fue impactado directamente**
—solo contagiado— se dispersa más del punto de impacto que en un control
idéntico con la ganancia en 0 (mismo patrón falsable que ya usaba P2-E
Parte 2). 27/27 tests de `test_opfor.py` pasan, sin regresiones.

### 8.2 Barrido depredador-presa (Chen & Kolokolnikov) — CERRADO

`research/barrido_depredador_presa.py` + `research/
BARRIDO_DEPREDADOR_PRESA.md` (nota completa con números, IC95% y
discusión). 540 réplicas reales (18 puntos × 30 réplicas, formación
cuadrada vs. circular × 9 potencias, 10-100 kW, a `DISTANCIA_COMBATE_M`
=60m con cañón pulsado — la misma geometría que ya validó P3-B).

**Resultado, honesto**: en formación cuadrada aparece una transición real
(con IC95% que NO se superponen) de meseta baja (10-40kW, ~0.009-0.016)
a meseta alta (80-100kW, ~0.031-0.032) — no una rampa lineal simple, pero
tampoco la curva de 4 regímenes con caída intermedia que predice el paper
para SU modelo (que tiene un depredador persiguiendo activamente; el
cañón acá dispara una vez y no persigue — sección 4 de la nota explica
por qué es razonable no ver esa forma exacta). En formación circular la
señal es demasiado ruidosa (CV 1.8-5.5) para afirmar nada con 30
réplicas — reportado como límite de resolución, no como hallazgo.

---

## 9. Misión ofensiva del enjambre — "¿por qué los drones no atacan?"

Motivado por una pregunta directa del usuario, evaluando el proyecto como
lo haría un evaluador externo: el enjambre era prey puro, patrullaba sin
misión — "¿lo pararon a tiempo?" no era una pregunta que el modelo
pudiera responder. Cerrado en 3 fases.

### 9.1 Motor — CERRADO (ver commit `feat(swarm): misión ofensiva`)

El enjambre avanza hacia un objetivo (por defecto, el propio arma —
"ataca la batería que lo enfrenta"). Un dron que llega queda marcado
`objetivo_alcanzado` (eje ortogonal a salud/enlace, mismo criterio que
P2-E) y deja de volar — es una BRECHA, no una baja.

Dos fallas reales encontradas y corregidas en el diseño, antes de dar
el mecanismo por terminado:
1. Avanzar solo el ancla de cohesión no alcanza — `_home_vector` da
   fuerza cero dentro de su radio (es un límite, no una meta); el
   enjambre quedaba orbitando el objetivo para siempre.
2. Un primer término de atracción nuevo, con peso "razonable" (del orden
   del resto de los pesos de boids), tampoco alcanzaba — la separación
   entre drones comprimidos hacia el mismo punto crece a la par y empata
   la atracción antes de que lleguen. Hizo falta un peso ~4x más fuerte
   (`BOIDS_MISSION_WEIGHT=8.0`, empírico) para que la atracción
   realmente gane — verificado con 10 y con 50 drones, convergencia
   limpia en 60-80s, sin oscilación.

Activado por defecto SOLO en la app en vivo — Monte Carlo y coevolución
NO, para no invalidar en silencio la calibración ya hecha con el
enjambre estático. 8 tests nuevos, suite completa sin regresiones.

### 9.2 Frontend mínimo — CERRADO

Sin esto, la app en vivo (que ahora mueve al enjambre por defecto) se
vería como un bug — drones agrupándose y "desapareciendo" cerca del
arma sin explicación. Nueva métrica "Brechas" en Operación, un dron que
llega pasa a un naranja distintivo en el mapa 3D (con su propio estallido
de partículas, no cae al piso — cumplió la misión, no lo derribaron),
entrada nueva en la leyenda y en el registro de eventos. Verificado en
vivo: demo real acumuló 36 brechas visibles antes de que se agotara el
tiempo de prueba.

### 9.3 Monte Carlo — CERRADO

`ExperimentConfig.con_mision` (opt-in, apagado por defecto). Punto de
diseño importante: el objetivo tiene que seguir la posición REAL del
arma en la réplica (`WeaponPolicy.origen_x/y`, como reubica P3-B), no el
`HPM_ORIGIN_X/Y` global — si no, con la geometría que usa la coevolución
(arma reubicada a `DISTANCIA_COMBATE_M`=60m) el enjambre terminaría
atacando un punto a 707m de donde el arma realmente está. Se sincroniza
explícitamente después de aplicar cualquier override de posición.

Mismo par primaria/secundaria que ya usa P1-A: `fraccion_alcanzo_
objetivo_media` (continua, bootstrap) y `probabilidad_brecha` (Bernoulli
por réplica — ¿llegó al menos uno?, Wilson) — la pregunta operacional
real, expuesta en `/api/experiments` y en el panel de Laboratorio con un
checkbox nuevo ("El enjambre ataca"). 4 tests nuevos (incluye uno que
prueba explícitamente que resultados de ANTES de este ítem, sin los
campos nuevos, no rompen `_summarize`). Verificado en vivo en el
navegador con y sin el checkbox activado, consola limpia.

### 9.4 Coevolución contra la brecha — CERRADO

Pedido explícito del usuario ("que la coevolución evolucione también
contra probabilidad_brecha"), la extensión que 9.3 dejó deliberadamente
afuera hasta que se pidiera a propósito.

`evaluar_enfrentamiento(...)` (la función que usan los ~10 tests
existentes y los dos experimentos de control de una sola población) NO
cambió ni de firma ni de comportamiento. La extensión vive en funciones
nuevas y paralelas: `_evaluar_enfrentamiento_con_mision(...)` (devuelve
`(fraccion_media, fraccion_alcanzo_objetivo)` del mismo lote de réplicas,
sin costo extra de simulación) y `_fitness_arma`/`_fitness_defensa`, que
con `con_mision=False` devuelven la señal cruda de siempre (byte a byte
igual que antes) y con `con_mision=True` promedian 50/50 con la señal de
misión: el arma contra "impidió la brecha" (`1 - fraccion_alcanzo`), la
defensa contra "llegó" (`fraccion_alcanzo`).

Por qué 50/50 y no otro peso: no hay evidencia para preferir un término
sobre el otro — neutralizar más no es lo mismo que impedir que lleguen
(un arma lenta puede neutralizar bastante y aun así dejar pasar al
resto) — y pesarlos distinto sin medir algo sería inventar un número,
lo mismo que este proyecto evita en el resto de sus constantes.

La frontera de Pareto (`puntos_arma`/`puntos_defensa`, y por lo tanto
`frontera_pareto_arma`/`frontera_pareto_defensa` en el JSON) sigue
guardando SIEMPRE `fraccion_media`/`supervivencia` crudas, nunca el
fitness combinado — para que esas etiquetas del JSON sigan significando
lo que dicen, con o sin misión. El fitness combinado gobierna selección
y reproducción del GA, pero no lo que se reporta como "fracción
neutralizada" o "supervivencia".

Hallazgo geométrico observado y NO corregido a propósito: con formaciones
grandes (P3-B usa `DISTANCIA_COMBATE_M=60m`, formaciones de 20-37+ drones
con 30m de espaciado pueden abarcar 180m+ de lado), algunos drones nacen
ya casi sobre el objetivo — se vieron brechas a `t=0.00s` en pruebas de
humo. No se tocó `DISTANCIA_COMBATE_M` ni la geometría de spawn para
"arreglarlo": cambiar esa constante invalidaría en silencio toda la
calibración previa de P1-A/P3-B y el barrido de potencia del depredador.
Queda documentado como una característica real del modelo a esa
distancia de combate, no como un bug.

Wiring end-to-end: `ExperimentConfig.con_mision` → `coevolucionar(...,
con_mision=...)` → `iniciar_job(..., con_mision=...)` (job en background,
incluida la réplica de muestra campeón-vs-campeón, que ahora también
respeta la bandera) → `POST /api/coevolucion/start` (`con_mision`,
apagado por defecto) → checkbox nuevo en el panel de Laboratorio
("Evolucionar también contra la brecha"). `resumen_json` expone
`fraccion_alcanzo_objetivo` en `mejor_arma_final`/`mejor_defensa_final` y
las series `fraccion_alcanzo_arma_por_generacion`/`..._defensa_...` —
`None` (no `0`) cuando `con_mision=False`, para no leer "el mejor arma
encontrada no impidió ninguna brecha" cuando en realidad la corrida ni
siquiera midió eso.

14 tests nuevos en `test_coevolution.py` (fórmulas de fitness en
aislado, `_evaluar_enfrentamiento_con_mision`, reproducibilidad byte a
byte con `con_mision=True`, `con_mision=False` idéntico al comportamiento
de antes de este ítem, y dos tests end-to-end contra el endpoint del
job). Suite completa sin regresiones. Verificado en vivo en el
navegador: corrida con el checkbox activado mostró "arma — 8.6% del
enjambre le llegó igual al objetivo; defensa — 13.8% de su enjambre
llegó al objetivo" en el resultado, coincidiendo exactamente con lo que
devolvió la API; corrida con el checkbox apagado no mostró ese bloque y
`con_mision: false`/campos `null` en la respuesta — consola sin errores
en ambos casos.

### 9.5 Kamikaze — el dron que llega inutiliza la plataforma de verdad — CERRADO

Hasta acá "brecha" (9.4) era una marca estadística — el dron llegaba, se
congelaba, no le pasaba nada al cañón. Pedido explícito: que llegar
inutilice la plataforma de verdad, no solo se registre.

`HPMWeapon.destruido`/`HPMissileSystem.destruido` (ambos `False` por
defecto): el primer dron que llega al objetivo (ver
`SimulationEngine._registrar_impactos_en_objetivo`) marca los dos, y se
quedan así — no se "enfrían" solos como el presupuesto de energía/
temperatura, necesitan `reset()`. `disparar()`/`lanzar()` rechazan por el
mismo canal que ya usaban para energía/temperatura agotada (mensaje en
`ultimo_rechazo`/`result["message"]`, sin excepción) — cero cambios en
`fire()`/`launch_missile()` ni en las rutas.

Gateado por `kamikaze_activo` (opt-in, `False` por defecto), **separado**
de `mision_activa`/`con_mision`: los experimentos Monte Carlo/coevolución
que ya usan `con_mision=True` miden `fraccion_alcanzo_objetivo`/
`probabilidad_brecha` asumiendo que el arma sigue disparando el resto de
la réplica después de una brecha — activar esto ahí cambiaría esos
resultados en silencio. Solo la app en vivo (`src/main.py`) lo activa.
Vehículo y lanzador comparten emplazamiento (mismo `HPM_ORIGIN_X/Y/Z`),
así que un impacto los deja a los dos fuera de servicio, no solo el
cañón.

En el camino se encontró un bug real preexistente, no introducido por
esto: el botón "DISPARAR CAÑÓN" nunca revisaba si el backend rechazaba
el disparo (`/api/fire` devuelve 200 OK con un mensaje de rechazo, no un
error HTTP — a propósito, el plan WTA depende de ese contrato) — el log
siempre decía "Cañón disparado" aunque el arma no hubiera hecho nada. Con
energía/temperatura era un descuido menor y transitorio; con "destruido"
(permanente) se vuelve mucho más engañoso, así que se corrigió ahí
mismo. El botón de misil no tenía este problema (esa ruta sí usa
`HTTPException`).

Frontend: el vehículo 3D se ennegrece (`Chasis`/`Torreta`/`EmisorHPM`/
`AcentoEnergia` — no ruedas/radar, que no tienen que ver con el impacto)
la primera vez que `snap.hpm.destruido` pasa a `true`, con un estallido
de partículas. Sincronizado desde el SNAPSHOT, no solo desde el evento
de log (`logs_recientes` solo trae lo reciente — un cliente que recién
conecta después del impacto no vería el log, pero sí sigue viendo
`snap.hpm.destruido`).

6 tests nuevos (`tests/test_opfor.py::TestKamikaze`), 160 tests de todos
los archivos que tocan `HPMWeapon`/`HPMissileSystem` sin regresiones.
Verificado en vivo: reset+start real (no forzado a mano), la misión
convergió y destruyó la plataforma a los t=45s — vehículo se puso negro
en el mapa 3D, "DISPARAR CAÑÓN" y "LANZAR MISIL" mostraron el rechazo
correcto en el log, reset por API lo reparó (`destruido: false` de
nuevo). Hallazgo honesto sin corregir: con `kamikaze_activo` puesto, la
demo en vivo pierde el arma de forma permanente de manera bastante
confiable a los 45-90s de arrancar — es la misma convergencia rápida ya
documentada en 9.1, ahora con una consecuencia irreversible en vez de
solo estadística. No es un bug, es el ritmo real que da esta calibración
combinado con esta característica nueva — mencionado acá por si en algún
momento se quiere ajustar el ritmo del "primer combate" de la demo.

### 9.6 Vehículo móvil — "shoot and scoot" — CERRADO

Pedido explícito, y resuelve por su cuenta la objeción física que yo
mismo había puesto contra un vehículo móvil: un HPM real no puede apuntar
con precisión en movimiento, pero SÍ puede reposicionarse ENTRE
disparos — es la doctrina real de sistemas de defensa aérea de corto
alcance (Pantsir y similares): se mueven, se detienen, recién ahí operan.

`HPMWeapon.destino_x/y` (`None` = quieto) + `iniciar_movimiento`/
`actualizar_movimiento(dt)`, llamado desde `HPMWeapon.actualizar` (mismo
método que ya avanzaba enfriamiento/recarga cada tick). A
`VEHICULO_VELOCIDAD_M_S=8.3` (~30km/h, crucero campo traviesa de un
vehículo rastreado liviano — elegido para no competir en velocidad con
el propio avance del enjambre, `SWARM_AVANCE_VELOCIDAD_M_S=20`, o dejaría
de leerse como "reposicionar la batería" y pasaría a ser una
persecución). `listo_para_disparar()`/`disparar()` rechazan en tránsito
por el mismo canal que ya usaban destruido/energía/temperatura; el
lanzador de misiles no tiene su propio `origen_x/y` (recibe la posición
del cañón en cada lanzamiento), así que se gatea aparte en
`SimulationEngine.launch_missile`. El jammer comparte vehículo — su
`origen_x/y` se sincroniza con el del cañón cada tick.

Decisión de diseño confirmada explícitamente con el usuario (no asumida):
el objetivo del enjambre (misión ofensiva) sigue la posición ACTUAL del
vehículo, no la de cuando arrancó la simulación — barato de implementar
(sobreescribir `swarm.objetivo_x/y` cada tick si `mision_activa`), y con
una consecuencia táctica real y no trivial: mudarse hacia el lado del
mapa donde está el enjambre ACELERA el kamikaze en vez de evitarlo,
verificado en vivo (moví el vehículo, el enjambre redirigió de inmediato
y lo alcanzó bastante antes de lo que hubiera tardado quieto). Es
comportamiento emergente correcto, no un bug — confirma que el sistema
de misión y el de movimiento están genuinamente conectados.

Hallazgo honesto, no decidido a propósito, dejado tal cual: si el
kamikaze destruye la plataforma MIENTRAS está en tránsito, el vehículo
de todos modos termina de llegar a destino — la destrucción apaga el
emisor (`disparar()`/`lanzar()` rechazan), no el motor/tren de rodaje
(`actualizar_movimiento` no chequea `destruido`). Defendible como está
(el impacto fue sobre el emisor específicamente, según el propio mensaje
de rechazo), pero no fue una decisión explícita — si en algún momento se
quiere que un vehículo destruido quede totalmente inmóvil, es un chequeo
de una línea.

Frontend: botón "MOVER PLATAFORMA" arma un modo de click-en-el-mapa
(`activarModoMover` en render3d.js, raycasting contra el plano del
suelo, conversión a coordenadas del mundo); badge del panel alterna
"Estático"/"En movimiento" leyendo directo del snapshot (no del estado
que se congela mientras el usuario arrastra un slider); posición del
vehículo suavizada con el mismo criterio de lerp que ya usan los drones,
para que no salte entre snapshots.

9 tests nuevos (`tests/test_opfor.py::TestVehiculoMovil`), 210 tests de
todo lo que toca `HPMWeapon`/`SimulationEngine` sin regresiones.
Verificado en vivo end-to-end: click en el mapa → POST /api/hpm/mover →
vehículo visible moviéndose en el mapa 3D, badge y estado del panel
correctos, "DISPARAR CAÑÓN"/"LANZAR MISIL" rechazados mientras viaja,
llega exacto al destino elegido y vuelve a poder disparar, reset lo
devuelve al origen.

### 9.7 Edificios atacables — motor cerrado, falta visual y línea de vista — PARCIAL

Pedido explícito: un pueblito de edificios que el enjambre también pueda
elegir atacar, cada uno con su propia salud (a diferencia del vehículo,
un solo impacto kamikaze). Alcance confirmado con el usuario antes de
programar: 3-5 edificios ("un pueblito chico"), layout que yo diseño.

`src/models/structure.py` — `Estructura`: posición fija, `salud`/
`salud_maxima`, `recibir_impacto_kamikaze(daño)` (default
`ESTRUCTURA_DANO_POR_DRON=25`, 4 drones en promedio para tirar una,
número elegido — no medido — para que sea un objetivo con cuerpo pero
alcanzable por una fracción razonable del enjambre, no todo entero).
Layout: 4 edificios agrupados cerca de (800,800), esquina OPUESTA al
vehículo (que arranca en `HPM_ORIGIN`=(0,0)) — a propósito, para que el
enjambre tenga una elección táctica real entre dos direcciones, no un
objetivo "de paso".

`SimulationEngine._elegir_objetivo_enjambre()` (nuevo, corre cada tick si
`mision_activa`): entre el vehículo (si no destruido) y cada estructura
no destruida, elige la más cercana al ANCLA de cohesión del enjambre
(`swarm.formacion_x/y`, no un dron individual — es el punto que el
modelo de movimiento realmente usa). Guarda cuál quedó activo en
`_objetivo_actual` para que `_registrar_impactos_en_objetivo` sepa a
quién dañar cuando llega un dron: si el objetivo activo era el vehículo,
kamikaze (9.5) sin cambios; si era una estructura, le resta salud por
CADA dron que llega ese tick (no solo el primero, como el vehículo). Un
dron ya marcado `objetivo_alcanzado` no se ve afectado si el objetivo
cambia después (redirige el resto del enjambre, no a los que ya
llegaron). Si todo lo destruible ya cayó, el enjambre se queda sin
objetivo (`objetivo_x/y=None`) — mismo estado ya manejado que
`mision_activa=False`, sin caso especial.

`estructuras_activas` (opt-in, `False` por defecto, deliberadamente
APARTE de `mision_activa`/`con_mision` — mismo criterio que
`kamikaze_activo`): Monte Carlo/coevolución con `con_mision=True` asumen
un único objetivo posible; agregar estructuras ahí cambiaría en silencio
qué miden `fraccion_alcanzo_objetivo`/`probabilidad_brecha`. Solo la app
en vivo lo activa.

15 tests nuevos (`TestEstructura` + `TestEstructurasAtacables`), 145
tests de todo lo que toca `SimulationEngine`/experimentos sin
regresiones. Verificado en vivo con la demo real corriendo sola (sin
forzar nada a mano): el enjambre arrancó atacando el pueblito (más
cerca que el vehículo desde su punto de partida), tiró el primer
edificio a los t=33s, los 4 a los t=41s, y redirigió solo hacia el
vehículo apenas no quedó nada más que atacar — comportamiento emergente
correcto, no forzado. Snapshot (`GET /api/status`) ya expone
`estructuras` y `mision.objetivo_tipo/objetivo_id`; probado que no rompe
el frontend actual (consola limpia) aunque todavía no dibuja nada nuevo.

**Falta, deliberadamente pospuesto** (confirmado con el usuario, se hace
en fases — línea de vista ya cerrada, ver 9.8; scripts de Blender para
los modelos 3D ya escritos, ver 9.9): la integración visual del
frontend (cargar `arboles.glb`/`edificio.glb`/`trinchera.glb` en
`render3d.js`, clonar una instancia por `Estructura` del snapshot,
reflejar salud/destrucción visualmente, dispersar árboles/trinchera
como props decorativos). El motor ya funciona y está probado
independientemente de que exista lo visual.

### 9.8 Línea de vista física — CERRADO

La otra mitad del pedido "terreno físico, no solo decorativo" (9.7):
edificios/árboles bloqueando el haz de verdad, no solo existiendo como
objetivo atacable.

`hpm_engine.linea_de_vista_bloqueada(origen_x, origen_y, destino_x,
destino_y, obstaculos)` — intersección segmento-círculo estándar
(fórmula cuadrática), `obstaculos` una lista de `(x, y, radio)`.
Simplificación deliberada y documentada: el chequeo es 2D en el plano
del suelo, sin altura de obstáculo ni trayectoria 3D del rayo — mismo
criterio que "sin near-field" en `docs/FISICA_Y_MATEMATICA.md` §4 (no
inventar un dato — altura de edificio — que no está medido). Bloqueo
BINARIO (todo o nada), no atenuación graduada — a 2.45GHz un edificio
real no deja pasar una fracción "razonable" de la señal, y un
coeficiente de atenuación parcial sería un número inventado.

Conectado en los TRES subsistemas que "ven" al enjambre, cada uno con
`obstaculos: list | None = None` (default = cero obstáculos, idéntico a
antes de esto para todo llamador existente):
- `HPMWeapon.disparar()`: un dron geométricamente en el cono pero
  detrás de un obstáculo NO recibe daño — ni se llama
  `drone.recibir_daño` (cero efectos secundarios en salud/riesgo
  latente). Sigue apareciendo en `eventos` con `"bloqueado": true` y
  `probabilidad`/`neutralizado` en 0/False, para que quede visible que
  estaba en el cono pero protegido, no que el arma lo ignoró.
- `HPMissile.detonar()`: mismo criterio, para la detonación de área.
- `TrackManager.actualizar()` (radar): un dron detectable por SNR pero
  detrás de un obstáculo NO se detecta esta revisita — un radar real
  tampoco ve a través de un edificio.

`SimulationEngine._obstaculos_activos()` ensambla la lista desde
`self.estructuras` no destruidas (`Estructura.radio_bloqueo`, nueva
constante `ESTRUCTURA_RADIO_BLOQUEO_M=12`, más chico que el radio de
impacto de la misión a propósito — "esto bloquea físicamente un haz" es
un círculo más ajustado que "llegaste y contás como que llegaste"). Una
estructura destruida deja de bloquear — un edificio caído no es un
obstáculo sólido.

**Bug real encontrado de paso, no introducido por esto**: el radar
(`Swarm.actualizar` → `track_manager.actualizar`) usaba SIEMPRE
`HPM_ORIGIN_X/Y` (la constante fija), incluso después de que el
vehículo se hubiera reposicionado (9.6, "shoot and scoot") — quedaba
mirando desde el punto viejo. `Swarm.actualizar()` ganó
`origen_radar_x/y` (`None` default = comportamiento idéntico al de
antes), y `SimulationEngine._tick` ahora pasa la posición ACTUAL del
vehículo. Verificado con un test dedicado (mover el vehículo, dejarlo
avanzar, confirmar que un dron cerca del nuevo origen se detecta — si el
radar siguiera mirando desde el viejo, no lo haría).

17 tests nuevos (`tests/test_linea_de_vista.py`, geometría + los tres
subsistemas + integración vía `SimulationEngine`), 287 tests de todo lo
que toca cañón/misil/radar/swarm/experimentos sin regresiones, suite
completa corrida en background sin regresiones. Verificado con llamadas
directas al motor real (mismo método exacto que usa `/api/fire` — no un
mock): dron detrás de un edificio, visto desde el cañón, sale
`bloqueado=true`, salud sin tocar; dron no alineado dispara normal;
radar no detecta detrás de un obstáculo y sí sin él. No se pudo
"cazar" en vivo por HTTP un disparo bloqueado ocurriendo naturalmente
durante la demo (la ventana geométrica exacta — un dron pasando justo
detrás de un edificio en el ángulo del cañón — es angosta y la
convergencia de la misión es rápida, mismo problema de timing ya
documentado en 9.1/9.5), pero el código que corre por HTTP es
literalmente el mismo que se probó directo.

### 9.9 Modelos 3D de escenario (árboles, edificio, trinchera) — CERRADO

Segunda mitad de 9.7/geografía general: los tres scripts de Blender
para el escenario rural (referencia visual "pueblo disperso, estilo
guerra rural"), mismo patrón que `generar_lanzador_hpm.py`/
`generar_dron.py` (materiales locale-safe por `node.type`/
`input.identifier`, nunca por nombre visible — Blender en español
rompe la búsqueda por nombre en silencio).

- `tools/blender/generar_arboles.py` → `frontend/models/arboles.glb`:
  3 variantes (bajo/mediano/alto) en un solo archivo — tronco cónico
  de 8 lados + racimo de 2-3 icoesferas de follaje con jitter
  (`random.Random(2026)`, semilla fija para reproducibilidad), dos
  tonos de verde alternados. El frontend elegirá una variante al azar
  por posición para que una fila de árboles no se vea repetida.
- `tools/blender/generar_edificio.py` → `frontend/models/edificio.glb`:
  casa rural atacable (ver `Estructura`, 9.7) con techo a dos aguas de
  geometría real (dos paneles rotados que se encuentran en la
  cumbrera — matemática derivada a mano con `hypot`/`atan2`, no
  aproximada con una caja texturizada), chimenea, puerta y dos
  ventanas. Genera la casa intacta únicamente — el tintado por daño
  es responsabilidad de Three.js en el frontend (mismo patrón que
  `setPlataformaDestruida` del vehículo), no de este script.
- `tools/blender/generar_trinchera.py` → `frontend/models/trinchera.glb`:
  parapetos de sacos de arena (dos filas, aparejadas, con jitter de
  tamaño/posición para no leerse como clones) a los lados de una
  franja de tierra removida. Se optó por sacos + tierra removida en
  vez de una zanja cavada de verdad porque el suelo del mapa
  (`buildGround` en `render3d.js`) es un plano liso sin relieve —
  cavarlo de verdad exigiría deformar el terreno, un cambio de alcance
  mayor no pedido. Puramente decorativo por ahora: a diferencia de los
  edificios, no tiene salud ni bloquea línea de vista — eso no fue
  pedido para la trinchera específicamente (solo los edificios se
  confirmaron como "atacables con salud propia"; el terreno en general
  como "bloquea línea de vista" ya se resolvió en 9.8 vía el radio de
  bloqueo de `Estructura`, que la trinchera no tiene).

Los tres scripts se corrieron en Blender (usuario) y los `.glb`
resultantes se verificaron parseando el binario directo (header + chunk
JSON), igual que vehículo/dron — sin capturas de pantalla:
- `arboles.glb` (43.7 KB): 11 nodos (3 troncos + 8 esferas de follaje,
  2+3+3 por variante), materiales `Tronco`/`Follaje1`/`Follaje2` con
  color correcto (sin el gris `[0.8,0.8,0.8]` del bug de locale).
- `edificio.glb` (37.1 KB): 7 nodos (`Edificio`, `Techo_Izquierdo/
  Derecho`, `Chimenea`, `Puerta`, `Ventana_Izquierda/Derecha`),
  materiales `Pared`/`Techo`/`Madera`/`Hueco` correctos.
- `trinchera.glb` (730 KB): 95 nodos (`Trinchera` + 47 sacos por lado,
  24+23, en 2 filas aparejadas), materiales `Saco`/`TierraRemovida`
  correctos.

Integración visual en `frontend/js/render3d.js` (mismo módulo IIFE,
mismo patrón que vehículo/dron — `GLTFLoader` una vez, `clone(true)` +
clonado de materiales por instancia):
- **Edificios**: un `edificioTemplate` cargado una vez; cada
  `Estructura` del snapshot (`snap.estructuras`) clona su propia
  instancia la primera vez que aparece, en su posición real (fija, no
  como los drones). Salud/destrucción se reflejan sobre esa MISMA
  instancia cada tick — tiñendo gradualmente "Pared"/"Techo" hacia un
  negro humo (`0x14100c`) proporcional a `1 - salud/salud_maxima`, y
  "hundiendo" el modelo (`scale.y` hacia 0.25) cuando `destruida=true`
  — mismo criterio barato que la caída de un dron: comunica destrucción
  sin necesitar un modelo de escombros aparte. Un `spawnParticleBurst`
  marca el momento exacto de la destrucción. Como lee `snap.estructuras`
  en cada `updateSnapshot`, un `reset()` del backend (salud vuelve a
  máxima, `destruida=false`) se refleja solo, sin lógica extra en
  render3d.js.
- **Árboles**: sin entidad en el backend (ver 9.9), así que se
  dispersan en el CLIENTE, una sola vez, con un PRNG determinista
  (`mulberry32`, semilla 2026 — misma semilla que los scripts de
  Blender, por consistencia, no reproducibilidad científica: esto es
  puramente decorativo) apenas se conocen el tamaño real del campo y
  las posiciones reales de vehículo/estructuras — para no hacer brotar
  un árbol encima de un edificio o del vehículo (radios de exclusión
  45m/35m). 55 árboles, variante elegida al azar entre las 3 del
  `.glb`, escala/rotación con jitter para no leerse como clones.
- **Trinchera**: un único emplazamiento, colocado una vez 25m por
  delante de la posición INICIAL del vehículo (hacia el centro del
  campo, de donde viene el enjambre por defecto) — NO sigue al vehículo
  si este se reposiciona después ("shoot and scoot", 9.6): una
  trinchera real se cava una vez, no se reubica sola.

Verificado en vivo (Chrome, backend real corriendo, demo activa): los 5
`.glb` (dron/lanzador/edificio/árboles/trinchera) cargan con HTTP 200,
consola sin errores. "Ver plataforma" mostró el vehículo Y la trinchera
juntos, correctamente posicionados/orientados uno junto al otro. Los
árboles se ven dispersos en la vista general (no se pudo acercar la
cámara lo suficiente para confirmar su geometría en detalle por una
limitación de la herramienta de automatización del navegador — el
wheel-zoom de OrbitControls no respondió a los eventos simulados — pero
cargan sin error y reutilizan exactamente el mismo código de
instanciación ya confirmado funcionando para la trinchera).

**Falta**: nada pendiente de esta fase. Como trabajo futuro (no pedido
todavía): dar a la trinchera un `radio_bloqueo` propio si se decide que
también debe bloquear línea de vista (hoy no lo hace — ver la
justificación en el propio script), y/o un toggle de UI para
mostrar/ocultar árboles si el mapa se siente sobrecargado.

### 9.10 Relieve del terreno (colinas) y textura de tierra — CERRADO

El usuario reportó que la textura de tierra de 9.9 se veía mal (se leía
como estática de TV, no tierra) y preguntó, como decisión de diseño, si
convenía modelar colinas en Blender en vez de solo "pintar" el piso.

**Decisión: relieve real en Three.js, NO en Blender.** El piso se genera
por código (`buildGround()` en `render3d.js`) porque tiene que ajustarse
al tamaño de campo que reporte el backend (`FIELD_WIDTH/HEIGHT`,
configurable) — un mesh de colinas modelado a mano en Blender con una
forma fija se vería estirado/deformado si el campo cambia de tamaño. La
alternativa correcta es desplazar en altura los vértices del mismo plano
que ya existía.

- `alturaTerreno(wx, wy)`: dos octavas de ruido "valor" (grilla de
  `mulberry32` interpolada con smoothstep — no es Perlin/simplex de
  verdad, pero alcanza para colinas suaves sin sumar una librería
  externa) — una de longitud de onda grande (colinas, ~11m de amplitud)
  y otra más fina encima (ondulación, ~2.5m). Semillas fijas,
  reproducible entre recargas.
- `PlaneGeometry` del piso ahora tiene segmentos reales (no un solo
  quad) y `aplicarRelieveTerreno()` desplaza cada vértice según
  `alturaTerreno()`.
- **Puramente visual, no física**: línea de vista, movimiento y radar
  siguen siendo 2D sobre el plano x/y — mismo criterio que la
  simplificación ya documentada en `hpm_engine.linea_de_vista_bloqueada`
  (no modelar algo sin un dato medido detrás). El raycasting de "click
  para mover" (`configurarClickParaMover`) también se queda
  deliberadamente sobre un plano flat en y=0, no sobre la malla con
  relieve — el modelo de movimiento es 2D, intersectar la malla real no
  cambiaría nada salvo agregar complejidad.
- Vehículo, edificios, árboles y trinchera ahora se "apoyan" en
  `alturaTerreno()` en vez de asumir y=0 — sin esto quedarían flotando o
  hundidos en las colinas. La grilla/el borde tácticos se quedan PLANOS
  a propósito (referencia de coordenadas tipo HUD, no terreno físico).

**Textura**: el intento original (grano per-píxel de alta frecuencia, o
blobs grandes con opacidad alta) o se leía como estática de TV o tapaba
la base entera (una "alfombra caqui" uniforme). La solución fue generar
un canvas CHICO (20×20) con una mota de color pesada hacia la base
oscura (~78% de probabilidad) por celda, escalado hacia un canvas grande
con suavizado de imagen activado — el navegador interpola linealmente
entre celdas, dando manchas difusas orgánicas sin dibujar a mano
cientos de blobs. Selección de color a propósito PESADA (no uniforme)
porque el suavizado promedia colores vecinos: si la base oscura y los
parches claros aparecen con la misma frecuencia, el promedio termina
siendo un tono parejo, no "tierra oscura con parches ocasionales".

**Hillshading analítico**: el piso usa `MeshBasicMaterial` (sin luz —
con la iluminación tan tenue de esta escena, un material que sí
reacciona a la luz volvía el patrón invisible, más oscuro que el plano
de color original que reemplazaba). Pero eso significa que el relieve,
aunque geométricamente real, es invisible a simple vista desde arriba —
un material sin luz no sombrea laderas solo. Se calculó un sombreado a
mano (color de vértice) por diferencias finitas de altura + producto
punto contra una luz falsa fija — técnica estándar de mapas de relieve
(hillshade). Dos ajustes necesarios, verificados numéricamente antes de
tocar el navegador (no a ojo): (1) colinas de 11m sobre celdas de ~166m
tienen una pendiente real de ~6%, que da un contraste de sombreado
prácticamente invisible — hubo que EXAGERAR la pendiente ×10 solo para
el cálculo de la normal de sombreado (la altura real de la malla no se
toca); (2) sobre una textura tan oscura (valores ~10-40 de 255), un
rango de brillo sutil (0.55x-1.1x) se traduce en 2-3 unidades de
diferencia — invisible en la práctica — así que el rango final es mucho
más ancho (0.2x-1.6x), con las sombras poniéndose bien oscuras en vez de
las laderas poniéndose más claras que el registro oscuro del resto de
la escena.

Verificado en vivo (Chrome, backend real corriendo): sin errores de
consola, el vehículo se apoya correctamente sobre el relieve en la vista
cercana ("Ver plataforma"), y el sombreado de colinas se nota en la
vista táctica de arriba sin tapar la lectura de los drones.

**Bug real encontrado con auditoría numérica antes de comitear (no a
ojo)**: `alturaTerreno()` tilea la octava de ondulación fina ×3 con
`(u*3) % 1` para que se repita más seguido que las colinas grandes —
pero `crearRuidoValor()` generaba una grilla de valores independientes
sin que el borde derecho/inferior coincidiera con el izquierdo/superior,
así que en los límites de cada tile (`field.width/3`, `2×field.width/3`,
mismo en Y) el ruido saltaba entre dos celdas de grilla NO
relacionadas. Medido: la pendiente ahí era ~10x más empinada que la
pendiente típica — con el hillshading tan exagerado de este mismo ítem
(ver arriba), eso se iba a leer como una línea de sombra recta cruzando
el mapa en esos tres puntos fijos, un defecto claramente artificial (no
orgánico) fácil de notar en la vista táctica. `crearRuidoValor()` ganó
un parámetro `periodico` (fuerza los bordes de la grilla a repetir el
lado opuesto — topología de toro, técnica estándar para ruido tileable)
y `ruidoOndulacion` lo usa; `ruidoColinas` no lo necesita porque no se
tilea. Verificado numéricamente (script standalone, no en el navegador)
que el salto en la costura bajó de ~10x a ~0.06x el gradiente típico
antes de volver a probar en Chrome.

**Otros hallazgos de la auditoría, documentados pero NO corregidos
(trade-offs conscientes, no bugs)**:
- La textura de tierra (`crearTexturaTerreno`) tiene el mismo problema
  de fondo en teoría — el canvas base de 20×20 tampoco es tileable de
  verdad — pero al ser grano fino y mayormente aleatorio (no una
  pendiente con dirección), el defecto se disuelve en el ruido en vez de
  leerse como una línea recta. Se podría aplicar la misma técnica de
  toro si en algún momento se nota, no fue necesario acá.
- `snap.field` puede en teoría cambiar en runtime (`updateSnapshot`
  reasigna `field` si difiere) pero HOY ningún escenario cambia
  `FIELD_WIDTH/HEIGHT` — es código muerto, no alcanzable. Si algún día
  se agrega un escenario con otro tamaño de campo, la malla del piso
  (construida una sola vez en `buildGround()`) quedaría con el tamaño
  viejo mientras `alturaTerreno()` (recalculada cada tick para el
  vehículo) usaría el tamaño nuevo — vehículo y piso visualmente
  desincronizados. No se corrigió porque hoy es inalcanzable; dejar
  documentado para no repetir la investigación si se agrega esa
  feature.

**Mejoras propuestas y aplicadas** (pedidas explícitamente por el
usuario tras la auditoría):
1. **Luz del hillshading sincronizada con el sol real de la escena**:
   `_luzRelieve` ya no es una dirección inventada aparte — se deriva de
   `sun.position` en `init()` (con el mismo intercambio de ejes que usa
   `worldToThree`, documentado ahí). Coherencia visual, sin costo.
2. **Toggle de UI "Relieve"** (`frontend/index.html`, checkbox
   `toggle-relieve`, junto a "Mostrar tracks"): `Render3D.setRelieveVisible(bool)`
   apaga/prende SOLO el color de sombreado (`colorAttr.array`), no la
   geometría — las colinas reales siguen ahí, solo deja de notarse a
   simple vista. Pensado para si el contraste del hillshading termina
   compitiendo con la lectura de drones en escenarios densos.
3. **Los árboles ahora excluyen la trinchera**: antes solo evitaban
   pisar edificios/vehículo — se extrajo `calcularPosicionTrinchera()`
   de `colocarTrinchera()` para que `dispersarArboles()` pueda calcular
   la MISMA posición (sin duplicar la fórmula) y agregarla a la lista de
   exclusión (radio 25m).

### 9.11 Auditoría de backend — CERRADO

Pedido explícito del usuario tras cerrar el relieve del terreno: auditar
el backend (~12.000 líneas) con el mismo rigor que el frontend —
verificar con ejecución/cálculo real, no a ojo. Se repartió en 3 forks en
paralelo por subsistema (física central: `hpm_engine.py`/`physics.py`/
`propagation.py`/`radar_engine.py`; orquestación y modelos: `simulation.py`
+ todos los `src/models/*.py`; capa de análisis: `targeting.py`/
`coevolution.py`/`experiments.py`/`sensitivity.py`/`analytics.py`/
`parametros.py`/`validation.py`/`reproducibilidad.py`), más una revisión
directa propia de `config.py` (930 líneas) y la capa de API
(`routes.py`/`websocket.py`/`coevolucion_jobs.py`), que ningún fork cubría.

**Conclusión general**: este backend ya venía con un nivel de auditoría
y documentación inusualmente alto — el trail de comentarios referencia
ítems de auditoría previos (P0-B, P1-A a P1-F, P2-A a P2-G, P3-A/B) y
cada constante no trivial cita su fuente (paper, derivación propia, o
valor de ingeniería declarado como tal). Ningún fork encontró una
constante sin justificación. Los tres bugs reales encontrados son
estructurales (estado no sincronizado/no reseteado), no errores de la
física en sí.

**Bugs reales, verificados y corregidos**:
1. **`simulation.py::_build_snapshot()` — el snapshot del radar
   reportaba un origen FIJO** (`HPM_ORIGIN_X/Y`) en vez de la posición
   real del vehículo (`self.hpm.origen_x/y`) — la física de detección ya
   seguía al vehículo movido (fix de esta sesión, §9.8), pero el campo
   de DISPLAY que lee `render3d.js` para dibujar el anillo/ping de
   barrido se había quedado con las constantes viejas: el mismo patrón
   corregido en un lugar y no buscado en los demás. Verificado antes del
   fix moviendo el vehículo a (400,0) y comparando `hpm.origen_x` real
   (82.99 tras 10s) contra `snapshot.radar.origen_x` (0.0).
2. **`simulation.py::reset()` no reiniciaba `swarm.objetivo_x/y`** — se
   reinicia `_objetivo_actual` pero el objetivo real del enjambre solo
   se recalcula dentro de un tick corriendo (`_elegir_objetivo_enjambre`),
   que no corre mientras la simulación está detenida. Entre un `reset()`
   y el próximo `start()`, `/api/status` podía mostrar un objetivo de
   misión de la corrida anterior. Se autocuraba en el primer tick si
   `mision_activa`, pero mentía mientras tanto.
3. **`radar_engine.py::TrackManager` nunca corregía `track.z`**, solo
   x/y/vx/vy/ax/ay — quedaba congelado en la altitud que tenía el dron
   al momento de adquirir el track, para siempre (el dron sí varía en Z:
   `DRONE_BOB_AMPLITUDE_M=4` de oscilación constante,
   `DRONE_LOST_LINK_DESCENT_RATE_M_S=2.0` si pierde enlace). Inerte hoy
   (los dos consumidores de `posicion_para()` descartan el tercer valor
   explícitamente), pero una trampa real para quien extienda la guía
   del misil a 3D asumiendo que está vivo. Fix mínimo: `track.z` se
   refresca DIRECTO a la altitud real en cada revisita (no filtrado con
   α-β-γ como x/y — no hay `vz`/`az` en `Track`, así que no hay nada que
   corregir gradualmente en esa dimensión; si se necesita z realmente
   ESTIMADO más adelante, extender el filtro en serio, no parte de este
   fix).

**Fragilidades de reproducibilidad corregidas** (no bugs hoy — el
proyecto se exige "misma semilla, mismo resultado byte a byte" y ambas
dependían de una garantía que el lenguaje no da):
4. **`targeting.py::asignar_greedy`** — el desempate entre pares con
   ganancia marginal igual iteraba `for i in libres` sobre un `set` de
   enteros; funciona hoy por un detalle de implementación de CPython
   (orden ascendente para enteros chicos), no por garantía del
   lenguaje. Cambiado a `for i in sorted(libres)`.
5. **`coevolution.py::GenomaArma`/`GenomaDefensa`** — el elitismo lleva
   el genoma campeón a la siguiente generación POR REFERENCIA, y ese
   mismo objeto queda guardado en el historial de generaciones pasadas
   ya reportado. Era seguro porque cruce/mutación siempre construían una
   instancia nueva (nunca mutaban su argumento) — salvo `_mutar_arma`,
   que SÍ mutaba `nuevo` in-place (`nuevo.duty_cycle = ...`,
   `setattr(nuevo, campo, valor)`), aunque `nuevo` era una instancia
   recién creada y no el genoma pasado, así que tampoco corrompía nada
   hoy. Se congelaron ambos dataclasses (`frozen=True`) y se refactorizó
   `_mutar_arma` para construir valores en un dict local en vez de mutar
   una instancia — con esto, un descuido futuro que mute el historial
   por accidente es un `TypeError` inmediato, no una corrupción
   silenciosa. Verificado con un smoke test directo (mutación, cruce,
   intento de asignación directa → `FrozenInstanceError` como se espera).

**Propuestas no aplicadas** (bajo impacto, quedan para más adelante si
hace falta): guardar/documentar el supuesto de que `matriz_de_bajas_
esperadas` (siembra `seed + i*1000 + j`) nunca ve más de 1000 clusters
(hoy imposible dado el tamaño de campo); test explícito para
`_build_snapshot()` llamado inmediatamente después de `reset()` sin
ticks intermedios (donde vivía el bug 2).

Verificado: 141/141 tests dirigidos (coevolución, línea de vista, radar
dinámico, simulación, targeting) y 552/552 de la suite completa, sin
regresiones.

### 9.12 Auditoría de backend, segunda ronda — CERRADO

Pedido explícito del usuario tras cerrar la primera ronda (§9.11): auditar
de nuevo, más profundo, apuntando a lo que la primera pasada no cubrió en
detalle — modelos de entidad completos, interacción entre las features
NUEVAS de esta sesión (estructuras + línea de vista + movimiento del
vehículo + misión ofensiva), calidad de la propia suite de tests, y
gestión de recursos/rendimiento con medición real. Otra vez 3 forks en
paralelo por ángulo, cada uno con instrucción explícita de traer
propuestas de mejora concretas con su razón.

**Bugs reales, verificados y corregidos:**

1. **Un dron aterrizado por falla de enlace contaba como brecha**
   (`swarm.py::_detectar_impactos_en_objetivo`). El chequeo de llegada
   excluía `NEUTRALIZADO` y `objetivo_alcanzado` previo, pero no
   `aterrizado` — justo cuando el jammer FUNCIONA (fuerza un aterrizaje
   forzoso, perfil ATERRIZAR de P2-E) y ese dron cae cerca del objetivo
   por casualidad, se contaba igual como éxito de la misión ofensiva.
   Contaminaba `probabilidad_brecha` (métrica científica reportada por
   `/api/experiments`) en el escenario exacto donde la defensa tuvo
   éxito. Fix: excluir también `drone.aterrizado`.

2. **Una estructura destruida DENTRO de un tick seguía bloqueando línea
   de vista para el resto de ESE MISMO tick** (`simulation.py::_tick`).
   `obstaculos = self._obstaculos_activos()` se calculaba una vez al
   principio del tick y se reutilizaba tal cual para
   `missile_system.actualizar_misiles()`, que corre DESPUÉS de
   `swarm.actualizar()` — que puede destruir una estructura vía impacto
   kamikaze en la misma llamada. Ventana de un tick, pero real y
   reproducible. Fix: recalcular `self._obstaculos_activos()` justo antes
   de la llamada al misil, no reusar la variable vieja.

3. **El vehículo podía autobloquearse la línea de vista** si se movía
   encima o cerca del `radio_bloqueo` de una estructura
   (`hpm_engine.py::_segmento_intersecta_circulo` + `mover_plataforma`).
   Cuando el origen del segmento cae DENTRO del círculo de un obstáculo,
   la ecuación cuadrática da bloqueado para CUALQUIER dirección — el
   vehículo "dispara a través de su propio escombro". `mover_plataforma()`
   no validaba proximidad a estructuras, así que nada impedía posicionar
   el vehículo exactamente sobre una — cañón/misil/radar quedaban ciegos
   hacia todo el mapa, permanentemente, sin ningún mensaje de error. Fix:
   `mover_plataforma()` ahora rechaza (mismo patrón que el resto del
   método: `{"success": False, "message": ...}`, ya expuesto como 400 por
   `POST /api/hpm/mover`) un destino dentro del radio de bloqueo de
   cualquier estructura NO destruida. Se rechaza en vez de recortar al
   borde más cercano: no hay un borde "correcto" obvio sin más contexto
   de hacia dónde venía el vehículo — decisión de producto que se dejó
   señalada, no una que hiciera falta inventar.

**Rendimiento, medido antes y después (no especulado):**

4. **Con 500 drones (el máximo que permite `StartRequest.cantidad`), un
   tick tardaba 235ms contra un presupuesto de 16.7ms a 60fps — ~14x
   sobre presupuesto.** `cProfile` señaló la causa exacta:
   `flocking.py::compute_headings` llamaba `np.mean`/`np.sum` UNA VEZ POR
   DRON dentro de un loop Python (separación, alineación, cohesión) — con
   500 drones son miles de llamadas numpy por tick, cada una pagando el
   overhead de despacho de un ufunc sobre un array chico, más caro que el
   cálculo en sí.

   Fix en dos pasos, cada uno verificado por separado:
   - Separación/alineación/cohesión reescritas como operaciones
     matriciales sobre TODOS los drones a la vez (`vecinos_f @ vx`, etc.)
     en vez de una reducción numpy por dron dentro del loop — la red de
     vecinos y la física de cada término son exactamente las mismas,
     cambia solo CÓMO se suma/promedia. **Verificado con equivalencia
     numérica EXACTA** contra la versión anterior (`git show HEAD:...` +
     comparación directa en 10 escenarios distintos, incluyendo n=1, n=2,
     n=500, con/sin amenaza activa, con/sin misión activa): diferencia
     máxima 0.0 grados en todos los casos. Resultado: 235ms → 76ms
     (3.1x).
   - `_girar_hacia` usaba `np.clip` sobre un ESCALAR (un solo float) para
     acotar el giro — reemplazado por `min`/`max` de Python puro
     (`angle_difference` ya devuelve un float plano, no hay nada que
     `np.clip` aporte ahí salvo overhead de ufunc). Re-verificada la
     equivalencia numérica exacta después de este segundo cambio (sigue
     en 0.0 grados). Resultado: 76ms → 70ms.

   **Estado final: 235ms → 70ms (3.3x), sigue 4.2x sobre presupuesto a
   swarm_size=500.** Con el tamaño por defecto real (`SWARM_SIZE=50`, lo
   que corre la demo/app en vivo) el margen es amplio: 2.9ms/tick, 0.18x
   del presupuesto. A 100 drones ya está al límite (0.84x); arriba de 200
   sigue por sobre presupuesto. Cerrar el resto del gap en el caso
   extremo (500) exigiría tocar más código caliente (radar, cálculo de
   acoplamiento de susceptibilidad, construcción del snapshot — todos
   aparecen en el segundo profile) — se dejó así a propósito: el hallazgo
   original apuntaba específicamente al patrón de `flocking.py`, y seguir
   optimizando código no señalado por la auditoría para un caso de borde
   que la demo real nunca alcanza sería alcance no pedido.

5. **`ExperimentManager._records` crecía sin límite**, a diferencia de
   `coevolucion_jobs.py`, que documenta el mismo trade-off ("vive en
   memoria, sin expiración") explícitamente como aceptable para una
   herramienta de un solo usuario. Con `con_preview=True` un solo registro
   puede pesar más de 1MB (fotogramas completos de una réplica), y
   `ExperimentRequest` permite `t_max_s` hasta 600s — un proceso de vida
   larga con varios experimentos largos sí acumula memoria real. Fix:
   `MAX_EXPERIMENTOS_GUARDADOS = 200`, poda los TERMINADOS
   (completado/error) más viejos al superar el techo — nunca poda uno
   corriendo. Verificado con un smoke test directo (poda los más viejos
   cuando corresponde, nunca poda uno activo).

**Gaps de test reales encontrados, NO cerrados en este ítem** (quedan
para más adelante, ya señalados con precisión si hace falta volver):
ningún test combina `mover_plataforma`/vehículo-en-movimiento con
`estructuras_activas=True` a la vez (el cruce exacto donde vive el bug 3
de esta ronda); ningún test fija como contrato explícito que un dron con
`objetivo_alcanzado=True` puede recibir fuego después y quedar contado
simultáneamente como brecha Y como neutralizado (parece el comportamiento
narrativo correcto, pero nunca se verificó a propósito).

Verificado: 230/230 tests dirigidos y 552/552 de la suite completa, sin
regresiones. Bonus no buscado: la suite completa tardó 6:14 contra los
19:46 de la corrida anterior (3.2x más rápida) — la vectorización de
`flocking.py` acelera también a los tests, que corren el motor real, no
mockeado.

### 9.13 Crítica de "científico militar" — 5 propuestas implementadas

Tras cerrar las dos rondas de auditoría, el usuario pidió una crítica
directa: "si fueses un científico militar, qué criticarías, qué
propondrías" — no más bugs, capacidad real. Se identificaron 5 gaps
(calibración con 2 puntos de datos, cero adversario adaptativo contra EW,
un solo nodo/sensor, cero dimensión de costo, terreno decorativo) y se
implementaron 5 propuestas concretas, en el orden pedido.

**1. Capa de costo-intercambio (`src/config.py`, `targeting.py`,
`experiments.py`)** — CERRADO. El WTA optimizaba/el Monte Carlo medía
bajas esperadas, nunca costo — una asignación "óptima" en física puede
ser pésima en doctrina (gastar un misil de $50k contra un dron de $1k).
Tres constantes nuevas (`COSTO_DISPARO_CANION_USD=25`,
`COSTO_MISIL_USD=50000`, `COSTO_DRON_HOSTIL_USD=1000`, cada una con su
ancla real declarada — Epirus Leonidas/THOR para el cañón, Switchblade
300 para el misil, precios públicos de FPV en Rusia-Ucrania para el
dron). `planificar_asignacion()` y `ExperimentManager._summarize()`
ahora reportan `costo_intercambio` (costo total, costo por baja
esperada/neutralizado, razón contra el costo de un dron hostil) — SIN
cambiar qué optimiza el WTA ni qué mide el Monte Carlo, solo agregando el
reporte. Verificado con una corrida real: a la distancia por defecto de
la demo (~600m), el plan óptimo cuesta **106x** el precio de un dron
hostil — confirma la crítica original con un número. Wireado también en
el frontend (Planificación y Laboratorio).

**2. Superficie de validez en la UI** — CERRADO. El análisis de
sensibilidad (`amenazas_a_la_validez`, qué parámetro domina la varianza
y no está calibrado) YA EXISTÍA como panel en la pestaña Laboratorio,
pero requería que el usuario lo pidiera a mano — invisible durante la
operación en vivo. Se agregó una tarjeta "Validez del modelo" en el
panel de Métricas de la pestaña Operación (`actualizarValidezModelo` en
`script.js`): distancia del vehículo al dron activo más cercano,
comparada contra el rango calibrado real (`/api/calibracion`,
`CALIBRACION_DISTANCIA_M` = 20-40m) — verde si está dentro, ámbar si es
extrapolación moderada (hasta 3x el borde), rojo si no hay ningún dato
real cerca. Verificado en vivo: con la demo default (~600m del arma), la
tarjeta muestra correctamente rojo — el modelo SIEMPRE está operando
fuera de su rango calibrado en el uso normal de la app, y ahora eso se
ve sin tener que ir a buscar el panel de sensibilidad.

**3. Defensa multi-nodo, alcance acotado — 2 cañones fijos con cesión de
blanco** — CERRADO. Alcance deliberadamente recortado (confirmado con
el usuario antes de implementar, ver la pregunta de esta sesión): un
SEGUNDO `HPMWeapon` fijo (`SimulationEngine.hpm_b`, posición
`HPM_NODO_B_ORIGIN_X/Y=(1000,1000)`, esquina opuesta al nodo A y lejos
del radio de bloqueo de las estructuras), SIN misil ni jammer propios —
el valor real de la feature es la cesión de blanco en el WTA, no
duplicar cada subsistema. Opt-in (`nodo_b_activo`, mismo criterio que
`kamikaze_activo`/`estructuras_activas`: solo la app en vivo lo prende).

- `OpcionDeDisparo` ganó un campo `nodo: "a"|"b"` (default "a",
  retrocompatible) — el cálculo de bajas esperadas YA usaba origen_x/y/z
  por opción, así que la cesión de blanco sale del MISMO optimizador sin
  cambiarlo: agregar las opciones del nodo B a la misma lista alcanza.
- `fire()` se refactorizó en un helper privado (`_disparar_nodo`)
  reutilizado por `fire_b()` — evita duplicar ~70 líneas de lógica de
  disparo (línea de vista, analíticas, memoria de amenaza, logs)
  idéntica entre los dos nodos.
- Nuevo endpoint `POST /api/fire_b`, mismo contrato que `/api/fire` (200
  OK + mensaje si rechaza, nunca error HTTP).
- Frontend: segundo vehículo (mismo `lanzador_hpm.glb`, clonado) +
  segundo cono de disparo, ambos ocultos hasta que `snap.hpm_b` llega no
  nulo; panel "Cañón B" en la UI, oculto por el mismo motivo.
- **Bug real encontrado y corregido al cablear el frontend, antes de
  llegar a producción**: `EJECUTAR PLAN` calculaba el rumbo de CUALQUIER
  disparo del plan usando el origen del nodo A — para un disparo
  asignado al nodo B (por la cesión de blanco recién agregada), eso
  apuntaría el cañón B en la dirección incorrecta. `bearingHaciaCentroide`
  ganó parámetros de origen opcionales; `btnWtaExecute` ahora calcula el
  rumbo del nodo B desde SU propio origen y llama `/api/fire_b`.
- Verificado end-to-end con un script standalone (ambos nodos disparan,
  el plan WTA asigna a `{'a','b'}`, costo-intercambio funciona con 2
  nodos, `fire_b()` rechaza si `nodo_b_activo=False`, `reset()` limpia
  el nodo B) y en vivo en el navegador (panel visible, `/api/fire_b`
  responde 200, sin errores de consola) — no se pudo confirmar
  visualmente el segundo modelo 3D en pantalla por la misma limitación
  de navegación de cámara del agente de automatización ya documentada
  en sesiones anteriores de este archivo, pero el código de renderizado
  es un espejo directo del patrón ya probado del nodo A.
- **Hallazgo aparte, NO corregido (fuera de alcance de este ítem)**:
  `SimulationEngine.reset()` nunca restauraba `energia_actual_kj`/
  `temperatura_c` del cañón a plena carga/temperatura ambiente — ni para
  el nodo A (bug preexistente) ni se agregó esa restauración para el
  nodo B (se mantuvo fiel al comportamiento existente en vez de arreglar
  un bug no pedido a mitad de esta feature). Queda señalado para una
  próxima pasada.

**4 y 5 (línea de vista con relieve real, sensor RF)**: ver §9.14 más
abajo.

Verificado: 213/213 tests dirigidos (targeting, simulación, opfor,
experimentos, coevolución) y 552/552 de la suite completa, sin
regresiones tras las 3 features.

### 9.14 Crítica de "científico militar" — features 4 y 5 (relieve real + sensor RF) — CERRADO

Continuación de §9.13: las últimas dos de las 5 propuestas, en el mismo
orden que pidió el usuario.

**4. Línea de vista con relieve real del terreno** — CERRADO. Hasta
acá, `linea_de_vista_bloqueada` solo conocía obstáculos artificiales
(círculos de estructuras) — las colinas que el frontend YA dibuja
(`render3d.js`, ruido de valor con semillas fijas) no afectaban a la
física en absoluto: un cañón podía "disparar a través" de una colina que
el jugador veía en pantalla.

- Nuevo módulo `src/engine/terreno.py`: puerto EXACTO (no aproximado) del
  generador de ruido del frontend a Python — PRNG mulberry32 con
  aritmética de 32 bits replicada a mano (`Math.imul`, `|0`, `>>>`), 2
  octavas de ruido de valor con interpolación smoothstep, tiling
  periódico en la octava de ondulación. Verificado corriendo el JS
  original con `node` y comparando 552 puntos contra el puerto Python:
  diff=0.0 exacto — no "parecido", IGUAL bit a bit. `ALTURA_COLINAS_M`/
  `ALTURA_ONDULACION_M` son copias literales de las constantes del
  frontend, deliberadamente NO configurables por entorno (evitar que
  backend y frontend diverjan con un `.env` mal puesto).
- `linea_de_vista_bloqueada` ganó `origen_z`/`destino_z`/
  `considerar_relieve` (opt-in, default el comportamiento de siempre) —
  ray-marching cada ~15m a lo largo del segmento 3D, comparando contra
  `altura_terreno(x,y)` en cada muestra. Enchufado, con el mismo flag
  opt-in (`relieve_bloquea_vision`), en TODOS los puntos donde ya se
  chequeaba línea de vista: `HPMWeapon.disparar`, `HPMissile.detonar`,
  `TrackManager.actualizar` (radar) — un mismo relieve para armas y
  sensor, no una física paralela para cada uno.
- **Hallazgo numérico verificado ANTES de integrar nada** (búsqueda de
  3000 muestras sobre geometrías de encuentro realistas, ver el docstring
  de `terreno.py`): con la amplitud de colinas ya elegida en el frontend
  por motivos de legibilidad visual (~13.5m máximo), el relieve
  prácticamente NUNCA bloquea contra un dron en vuelo normal (40-160m de
  altitud: 0/3000 casos bloqueados) pero SÍ es significativo contra un
  blanco cerca del suelo (0-20m, ej. un dron aterrizado por falla de
  enlace inducida por el jammer: 1928/3000 = 64.3% bloqueado). Se
  documenta así, tal cual, en vez de subir la altura de las colinas para
  forzar un resultado "más interesante" — es una característica física
  correcta (colinas suaves protegen objetivos bajos, no aeronaves en
  vuelo), no un bug.

**5. Sensor RF pasivo (ESM)** — CERRADO. El radar (`radar_engine.py`)
es monoestático — transmite y recibe su propia reflexión, ida y vuelta,
de ahí que su alcance caiga con `r⁴` y tenga un techo real DENTRO del
mapa (1000×1000m). Un sensor pasivo que solo ESCUCHA la emisión propia
del dron (enlace de control/telemetría) es un enlace unidireccional
(ecuación de Friis, `r²`) — mucho más alcance a igual potencia. Es
doctrina real de guerra electrónica (ESM/RWR superando en alcance al
radar que ilumina), no una particularidad inventada de este modelo.

- Nuevo módulo `src/engine/rf_sensor.py`: `rf_received_power_w` (Friis,
  `Gt·Gr` en vez de `G²` porque son dos antenas distintas, sin término
  de RCS) y `evaluar_deteccion_rf`, mismo patrón estructural que
  `radar_engine.evaluar_deteccion` (sigmoide sobre SNR, decisión
  determinística ≥50%, mismo `detection_probability` reutilizado).
- Constantes nuevas en `config.py`: `DRONE_TX_POWER_W` (25mW, ancla en
  control/telemetría tipo ELRS/Crossfire — NO el enlace de video, que
  suele ir más fuerte), `DRONE_TX_GAIN_DBI` (2 dBi, antena del dron
  casi omnidireccional), `RF_SENSOR_GAIN_DBI` (6 dBi, deliberadamente
  MENOS que los 25 dBi del plato del radar — un receptor de alerta
  pasiva prioriza cobertura angular, no un lóbulo angosto de
  seguimiento), `RF_SENSOR_FREQUENCY_GHZ` (2.4), `RF_SENSOR_SNR_
  THRESHOLD_DB`/`RF_SENSOR_SIGMOID_STEEPNESS` (mismo valor que el radar
  por ahora, pero como constante propia — no el mismo parámetro
  reutilizado — para poder diferenciar la electrónica de ambos
  receptores más adelante sin tocar firmas).
- **Verificado numéricamente ANTES de integrar** (mismo criterio de
  rigor que la feature 4): con los valores por defecto, el alcance de
  detección sale en **~3948m** — casi 3x la diagonal del mapa (~1414m).
  Dentro del mapa, con línea de vista libre, este sensor prácticamente
  SIEMPRE detecta — no hay "punto ciego por distancia" como sí lo hay
  con el radar. Deliberadamente NO se bajó la potencia del dron para
  forzar un alcance "más chico y creíble" — el hallazgo real es ese: la
  única defensa real contra este sensor es bloquear la línea de vista
  (terreno, estructuras — feature 4 de esta misma sesión), no la
  distancia.
- `TrackManager.actualizar` ganó `considerar_sensor_rf` (opt-in, default
  False): si el radar NO detecta a un dron, y el flag está activo, se
  evalúa TAMBIÉN contra el sensor RF — un "OR" geométrico sobre la MISMA
  línea de vista (obstáculos + relieve), no un tercer sensor
  independiente con su propio track. `Track` ganó `fuente_deteccion`
  ("radar"/"rf", puramente informativo) para transparencia — expuesto en
  el snapshot vía `drone_to_dict` como `fuente_deteccion`. Enchufado en
  `Swarm.actualizar` → `SimulationEngine.sensor_rf_activo` (mismo
  criterio opt-in que las 4 features anteriores) → activado en
  `main.py` para la app en vivo.
- A diferencia de la feature 4, el sensor RF SOLO afecta detección
  (`TrackManager`) — no se enchufó en `HPMWeapon.disparar`/
  `HPMissile.detonar` (esos ya tienen su propio chequeo de línea de
  vista para el DAÑO, sin relación con cómo se detectó al blanco).

Verificado: 9/9 tests dirigidos nuevos (`tests/test_sensor_rf.py`) +
31/31 de `tests/test_terreno.py` y `TestLineaDeVistaConRelieve` (§9.13
en curso, escritos junto con la feature 4) + 552/552 de la suite
completa, sin regresiones tras las 5 features.
