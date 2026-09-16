# Auditoría del CHECKLIST_MEJORAS.md

> Fecha: 2026-09-12 · Alcance: `CHECKLIST_MEJORAS.md` contra el árbol de trabajo real
> (123/123 tests en verde al momento de auditar) y contra arXiv:2602.08477, el paper
> sobre el que descansa toda la calibración del modelo `friis`.

Este documento existe para lo mismo que `FISICA_Y_MATEMATICA.md`: dejar por escrito
qué está bien, qué está mal, **con qué evidencia**, y qué no se pudo verificar. El
plan de acción derivado vive en [`ROADMAP_CIENTIFICO.md`](ROADMAP_CIENTIFICO.md).

---

## 0. Hallazgo previo: el checklist estaba desactualizado

**P1-01, P1-02, P1-03 y P2-04 ya estaban implementados** en el árbol de trabajo (sin
commitear), con tests, y la suite completa pasaba. El checklist los tenía sin marcar.

| Ítem | Evidencia de que está hecho |
|---|---|
| P1-01 Monte Carlo + IC95% | `src/engine/experiments.py` (256 L, `wilson_interval`, `ExperimentManager`, `run_replica`), `_tick()` extraído de `_run_loop`, `POST/GET /api/experiments`, `tests/test_experiments.py` |
| P1-02 Reproducibilidad | `src/utils/reproducibilidad.py` (`rng()`, `seed_simulacion`, `build_manifest`), `SIM_SEED`, todos los modelos migrados de `np.random.*` a `rng()`, `/api/export`, `/api/manifest` |
| P1-03 Duty cycle | `HPM_DUTY_CYCLE`, `pulse_coupling_factor()`, `friis_diagnostics` con pico/promedio, duty propagado a cañón/misil/API, panel físico |
| P2-04 Huella de susceptibilidad | `resonance_frequency_ghz`, `frequency_coupling` (lorentziana), `susceptibility_coupling_factor`, sorteo en `Drone.__init__` |

Trabajo realmente pendiente al auditar: **P2-05, P2-06, P3-07…P3-10**. Pero los
problemas de fondo están en lo que ya se dio por hecho, no en lo que falta.

## 0.1 La referencia existe y dice lo que se le atribuye

