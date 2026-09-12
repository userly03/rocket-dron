# Roadmap científico

> Derivado de [`AUDITORIA_CHECKLIST.md`](AUDITORIA_CHECKLIST.md). El checklist operativo
> vivo (con casillas para marcar) es [`../CHECKLIST_MEJORAS.md`](../CHECKLIST_MEJORAS.md).
> Este documento explica **el porqué y el orden**; el checklist dice **qué tocar**.

## La meta

Que este simulador sea un **instrumento de medición defendible**, no una demo. El
criterio concreto: que cualquier número que salga de él venga con (a) una fórmula
identificada por categoría, (b) un intervalo de confianza sobre la incertidumbre real
del modelo, y (c) un índice de sensibilidad que diga de qué parámetro depende ese
número. Con eso, las conclusiones sobre frecuencia óptima de ataque, CW vs pulsado, o
asignación arma-blanco dejan de ser opinión.

## El techo actual y por qué

El techo no es la física — la física de base está bien (ver auditoría §5). El techo es
que **el instrumento de medición no mide**:

1. El Monte Carlo varía solo la geometría del enjambre, no los parámetros del modelo →
   los IC no describen la incertidumbre del modelo.
2. El estimador es P(aniquilación total del enjambre) → vale 0 en casi todo el espacio
   de operación (medido: 1 baja en 240 exposiciones, `p̂ = 0`, `IC = [0, 0.32]`).
3. Nadie sabe de qué parámetros dependen los resultados: ~20 parámetros libres, **2**
   calibrados contra datos.

Mientras eso siga así, ni P2-05 (radar dinámico) ni P3-10 (coevolución) producen
conocimiento: producen números sin barra de error sobre un estimador ciego.

## Principio de ordenamiento

**Primero el instrumento, después los fenómenos.** Y dentro de cada fase: lo que
desbloquea antes que lo que consume; lo barato y confundidor antes que lo caro y
aditivo.

---

## Fase P0 — Desconfundir (horas)

Tres cambios chicos que invalidan mediciones si no se hacen primero.

### P0-A · `RADAR_FREQUENCY_GHZ` independiente
- **Qué:** el radar deja de reutilizar `HPM_FREQUENCY_GHZ`.
- **Dónde:** `src/config.py`, `src/engine/radar_engine.py`, `src/models/swarm.py`.
- **Tamaño:** S (una constante y su propagación).
- **Por qué:** la ecuación de radar lleva `λ²`. Barrer la frecuencia del arma para
  estudiar resonancia cambia simultáneamente el alcance de detección → cambia a cuántos
  drones se apunta → cambia las bajas. **El experimento estrella de P2-04 está
  confundido con un efecto instrumental.** Auditoría §3.2.
- **Done:** un test barre `HPM_FREQUENCY_GHZ` en [1, 8] GHz y verifica que el conteo de
  drones detectados **no cambia**; `RADAR_FREQUENCY_GHZ` por defecto = 2.45 para no
  mover la calibración existente.

### P0-B · RNG por réplica, inyectado
- **Qué:** `SimulationEngine` recibe su `numpy.random.Generator` en vez de leer el
  global del módulo. `seed_simulacion()` global se conserva solo para la sim interactiva.
- **Dónde:** `src/utils/reproducibilidad.py`, `src/engine/simulation.py`,
  `src/engine/experiments.py`, `src/models/{drone,swarm,hpm_missile}.py`.
- **Tamaño:** M.
- **Por qué:** hoy `ExperimentManager._run` (hilo background) y `_run_loop` (hilo de sim)
  sortean del mismo objeto global. Dos experimentos en paralelo se corrompen. El propio
  docstring de `experiments.py` lo declara como stopgap conocido. Auditoría §3.1.
- **Done:** un test corre un experimento **mientras** la sim interactiva está corriendo y
  verifica que las réplicas son bit a bit idénticas a correrlo aislado; dos experimentos
  concurrentes con la misma semilla dan resultados idénticos entre sí.

