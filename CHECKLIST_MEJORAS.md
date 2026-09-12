# CHECKLIST DE MEJORAS · v2

> **v2 (2026-09-12).** Reordenado y corregido tras la auditoría contra arXiv:2602.08477.
> El *por qué* de cada ítem y de cada reordenamiento está en
> [`docs/ROADMAP_CIENTIFICO.md`](docs/ROADMAP_CIENTIFICO.md); la evidencia de los
> defectos en [`docs/AUDITORIA_CHECKLIST.md`](docs/AUDITORIA_CHECKLIST.md).
> La v1 se conserva en [`docs/archivo/CHECKLIST_MEJORAS_v1.md`](docs/archivo/CHECKLIST_MEJORAS_v1.md).
>
> **Meta:** que el simulador sea un instrumento de medición defendible. Todo número que
> salga de él debe traer (a) fórmula identificada por categoría, (b) IC sobre la
> incertidumbre real del modelo, (c) índice de sensibilidad que diga de qué depende.
>
> Cada ítem se marca `[x]` cuando cumple su criterio de "done". Los `done` de v2 son
> falsables: si un criterio no puede fallar, no es un criterio.

---

## Ya implementado en v1 (verificado, con reservas)

- [x] **P1-01 · Monte Carlo + IC95%** — `src/engine/experiments.py`, `/api/experiments`.
      ⚠️ **Defectuoso:** el estimador es `P(aniquilación total)` y vale 0 casi siempre
      (medido: 1 baja en 240 exposiciones → `p̂=0`, `IC=[0, 0.32]`); y el MC varía solo
      la geometría del enjambre, no los parámetros del modelo. **Se reescribe en P1-A/P1-B.**
- [x] **P1-02 · Reproducibilidad: RNG sembrado + manifest + export** —
      `src/utils/reproducibilidad.py`, `/api/export`, `/api/manifest`.
      ⚠️ **Carrera de hilos:** `_rng` es global de módulo y lo comparten el hilo de
      experimentos y el de simulación en vivo. **Se arregla en P0-B.**
- [x] **P1-03 · Duty cycle: daño por pico y duración de pulso** — `HPM_DUTY_CYCLE`,
      `pulse_coupling_factor`, pico/promedio en el panel.
      ⚠️ El duty cycle coincide con el paper; `g(τ)=min(√(τ/τ_ref),3.0)` es un añadido
      sin cita y el `3.0` es un número mágico. **Se fundamenta en P1-E.**
- [x] **P2-04 · Huella de susceptibilidad: resonancia + polarización** —
      `frequency_coupling`, `susceptibility_coupling_factor`, sorteo por dron.
      ⚠️ Modelo distinto al del paper (lorentziana en frecuencia vs gaussiana en
      longitud; falta `L_eff=L/2`; polarización con distribución no física).
      **Se corrige en P1-C; su experimento estrella está confundido hasta P0-A.**

---

## P0 — Desconfundir (horas). Sin esto, las mediciones no valen

> **Fase P0 CERRADA (2026-09-12).** Suite: 123 → **149 tests verdes**.
> Verificado de forma independiente: generadores aislados, global intacto, dron
> reproducible con `rng` inyectado, fallback al global intacto, y sin referencias
> colgadas a `coupling_k`/`phys-k`/`probabilidad_referencia` fuera del uso interno del
> heatmap. Hallazgo 8 añadido a `docs/FISICA_Y_MATEMATICA.md` §1. Desviación aceptada:
> `Jammer` no recibió campo `rng` porque no hace ningún sorteo (su decisión es
> determinística sobre el campo E) — habría sido código muerto.

- [x] **P0-A · `RADAR_FREQUENCY_GHZ` independiente**
      qué: el radar deja de reutilizar `HPM_FREQUENCY_GHZ`. La ecuación de radar lleva
      `λ²`, así que barrer la frecuencia del arma hoy cambia también el alcance de
      detección → confunde el experimento de resonancia de P2-04 con un efecto
      instrumental.
      toca: `src/config.py`, `src/engine/radar_engine.py`, `src/models/swarm.py`.
      deps: ninguna.
      done: un test barre `HPM_FREQUENCY_GHZ` en [1, 8] GHz y el conteo de drones
      detectados **no cambia**; `RADAR_FREQUENCY_GHZ` por defecto 2.45 para no mover la
      calibración; suite verde.

- [x] **P0-B · RNG por réplica, inyectado**
      qué: `SimulationEngine` recibe su `numpy.random.Generator` en vez de leer el global
      del módulo; `seed_simulacion()` queda solo para la sim interactiva.
      toca: `src/utils/reproducibilidad.py`, `src/engine/simulation.py`,
      `src/engine/experiments.py`, `src/models/{drone,swarm,hpm_missile}.py`.
      deps: ninguna.
      done: un test corre un experimento **mientras** la sim interactiva corre y verifica
      que las réplicas son bit a bit idénticas a correrlo aislado; dos experimentos
      concurrentes con la misma semilla dan resultados idénticos entre sí.

