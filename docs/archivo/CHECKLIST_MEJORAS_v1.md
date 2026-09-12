# CHECKLIST DE MEJORAS

Orden de implementación: P1 → P2 → P3. Cada ítem es aditivo (no rompe el resto)
y se marca `[x]` cuando cumple su criterio de "terminada". Las marcadas
**(frontera)** son experimentales de alto riesgo/alto valor.

---

## P1 — Impacto inmediato

- [ ] P1-01 · Monte Carlo + IC95%
      qué: runner headless que ejecuta N réplicas de un escenario y reporta probabilidad de baja con intervalo de confianza del 95% (Wilson) y serie de convergencia.
      toca: nuevo `src/engine/experiments.py`; `src/engine/simulation.py` (extraer `step()` sincrónico del `_run_loop`); `src/api/routes.py` (endpoints); nuevo `tests/test_experiments.py`.
      deps: ninguna (numpy; IC de Wilson implementado a mano).
      done: `pytest tests/test_experiments.py -v` verde + suite completa sin regresiones; `POST /api/experiments` corre N réplicas en hilo con progreso consultable y `GET /api/experiments/{id}` devuelve p̂, IC95% y convergencia; con N grande el IC contiene la probabilidad teórica del modelo en un caso de referencia de cañón a quemarropa.

- [ ] P1-02 · Reproducibilidad: RNG sembrado + manifest + export
      qué: semilla configurable, `numpy.random.Generator` threadeado en vez del global, manifiesto JSON por corrida y export CSV de trayectorias/eventos.
      toca: `src/config.py` (`SIM_SEED`); `src/models/drone.py`, `src/models/swarm.py`, `src/models/hpm_missile.py` (puntos de sorteo); nuevo `src/utils/reproducibilidad.py`; `src/api/routes.py` (`/api/export`); nuevo `tests/test_reproducibilidad.py`.
      deps: stdlib `csv`/`json` (sin pandas).
      done: test de determinismo (misma semilla → misma corrida bit a bit, misma cantidad de kills y posiciones finales); semilla distinta → resultado distinto; `/api/export` genera CSV con eventos de disparos/detonaciones parseables.

- [ ] P1-03 · Duty cycle: daño por pico y duración de pulso
      qué: el umbral de daño pasa a depender de `E_pico` y `τ_pulso` (latchup depende de la energía del pulso), separando CW vs pulsado; `HPM_PULSE_DURATION_NS` deja de ser cosmético.
      toca: `src/engine/hpm_engine.py` (funciones `friis`); `src/config.py` (`HPM_DUTY_CYCLE`, pico/promedio); `src/models/jammer.py` (caso límite CW); `src/engine/analytics.py` (panel); `tests/test_simulation.py` / `tests/test_missile.py`.
      deps: ninguna.
      done: tests verifican que a igual energía total, un pulso corto de alto pico neutraliza a más distancia que CW; el panel físico reporta pico y promedio; el modelo `legacy` sigue seleccionable y la suite completa sigue verde.

## P2 — Impacto alto

- [ ] P2-04 · Huella de susceptibilidad: resonancia + polarización
      qué: cada dron sortea longitud de cableado → frecuencia de resonancia propia; acoplamiento η(f) lorentziana + factor de mismatch de polarización por dron; `HPM_FREQUENCY_GHZ` se vuelve variable física.
      toca: `src/models/drone.py` (sorteo de `longitud_cable_m`), `src/models/swarm.py`, `src/engine/hpm_engine.py` (`friis_diagnostics`), `src/config.py`; tests nuevos en `tests/test_simulation.py`.
      deps: numpy.
      done: test que cambiar `HPM_FREQUENCY_GHZ` cambia las bajas contra una mezcla con `f_res` conocida (máximo de η cerca de la resonancia, mínimo lejos); el blindaje binario actual convive con la huella continua sin romper `apply_hardening_odds`.