### P0-C · Sacar la gaussiana fantasma de la UI
- **Qué:** el panel físico deja de publicar `probabilidad_referencia` / `formula` /
  `coupling_k` de `gaussian_neutralization_prob`, un tercer modelo que no gobierna
  ninguna baja. Retirar `HPM_COUPLING_K` de la ruta `friis`.
- **Dónde:** `src/engine/analytics.py`, `frontend/js/charts.js`, `frontend/index.html`.
- **Tamaño:** S.
- **Por qué:** es un número con apariencia física en pantalla que no corresponde a nada
  — el pecado exacto que `FISICA_Y_MATEMATICA.md` declara haber corregido. Auditoría §4.1.
- **Done:** el panel muestra solo el modelo que gobierna las bajas; `grep coupling_k`
  en el frontend no devuelve nada; la suite sigue verde.

---

## Fase P1 — Reconstruir el instrumento (días)

Reescritura de P1-01. Es la fase que levanta el techo.

### P1-A · Estimador correcto: la réplica es la unidad de muestreo
- **Qué:** reemplazar `p̂ = P(aniquilación total)` por:
  - fracción neutralizada media **± IC por bootstrap sobre réplicas** (y/o t de Student),
  - distribución completa de `neutralizados_por_replica` como salida de primera clase,
  - Wilson conservado **solo** para métricas que sí son Bernoulli a nivel réplica
    (p. ej. "¿se aniquiló el enjambre?"), declarada como métrica secundaria.
- **Dónde:** `src/engine/experiments.py`, `src/api/routes.py`.
- **Tamaño:** M.
- **Por qué:** medido empíricamente, el estimador actual reporta `p̂ = 0` con 1 baja en
  240 exposiciones. Y aplicar Wilson a bajas agrupadas por dron es inválido: los drones
  de una réplica comparten geometría y semilla, no son independientes. Auditoría §1.2.
- **Done:** con la configuración por defecto (cañón a ~700 m) el experimento reporta una
  fracción media distinguible de 0 con IC finito; un test verifica que el IC por
  bootstrap cubre la fracción teórica en un caso analítico de quemarropa.

### P1-B · Monte Carlo sobre parámetros, no solo sobre geometría
- **Qué:** `ExperimentConfig` pasa a llevar **distribuciones**, no escalares, y el motor
  lee su configuración de una instancia inyectada en vez de constantes de módulo.
  Replicar las 7 fuentes del paper, empezando por la que falta por completo:
  **error de apuntado `Rayleigh(σ = 1°)`**. Cambiar polarización a `cos²(Uniform[0,π])`
  con piso 0.1.
- **Dónde:** nuevo `src/engine/parametros.py` (distribuciones + muestreo),
  `src/engine/experiments.py`, `src/config.py` (defaults como nominales),
  `src/engine/simulation.py` (config inyectable).
- **Tamaño:** L — es el cambio estructural de la fase.
- **Por qué:** el paper hace 10.000 tiradas variando potencia, diámetro de plato,
  eficiencia de apertura, error de apuntado, polarización, longitud de cable y umbrales.
  El simulador varía **nada** de eso. Los IC actuales describen el muestreo del enjambre,
  no la incertidumbre del modelo. El paper además concluye que polarización y orientación
  de cable **dominan** la incertidumbre (CV ≈ 39 % a 30 m). Auditoría §1.1.
- **Done:** `/api/experiments` acepta distribuciones por parámetro; un experimento con
  las 7 distribuciones del paper reproduce el orden de magnitud del CV reportado
  (≈39 % a 30 m); el manifiesto de corrida registra las distribuciones usadas, no solo
  los escalares.