- [x] **P0-C · Quitar la gaussiana fantasma de la UI**
      qué: el panel físico deja de publicar `probabilidad_referencia`/`formula`/
      `coupling_k` de `gaussian_neutralization_prob` — un tercer modelo que no gobierna
      ninguna baja pero se pinta en pantalla (`charts.js:144,148`, `index.html:85`).
      toca: `src/engine/analytics.py`, `frontend/js/charts.js`, `frontend/index.html`.
      deps: ninguna.
      done: el panel muestra solo el modelo que gobierna las bajas; `grep coupling_k` en
      el frontend no devuelve nada; suite verde.

## P1 — Reconstruir el instrumento (días). Esta fase levanta el techo

> **Estado P1 (2026-09-12).** Suite: **214 tests verdes**. Cerrados: P1-A, P1-D, P1-E.
> **P1-B parcial** (infraestructura y ganancia de plato sí; conexión al MC de enjambre
> no). **P1-C bloqueado** a falta del PDF del paper — con diagnóstico cuantificado de
> tres señales y la varianza atribuida. No se forzó ningún ajuste para cerrarlo.

- [x] **P1-A · Estimador con señal: la réplica es la unidad de muestreo**
      qué: fracción neutralizada media ± IC por bootstrap sobre réplicas; distribución
      completa de `neutralizados_por_replica` como salida de primera clase; Wilson
      conservado solo para métricas Bernoulli a nivel réplica, declarada secundaria.
      toca: `src/engine/experiments.py`, `src/api/routes.py`.
      deps: P0-B.
      done: con la config por defecto (cañón a ~700 m) el experimento reporta fracción
      media distinguible de 0 con IC finito; un test verifica que el IC por bootstrap
      cubre la fracción teórica en un caso analítico de quemarropa.
      **CERRADO (2026-09-12).** Métrica primaria `fraccion_media` con
      `ic95_bootstrap` (percentiles, 10.000 remuestreos, semilla fija) + `ic95_t`
      de contraste + `cv` + percentiles p5/p25/p50/p75/p95 + convergencia de la
      media. Wilson conservado, movido a `aniquilacion_total` y documentado como
      secundario. **Medido con la config por defecto:** `fraccion_media = 0.0056`,
      `IC = [0, 0.0139]` — contra `p̂ = 0.0`, `IC = [0, 0.3244]` de v1: **el IC es
      23× más estrecho y el punto ya no es 0**.
      ⚠ **CORRECCIÓN (2026-09-12, hallazgo de P2-A):** ese `0.0056` es real como
      salida del modelo, pero **a 700 m el 90.7 % de la probabilidad por dron es piso
      de la sigmoide, no física** (ver P1-F). El estimador funciona; lo que mide a rango
      largo está dominado por un artefacto del modelo de daño. La afirmación "el
      estimador ya tiene señal" se sostiene sobre la maquinaria estadística, **no**
      sobre el contenido físico del número. Se resuelve con P1-F. Verdad conocida: dos tests, uno
      sintético (Bernoulli(0.35), 60 réplicas, el IC la cubre con ancho < 0.15) y
      uno **a través del motor real** — 8 drones a 20 m en el eje del haz, cableado
      resonante (L = c/2f ⇒ η = 1) y polarización 1.0 ⇒ acoplamiento exactamente 1,
      cada dron Bernoulli(p) con la misma p sacada del propio
      `calculate_neutralization_probability_friis`; el IC sobre 40 réplicas la
      cubre. Sin scipy: tabla de t y bootstrap en numpy puro.
      *Nota de diseño descartado:* abrir el cono a 180° para "cubrir" a todos los
      drones NO funciona — `G ≈ 26000/apertura²` da G ≈ 0.80 a 180°, por debajo de
      isotrópico, y la probabilidad colapsa incluso a 1000 kW. En este modelo la
      apertura paga ganancia.