Verificado: **arXiv:2602.08477** (Anbar Jafari & Anbarjafari, feb-2026,
*"A Multi-physics Simulation Framework for High-power Microwave Counter-unmanned
Aerial System Design and Performance Evaluation"*) existe, es del dominio correcto, y
contiene literalmente el *"sigmoid-based semiconductor damage probability model
calibrated to published CMOS latchup thresholds"* que `FISICA_Y_MATEMATICA.md` §3.2 le
atribuye. La auditoría previa del proyecto fue honesta.

Lo que sigue se apoya en haber leído ese paper. Por eso es específico y no genérico.

---

## 1. Lo que el paper hace y el simulador no

### 1.1 El Monte Carlo implementado no es el Monte Carlo del paper — severidad alta

Es el hallazgo central. El paper hace **10.000 tiradas variando 7 parámetros del
modelo**:

| Parámetro | Distribución (paper) | En el simulador |
|---|---|---|
| Potencia TX | `Normal(25 kW, ±5%)` | constante |
| Diámetro del plato | `Normal(0.60 m, ±0.83%)` | no existe (apertura fija) |
| Eficiencia de apertura | `Uniform[0.50, 0.60]` | no existe |
| **Error de apuntado** | **`Rayleigh(σ = 1.0°)`** | **no existe** |
| Ángulo de polarización | `Uniform[0, π]` → `η = cos²φ` (piso 0.1) | `Uniform[0.3, 1.0]` como factor de potencia |
| Longitud de cable | `Uniform[5, 25] cm` | `Uniform[2, 15] cm` |
| `E₅₀`, `σ_E` por subsistema | `Normal(±15%)` | constantes |

`run_replica()` solo hace `seed_simulacion(cfg.semilla + replica_idx)` y construye un
`SimulationEngine`. La configuración del modelo vive en **constantes de módulo de
`config.py`** y nunca varía entre réplicas.

**Consecuencia:** el IC95% que reporta el simulador es un intervalo sobre el muestreo
geométrico del enjambre, **no sobre la incertidumbre epistémica del modelo**. No es el
número que el paper reporta y no es el número que hace falta para defender una
conclusión.

El paper además concluye que **la polarización y la orientación del cable dominan la
incertidumbre (CV ≈ 39 % a 30 m)** — justo los dos que el simulador modela con
distribuciones distintas. `cos²(Uniform[0,π])` tiene masa concentrada cerca de 0 y de 1
(forma arcoseno); `Uniform[0.3, 1.0]` es plana. **El modelo subestima sistemáticamente
la varianza del resultado.**

### 1.2 El estimador no tiene señal — severidad alta

`run_replica` devuelve `exito = (conteo["neutralizado"] >= total)` — es
**P(aniquilación total del enjambre)**, no "probabilidad de baja" como dice el
checklist. Medido sobre la configuración por defecto:

```
8 réplicas · 30 drones · cañón 25 kW, azimut 45°, enjambre circular a ~700 m
neutralizados por réplica:  0 0 0 0 0 1 0 0
p̂ = 0.0     IC95% = [0.0, 0.3244]
```

**1 baja en 240 exposiciones, y el estimador reporta `p̂ = 0` con un IC de ancho 0.32.**
La información está en `neutralizados_por_replica` y se descarta.

El criterio de "done" del checklist (*"con N grande el IC contiene la probabilidad
teórica del modelo en un caso de referencia de cañón a quemarropa"*) solo es
satisfacible en el caso degenerado de quemarropa, precisamente porque en el resto del
espacio de operación el estimador no tiene señal.

**Problema estadístico adicional:** aplicar Wilson a bajas agrupadas por dron es
inválido — los drones de una misma réplica comparten geometría, semilla y
configuración, no son Bernoulli independientes. La unidad de muestreo es la réplica.

### 1.3 El umbral calibrado absorbió el sesgo del Monte Carlo — severidad alta

El paper modela **cinco subsistemas** con sigmoides independientes:

| Subsistema | `E₅₀` [V/m] | `σ_E` [V/m] |
|---|---|---|
| GPS/GNSS LNA | 150 | 30 |
| Flight controller | 250 | 50 |
| ESC gate oxide | 300 | 60 |
| Camera CMOS | 200 | 40 |
| BMS MOSFET | 350 | 70 |

El simulador usa **un solo umbral agregado de 500 V/m**, que es **más alto que los
cinco**, y una pendiente `0.0075 V/m⁻¹` → `σ_E ≈ 133 V/m`, **mucho más ancha que las
suyas (30–70 V/m)**.

Por qué pasó: el 51.4 % @ 20 m y el 13.1 % @ 40 m son la **salida** de un MC de 10.000
tiradas sobre 7 fuentes de variabilidad y un modelo de eslabón más débil de 5
subsistemas. Ajustar una sigmoide **determinista** a esos dos puntos mete el sesgo
descendente del MC dentro del umbral y ensancha artificialmente la pendiente. Es la
razón de que la verificación del propio proyecto dé **43.6 % vs 51.4 %** (15 % de error
relativo) en vez de coincidir.

El paper lo dice explícitamente: las predicciones deterministas (83 % @ 20 m, 20 % @
40 m) **sobreestiman por un factor ≈1.6** respecto al MC.

**Modelo correcto:** cinco sigmoides con los `E₅₀`/`σ_E` del paper, eslabón más débil
`P_kill = 1 − Π(1 − pᵢ)`, más las distribuciones de §1.1 — y los 51.4 %/13.1 % **salen**
en vez de ajustarse.

### 1.4 El modelo de resonancia no es el del paper — severidad media

El paper **no** usa una lorentziana en frecuencia. Usa:

```
V_ind = E_inc · L_eff · F(θ_wire) · √(η_pol)        L_eff = L/2   (dipolo corto, L < λ/2)
V_res = V_ind · [1 + (Q−1)·exp(−(L − λ₀/2)² / (2σ_L²))]      Q ≈ 10,  σ_L = 0.02 m
η_pol = cos²φ,  acotado a ≥ 0.1
```

Tres diferencias concretas con `hpm_engine.frequency_coupling`:

1. **Realce gaussiano en longitud** alrededor de `L = λ₀/2`, no lorentziana en
   frecuencia alrededor de `f = c/2L`. `Q = 10`, no 5.
2. **Falta el factor `L_eff = L/2`.** En el código actual dos drones con el mismo
   desajuste acoplan la misma amplitud aunque uno tenga 2 cm de cable y el otro 15. La
   tensión inducida escala con la longitud efectiva.
3. `η_pol = cos²φ` con piso 0.1, contra `Uniform[0.3, 1.0]`.

### 1.5 El duty cycle sí coincide; la corrección temporal es un añadido sin respaldo — severidad media

Separando las dos mitades de P1-03:

- **Duty cycle:** el paper escala el pico con el duty (1 % duty → 500 kW pico → el
  campo a 40 m supera los 1.100 V/m). El código hace exactamente eso.
- **`g(τ) = min(√(τ/τ_ref), 3.0)`:** el paper **no** incorpora escalado temporal. Es un
  añadido del proyecto, sin cita, y el `3.0` es un número mágico que está haciendo el
  trabajo de un cambio de régimen físico.

Lo notable: `√(τ/τ_ref)` **coincide con el modelo Wunsch-Bell** de quemado de junturas
semiconductoras (umbral de potencia de falla `∝ τ^(−1/2)`, régimen de difusión
térmica). Está a una cita y dos tramos de ser ingeniería citable en vez de ad-hoc.

El paper también da un blanco medible que el checklist no usa: **el modo pulsado
extiende el alcance de 90 % de baja de ~18 m a ~88 m.**

---

## 2. Criterios de "done" que no pueden fallar

Tres ítems tienen criterios tautológicos. Un test que no puede fallar no valida nada.

| Ítem | Criterio | Por qué es tautológico |
|---|---|---|
| **P1-03** | *"a igual energía total, un pulso corto de alto pico neutraliza a más distancia que CW"* | El modelo es `pico = promedio/duty` → `duty↓ ⇒ E↑ ⇒ P↑` por álgebra. Además "a igual energía total" no se impone en ningún lado: `HPM_DUTY_CYCLE` y `HPM_PULSE_DURATION_NS` son perillas independientes. |
| **P3-07** | *"las bajas esperadas del plan ≥ bajas del greedy plano"* | El algoritmo propuesto es "greedy + búsqueda local", y la búsqueda local arranca **desde** el greedy → no puede ser peor por construcción. |
| **P1-01** | *"con N grande el IC contiene la probabilidad teórica"* | Solo satisfacible en el caso degenerado de quemarropa (§1.2). |

Reemplazos propuestos en [`ROADMAP_CIENTIFICO.md`](ROADMAP_CIENTIFICO.md): validar
P1-03 contra el blanco 18 m → 88 m del paper, y P3-07 contra fuerza bruta exacta en
instancias pequeñas.

---

## 3. Dependencias rotas y desacoples arquitectónicos

### 3.1 `_rng` global compartido entre hilos — severidad alta

El propio docstring de `experiments.py` lo confiesa:

> *"Limitación conocida (stopgap): las réplicas usan el generador global … Si la
> simulación interactiva consume aleatoriedad mientras corre un experimento, las
> réplicas dejan de ser bit a bit reproducibles."*

No es teórico: `ExperimentManager._run` corre en un hilo background y
`seed_simulacion()` reescribe el `_rng` **global del módulo**, mientras el hilo de
simulación en vivo (`_run_loop`) sortea del mismo objeto. Dos experimentos en paralelo
también se corrompen mutuamente.

**Causa raíz de orden:** P1-02 (reproducibilidad) era el cimiento de P1-01 (Monte
Carlo) y se implementó después. El código lleva la cicatriz.

### 3.2 El radar comparte frecuencia con el arma — severidad alta

`Swarm.actualizar` pasa `HPM_FREQUENCY_GHZ` a `evaluar_deteccion`, y la ecuación de
radar lleva `λ²`:

```
Pr = (Pt · G² · λ² · σ) / ((4π)³ · r⁴)
```

Entonces **barrer la frecuencia del arma para estudiar resonancia cambia
simultáneamente el alcance de detección del radar**, que cambia a cuántos drones se
apunta, que cambia las bajas. El efecto que P2-04 quiere medir queda confundido con un
efecto instrumental.

Es el experimento estrella de P2-04 ("¿a qué frecuencia conviene atacar?") invalidado
por un acoplamiento de una línea.

### 3.3 P2-05 no es aditivo — rompe la premisa del encabezado del checklist — severidad alta

El checklist afirma que *"cada ítem es aditivo (no rompe el resto)"*. P2-05 no lo es.

Hoy la detección vive **dentro** de `Swarm.actualizar()` y escribe un booleano en el
objeto dron (`drone.detectado`). Es **omnisciente por construcción**: el "radar" conoce
la posición verdadera exacta y solo decide si la revela.

Un `TrackManager` con filtro α-β-γ necesita **estado propio y separado** (posición
*estimada*, velocidad, edad, calidad). Pero todos los consumidores leen la posición
*verdadera*:

- `HPMissile._resolver_objetivo` → `min(detectados, key=distance(self.x, self.y, d.x, d.y))`
- `HPMissileSystem.lanzar` → centroide sobre `d.x, d.y` reales

Si no se cambian esos consumidores, el filtro es decorativo. Si se cambian, **se mueve
el auto-apuntado, el punto de detonación y los resultados calibrados**, y los tests
existentes de `guiado`/misil cambian de valor.

Segundo obstáculo: `evaluar_deteccion` es determinista (`p ≥ 0.5`) **a propósito**,
documentado como anti-parpadeo. Un modelo de revisita reintroduce estructura temporal y
ese hack tiene que salir.

### 3.4 `DroneEstado` mezcla salud con enlace — severidad media

Prerrequisito de P2-06 que el checklist no lista. `DroneEstado` combina **salud**
(`ACTIVO`/`DANADO`/`NEUTRALIZADO`) con **enlace** (`INTERFERIDO`) en un solo enum:

- Un dron interferido *y* dañado no es representable.
- La recuperación reconstruye la salud por inferencia:
  `drone.estado = DANADO if drone.salud < 50 else ACTIVO`.
- Los perfiles lost-link de P2-06 (hover/aterrizar/RTH/flyaway) son ortogonales a la
  salud por definición.

Bug relacionado: `Swarm.actualizar` excluye los `INTERFERIDO` de `compute_headings`, así
que **un dron interferido desaparece del cálculo de flocking de sus vecinos**. Sigue
físicamente ahí; sus vecinos deberían seguir separándose de él.

### 3.5 P3-08 (FDTD) corrige un régimen inalcanzable — severidad alta, sobra

Plato `D = 0.6 m`, `f = 2.45 GHz` → `λ = 0.1224 m`:

```
2D²/λ = 2·(0.6)² / 0.1224 ≈ 5.9 m
```

**La zona de campo cercano son ~6 metros.** El campo es de 1000×1000 m,
`MISSILE_DETONATION_DISTANCE = 80 m`, el bin más cercano de `analytics` es 0–50 m, y el
enjambre por defecto está a 500–900 m. Un parche FDTD de 10–20 m corregiría un régimen
**al que el simulador no llega nunca**. Es el ítem más caro (L) con efecto cero sobre
cualquier resultado.

Además el empalme es dimensionalmente traicionero: la función de Green **2D** decae como
`1/√r`, la Friis **3D** como `1/r`. *"Acoplado en la frontera al campo Friis lejano"*
esconde ese problema, no lo resuelve. Un solver TEz 2D tampoco puede representar un
plato 3D ni el acoplamiento 3D del dron.

### 3.6 P3-09 (thermal runaway): el presupuesto energético falla por ~10⁹ — severidad alta

Llevar una celda 18650 a runaway térmico requiere del orden de **10–20 kJ** inyectados
en la celda. Un pulso de 100 ns a 500 V/m acopla **microjoules** a una estructura de
captación de centímetros.

HPM no mata drones calentando la batería: mata el **flight controller, los ESC, el
front-end de GPS/RF** — exactamente los cinco subsistemas que el paper modela
(150–350 V/m). La premisa del mecanismo es insostenible.

**Lo que sí vale de P3-09** es la maquinaria: decaimiento por tick y **atribución
diferida de bajas al disparo original**. Eso cambia la curva de efectividad y es
operativamente real. Hay que cambiarle el mecanismo, no tirarlo.

### 3.7 P3-10 (coevolución) está bloqueado por la métrica, no por la dependencia — severidad alta

El fitness sale del runner MC, y ese fitness es `p̂ = P(aniquilación total)`, que **vale
0 en casi todo el espacio de parámetros** (§1.2). Un GA con fitness constante 0 no tiene
gradiente: **no evoluciona nada**.

El checklist declara `deps: requiere P1-01`. Pero P1-01 *existe* y aun así P3-10 no
puede funcionar. La dependencia real es *"requiere que P1-01 tenga un estimador con
señal"*.

### 3.8 P3-07 (WTA) tiene un sesgo de Jensen no mencionado — severidad media

Con P2-04 activo el acoplamiento varía por dron, así que "bajas esperadas de un cluster"
requiere agregar sobre la **distribución** de acoplamiento del cluster. Hacerlo con el
acoplamiento **medio** da un estimador sesgado, porque la sigmoide es no lineal
(desigualdad de Jensen). No está mencionado en el ítem.

### 3.9 Resumen de dependencias rotas

| # | Desacople | Severidad | Bloquea |
|---|---|---|---|
| 1 | MC varía solo el enjambre, no los parámetros del modelo | Alta | Toda conclusión cuantitativa |
| 2 | `p̂` = P(aniquilación total) → estimador sin señal | Alta | P3-10, y la lectura de P1-03/P2-04 |
| 3 | `_rng` global compartido entre hilos | Alta | Reproducibilidad de experimentos |
| 4 | Radar comparte `HPM_FREQUENCY_GHZ` | Alta | El experimento estrella de P2-04 |
| 5 | P2-05 exige reescribir todos los consumidores de posición | Alta | Calibración existente |
| 6 | `DroneEstado` mezcla salud y enlace | Media | P2-06 |
| 7 | P3-08 corrige `r < 5.9 m` en un campo de 1000 m | Alta | (esfuerzo inútil) |
| 8 | P3-09 falla el presupuesto energético por ~10⁹ | Alta | (premisa insostenible) |

---

## 4. Defectos de código independientes del checklist

Encontrados leyendo el árbol, no derivados de ningún ítem.

### 4.1 El panel físico publica un tercer modelo que no mata a nadie — severidad alta

`PhysicsAnalytics.get_physics_panel` expone `probabilidad_referencia`, que sale de
`gaussian_neutralization_prob` (`P = 1 − exp(−k·P·exp(−r²/2σ²))`), y publica ese
`formula` y `coupling_k`. El frontend los pinta:

- `frontend/js/charts.js:144` → `set("physics-formula", physics.formula)`
- `frontend/js/charts.js:148` → `set("phys-k", physics.coupling_k)`
- `frontend/index.html:85` → `<div class="physics-formula">P = 1 - exp(-k · P · exp(-r²/2σ²))</div>`

**Ni el modelo `friis` ni el `legacy` usan esa gaussiana.** Es un número con apariencia
física en la UI que no gobierna nada — el pecado exacto que `FISICA_Y_MATEMATICA.md`
declara haber corregido. `HPM_COUPLING_K = 0.42` es peso muerto en la ruta `friis`.

### 4.2 `run_replica` descarta los eventos de `_tick()` — severidad media

Nunca llama `_process_missile_events`, así que `analytics.record_missile_detonation` no
corre en Monte Carlo. Las bajas sí ocurren (dentro de `detonar`), pero el experimento
queda sin diagnóstico por disparo y sin curva de efectividad.

### 4.3 El jammer es el único arma inmune a la huella de susceptibilidad — severidad media

`Jammer._en_zona_de_efecto` usa `campo_e_v_m` (no `campo_e_efectivo_v_m`) y no pasa
`cable_length_m` / `polarization`. Defendible para CW, pero es una inconsistencia sin
documentar: P2-04 aplica a cañón y misil, no al jammer.

### 4.4 El taper angular es incoherente entre modelos — severidad media

`friis_diagnostics` aplica `cos²` a la **densidad de potencia**, y después
`efield_from_power_density` saca la raíz → en amplitud queda `cos¹`. El modelo `legacy`
aplica `cos²` directo a la **probabilidad**. Ninguno de los dos es un patrón de antena
real.

### 4.5 Aritmética de daño dimensionalmente vacía — severidad media

```python
dano = probabilidad * potencia * 0.5     # probabilidad × kW × 0.5 = "puntos de salud"
```

Presente en `Drone.recibir_daño` y `HPMissile.detonar`. Es el último resto de los
"puntos de daño arbitrarios" que `FISICA_Y_MATEMATICA.md` §5.4 declara haber eliminado.

### 4.6 `requirements.txt` incompleto — severidad media

`scipy 1.18.0` y `pandas 3.0.3` están instalados en el venv y no declarados. No encontré
imports en `src/`, pero el entorno no es reproducible desde `requirements.txt`.

---

## 5. Lo que está bien (verificado, no asumido)

Crédito donde corresponde:

- **`apply_hardening_odds`.** Detectar que desplazar `E₀` dentro de una sigmoide produce
  reducciones de 14× a 821× en vez de 2.5×, y arreglarlo en espacio de momios
  (`odds = p/(1−p)`, dividido por el factor), es el tipo de razonamiento que la mayoría
  de estos proyectos no hace.
- **El fusible de proximidad.** `HPMissile.debe_detonar` detona en el punto de máxima
  cercanía (cuando la distancia empieza a aumentar), no en el primer cruce del radio
  de armado. Es el principio de un VT fuze real.
- **`validation.py` chequea invariantes en tiempo real** y sabe que la monotonía
  probabilidad-vs-distancia **solo vale a offset angular igual** (`_mismo_offset`,
  tolerancia 2°). Esa sutileza es real y poca gente la ve.
- **La física de base es correcta:** `S = P·G/(4πr²)` (propagación esférica real),
  `E = √(S·377)` (impedancia del vacío), `G ≈ 26000/apertura²` (aproximación de
  ingeniería de radar verificable), navegación proporcional con la simplificación
  declarada, reflexión especular correcta.
- **El perfil de altitud del misil** converge a la altitud *ponderada del grupo* con
  tasa limitada, en vez de a un tiempo estimado al lanzar. La nota de diseño explica por
  qué la versión anterior fallaba.
- **La disciplina documental.** Tres categorías declaradas (física establecida /
  aproximación de ingeniería / decisión de diseño), tabla de hallazgos con severidad y
  estado, sección de limitaciones conocidas. Un proyecto que documenta *"el README
  atribuía esta fórmula a un paper — verificado, la atribución era falsa"* tiene más
  valor científico que uno con los tests verdes.

---

## 6. Lo que no se pudo verificar

Declarado explícitamente, como pide la disciplina del proyecto:

- **Las instrucciones oficiales de instalación de Graphify.** `graphify.net` devuelve
  HTTP 403 a cualquier fetch programático. Se trabajó contra la CLI instalada
  (`graphifyy v0.9.48`) como fuente de verdad. El comando `private-context doctor` del
  enunciado original **no existe** en graphifyy; pertenece a otro producto.
- **Los detalles finos del paper.** Se obtuvieron vía fetch con resumen del HTML de
  arXiv, no leyendo el PDF completo. Existencia, autores, título y la cita del modelo
  sigmoide **están confirmados**; la tabla de 5 subsistemas y las 7 distribuciones del
  MC son de segunda mano. **Antes de reescribir la calibración (P1b del roadmap), hay
  que leer el paper directo.**
- **El comportamiento visual del frontend.** No se levantó la app. La afirmación de §4.1
  sale de leer `charts.js` y `index.html`, no de ver la UI.
- **Si `scipy`/`pandas` los usa algo del proyecto.** Están en el venv; no se encontraron
  imports en `src/` pero no se barrió exhaustivamente.
- **Validación contra datos reales más allá de un paper.** Toda la calibración descansa
  en dos puntos de arXiv:2602.08477. No hay segunda fuente independiente.

---

## 7. Diagnóstico en una línea

El techo del proyecto está puesto por **el instrumento de medición**, no por la física.
El Monte Carlo repite la misma configuración nominal con distintas semillas de enjambre y
reporta P(aniquilación total), que vale 0 casi siempre. Arreglar eso (§1.1, §1.2, §3.1)
es cuestión de días y es lo que hace que todo lo demás tenga dónde apoyarse — incluido el
análisis de sensibilidad, que es donde este simulador pasa de didáctico a defendible.

## 8. Referencias

- **arXiv:2602.08477** — Anbar Jafari & Anbarjafari (2026), *"A Multi-physics Simulation
  Framework for High-power Microwave Counter-unmanned Aerial System Design and
  Performance Evaluation"*. <https://arxiv.org/html/2602.08477>
- **arXiv:2510.16495** — *"Performance Evaluation of High Power Microwave Systems Against
  UAVs: A Probabilistic Antenna Propagation Framework with Sensitivity Analysis"*.
  <https://arxiv.org/pdf/2510.16495> — paper hermano, respalda el ítem de sensibilidad
  global del roadmap.
- **Wunsch, D.C. & Bell, R.R. (1968)** — *"Determination of Threshold Failure Levels of
  Semiconductor Diodes and Transistors Due to Pulse Voltages"*, IEEE Trans. Nucl. Sci.
  Origen de la ley `P_fail ∝ τ^(−1/2)` que el proyecto ya usa sin citar.
- `docs/FISICA_Y_MATEMATICA.md` — auditoría física previa del proyecto.