### P1-C · Recalibrar contra el modelo real: 5 subsistemas, eslabón más débil
- **Qué:** reemplazar el umbral agregado único (`E₀ = 500 V/m`, `k = 0.0075`) por las
  cinco sigmoides del paper (GPS/GNSS LNA 150±30, flight controller 250±50, ESC gate
  oxide 300±60, camera CMOS 200±40, BMS MOSFET 350±70 V/m) con
  `P_kill = 1 − Π(1 − pᵢ)`.
- **Dónde:** `src/engine/hpm_engine.py`, `src/config.py`, `src/models/drone.py`.
- **Tamaño:** M.
- **Por qué:** `E₀ = 500 V/m` es **más alto que los cinco umbrales del paper**, y la
  pendiente implícita (`σ_E ≈ 133 V/m`) mucho más ancha que las suyas (30–70 V/m).
  Pasó porque se ajustó una sigmoide determinista a dos puntos que son **salida** de un
  MC de 10.000 tiradas: se absorbió el sesgo del MC dentro del umbral. Es la razón de que
  la verificación del proyecto dé 43.6 % vs 51.4 %. Con el modelo correcto los dos puntos
  **salen** en vez de ajustarse. Auditoría §1.3.
- **Done:** con P1-B activo, el MC reproduce 51.4 % @ 20 m y 13.1 % @ 40 m dentro del
  ±1 % que el paper declara, **sin ajustar ningún umbral a esos puntos**; se documenta el
  umbral agregado viejo como aproximación histórica.
- **Prerrequisito:** leer el PDF del paper directo (la tabla de subsistemas de esta
  auditoría es de segunda mano — ver auditoría §6).

### P1-D · Test de regresión de la calibración
- **Qué:** un test que re-deriva los dos puntos publicados desde la configuración
  **actual** y falla si alguno se mueve más del margen declarado.
- **Dónde:** `tests/test_calibracion.py`, helper en `src/engine/validation.py`.
- **Tamaño:** S.
- **Por qué:** hoy la calibración vive en comentarios. Nada impide que cambiar un default
  de duty cycle o de acoplamiento la invalide en silencio — y de hecho §1.3 sugiere que
  eso ya está a medio pasar. Es la mejora más barata del roadmap y la que protege todo
  lo demás.
- **Done:** el test existe, pasa, y falla si se toca `HPM_E_THRESHOLD_V_M`,
  `HPM_CONE_APERTURE` o `HPM_DUTY_CYCLE`.

### P1-E · Ley de daño Wunsch-Bell por tramos
- **Qué:** reemplazar `g(τ) = min(√(τ/τ_ref), 3.0)` por la ley de quemado de junturas
  con sus tres regímenes y ventana de validez explícita:
  adiabático (`τ ≲ 100 ns`, umbral `∝ 1/τ`) / difusión térmica (`∝ τ^(−1/2)`) /
  estado estacionario (`τ ≳ 10 µs`, independiente de `τ`). Eliminar
  `HPM_PULSE_COUPLING_MAX`.
- **Dónde:** `src/engine/hpm_engine.py`, `src/config.py`.
- **Tamaño:** S.
- **Por qué:** el paper **no** incorpora escalado temporal; `g(τ)` es un añadido del
  proyecto sin cita, y el `3.0` es un número mágico haciendo el trabajo de un cambio de
  régimen físico. Lo notable: el `√τ` del código **ya coincide** con el régimen de
  difusión térmica de Wunsch-Bell. Está a una cita y dos tramos de ser ingeniería
  citable. Auditoría §1.5.
- **Done (reemplaza el criterio tautológico de P1-03):** validar contra el blanco
  medible del paper — **el modo pulsado extiende el alcance de 90 % de baja de ~18 m a
  ~88 m**. El test anterior ("pulsado > CW") no puede fallar por álgebra y se retira como
  criterio de aceptación.

---

## Fase P2 — Física que cambia números en el rango real (semanas)