- [ ] **P1-B · Monte Carlo sobre parámetros, no solo sobre geometría**
      qué: `ExperimentConfig` lleva distribuciones, no escalares; el motor lee config
      inyectada en vez de constantes de módulo. Replicar las 7 fuentes del paper,
      empezando por la ausente: **error de apuntado `Rayleigh(σ=1°)`**. Polarización pasa
      a `cos²(Uniform[0,π])` con piso 0.1.
      toca: nuevo `src/engine/parametros.py`, `src/engine/experiments.py`,
      `src/config.py`, `src/engine/simulation.py`.
      deps: P1-A.
      done: `/api/experiments` acepta distribuciones por parámetro; un experimento con
      las 7 distribuciones reproduce el orden de magnitud del CV del paper (≈39% a 30 m);
      el manifiesto registra las distribuciones, no solo los escalares.
      **PARCIAL (2026-09-12).** Hecho y verificado:
      · `src/engine/parametros.py` — distribuciones como objetos de primera clase
        (`Constante`/`Normal`/`Uniforme`/`Rayleigh`/`NormalRelativa`), con
        `EspecificacionMC.nominal()` (retrocompatible, todo constante) y
        `.del_paper()` (las 8 fuentes de la Tabla 2). Serializables al manifiesto.
      · **Error de apuntado `Rayleigh(σ=1°)`: existe. Antes no estaba en absoluto.**
      · **Polarización corregida a `cos²(U[0,π])` con piso 0.1.** Verificado que la
        distribución es bimodal (tipo arcoseno): el `Uniforme[0.3,1.0]` viejo era plano
        y subestimaba la varianza, justo en la variable dominante.
      · **Ganancia de plato real `G = η(πD/λ)²`** → **21.16 dBi contra los 21.2
        publicados**. Cierra el sesgo sistemático de campo de **−6.4% a −0.5%**
        (el mismo que `test_calibracion.py` había medido idéntico en los dos puntos).
        Coexiste con la aproximación vieja bajo `HPM_ANTENNA_MODEL`; el default no
        cambia para no mover la calibración.
      · `monte_carlo_blanco_unico()` — el MC de parámetros del paper sobre un blanco
        único, que es la prueba de aceptación real (el número publicado es la
        probabilidad de baja de UN blanco bajo incertidumbre, no un resultado de
        enjambre). 36 tests nuevos en `tests/test_parametros.py`.
      **NO hecho:** la variación de parámetros **no** está conectada a las réplicas de
      enjambre (`run_replica` sigue usando la config nominal), porque eso exige el
      refactor de inyección de config en todo el motor y P1-C está bloqueado, así que
      todavía no se sabe qué distribución de acoplamiento es la correcta. Tampoco hay
      endpoint `/api/experiments` con distribuciones. **El CV medido es 0.6285 a 30 m
      contra el ≈0.39 del paper — el criterio de aceptación NO se cumple** (ver P1-C).

- [ ] **P1-C · Recalibrar al modelo real: 5 subsistemas, eslabón más débil**
      qué: reemplazar el umbral agregado único (`E₀=500 V/m`, `k=0.0075`) por las cinco
      sigmoides del paper (GPS/GNSS LNA 150±30, flight controller 250±50, ESC gate oxide
      300±60, camera CMOS 200±40, BMS MOSFET 350±70 V/m) con `P_kill = 1 − Π(1−pᵢ)`.
      El 500 V/m actual es más alto que los cinco: se ajustó una sigmoide determinista a
      dos puntos que son salida de un MC, absorbiendo su sesgo.
      toca: `src/engine/hpm_engine.py`, `src/config.py`, `src/models/drone.py`.
      deps: P1-B. **Prerrequisito: leer el PDF del paper directo** (la tabla de
      subsistemas de la auditoría es de segunda mano).
      done: con P1-B activo, el MC reproduce 51.4% @ 20 m y 13.1% @ 40 m dentro del ±1%
      declarado, **sin ajustar ningún umbral a esos puntos**; el umbral agregado viejo
      queda documentado como aproximación histórica.
      **⚠ BLOQUEADO (2026-09-12).** Implementado bajo `HPM_DAMAGE_MODEL =
      "subsistemas"` (default sigue `"agregado"`, nada por defecto depende de él), pero
      **NO valida**. Diagnóstico completo en `docs/FISICA_Y_MATEMATICA.md` §3.6.
      El argumento metodológico se sostiene: agregado = 2 params / 2 puntos = **0 gl,
      no falsable**; subsistemas = 1 param / 2 puntos = **1 gl, falsable**. Pero falla:
      · **Señal 1:** residuos −1.15 pp (20 m) y **+4.32 pp** (40 m), márgenes ±1.0/±0.7.
        Signos opuestos ⇒ ningún `k` único los cierra.
      · **Señal 2:** el MC queda por *encima* de su determinista; el paper reporta lo
        inverso ("MC systematically lower"). ⇒ la varianza está en la zona **convexa**
        (cola baja), donde promediar sube la media (Jensen).
      · **Señal 3:** CV = 0.6285 a 30 m contra ≈0.39 del paper.
      · **Atribución de varianza:** la **polarización explica el 55% del CV**
        (apagarla lo baja de 0.628 a 0.284 — *por debajo* del paper, así que la verdad
        está en medio). Coincide con el paper en *cuál* parámetro domina; discrepa en
        la *magnitud*.
      **ERROR DE MÉTODO QUE COMETÍ Y DESCARTÉ:** el primer ajuste dio `k=0.2568` con
      residuos −0.11/+0.62 pp, *dentro* de márgenes — pero ajustaba el cálculo
      **determinista** a puntos que son salida de un **Monte Carlo**, o sea absorbía el
      sesgo del MC dentro del parámetro: el defecto §1.3 cometido de nuevo. Lo delató
      que la dirección del sesgo salía opuesta a la que el paper declara.
      **Para desbloquear, confirmar contra el PDF (en orden de impacto):**
      (1) `F(θ_wire)`, el factor de orientación de cable, no está implementado y puede
      ser parcialmente redundante con `η_pol` → sobredispersión;
      (2) si el piso de 0.1 se aplica a `η_pol` o a `√η_pol` (cambia el mínimo de
      acoplamiento de 0.316 a 0.1 en amplitud, o sea toda la cola convexa);
      (3) la inconsistencia dimensional V/m vs voltios de la cadena de acoplamiento.
      El realce por resonancia se omitió a propósito: añadiría varianza y la señal 3
      dice que ya hay de más.
      Las tres señales están fijadas en
      `tests/test_parametros.py::TestModeloSubsistemasBloqueado`, con la lógica
      invertida: verifican que el modelo **no** cierra. Si alguien lo arregla, fallan.