- [ ] P2-05 · Radar dinámico: barrido + filtro de track
      qué: radar deja de ser umbral instantáneo por dron: patrón de barrido con tiempo de revisita, archivo de tracks con filtro α-β-γ y pérdida de track por maniobra brusca.
      toca: `src/engine/radar_engine.py` (rewrite a `TrackManager`); `src/models/swarm.py`; `src/models/hpm_missile.py` (lock-on sobre tracks); `src/config.py` (revisita, ganancia de proceso); tests.
      deps: numpy.
      done: un dron dentro de rango se detecta recién tras la revisita correspondiente (no al primer tick); un dron que maniobra bruscamente pierde el track; sin track no hay lock-on nuevo del misil (caso existente `guiado` cubierto por test); suite verde.

- [ ] P2-06 · OPFOR reactivo + perfiles de pérdida de enlace
      qué: drones recuerdan el último punto de impacto y aplican un repulsor con decaimiento (dispersión post-ataque); el jammer deja de congelar: asigna un perfil lost-link por dron (hover / aterrizar / return-to-home / flyaway).
      toca: `src/engine/flocking.py` (término de amenaza); `src/models/drone.py` (memoria + perfil); `src/models/jammer.py`; `src/engine/simulation.py` (eventos); tests.
      deps: ninguna.
      done: tras una detonación la distancia media del enjambre al punto de impacto aumenta (test); cada perfil lost-link tiene test (flyaway se aleja a rumbo fijo, RTH regresa al centro); recuperación de enlace respeta el perfil; suite verde.

## P3 — Frontera

- [ ] P3-07 · Asignación arma-blanco optimizada (WTA)
      qué: capa de decisión que, dado tracks detectados y presupuesto de munición/energía, calcula la asignación arma↔cluster que maximiza bajas esperadas (greedy + búsqueda local sobre el problema WTA).
      toca: nuevo `src/engine/targeting.py`; `src/api/routes.py` (`/api/targeting/plan`); `src/engine/simulation.py`; tests.
      deps: numpy.
      done: el plan cubre solo tracks detectados sin exceder la munición; en casos de prueba las bajas esperadas del plan ≥ bajas del greedy plano (test); endpoint verificable con curl; suite verde.

- [ ] P3-08 · **(frontera)** FDTD 2D de campo cercano
      qué: solver FDTD 2D (TEz) en numpy sobre un parche local (~10–20 m) alrededor de la detonación, acoplado en la frontera al campo Friis lejano; corre offline y alimenta una tabla de corrección para r < 2D²/λ.
      toca: nuevo `src/engine/em_field.py`; hook de lookup en `src/engine/hpm_engine.py`; chequeo cruzado en `src/engine/validation.py`; runner offline (CLI); tests.
      deps: numpy (numba opcional para velocidad).
      done: el solver es estable (test de condición de Courant) y converge (refinamiento de malla cambia el resultado menos del 5%); en la zona near-field la corrección difiere de Friis en la dirección físicamente esperada; sin impacto en el bucle de 60 FPS (tabla precalculada, fallback a Friis puro).

- [ ] P3-09 · **(frontera)** Thermal runaway con kills diferidos
      qué: energía absorbida del pulso → temperatura de celda Li-ion con decaimiento térmico por tick → probabilidad de *thermal runaway* con constante de tiempo propia; kills atribuidos al disparo original aunque ocurran ticks después.
      toca: `src/models/drone.py` (estado térmico); `src/engine/simulation.py` (decaimiento por tick); `src/engine/analytics.py` (atribución diferida en `record_*`); tests.
      deps: numpy.
      done: con reloj controlado, un dron dañado puede neutralizarse ticks después del pulso y el evento queda atribuido a ese disparo (test); la curva de efectividad registra kills diferidos; suite verde.

- [ ] P3-10 · **(frontera)** Coevolución genética arma ↔ enjambre
      qué: algoritmo genético de dos poblaciones (parámetros del arma vs parámetros del enjambre incl. evasión de P2-06) con fitness medido por el runner Monte Carlo; salida: frontera de Pareto arma↔defensa.
      toca: nuevo `src/engine/coevolution.py`; `src/engine/experiments.py`; `src/api/routes.py`; tests.
      deps: requiere P1-01 (y consume P2-04/P2-06 si existen, con fallback a parámetros fijos).
      done: corrida corta (pocas generaciones, réplicas reducidas) mejora el fitness de cada población y degrada el del adversario; test de no-regresión del motor con la corrida genética activa; suite verde.