### P2-A · Análisis de sensibilidad global (Morris → Sobol) ⭐
- **Qué:** descomposición de varianza de la probabilidad de baja sobre los ~20 parámetros
  libres. Screening de Morris primero (barato), índices de Sobol después.
- **Dónde:** nuevo `src/engine/sensitivity.py` sobre `experiments.py`; endpoint
  `/api/sensitivity`.
- **Tamaño:** M (Morris es S; Sobol completo es M).
- **Por qué:** es **el mayor salto científico del roadmap**. Hoy no se puede responder
  "¿esta conclusión depende de un parámetro calibrado o de uno inventado?". Con índices
  de Sobol se puede decir *"el alcance efectivo está dominado por `E₅₀` (S₁ = 0.4) y
  polarización (0.3); el tope de acoplamiento de pulso aporta < 0.02"* — y ahí las
  objeciones a los números mágicos se responden con datos. Es también la defensa contra
  la crítica obvia al proyecto entero: *"ajustaste 20 parámetros a 2 puntos de datos"*.
  El framework de referencia hace esto ([arXiv:2510.16495](https://arxiv.org/pdf/2510.16495)
  está dedicado a ello); el simulador no.
- **Done:** un informe reproducible con los índices de primer orden y total para los
  parámetros del panel físico; los 3 parámetros dominantes quedan documentados en
  `FISICA_Y_MATEMATICA.md`; corre en CI con presupuesto reducido.

### P2-B · Curva dosis-respuesta recuperada de los datos simulados
- **Qué:** ajuste por máxima verosimilitud de `P(kill)` vs `E` a partir de las réplicas,
  con IC por bootstrap, y comparación automática contra los puntos de calibración.
- **Dónde:** `src/engine/experiments.py`, `src/engine/validation.py`.
- **Tamaño:** M.
- **Por qué:** cierra el lazo. En vez de un `p̂` puntual, se recupera la curva que el
  simulador **implica** y se contrasta con la que se le metió. Si un cambio en duty cycle
  o resonancia desplaza la calibración, se ve como un desplazamiento de la curva en vez
  de descubrirlo meses después. Es el estimador que P1-A necesita para ser útil.
- **Done:** el endpoint devuelve `E₅₀` y `σ_E` ajustados con IC, y un test verifica que
  recuperan los valores de entrada dentro del IC cuando se corre contra el propio modelo.

### P2-C · Dos rayos (reflexión en tierra) + patrón de antena real ⭐
**Reemplaza P3-08 (FDTD), que se corta.**
- **Qué:** interferencia directo/reflejado sobre tierra, y un patrón de antena con taper
  y lóbulos laterales en lugar del hack `cos²`.
- **Dónde:** nuevo `src/engine/propagation.py`; `hpm_engine.power_density` y el taper
  angular de `friis_diagnostics`.
- **Tamaño:** M.
- **Por qué:** opera exactamente en el rango donde el simulador vive (50–900 m), a
  diferencia de los **5.9 m** de zona de campo cercano que el FDTD iba a corregir
  (auditoría §3.5). Produce lobes y nulos de ±6 dB — más grandes que varios de los
  efectos que el checklist original perseguía — y **convierte la altitud en variable
  táctica**: un enjambre puede volar en un nulo de interferencia, y el simulador ya tiene
  altitud 3D (40–160 m) para representarlo. Ese es un resultado publicable; la corrección
  de campo cercano a 6 m no lo es. Arregla también la incoherencia del taper
  (auditoría §4.4).
- **Done:** el campo E vs altitud a rango fijo muestra el patrón de lobes/nulos esperado
  para la geometría (emisor a `z = 8 m`); un test verifica la posición del primer nulo
  contra el cálculo analítico de diferencia de camino; sin impacto en el bucle de 60 FPS.

### P2-D · Modelo upset-vs-damage con fallo latente ⭐
**Reemplaza la premisa de P3-09; conserva su maquinaria.**
- **Qué:** dos umbrales por subsistema (*upset* recuperable / *damage* permanente) y una
  tasa de riesgo para fallo diferido. Reemplaza la aritmética
  `probabilidad · potencia · 0.5` por contabilidad de energía absorbida. Mantiene el
  decaimiento por tick y la **atribución diferida de bajas al disparo original**.
- **Dónde:** `src/models/drone.py` (estado por subsistema), `src/engine/simulation.py`
  (decaimiento por tick), `src/engine/analytics.py` (atribución diferida en `record_*`).
- **Tamaño:** M.
- **Por qué:** el thermal runaway de batería del checklist original **falla el
  presupuesto energético por ~10⁹** (10–20 kJ para llevar una 18650 a runaway, vs
  microjoules acoplados por un pulso de 100 ns a 500 V/m — auditoría §3.6). La
  literatura de EMI separa *upset* (recuperable, umbral bajo) de *damage* (permanente,
  umbral alto), y una sola sigmoide a "neutralizado" no puede expresar el caso
  operativamente decisivo: **un enjambre que se desordena y se recupera**. Encaja con los
  5 subsistemas de P1-C, y elimina el último "punto de daño" arbitrario del repo
  (auditoría §4.5).
- **Done:** con reloj controlado, un dron con *upset* recupera y uno con *damage* no; una
  baja diferida queda atribuida al disparo original en la curva de efectividad; la
  fracción upset/damage aparece en el panel.

### P2-E · OPFOR reactivo + perfiles de pérdida de enlace
**Era P2-06. Con el prerrequisito que faltaba.**
- **Qué:** (i) **partir `DroneEstado` en dos campos ortogonales** (`estado_salud` y
  `estado_enlace`); (ii) memoria del último punto de impacto con repulsor decadente;
  (iii) el jammer asigna perfil lost-link por dron (hover / aterrizar / RTH / flyaway)
  en vez de congelar.
- **Dónde:** `src/models/drone.py`, `src/models/jammer.py`, `src/engine/flocking.py`,
  `src/engine/simulation.py`.
- **Tamaño:** M.
- **Por qué:** el enum único mezcla salud con enlace, así que un dron interferido **y**
  dañado no es representable y la recuperación reconstruye la salud por inferencia
  (`DANADO if salud < 50 else ACTIVO`). Los perfiles lost-link son ortogonales a la salud
  por definición → sin partir el estado, P2-06 no se puede implementar limpio.
  Auditoría §3.4. Arregla además que los drones interferidos desaparecen del flocking de
  sus vecinos (siguen físicamente ahí).
- **Done:** tras una detonación la distancia media del enjambre al punto de impacto
  aumenta; cada perfil lost-link tiene test; un dron interferido sigue contando como
  vecino en `compute_headings`; la suite verde.

### P2-F · Presupuesto de potencia primaria y térmico del arma
- **Qué:** cargador / PRF / límite térmico del cañón; energía por disparo y tiempo de
  recuperación.
- **Dónde:** `src/models/hpm_weapon.py`, `src/models/hpm_system.py`,
  `src/engine/analytics.py`.
- **Tamaño:** S/M.
- **Por qué:** en sistemas reales (Epirus Leonidas, THOR) el límite no es el haz sino la
  potencia primaria y la refrigeración. Hoy el cañón dispara infinito a 25 kW, y eso
  **vacía de contenido a P3-A (WTA)**: sin restricción de energía, la asignación
  arma-blanco óptima es "disparale a todo". Con presupuesto, WTA pasa a ser un problema
  real y P3-C (coevolución) tiene una dimensión defensiva auténtica que optimizar.
- **Done:** el cañón agota y recupera energía; un test verifica que la cadencia sostenida
  queda acotada por el límite térmico; el panel reporta energía disponible.

### P2-G · Radar dinámico: barrido + filtro de track
**Era P2-05. Último de la fase por ser el más caro y el más destructivo de la calibración.**
- **Qué:** en **dos pasos**.
  1. Extraer la detección de `Swarm.actualizar` a un `TrackManager` con estado propio
     (posición *estimada*, velocidad, edad, calidad), **manteniendo el comportamiento
     actual**.
  2. Recién después: patrón de barrido con tiempo de revisita, filtro α-β-γ, pérdida de
     track por maniobra brusca, y migrar todos los consumidores a leer posiciones
     estimadas.
- **Dónde:** `src/engine/radar_engine.py`, `src/models/swarm.py`,
  `src/models/hpm_missile.py`, `src/models/hpm_system.py`, `src/config.py`.
- **Tamaño:** L.
- **Por qué:** hoy el radar es **omnisciente por construcción** — conoce la posición
  verdadera y solo decide si la revela (`drone.detectado`). Un filtro α-β-γ sobre un
  booleano en el objeto dron es decorativo, porque todos los consumidores
  (`HPMissile._resolver_objetivo`, `HPMissileSystem.lanzar`) leen `d.x, d.y` reales. Y
  `evaluar_deteccion` es determinista **a propósito** (anti-parpadeo): un modelo de
  revisita obliga a quitar ese hack. **Este ítem NO es aditivo**, contra lo que afirma el
  encabezado del checklist original. Auditoría §3.3.
- **Done (paso 1):** test de regresión — las bajas y el conteo de detectados son
  idénticos antes y después de la extracción. **(paso 2):** un dron dentro de rango se
  detecta recién tras la revisita; un dron que maniobra bruscamente pierde el track; sin
  track no hay lock-on nuevo; los cambios en los números calibrados quedan documentados.

---

## Fase P3 — Frontera (una vez que el instrumento mide)

### P3-A · Asignación arma-blanco optimizada (WTA)
**Era P3-07.**
- **Qué:** capa de decisión que, dados tracks detectados y presupuesto de munición/
  energía, calcula la asignación arma↔cluster que maximiza bajas esperadas.
- **Dónde:** nuevo `src/engine/targeting.py`, `/api/targeting/plan`,
  `src/engine/simulation.py`.
- **Tamaño:** M.
- **Depende de:** P2-F (sin presupuesto energético el problema es trivial) y P2-G paso 1
  (necesita tracks, no omnisciencia).
- **Por qué:** es el primer ítem que produce una **decisión** y no solo una predicción.
  Con presupuesto energético y tracks imperfectos, WTA es el problema real de un sistema
  C-UAS.
- **Done (reemplaza el criterio tautológico):** comparar contra **fuerza bruta exacta**
  en instancias pequeñas (≤6 armas × ≤6 clusters), no contra el greedy — la búsqueda
  local arranca desde el greedy y no puede ser peor por construcción. La esperanza de
  bajas por cluster se agrega sobre la **distribución** de acoplamiento, no sobre su
  media (la sigmoide es no lineal: sesgo de Jensen — auditoría §3.8).

### P3-B · Coevolución genética arma ↔ enjambre
**Era P3-10.**
- **Qué:** algoritmo genético de dos poblaciones con fitness medido por el runner Monte
  Carlo; salida: frontera de Pareto arma↔defensa.
- **Dónde:** nuevo `src/engine/coevolution.py`, `src/engine/experiments.py`.
- **Tamaño:** L.
- **Depende de:** **P1-A obligatorio**. Consume P2-D, P2-E, P2-F.
- **Por qué va último:** con el estimador actual el fitness es `P(aniquilación total) = 0`
  en casi todo el espacio → **gradiente nulo, el GA no evoluciona nada**. El checklist
  original declaraba `deps: requiere P1-01`, pero P1-01 existía y aun así el ítem estaba
  bloqueado: la dependencia real es *"requiere que P1-01 tenga un estimador con señal"*.
  Auditoría §3.7.
- **Done:** una corrida corta mejora el fitness de cada población y degrada el del
  adversario; la frontera de Pareto es reproducible con la misma semilla.

---

## Cortado

### ~~P3-08 · FDTD 2D de campo cercano~~
**Cortado.** Con `D = 0.6 m` y `f = 2.45 GHz`, la zona de campo cercano es
`2D²/λ ≈ 5.9 m`. El campo es de 1000×1000 m, la distancia de detonación 80 m, y el
enjambre por defecto está a 500–900 m. **Un parche FDTD de 10–20 m corrige un régimen al
que el simulador no llega nunca**: es el ítem más caro (L) con efecto cero sobre
cualquier resultado. Además el empalme es dimensionalmente frágil (Green 2D decae como
`1/√r`, Friis 3D como `1/r`) y un solver TEz 2D no puede representar un plato 3D.

Sustituido por **P2-C** (dos rayos + patrón de antena real), que opera en el rango donde
el simulador vive y hace de la altitud una variable táctica. Auditoría §3.5.

### ~~`HPM_PULSE_COUPLING_MAX = 3.0`~~
Cortado como concepto: lo reemplaza la ley por tramos de P1-E.

### ~~`HPM_COUPLING_K` y la gaussiana en el panel físico~~
Cortados en P0-C: un tercer modelo que no gobierna ninguna baja.

---

## Orden de ejecución

```
P0-A  radar/arma separadas                    S    ← horas, desconfunde P2-04
P0-B  RNG por réplica inyectado               M
P0-C  quitar gaussiana fantasma de la UI      S
─────────────────────────────────────────────────  el instrumento
P1-A  estimador con señal (bootstrap)         M    ← desbloquea P3-B
P1-B  MC sobre parámetros (+ error apuntado)  L    ← el cambio estructural
P1-C  5 subsistemas, eslabón más débil        M    (leer el PDF antes)
P1-D  test de regresión de calibración        S    ← protege todo lo demás
P1-E  Wunsch-Bell por tramos                  S
─────────────────────────────────────────────────  la física que importa
P2-A  sensibilidad global (Morris → Sobol)    M    ⭐ mayor salto científico
P2-B  dosis-respuesta por máxima verosimilitud M
P2-C  dos rayos + patrón de antena            M    ⭐ reemplaza P3-08
P2-D  upset/damage + fallo latente            M    ⭐ reemplaza P3-09
P2-E  OPFOR reactivo + lost-link              M    (estado partido primero)
P2-F  presupuesto energético del arma         S/M  ← da sentido a P3-A
P2-G  radar dinámico (2 pasos)                L    ← el más disruptivo, al final
─────────────────────────────────────────────────  frontera
P3-A  WTA con validación exacta               M
P3-B  coevolución genética                    L    ← gated por P1-A
```

## Trazabilidad con el checklist original

| Original | Destino | Estado |
|---|---|---|
| P1-01 Monte Carlo | P1-A + P1-B | implementado pero **defectuoso** → reescribir |
| P1-02 Reproducibilidad | P0-B | implementado, con carrera de hilos → arreglar |
| P1-03 Duty cycle | P1-E | implementado; duty ✅, `g(τ)` sin respaldo → citar |
| P2-04 Susceptibilidad | P0-A + P1-C | implementado; modelo distinto al del paper |
| P2-05 Radar dinámico | P2-G | pendiente, replanteado en 2 pasos |
| P2-06 OPFOR + lost-link | P2-E | pendiente, + prerrequisito de estado partido |
| P3-07 WTA | P3-A | pendiente, criterio de done corregido |
| P3-08 FDTD | ~~cortado~~ → P2-C | régimen inalcanzable |
| P3-09 Thermal runaway | P2-D | premisa cortada, maquinaria conservada |
| P3-10 Coevolución | P3-B | pendiente, gated por P1-A |
| — | P1-D, P2-A, P2-B, P2-F | **nuevos** |