- [x] **P1-D · Test de regresión de la calibración**
      qué: un test que re-deriva los dos puntos publicados desde la configuración actual
      y falla si alguno se mueve más del margen declarado.
      toca: nuevo `tests/test_calibracion.py`, helper en `src/engine/validation.py`.
      deps: ninguna (se puede hacer ya, contra la calibración actual).
      done: el test existe, pasa, y falla si se toca `HPM_E_THRESHOLD_V_M`,
      `HPM_CONE_APERTURE` o `HPM_DUTY_CYCLE`.
      **CERRADO (2026-09-12).** 12 tests + `GET /api/calibracion` +
      `validation.verificar_calibracion()`. **No hay deriva código↔documentación:**
      medido 43.56% @ 20 m y 11.87% @ 40 m, contra 43.6%/11.9% documentados en §3.4.
      Campo E: 465.48 / 232.74 V/m contra 497.2 / 248.6 del paper → **−6.4% en ambos
      puntos**, sesgo idéntico que confirma que es el offset de ganancia (20.6 vs
      21.2 dBi) y no un error de modelo. Tolerancia ±0.5 pp contra la fotografía del
      simulador; contra el paper solo informativa. Las 4 constantes rompen la tolerancia
      al parchearlas (verificado que el test SÍ puede fallar; hubo que leer
      `config.HPM_*` por atributo en la llamada, porque
      `calculate_neutralization_probability_friis` captura `e_threshold`/`steepness`
      como defaults de parámetro al importar y `monkeypatch` no los alcanzaba).

- [x] **P1-E · Ley de daño Wunsch-Bell por tramos**
      qué: reemplazar `g(τ)=min(√(τ/τ_ref),3.0)` por la ley de quemado de junturas con
      sus tres regímenes y ventana de validez: adiabático (`τ≲100 ns`, umbral `∝1/τ`) /
      difusión térmica (`∝τ^(−1/2)`) / estado estacionario (`τ≳10 µs`, independiente).
      Eliminar `HPM_PULSE_COUPLING_MAX`. El `√τ` actual **ya coincide** con el régimen de
      difusión térmica: falta la cita y los dos tramos.
      toca: `src/engine/hpm_engine.py`, `src/config.py`, `tests/test_duty_cycle.py`.
      deps: ninguna.
      done: **validar contra el blanco del paper — el modo pulsado extiende el alcance
      de 90% de baja de ~18 m a ~88 m.** El criterio viejo ("pulsado > CW") se retira:
      no puede fallar por álgebra.
      **CERRADO (2026-09-12).** Ley por tramos implementada, `HPM_PULSE_COUPLING_MAX`
      eliminada, `docs/FISICA_Y_MATEMATICA.md` §3.5 + referencia a Wunsch-Bell 1968.
      **Hallazgo: el exponente viejo tenía una raíz de más.** Wunsch-Bell da un umbral
      de POTENCIA y la sigmoide opera sobre CAMPO, así que falta `E_fail ∝ √P_fail` y
      el exponente correcto en difusión térmica es **1/4, no 1/2**. Y el tope mágico
      `3.0` resultó ser casi exactamente el techo físico del régimen estacionario
      (`(10000/100)^(1/4) = 3.1623`) — el **valor** estaba bien por casualidad, pero la
      saturación ocurría a τ ≈ 900 ns en vez de a los 10 µs físicos. Los dos defectos
      se cancelaban parcialmente, que es lo que los hacía invisibles.
      Continuidad verificada en ambos quiebres (salto < 1e-9). `g(τ_ref) = 1` exacto:
      calibración intacta (43.5634% / 11.8737%).
      **Alcance de 90% de baja medido: CW 11.74 m (paper 18 m), pulsado 52.50 m
      (paper 88 m), cociente 4.47 (paper 4.89).** La brecha absoluta está atribuida y
      cuantificada: el umbral agregado exige `E = 500 + ln(9)/0.0075 = 793 V/m` para el
      90%, mientras el paper declara 90% a ~552 V/m; el offset de ganancia (−6.4%) solo
      movería el alcance a ~12.5 m. **Es evidencia cuantitativa a favor de P1-C**
      (el OR-gate de 5 subsistemas alcanza el 90% a mucho menos campo). El cociente
      4.47 es `√(500/25) = √20`, una identidad algebraica del escalado de pico — se
      verifica como test de implementación, NO como validación física; el contenido
      falsable de P1-E son la continuidad, los exponentes y el techo.

