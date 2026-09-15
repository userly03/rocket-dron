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
| Chen & Kolokolnikov (2014), arXiv:1403.3250 | Régimen no monótono: fuerza del depredador determina escape/confusión/persecución/captura | ✅ Barrido corrido — ver §6. No apareció la curva de 4 regímenes (el arma no persigue, a diferencia del modelo del paper), pero sí una transición real de meseta baja→alta en formación compacta |
| Olson et al. (2013), arXiv:1209.3330 | Confusión del depredador basta para evolucionar enjambramiento (algoritmo evolutivo) | Anclaje teórico para P3-B (coevolución), ya implementado — no cambia código |
| Attanasi et al., Nature Physics / arXiv:1303.7097 | Ondas de agitación en bandadas: la alarma se propaga más rápido que el grupo | ✅ **Implementado** — ver §6, `flocking.propagate_alarm` (P2-E, Parte 4) |
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

- **Panel "Experimentos Monte Carlo"** — ✅ **CERRADO.** Expone
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

## 4. Reordenamiento UI/UX — ✅ CERRADO

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

## 5. Reproducción visual de una réplica (Monte Carlo + coevolución) — ✅ CERRADO

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

## 6. Migración de paleta — ✅ CERRADO

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

## 7. Iconografía — ✅ CERRADO

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

### 8.1 Propagación de alarma entre vecinos — ✅ CERRADO

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

### 8.2 Barrido depredador-presa (Chen & Kolokolnikov) — ✅ CERRADO

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

### 9.1 Motor — ✅ CERRADO (ver commit `feat(swarm): misión ofensiva`)

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

### 9.2 Frontend mínimo — ✅ CERRADO

Sin esto, la app en vivo (que ahora mueve al enjambre por defecto) se
vería como un bug — drones agrupándose y "desapareciendo" cerca del
arma sin explicación. Nueva métrica "Brechas" en Operación, un dron que
llega pasa a un naranja distintivo en el mapa 3D (con su propio estallido
de partículas, no cae al piso — cumplió la misión, no lo derribaron),
entrada nueva en la leyenda y en el registro de eventos. Verificado en
vivo: demo real acumuló 36 brechas visibles antes de que se agotara el
tiempo de prueba.

### 9.3 Monte Carlo — ✅ CERRADO

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

### 9.4 Coevolución contra la brecha — ✅ CERRADO

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

### 9.5 Kamikaze — el dron que llega inutiliza la plataforma de verdad — ✅ CERRADO

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
