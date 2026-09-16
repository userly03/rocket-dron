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
      **Defectuoso:** el estimador es `P(aniquilación total)` y vale 0 casi siempre
      (medido: 1 baja en 240 exposiciones → `p̂=0`, `IC=[0, 0.32]`); y el MC varía solo
      la geometría del enjambre, no los parámetros del modelo. **Se reescribe en P1-A/P1-B.**
- [x] **P1-02 · Reproducibilidad: RNG sembrado + manifest + export** —
      `src/utils/reproducibilidad.py`, `/api/export`, `/api/manifest`.
      **Carrera de hilos:** `_rng` es global de módulo y lo comparten el hilo de
      experimentos y el de simulación en vivo. **Se arregla en P0-B.**
- [x] **P1-03 · Duty cycle: daño por pico y duración de pulso** — `HPM_DUTY_CYCLE`,
      `pulse_coupling_factor`, pico/promedio en el panel.
      El duty cycle coincide con el paper; `g(τ)=min(√(τ/τ_ref),3.0)` es un añadido
      sin cita y el `3.0` es un número mágico. **Se fundamenta en P1-E.**
- [x] **P2-04 · Huella de susceptibilidad: resonancia + polarización** —
      `frequency_coupling`, `susceptibility_coupling_factor`, sorteo por dron.
      Modelo distinto al del paper (lorentziana en frecuencia vs gaussiana en
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
      **CORRECCIÓN (2026-09-12, hallazgo de P2-A):** ese `0.0056` es real como
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

- [x] **P1-C · Recalibrar al modelo real: 5 subsistemas, eslabón más débil** —
      **CERRADO (2026-09-13) con criterio de aceptación RELAJADO, declarado por
      escrito — no con el criterio original.**
      qué: reemplazar el umbral agregado único (`E₀=500 V/m`, `k=0.0075`) por las cinco
      sigmoides del paper (GPS/GNSS LNA 150±30, flight controller 250±50, ESC gate oxide
      300±60, camera CMOS 200±40, BMS MOSFET 350±70 V/m) con `P_kill = 1 − Π(1−pᵢ)`.
      toca: `src/engine/hpm_engine.py`, `src/config.py`, `src/models/drone.py`.
      deps: P1-B.
      done ORIGINAL (no cumplido, ver más abajo): con P1-B activo, el MC reproduce
      51.4% @ 20 m y 13.1% @ 40 m dentro del ±1% declarado, **sin ajustar ningún
      umbral a esos puntos**.

      **Historia de la investigación (completa en `docs/FISICA_Y_MATEMATICA.md`
      §3.6/§3.6.1)**: el usuario consiguió y leyó el PDF completo del paper (17
      páginas — una primera pasada con el comando `file` había reportado
      incorrectamente "6 páginas", corregido con `pdfinfo`; no hay v2, no hacía
      falta, el v1 ya estaba completo). Trajo el código fuente del modelo y, clave,
      la **Tabla 3** con resultados en 5 distancias (no solo 2), incluida la media y
      desviación del CAMPO. Esto permitió:
      · **Confirmar y corregir** en el motor principal el piso de polarización sobre
        `η_pol=cos²φ` (potencia) y el modelo de apuntado gaussiano
        (`G_point=exp(-2.76·θ_norm²)`) — ver hallazgo 14.
      · **Descubrir que "CV≈39%" es el CV del CAMPO (V/m), no de la probabilidad de
        baja** — dos estadísticos que se venían comparando como si fueran el mismo.
        Medido correctamente: **el simulador reproduce la Tabla 3 del campo con
        precisión** (media dentro de 2-3%, CV=0.394 contra ≈0.39) —
        `tests/test_parametros.py::TestCampoReproduceLaTabla3`, PASA.
      · **El hallazgo central de este ítem**: aplicando el modelo de 5 subsistemas
        del PROPIO paper (Tabla 1 + Ec. 7, su sigmoide exacta, sin sustituir nada del
        proyecto) sobre ese campo que ya coincide, la probabilidad sale ≈100% en las
        5 distancias, no 51.4%-13.1%. **La Tabla 1 y la Tabla 3 del propio paper no
        son algebraicamente consistentes entre sí** — verificado con triple control
        (campo MC, campo determinista, dos sigmoides distintas). No es un defecto de
        este proyecto: es un defecto real del paper de referencia, del mismo tipo
        que el hallazgo 10 (los tres números publicados mutuamente inconsistentes).
      · **Descartado** que la cadena de voltios (Ec. 4-5, §4.5) sea el paso que
        falta: esa sección es un análisis mecanístico separado sobre el ESC
        (voltios contra ruptura MOSFET), y la Tabla 3 reporta el campo en V/m
        directo — sin pasar por voltios. No hay inconsistencia dimensional.

      **Cómo se cerró**: dado que el paper mismo no se puede corregir, se cierra
      para este proyecto reajustando el único parámetro libre
      (`HPM_COUPLING_FIELD_EFFICIENCY = 0.44`, MC en el lazo sobre los 5 puntos de
      la Tabla 3) y **aceptando explícitamente un margen más ancho** que el que el
      paper declara para sus propios 2 puntos (±1.0/±0.7pp): con `k=0.44` el
      residuo es pequeño y decrece monótonamente con la distancia (+2.1pp a 20m →
      −4.2pp a 40m), un patrón consistente con ruido de reimplementación
      independiente, no con un error conceptual. **El criterio original NO se
      cumple** — `k` es exactamente el ajuste que ese criterio prohíbe — y eso
      queda fijado en un test que falla si alguna vez SÍ se cumple sin querer
      (`test_no_cierra_dentro_del_margen_original_del_paper`), como señal de que
      hay que revisar si cambió algo.
      Tests: `tests/test_parametros.py::TestModeloSubsistemasCalibradoConReserva`
      (5 tests: reproduce la Tabla 3 dentro de ±5pp declarado, residuo monótono,
      control negativo del margen original, descarta k=1.0, confirma que el motor
      interactivo sigue en `"agregado"` por defecto).
      **Efecto colateral positivo:** al corregir la polarización en el motor
      principal, el sesgo de Jensen medido en P3-A pasó de +66% a **+83%**.
      Calibración (P1-D, modelo `"agregado"`) intacta — nada del comportamiento por
      defecto del simulador interactivo cambió. Suite completa 452/452.

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

- [x] **P1-F · Eliminar el piso de la sigmoide: logística en `ln E`, no en `E`**
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
      **CERRADO (2026-09-12).** `HPM_LINK_FUNCTION = "log_logistica"` por defecto; la
      logística queda seleccionable. `P(E=0) = 0` **exacto** en las dos rutas de daño.
      **Calibración movida y documentada:** 0.4356/0.1187 → **0.4677/0.1113**. Nótese
      que queda MÁS CERCA del paper a 20 m (−4.63 pp contra −7.84 pp). A 700 m la
      probabilidad cayó de 0.0253 a **0.00004** (factor 630).
      Se ajustó contra el campo del **paper**, no del simulador: `E₅₀` es propiedad de
      la electrónica del blanco, no de la antena del arma — ajustarlo contra el campo
      del simulador habría metido el déficit de ganancia del emisor dentro del umbral
      del blanco, el mismo error de categoría del hallazgo 2. El residuo de −4.63 pp
      es atribuible a ese déficit y se cierra con `HPM_ANTENNA_MODEL = "plato"`.
      **Conversión entre familias:** `b = E₅₀/σ` preserva la pendiente en `E₅₀`.
      Aplicada a la Tabla 1 del paper da **exactamente 5.0 en los cinco subsistemas**
      → hallazgo propio: la columna `σ_E` es literalmente `E₅₀/5` y **no aporta
      información independiente** de la columna `E₅₀`.
      **9 tests se movieron, cada uno con su justificación en el propio test.** Dos
      merecen mención:
      · El detector de regresiones de P1-D **dejó de detectar** y lo destapó su propio
        test: `verificar_calibracion` no pasaba `e50`/`b`/`link` explícitos, así que
        `monkeypatch` no los alcanzaba. Es la misma trampa que P1-D había resuelto, un
        nivel más arriba. Reparado y ampliado con un test nuevo que detecta el cambio
        de función de enlace (la regresión más grave posible tras P1-F).
      · `test_el_alcance_decrece_al_subir_el_umbral` parcheaba `e_threshold`, que la
        log-logística ignora: habría quedado comparando dos corridas idénticas,
        pasando por casualidad sin probar nada.
      **Efecto colateral valioso:** con el piso fuera, el cañón a 700 m da
      **exactamente 0 bajas en 12 réplicas** — la respuesta físicamente correcta. El
      `0.0056` de P1-A era íntegramente piso. Un estimador que nunca dice cero no sirve
      para decidir nada: los tests de P1-A se reorganizaron para validar con el misil
      (que sí engancha) más un test nuevo que verifica que el cañón reporta cero.
      **Sensibilidad re-corrida (hecho):** los índices se movieron y el hallazgo central
      **se agravó** — la suma de `S_T` de los parámetros no calibrados pasó de 0.43-0.59
      a **0.45-0.69**, y a 60 m es el **69 %** de la varianza. §3.8 actualizada.

- [x] **P1-G · Los tres números del paper son mutuamente inconsistentes**
      *(hallazgo derivado de P1-F, no es trabajo de código)*
      51.4 % @ 20 m y 13.1 % @ 40 m fijan `b = 2.81`; el alcance de 90 % de baja de
      ~18 m exige `b = 20.32` — factor **7.2**. Entre 497 y 552 V/m (+11 % de campo) la
      probabilidad tendría que saltar de 51.4 % a 90 %. Pasa con cualquier ajuste de dos
      parámetros, logística incluida (`P(552.4) = 0.597`, no 0.90).
      Explicación más probable (**inferencia**, no dato): los 18 m salen de su curva
      **determinista**, no de la Monte Carlo contra la que el simulador calibra. Los
      puntos deterministas del paper (83 % @ 20 m, 20 % @ 40 m) dan `b = 4.29`, y
      determinista + 18 m da `b = 5.81`: mismo orden. El 20.32 es el outlier.
      **Consecuencia retroactiva: el criterio de aceptación de P1-E (18 m/88 m) nunca
      fue alcanzable desde los puntos de calibración.** Explica por qué la brecha no
      cerró ni con la logística (11.74 m) ni con la log-logística (8.74 m).
      Fijado como aritmética verificable en
      `test_la_cifra_de_90pc_del_paper_es_internamente_inconsistente`. No es corregible
      desde acá: es un problema de la referencia. **Confirmar contra el PDF.**

## P2 — Física que cambia números en el rango real (semanas)

> **Estado P2 (2026-09-12).** P2-A cerrado — y su primer resultado fue destapar
> **P1-F**, un artefacto que domina el 90 % de la probabilidad reportada en todo el
> rango de combate por defecto. Eso es exactamente para lo que servía el ítem.

- [x] **P2-A · Análisis de sensibilidad global (Morris → Sobol)**
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
      · **Los dos que siguen NO están calibrados:** `coupling_field_efficiency`
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

- [x] **P2-B · Curva dosis-respuesta por máxima verosimilitud**
      qué: ajuste ML de `P(kill)` vs `E` desde las réplicas, con IC por bootstrap, y
      comparación automática contra los puntos de calibración. Cierra el lazo: se recupera
      la curva que el simulador **implica** y se contrasta con la que se le metió.
      toca: `src/engine/experiments.py`, `src/engine/validation.py`.
      deps: P1-A.
      done: el endpoint devuelve `E₅₀` y `σ_E` ajustados con IC; un test verifica que
      recuperan los valores de entrada dentro del IC al correr contra el propio modelo.
      **CERRADO (2026-09-12).** `GET /api/dosis-respuesta` + 17 tests. Ajuste por
      máxima verosimilitud vía **Newton-Raphson/IRLS** (log-verosimilitud logística
      cóncava, sin scipy), validado ANTES de usarlo contra datos sintéticos con
      parámetros conocidos (recupera `E₅₀`/`b` dentro de ±5-8% en 3 casos de prueba;
      converge en 8 iteraciones, igual resultado que con 200).
      **Adaptativo a `HPM_LINK_FUNCTION`** (log-logística por defecto desde P1-F): el
      ítem original pedía "E₅₀/σ_E" en lenguaje de logística — ajustar esa familia sobre
      un motor que corre en log-logística habría recuperado el modelo equivocado. Se
      ajusta la familia ACTIVA, con un "σ_E equivalente" (`E₅₀/b`) reportado aparte.
      **Sobre el motor real, huella de susceptibilidad fijada** (mismo criterio que la
      verdad conocida de P1-A): recupera `E₅₀=496.70` (configurado 487.39) y `b=2.8187`
      (configurado 2.8106), **ambos dentro del IC95%** — `recupera_la_calibracion=True`.
      **Control negativo, para confirmar que el chequeo no es decorativo:** datos con
      `E₅₀=700` (deliberadamente distinto) dan `recupera_la_calibracion=False` con el IC
      sin tocar el valor real configurado.

- [x] **P2-C · Dos rayos (reflexión en tierra) + patrón de antena real**
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
      **CERRADO (2026-09-12).** `src/engine/propagation.py` + 31 tests. Ambos efectos
      **opt-in** (`PROPAGATION_GROUND_REFLECTION`, `PROPAGATION_ANTENNA_PATTERN`) porque
      mueven la calibración de §3.4. Documentado en §3.9.
      **Patrón de Airy validado contra sus valores analíticos:** HPBW 12.05° (vs 11.91°
      de `58.4λ/D`), primer nulo a 14.40° con −118 dB, **primer lóbulo lateral a −17.57 dB
      exacto**. `J₁` con la aproximación de Abramowitz-Stegun §9.4 (error < 1e-7 contra
      valores tabulados), porque `scipy` no está en `requirements.txt`.
      **Hallazgo: el `cos²` subestima brutalmente el borde del haz.** +7.2 dB de
      discrepancia a 6°, **+28.9 dB a 7.4°**, y fuera del cono nominal `cos²` da
      exactamente cero mientras Airy da −5 dB (el primer nulo no llega hasta 14.4°).
      Integrado sobre el ángulo sólido, Airy ve **3.2× más potencia**. O sea: el modelo
      **subestima la letalidad fuera de eje** — con `cos²` un enjambre justo fuera del
      haz es perfectamente seguro.
      **MI PROPIA JUSTIFICACIÓN DE ESTE ÍTEM ERA FALSA.** El roadmap decía que la
      reflexión en tierra "convierte la altitud en variable táctica: un enjambre puede
      volar en un nulo". A 2.45 GHz las franjas miden **0.76 m a 100 m y 5.35 m a 700 m**,
      con **22–157 ciclos** en la banda de vuelo (40–160 m), y el dron oscila ±4 m:
      cruza varias franjas por oscilación. **Es el mismo error de escala que motivó
      cortar P3-08, cometido en su reemplazo.**
      **El uso correcto es estadístico:** `⟨|F|²⟩ = 2` exacto ⇒ el espacio libre
      **subestima la potencia media sobre tierra en 3.01 dB**, verificado en 6
      combinaciones de frecuencia (0.5/2.45 GHz) y rango (100/300/700 m). Más una
      dispersión p5–p95 de **−16 a +6 dB** que entra como varianza (y P2-A demostró que
      la varianza domina). La altitud **sí** es táctica por debajo de ~0.5 GHz (franja de
      26 m a 700 m), y `franja_resoluble()` lo dice en vez de dejarlo asumido.
      Fijado en `TestFranjasNoSonResolubles`, que falla si cambia la frecuencia, la
      altura del emisor o la amplitud de oscilación — porque entonces la conclusión
      cambia.

- [x] **P2-D · Upset vs damage + fallo latente**
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
      **CERRADO (2026-09-12).** `Drone.entrar_en_riesgo_latente` (punto de entrada
      compartido cañón/misil), `Swarm.actualizar_riesgos_latentes`,
      `analytics.record_delayed_kill` + `_upgrade_hit`, `Swarm.contar_upset_damage`. 38
      tests nuevos en `tests/test_upset_damage.py`.
      **Umbral de upset derivado del de daño YA CALIBRADO** (`E₅₀,upset = E₅₀,damage /
      10^(10dB/20) ≈ 154.13 V/m`), no de la Tabla 1 de P1-C —bloqueada— para no propagarle
      su falta de validación a un mecanismo nuevo. Zona `[P_damage, P_upset)` con ancho
      apreciable en todo el rango de combate (0.47-0.66 de ancho entre 20 y 60 m).
      **Energía absorbida con unidades reales** (`S_promedio·A_efectiva·duración`, en
      julios) reemplaza `probabilidad·potencia·0.5`. `A_efectiva = cable_length_m²`: no
      introduce parámetro libre nuevo, reutiliza la huella de susceptibilidad ya sorteada.
      Verificado: escala exactamente ×4 al duplicar el cable, ×2 al duplicar la duración.
      **Encontré y corregí mi propio error de diseño antes de cerrar el ítem:** el
      primer valor del hazard rate (`2.0/s`) parecía razonable mirado un tick, pero
      integrado sobre la cola de decaimiento (`P(falla eventual)=1-exp(-h₀·τ)`) daba
      **99.3% de muerte eventual** medido por simulación — contradecía el propio propósito
      del ítem ("se desordena y se recupera"). Corregido derivando `h₀=ln(2)/τ≈0.1733/s`:
      fija el PEOR caso de la zona de upset en un lanzamiento de moneda (50%), verificado
      contra la fórmula cerrada con 1500 repeticiones/severidad (±0.05 de tolerancia).
      **Comportamiento degradado real, no solo diagnóstico:** `flight_controller` en
      upset congela el rumbo (verificado contra un vecino control que sí gira);
      `gps_gnss_lna` en upset degrada RTH a "mantener rumbo" (verificado contra el mismo
      escenario sin el upset, que sí gira hacia home).
      **Atribución diferida verificada de punta a punta, sin forzar nada más que la
      maduración**: un disparo real a 30 m mete un dron en upset orgánicamente, el
      `shot_id` se atribuye correctamente, y tras 60 s el dron muere por fallo latente
      con `shot_history` mostrando `neutralizados: 1, bajas_diferidas: 1` en la entrada
      ORIGINAL — sin duplicar el conteo de `intentos` en la curva de efectividad.
      Calibración intacta (0.4677/0.1113, desviación <0.003 pp).

- [x] **P2-E · OPFOR reactivo + perfiles de pérdida de enlace** *(era P2-06)*
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
      **CERRADO (2026-09-12).** 22 tests nuevos en `tests/test_opfor.py`.
      **Estado partido sin romper la interfaz:** `estado_salud` (ACTIVO/DANADO/
      NEUTRALIZADO) y `estado_enlace` (OK/INTERFERIDO) como ejes ortogonales, con
      `estado` conservado como **propiedad derivada** (prioridad NEUTRALIZADO >
      INTERFERIDO > DANADO > ACTIVO) más un setter de compatibilidad que enruta cada
      valor a su eje **sin cruzarlos**. Verificado: un dron dañado Y sin enlace es
      ahora representable (antes imposible), los cuatro casos del getter dan lo mismo
      que antes, y asignar `estado = NEUTRALIZADO` a un dron interferido no le borra el
      enlace perdido. `HPMissile.detonar`, `HPMWeapon`, `drone_to_dict`, el frontend y
      los tests existentes siguen funcionando sin cambios.
      **Dispersión post-impacto contra su CONTROL** (mismo escenario, misma semilla,
      `amenaza_intensidad = 0`): distancia media al punto de impacto **22.54 m vs
      19.34 m**, un **+16.6 %**. Sin el control el test no probaría nada — el enjambre
      se mueve igual de todos modos.
      **Bug del vecino corregido:** un dron con enlace perdido ya no desaparece del
      flocking de sus vecinos. Verificado en un caso no degenerado: el rumbo del vecino
      es 60° con el interferido presente y 90° sin él.
      **Los cuatro perfiles, medidos:** flyaway se aleja monótonamente (100→250→400→550 m
      del centro); RTH converge al centro (100→2.4 m y luego orbita, porque no puede
      detenerse); aterrizar desciende a 2 m/s y toca suelo en **t = 49.9 s** desde 100 m
      (predicho 50.0) y **queda inerte para siempre** incluso tras recuperar el enlace;
      hover mantiene posición. Fracciones RTH 0.40 / HOVER 0.30 / ATERRIZAR 0.20 /
      FLYAWAY 0.10, justificadas contra doctrina pública de failsafe de flight
      controllers, con flyaway deliberadamente no nulo.
      **El quinto término del flocking está argumentado, no añadido:** es la misma forma
      funcional que la separación (1/distancia) contra un punto en memoria en vez de un
      vecino; es condicional (aporta **cero** exacto sin impactos previos, así que un
      enjambre nunca atacado vuela idéntico a antes de P2-E); decae; y es falsable por
      el test de control. Mismo criterio que la nota de diseño del término `home`.
      Corregida además una inconsistencia preexistente: la rama `n<2` de
      `compute_headings` no aplicaba `BOIDS_HOME_WEIGHT` al término home, a diferencia
      de las otras dos ramas.
      **nota:** `RTH` orbita alrededor del centro al llegar (no puede frenar). Es
      consistente con el modelo de velocidad constante del simulador, pero un RTH real
      aterriza o mantiene posición al llegar. Anotado, no corregido.

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
      **nota menor:** el interlock es PRE-disparo, así que el último disparo permitido
      puede sobrepasar el límite (medido: termina en 125.625 °C con `HPM_TEMP_MAX_C` =
      125). Es defendible —un interlock real chequea antes de disparar, no a mitad— pero
      el panel muestra `temperatura_c > temperatura_max_c`, que se lee como error.
      Arreglo trivial si se quiere: chequear `T + ΔT ≤ T_max` en vez de `T < T_max`.


- [x] **P2-G · Radar dinámico: barrido + filtro de track** *(era P2-05)*
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
      **CERRADO (2026-09-13).** `radar_engine.Track`/`TrackManager` + migración de
      `HPMissile`/`HPMissileSystem`. 21 tests nuevos en `tests/test_radar_dinamico.py`.
      **Paso 1 — regresión verificada:** en régimen estacionario (drones detenidos,
      muchas revisitas) el conteo de detectados coincide **exacto** con
      `evaluar_deteccion()` aplicada directamente — la ecuación no cambió, solo cuándo
      se consulta y dónde vive el resultado.
      **Paso 2 — barrido (`RADAR_REVISITA_S=1.0s`) + filtro α-β-γ**, validado
      empíricamente antes de confiar en él: sobre una trayectoria de velocidad
      constante (20s), el error de posición converge a <5m y la velocidad estimada
      converge dentro de un 15% de la real; el error NO diverge entre 10s y 40s de
      seguimiento (test explícito de estabilidad).
      **Pérdida de track por maniobra** (`RADAR_PERDIDA_TRACK_RESIDUAL_M=120m`)
      calibrada para distinguir vuelo normal de una maniobra real: verificado que 10s
      de giro boids al máximo (30 m/s) NO pierde el track, mientras que un salto de 3×
      el umbral SIEMPRE lo pierde.
      **Migración quirúrgica de los consumidores:** la adquisición de un blanco NUEVO
      (`_resolver_objetivo`, el centroide de auto-apuntado de `lanzar`) usa la posición
      ESTIMADA del track; la NAVEGACIÓN una vez fijado el objetivo sigue usando la
      posición VERDADERA sin cambios (el buscador propio del misil, documentado desde
      antes de P2-G). Verificado con un caso donde posición real y track apuntan a
      blancos opuestos: adquisición sigue al track, navegación sigue a la posición real.
      **Impacto medido en la calibración de intercepción:** 30/30 lanzamientos con
      semillas distintas detonaron correctamente (0 destruidos sin detonar) — la tasa
      del ~99% documentada en `MISSILE_MAX_TURN_RATE_DEG_S` no se degrada.
      Un test de regresión existente (`test_desacople_frecuencia.py`) pasaba de forma
      **vacía** tras la migración (comparaba `0 == 0` porque su helper usaba `dt=0.0`,
      que nunca dispara un barrido) — corregido forzando el reloj de barrido; ahora
      compara conteos reales de nuevo.
      Calibración intacta (0.4677/0.1113, desviación <0.003 pp).

## P3 — Frontera (una vez que el instrumento mide)

- [x] **P3-A · Asignación arma-blanco optimizada (WTA)** *(era P3-07)*
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
      **CERRADO (2026-09-13).** `src/engine/targeting.py` + `GET /api/targeting/plan`.
      40 tests nuevos en `tests/test_targeting.py`.
      **Sesgo de Jensen medido, no solo evitado**: bajas esperadas por Monte Carlo sobre
      la distribución de acoplamiento dan **0.0221**, contra **0.0121** usando el
      acoplamiento promedio — **+83%** de subestimación si se hubiera usado la media
      (la sigmoide es cóncava en el rango relevante). *(Número actualizado 2026-09-13
      tras corregir la distribución de polarización, ver P1-C más abajo — antes +66%,
      medido con la distribución vieja e incorrecta; el hallazgo cualitativo no cambió.)*
      **Validado contra fuerza bruta EXACTA** (no contra el propio greedy, que es
      tautológico por construcción — la búsqueda local arranca desde ahí):
      · 20 matrices de valor ALEATORIAS (sin estructura física), ≤6×6: **17/20 exactas**,
        gap medio 0.24%, máximo 2.30%.
      · 15 instancias REALISTAS (generadas por el modelo físico real, el caso de uso
        genuino): **15/15 exactas** — el óptimo, siempre.
      La brecha en instancias adversariales es un resultado TEÓRICO esperado (WTA es
      NP-difícil) y se declara, no se oculta.
      **La búsqueda local necesitó dos vecindarios, no uno**: con solo reasignación de un
      elemento, 4/20 instancias aleatorias no igualaban la fuerza bruta; añadiendo
      intercambio de pares (dos opciones ya asignadas cambian sus clusters), bajó a 3/20
      — mejora real, sin eliminar el problema teórico adversarial.
      Calibración intacta (0.4677/0.1113, desviación <0.003 pp).

- [x] **P3-B · Coevolución genética arma ↔ enjambre** *(era P3-10)* — **CERRADO (2026-09-13).**
      qué: GA de dos poblaciones con fitness medido por el runner Monte Carlo; salida:
      frontera de Pareto arma↔defensa.
      toca: nuevo `src/engine/coevolution.py`, `src/engine/experiments.py`.
      deps: **P1-A obligatorio.** Consume P2-D, P2-E, P2-F.
      por qué va último: con el estimador de v1 el fitness es `P(aniquilación total)=0` en
      casi todo el espacio → gradiente nulo, el GA no evoluciona nada. v1 declaraba
      `deps: requiere P1-01`, pero P1-01 existía y el ítem seguía bloqueado.
      done: una corrida corta mejora el fitness de cada población y degrada el del
      adversario; la frontera de Pareto es reproducible con la misma semilla.

      **Tres obstáculos reales encontrados y corregidos antes de cerrar** (ver
      docs/FISICA_Y_MATEMATICA.md §3.14 para el detalle numérico):
      1. A la distancia de combate por defecto del proyecto (~707 m) la letalidad del
         cañón (acotada por su presupuesto energético, P2-F) es de orden 1e-4 por disparo
         → fitness idénticamente 0.0, mismo problema que motivó este ítem, reaparecido un
         nivel más abajo. Corregido dando a `WeaponPolicy` un override de emplazamiento
         (`origen_x`/`origen_y`) y operando la coevolución a 60 m — dentro del alcance de
         90% de baja que el propio paper reporta para modo pulsado (~88 m).
      2. `duty_cycle` (rango `[0.01, 1.0]`, dos órdenes de magnitud, efecto multiplicativo)
         muestreado uniforme dejaba ~91% de la masa fuera de la región letal: 7 de 8
         individuos aleatorios daban fracción 0.0 en sus 4 réplicas, anulando la selección
         casi toda generación. Corregido con inicialización/cruce/mutación en escala
         logarítmica.
      3. Semillas de individuos consecutivos se solapaban parcialmente (mismo sorteo de
         enjambre para algunas réplicas de individuos distintos) — corregido espaciándolas
         por `réplicas_por_evaluación`.

      **Medido** (oponente fijo, para aislar el ruido de un rival que también evoluciona;
      fitness = media de la población, no el del mejor individuo — ver §3.14 sobre el
      "ceiling effect" del máximo a esta escala de letalidad):

      | Población | Fitness medio, gen. 1 → gen. 6 (semilla 42) |
      |---|---|
      | Arma vs. defensa fija (cuadrada, 20) | 0.0017 → 0.0100 (×6.0) |
      | Defensa vs. arma fija (80kW/15°/duty=0.01) | 0.9862 → 0.9963 |

      Arma final: `duty_cycle≈0.014` (extremo pulsado), `potencia≈31kW`. Defensa final:
      `formación=circular`, `cantidad≈54` — ambos coherentes con los dos gradientes reales
      documentados (pulsado > CW a igual energía; dispersión > formación compacta contra un
      arma de haz angosto). Reproducibilidad exacta con la misma semilla verificada
      (`tests/test_coevolution.py::TestReproducibilidad`). 23 tests nuevos, calibración
      intacta (0.4677/0.1113).
      *(Números re-medidos 2026-09-13 tras corregir la distribución de polarización del
      motor principal — ver P1-C más abajo; antes 0.0017→0.0158/×9.3 y 0.9813→0.9956. El
      hallazgo cualitativo no cambió.)*

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

- [x] `run_replica` descarta los eventos de `_tick()`. **CERRADO (2026-09-12).**
      Ahora procesa `eventos_misil`/`eventos_jamming` con los mismos métodos que usa el
      bucle interactivo (`_process_missile_events`/`_process_jamming_events`), así que
      una detonación de misil durante Monte Carlo deja el mismo rastro en `analytics`
      (shot_history, curva de efectividad) que una detonación en vivo. Verificado: un
      misil lanzado en una réplica sintética termina en `shot_history` con
      `tipo="misil"`, y una réplica completa con arma "misil" deja entradas en
      `distance_stats`.
- [x] El jammer es el único arma inmune a la huella de susceptibilidad. **CERRADO
      (2026-09-12).** Corregido de forma parcial y deliberada: `_en_zona_de_efecto` ahora
      aplica `susceptibility_coupling_factor(cable_length_m=None, polarization=...)`, o
      sea que el **mismatch de polarización SÍ afecta** al jammer (verificado: a r=700 m
      un dron con polarización óptima queda interferido y uno con polarización pobre no),
      pero la **resonancia de cableado NO** (verificado: dos drones con la misma
      polarización y cableado muy distinto dan la misma decisión). Argumento: la
      resonancia de cableado modela acoplamiento incidental a un arnés no apantallado que
      no fue diseñado como antena; el enlace de control sí tiene una antena receptora
      deliberada, sintonizada a su banda, sin ese desajuste aleatorio.
- [x] `requirements.txt` no declara `scipy`/`pandas`. **VERIFICADO, sin acción
      necesaria (2026-09-12).** `grep -rln "import scipy\|import pandas" src/ tests/`
      no devuelve nada: ninguno de los dos se usa en el proyecto. Son ruido preexistente
      del venv (probablemente de otra herramienta instalada en el mismo entorno), no una
      dependencia real — de hecho `experiments.py` y `sensitivity.py` documentan
      explícitamente que evitan `scipy` a propósito para que `requirements.txt` siga
      siendo la fuente de verdad del entorno. Añadirlos declararía una dependencia falsa.
- [x] **`check_shot_invariants` da falsos positivos desde P2-04.** **CERRADO
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
      `[VALIDACIÓN] la probabilidad no decrece con la distancia: d=898.67m→p=0.0097
      vs d=899.1m→p=0.0244`. El invariante es correcto solo a acoplamiento
      comparable; hay que añadir esa condición al chequeo o el log se llena de
      advertencias que no son defectos.