- [ ] **P1-F · 🔴 Eliminar el piso de la sigmoide: logística en `ln E`, no en `E`**
      *(encontrado por P2-A el 2026-09-12 — no estaba en v1 ni en v2)*
      qué: la sigmoide de daño es logística en `E` y tiene soporte en todo ℝ, pero el
      campo eléctrico es POSITIVO. Consecuencia estructural: **`P(E=0) ≠ 0`.** Medido:
      **2.30 %** (modelo agregado) y **3.30 %** (OR-gate de 5 subsistemas). Un dron sin
      campo aplicado tiene 2-3 % de probabilidad de caer.
      **magnitud del daño al resultado:** más allá de **~97 m** MÁS DE LA MITAD de la
      probabilidad reportada es piso; a **700 m** (el rango de combate por defecto, con
      el enjambre circular a 500-900 m) el **90.7 %** del número es artefacto; a 2 km,
      el 96.6 %. **Todo el rango de combate por defecto está en zona dominada por el
      artefacto.**
      corrección **ya verificada**: reemplazar por una **log-logística**,
      `P(E) = 1/(1+(E₅₀/E)^b)`, que da `P(0) = 0` exacto. Ajuste a los dos puntos
      publicados: **E₅₀ = 487.39 V/m, b = 2.8106 → residuos 0.0000 pp en AMBOS**
      (el modelo actual se queda en −1.92 pp a 20 m). Mismos 2 parámetros libres, mismo
      grado de libertad, ajuste exacto y sin artefacto. A 700 m da 0.000040 en vez de
      0.025326 — un factor 633.
      por qué es la elección correcta y no un parche: una logística en `ln E` (o
      equivalentemente una log-logística en `E`) es el modelo estándar de dosis-respuesta
      para dosis positivas, precisamente porque el soporte de la distribución de umbrales
      es `(0, ∞)`. La logística en `E` implica que una fracción de la población falla a
      campo negativo, que no significa nada.
      toca: `src/engine/hpm_engine.py` (las dos funciones `_friis` y
      `probabilidad_dano_subsistema`), `src/config.py`, `tests/test_calibracion.py`
      (los valores se mueven: es un cambio que AFECTA LA CALIBRACIÓN y por eso es un
      ítem propio y no un arreglo silencioso), `tests/test_sensibilidad.py`
      (`test_desapunte_extremo_deja_el_PISO_de_la_sigmoide` debe fallar y actualizarse).
      deps: ninguna. **Debería ir antes que P2-B** (la curva dosis-respuesta ajustaría
      sobre un modelo con artefacto) y antes de cualquier conclusión a rango medio/largo.
      done: `P(0) = 0` exacto en ambos modelos de daño; los dos puntos publicados se
      reproducen con residuo < 0.1 pp; `tests/test_calibracion.py` actualizado con los
      valores nuevos y su justificación; sensibilidad re-corrida (los índices cambian:
      el piso estaba comprimiendo la varianza a rango largo).

## P2 — Física que cambia números en el rango real (semanas)

> **Estado P2 (2026-09-12).** P2-A cerrado — y su primer resultado fue destapar
> **P1-F**, un artefacto que domina el 90 % de la probabilidad reportada en todo el
> rango de combate por defecto. Eso es exactamente para lo que servía el ítem.

- [x] **P2-A · ⭐ Análisis de sensibilidad global (Morris → Sobol)**
      qué: descomposición de varianza de la probabilidad de baja sobre los ~20 parámetros
      libres. Screening de Morris primero, índices de Sobol después.
      toca: nuevo `src/engine/sensitivity.py`, `/api/sensitivity`.
      deps: P1-A, P1-B.
      por qué: es el mayor salto científico del roadmap. Hoy no se puede responder si una
      conclusión depende de un parámetro calibrado o de uno inventado — y es la defensa
      contra la crítica obvia al proyecto ("ajustaste 20 parámetros a 2 puntos de datos").
      done: informe reproducible con índices de primer orden y total; los 3 parámetros
      dominantes documentados en `FISICA_Y_MATEMATICA.md`; corre en CI con presupuesto
      reducido.
      **CERRADO (2026-09-12).** `src/engine/sensitivity.py` + `GET /api/sensibilidad`
      + 30 tests. Morris (efectos elementales, `μ*` con valor absoluto según
      Campolongo) y Sobol (estimadores de Saltelli 2010, coste `N(k+2)`). Documentado
      en `docs/FISICA_Y_MATEMATICA.md` §3.8. Todo en numpy; sin secuencias de Sobol
      porque `scipy` no está en `requirements.txt` → converge como 1/√N, declarado.
      **ESTIMADOR VALIDADO ANTES DE USARLO:** contra la función de Ishigami, que tiene
      índices analíticos, incluido el caso duro de `x₃` (`S₁`=0 exacto, `S_T`=0.244:
      puro efecto por interacción). Medido a `n_base`=32768: errores ≤ 0.012 en los
      seis índices; `x₃` da `S₁`=0.0034 y `S_T`=0.2416. Sin esa validación los índices
      sobre el modelo serían números sin respaldo, que es lo que P2-A viene a eliminar.
      **RESULTADOS (30 m, 13 parámetros, 30 720 evaluaciones):**
      · **La polarización domina:** `S₁`=0.571, `S_T`=0.647. Confirma por
        descomposición de varianza lo que §3.6 había estimado a mano (55 % del CV) —
        ahora con una fracción que *suma*, no una diferencia de varianzas.
      · **⚠ Los dos que siguen NO están calibrados:** `coupling_field_efficiency`
        (`S_T`=0.272, el parámetro provisional de P1-C bloqueado) y `pulse_duration_ns`
        (`S_T`=0.159, la extensión Wunsch-Bell que no viene del paper). **Juntos
        aportan 43-59 % de la varianza según la distancia.** Es el hallazgo central: hay
        que decirlo antes de publicar cualquier resultado del modelo de subsistemas.
      · **Los 5 umbrales publicados aportan poco** (`S_T` ≤ 0.024): su rango ±15 % es
        estrecho frente a la dispersión del acoplamiento. Orienta el esfuerzo de
        calibración hacia el acoplamiento, no hacia los umbrales.
      · **Interacciones relevantes:** `ΣS₁`=0.69-0.87 ⇒ quedarse en efectos principales
        perdería 13-31 % de la varianza. Justifica calcular `S_T`.
      · **Morris y Sobol coinciden 3/3** en los dominantes a las tres distancias
        (chequeo de sanidad interno: si discreparan, uno está mal muestreado).
      · `longitud_cable_m` da `S₁`=`S_T`=0 **exacto** — no es física, es la detección
        automática de que el realce por resonancia está omitido (§3.6). Se deja en el
        espacio a propósito, con un test que falla si alguien lo conecta.
      **Y encontró el defecto P1-F** (piso de la sigmoide), que no estaba buscado.

- [ ] **P2-B · Curva dosis-respuesta por máxima verosimilitud**
      qué: ajuste ML de `P(kill)` vs `E` desde las réplicas, con IC por bootstrap, y
      comparación automática contra los puntos de calibración. Cierra el lazo: se recupera
      la curva que el simulador **implica** y se contrasta con la que se le metió.
      toca: `src/engine/experiments.py`, `src/engine/validation.py`.
      deps: P1-A.
      done: el endpoint devuelve `E₅₀` y `σ_E` ajustados con IC; un test verifica que
      recuperan los valores de entrada dentro del IC al correr contra el propio modelo.

- [ ] **P2-C · ⭐ Dos rayos (reflexión en tierra) + patrón de antena real**
      *(reemplaza P3-08, cortado)*
      qué: interferencia directo/reflejado sobre tierra y patrón de antena con taper y
      lóbulos laterales, en lugar del hack `cos²` (que además es incoherente: `cos²` sobre
      densidad de potencia da `cos¹` en amplitud, mientras el modelo `legacy` aplica
      `cos²` a la probabilidad).
      toca: nuevo `src/engine/propagation.py`, `src/engine/hpm_engine.py`.
      deps: ninguna.
      por qué: opera en 50–900 m, donde el simulador vive, a diferencia de los 5.9 m de
      campo cercano del FDTD. Lobes y nulos de ±6 dB **convierten la altitud en variable
      táctica** — el simulador ya tiene altitud 3D (40–160 m) para representarlo.
      done: el campo E vs altitud a rango fijo muestra el patrón de lobes/nulos esperado
      para emisor a `z=8 m`; un test verifica la posición del primer nulo contra el
      cálculo analítico de diferencia de camino; sin impacto en el bucle de 60 FPS.

- [ ] **P2-D · ⭐ Upset vs damage + fallo latente**
      *(reemplaza la premisa de P3-09; conserva su maquinaria)*
      qué: dos umbrales por subsistema (*upset* recuperable / *damage* permanente) y tasa
      de riesgo para fallo diferido. Reemplaza `dano = probabilidad*potencia*0.5`
      (dimensionalmente vacío) por contabilidad de energía absorbida. Mantiene el
      decaimiento por tick y la **atribución diferida de bajas al disparo original**.
      toca: `src/models/drone.py`, `src/engine/simulation.py`, `src/engine/analytics.py`.
      deps: P1-C (los 5 subsistemas).
      por qué: el thermal runaway de batería falla el presupuesto energético por ~10⁹
      (10–20 kJ para una 18650 vs microjoules acoplados). La literatura de EMI separa
      upset de damage, y una sola sigmoide a "neutralizado" no puede expresar el caso
      decisivo: un enjambre que se desordena y **se recupera**.
      done: con reloj controlado, un dron con upset recupera y uno con damage no; una baja
      diferida queda atribuida al disparo original en la curva de efectividad; la fracción
      upset/damage aparece en el panel.

- [ ] **P2-E · OPFOR reactivo + perfiles de pérdida de enlace** *(era P2-06)*
      qué: (i) **partir `DroneEstado` en `estado_salud` y `estado_enlace`** — prerrequisito
      que v1 no listaba; (ii) memoria del último punto de impacto con repulsor decadente;
      (iii) el jammer asigna perfil lost-link por dron (hover/aterrizar/RTH/flyaway) en
      vez de congelar. Arregla también que los drones interferidos desaparecen del
      flocking de sus vecinos.
      toca: `src/models/drone.py`, `src/models/jammer.py`, `src/engine/flocking.py`,
      `src/engine/simulation.py`.
      deps: ninguna.
      done: tras una detonación la distancia media del enjambre al punto de impacto
      aumenta; cada perfil lost-link tiene test; un dron interferido sigue contando como
      vecino en `compute_headings`; suite verde.

- [x] **P2-F · Presupuesto de potencia primaria y térmico del arma**
      qué: cargador/PRF/límite térmico del cañón; energía por disparo y tiempo de
      recuperación. Hoy el cañón dispara infinito a 25 kW.
      toca: `src/models/hpm_weapon.py`, `src/models/hpm_system.py`,
      `src/engine/analytics.py`.
      deps: ninguna.
      por qué: en Leonidas/THOR el límite es potencia primaria y refrigeración, no el haz.
      Sin esto, P3-A (WTA) es trivial: la asignación óptima es "disparale a todo".
      done: el cañón agota y recupera energía; un test acota la cadencia sostenida por el
      límite térmico; el panel reporta energía disponible.
      **CERRADO (2026-09-12).** 8 constantes nuevas (todas en `_MANIFEST_KEYS`),
      `HPMWeapon` con `energia_actual_kj`/`temperatura_c`/`ultimo_rechazo`,
      `enfriar`/`recargar`/`actualizar` llamados desde `SimulationEngine._tick`,
      `presupuesto_arma` en el panel físico. 55 tests nuevos.
      **El térmico ata antes que el energético, por diseño:** 12.5 kJ y +4.375 °C por
      disparo ⇒ **23 disparos sostenidos** (usando 287.5 de 500 kJ). Verificado de forma
      independiente: la ráfaga se corta exactamente ahí. `τ = C/k = 100 s` de constante
      de enfriamiento, con la **solución exacta de Newton** (no Euler) — comprobado
      contra `T_amb+(T₀−T_amb)e^(−kt)` con error 0.00e+00 a t = 0/50/100/200 s.
      Recarga lineal a 10 kW (deliberadamente menor que los 25 kW de disparo: es la
      razón de existir de un banco intermedio) y satura en el máximo.
      **Problema de escala resuelto con criterio:** `potencia · HPM_PULSE_DURATION_NS`
      da mJ, irrelevante para cualquier presupuesto. Se introdujo
      `HPM_DISPARO_DURACION_S = 0.5 s`: la energía de "un disparo" es la de la **ráfaga
      completa**, no la de un pulso aislado. `HPM_PULSE_DURATION_NS` sigue gobernando
      solo `g(τ)` de Wunsch-Bell y no entra al balance. Declarado como decisión de
      modelado, no dato del paper (arXiv:2602.08477 no publica presupuesto térmico).
      El rechazo propaga limpio al API (mensaje explícito, sin excepción, sin
      contabilizar un disparo falso) — verificado.
      ⚠ **nota menor:** el interlock es PRE-disparo, así que el último disparo permitido
      puede sobrepasar el límite (medido: termina en 125.625 °C con `HPM_TEMP_MAX_C` =
      125). Es defendible —un interlock real chequea antes de disparar, no a mitad— pero
      el panel muestra `temperatura_c > temperatura_max_c`, que se lee como error.
      Arreglo trivial si se quiere: chequear `T + ΔT ≤ T_max` en vez de `T < T_max`.


- [ ] **P2-G · Radar dinámico: barrido + filtro de track** *(era P2-05)*
      qué: **en dos pasos.** (1) Extraer la detección de `Swarm.actualizar` a un
      `TrackManager` con estado propio (posición estimada, velocidad, edad, calidad),
      manteniendo el comportamiento actual. (2) Recién después: revisita, filtro α-β-γ,
      pérdida de track por maniobra, y migrar todos los consumidores a leer posiciones
      **estimadas**.
      toca: `src/engine/radar_engine.py`, `src/models/swarm.py`,
      `src/models/hpm_missile.py`, `src/models/hpm_system.py`, `src/config.py`.
      deps: ninguna, pero va al final de la fase: **no es aditivo.**
      por qué: hoy el radar es omnisciente por construcción — conoce la posición real y
      solo decide si la revela. Un filtro α-β-γ sobre un booleano en el dron es
      decorativo, porque `HPMissile._resolver_objetivo` y `HPMissileSystem.lanzar` leen
      `d.x, d.y` reales. Migrarlos **mueve el auto-apuntado, el punto de detonación y los
      números calibrados**.
      done (paso 1): test de regresión — bajas y conteo de detectados idénticos antes y
      después. (paso 2): un dron dentro de rango se detecta recién tras la revisita; un
      dron que maniobra pierde el track; sin track no hay lock-on nuevo; los cambios en
      los números calibrados quedan documentados.

## P3 — Frontera (una vez que el instrumento mide)

- [ ] **P3-A · Asignación arma-blanco optimizada (WTA)** *(era P3-07)*
      qué: capa de decisión que, dados tracks detectados y presupuesto de munición/
      energía, calcula la asignación arma↔cluster que maximiza bajas esperadas
      (greedy + búsqueda local).
      toca: nuevo `src/engine/targeting.py`, `/api/targeting/plan`,
      `src/engine/simulation.py`.
      deps: **P2-F** (sin presupuesto el problema es trivial) y **P2-G paso 1** (necesita
      tracks, no omnisciencia).
      done: comparar contra **fuerza bruta exacta** en instancias pequeñas (≤6 armas ×
      ≤6 clusters), no contra el greedy — la búsqueda local arranca desde el greedy y no
      puede ser peor por construcción. La esperanza de bajas por cluster se agrega sobre
      la **distribución** de acoplamiento, no sobre su media (sesgo de Jensen: la sigmoide
      es no lineal).

- [ ] **P3-B · Coevolución genética arma ↔ enjambre** *(era P3-10)*
      qué: GA de dos poblaciones con fitness medido por el runner Monte Carlo; salida:
      frontera de Pareto arma↔defensa.
      toca: nuevo `src/engine/coevolution.py`, `src/engine/experiments.py`.
      deps: **P1-A obligatorio.** Consume P2-D, P2-E, P2-F.
      por qué va último: con el estimador de v1 el fitness es `P(aniquilación total)=0` en
      casi todo el espacio → gradiente nulo, el GA no evoluciona nada. v1 declaraba
      `deps: requiere P1-01`, pero P1-01 existía y el ítem seguía bloqueado.
      done: una corrida corta mejora el fitness de cada población y degrada el del
      adversario; la frontera de Pareto es reproducible con la misma semilla.

---

## Cortado en v2

- ~~**P3-08 · FDTD 2D de campo cercano**~~ — con `D=0.6 m` y `f=2.45 GHz`, la zona de
  campo cercano es `2D²/λ ≈ 5.9 m`. El campo es de 1000×1000 m y el enjambre está a
  500–900 m: **corrige un régimen al que el simulador no llega nunca.** Ítem más caro (L)
  con efecto cero. Además el empalme es dimensionalmente frágil (Green 2D `1/√r` vs Friis
  3D `1/r`). **Sustituido por P2-C.**
- ~~`HPM_PULSE_COUPLING_MAX = 3.0`~~ — número mágico haciendo el trabajo de un cambio de
  régimen físico. Lo reemplaza P1-E.
- ~~`HPM_COUPLING_K` + gaussiana en el panel~~ — tercer modelo que no gobierna bajas.
  Lo quita P0-C.

## Deuda técnica menor (sin fase asignada)

- [ ] `run_replica` descarta los eventos de `_tick()`: nunca llama
      `_process_missile_events`, así que el MC no tiene diagnóstico por disparo ni curva
      de efectividad. Las bajas sí se cuentan.
- [ ] El jammer es el único arma inmune a la huella de susceptibilidad
      (`_en_zona_de_efecto` usa `campo_e_v_m` y no pasa `cable_length_m`/`polarization`).
      Defendible para CW, pero hay que documentarlo o corregirlo.
- [ ] `requirements.txt` no declara `scipy 1.18.0` ni `pandas 3.0.3`, instalados en el
      venv. El entorno no es reproducible desde requirements.
- [x] **`check_shot_invariants` da falsos positivos desde P2-04.** ✅ **CERRADO
      (2026-09-12).** Los eventos de `HPMWeapon.disparar` y `HPMissile.detonar` ahora
      llevan `factor_acoplamiento`; el chequeo exige offset angular **y** acoplamiento
      comparable (tolerancia relativa 15 %) antes de exigir monotonía, y degrada sin
      reportar si falta el dato (modelo `legacy`). Verificado con el caso real del log
      (acoplamientos 0.15/0.95 → **0 avisos**) y con monotonía realmente violada a
      acoplamientos comparables (0.90/0.92 → **sí avisa**), o sea que el chequeo no
      quedó ciego. La monotonía
      probabilidad-vs-distancia se verifica a offset angular igual
      (`_mismo_offset`, ±2°), pero la huella de susceptibilidad añadió una segunda
      variable por dron: dos drones a la misma distancia y mismo offset pueden tener
      acoplamientos `√(η·pol)` muy distintos. Observado en corridas reales:
      `[VALIDACIÓN] ⚠ la probabilidad no decrece con la distancia: d=898.67m→p=0.0097
      vs d=899.1m→p=0.0244`. El invariante es correcto solo a acoplamiento
      comparable; hay que añadir esa condición al chequeo o el log se llena de
      advertencias que no son defectos.
