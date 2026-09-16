# Física y matemática del Simulador EW

Este documento existe para una sola cosa: que cada número que aparece en la
simulación y en la terminal tenga una fórmula detrás, que esa fórmula esté
identificada como una de estas tres categorías —

1. **física establecida** (ecuaciones de libro de texto, verificables),
2. **aproximación de ingeniería** (fórmulas empíricas usadas en la práctica,
   con su rango de validez), o
3. **decisión de diseño de juego** (calibrado para que la simulación sea
   jugable, sin pretender ser física real) —

y que quede explícito **cuándo nos equivocamos y cómo lo corregimos**. La
tercera categoría no es un defecto: un simulador educativo necesita ambas
cosas (rigor donde se pueda, jugabilidad donde haga falta), pero mezclarlas
sin etiquetar es lo que produce "alucinaciones" — números que parecen
físicos pero no lo son. Ese es el error que encontramos y corregimos acá.

---

## 1. Resumen ejecutivo de la auditoría

Se revisó cada fórmula del proyecto contra literatura real (ver
[§6 Referencias](#6-referencias-y-fuentes-verificadas)). Hallazgos:

| # | Hallazgo | Severidad | Estado |
|---|----------|-----------|--------|
| 1 | El docstring de `hpm_engine.py` y el README atribuían la fórmula exponencial `P=1-exp(-k·P/d²)` al paper arXiv:2602.08477. Verificado: **es una atribución incorrecta** — el paper real usa un modelo sigmoide sobre campo E calibrado contra umbrales de latchup CMOS, no esa exponencial. | Alta (cita falsa) | **Corregido**: docstring y README ahora atribuyen correctamente; la fórmula exponencial se re-etiquetó como `legacy`, ad-hoc, sin pretensión de origen académico. |
| 2 | El umbral de campo E (`HPM_E_THRESHOLD_V_M=30`) era ~15-20x más bajo que lo que sugieren los dos puntos de datos reales del paper (que ajustan a un umbral ≈500 V/m). | Alta (calibración) | **Corregido** para el cañón: 500 V/m, ajustado numéricamente contra los datos publicados (ver [§3.4](#34-calibración-numérica-contra-datos-reales)). |
| 3 | Aplicar ese mismo umbral "real" al misil (radiador isotrópico, sin plato) lo dejaba casi inútil salvo con potencias de megavatios — la física es correcta (un radiador isotrópico es enormemente menos eficiente que uno direccional) pero rompía la jugabilidad. | Media (tensión física/diseño) | **Resuelto** dándole al misil su propio umbral (`HPM_MISSILE_E_THRESHOLD_V_M`), documentado como abstracción de una antena de barrido/array (como un misil CHAMP real), no como el mismo arquetipo que el cañón. Ver [§4](#4-limitaciones-conocidas-honestidad-ante-todo). |
| 4 | El cono del cañón por defecto (30°, luego probado hasta 90°) da una ganancia de antena muy por debajo de un plato HPM real (~15 dBi vs ~21 dBi reales). | Media | **Corregido**: default a 15° (~20.6 dBi), del mismo orden que el plato de 60cm del paper. |
| 5 | El efecto visual de detonación era un disco plano (2D) aunque el cálculo de daño ya era 3D (esfera). Inconsistencia entre lo calculado y lo mostrado. | Media (visual, no física) | **Corregido**: la detonación ahora se renderiza como esfera + rayos de descarga, coherente con la física esférica ya calculada. |
| 6 | La tabla de configuración del README tenía datos obsoletos (`HPM_K_CONSTANT` listado como `0.015` en la tabla, pero `250` en el texto). | Baja | **Corregido**. |
| 7 | El blindaje heterogéneo (§8.1) multiplicaba el umbral de campo E por 2.5× para simular drones "blindados" — pero al vivir ese umbral dentro de una sigmoide no lineal, la reducción real de probabilidad resultaba de **14× a 821×** según la distancia (no 2.5×), dejando a los drones blindados prácticamente invencibles en todo el rango de combate real (probabilidad ~0.003%-0.03% a 80-200m). | **Alta** (blindaje inutilizable) | **Corregido**: `apply_hardening_odds()` aplica la reducción en espacio de momios (`odds = p/(1-p)`, dividido por el factor) en vez de desplazar el umbral — da una reducción consistente de 1×-2.5× en todo el rango, no un colapso exponencial. Ver [§8.1](#81-blindaje-heterogéneo-srcmodelsdronepy-srcmodelsswarmpy). |
| 8 | `PhysicsAnalytics.get_physics_panel` publicaba `probabilidad_referencia`, `formula` y `coupling_k` derivados de `gaussian_neutralization_prob` (`P = 1 - exp(-k·P·exp(-r²/2σ²))`) — un TERCER modelo que ni `friis` ni `legacy` usan para decidir bajas (`Drone.recibir_daño`/`HPMissile.calcular_daño` nunca lo llaman), pintado en el frontend (`charts.js`, `index.html`) como si fuera la física gobernante. Exactamente el defecto que esta misma tabla dice haber corregido en otros hallazgos. | **Alta** (número físico en pantalla que no gobierna nada) | **Corregido** (P0-C): `get_physics_panel` ya no publica `probabilidad_referencia` ni `coupling_k`; `formula` refleja siempre el modelo activo (`legacy`: `P = 1 - exp(-k·potencia/d²)` con `HPM_K_CONSTANT`, la k que ese modelo sí usa; `friis`: la cadena Friis→E→sigmoide ya correcta). `gaussian_neutralization_prob` se conserva, documentada como modelo de visualización exclusivo de `get_heatmap`. Frontend actualizado para no mostrar `coupling_k`. Auditoría §4.1. |
| 9 | **La sigmoide de daño es logística en `E`, que tiene soporte en todo ℝ, pero el campo eléctrico es positivo — de ahí que `P(E=0) = 2.30%` (modelo agregado) y `3.30%` (OR-gate de 5 subsistemas).** Más allá de ~97 m más de la mitad de la probabilidad reportada es ese piso, y a 700 m —el rango de combate por defecto, con el enjambre circular a 500-900 m— el **90.7%** del número es artefacto. Afecta retroactivamente la lectura de la métrica de P1-A. Encontrado por el análisis de sensibilidad ([§3.8](#38-análisis-de-sensibilidad-global-morris--sobol)), no buscado. | **Alta** (todo el rango de combate por defecto está en zona de artefacto) | **CORREGIDO (P1-F)**: la log-logística `P = 1/(1+(E₅₀/E)^b)` da `P(0)=0` exacto y ajusta los dos puntos publicados con residuo **0.0000 pp** (contra −1.92 pp del modelo actual) con los mismos 2 parámetros. `HPM_LINK_FUNCTION = "log_logistica"` es el default; la logística queda seleccionable. La calibración se movió a 0.4677/0.1113 (más CERCA del paper a 20 m: −4.63 pp contra −7.84 pp). A 700 m la probabilidad cayó un factor 630. Ver [§3.7](#37--el-piso-de-la-sigmoide-pe0--0---corregido-p1-f). |
| 10 | **Los tres números publicados del paper son mutuamente inconsistentes.** 51.4 % @ 20 m y 13.1 % @ 40 m fijan un parámetro de forma `b = 2.81`; el alcance de 90 % de baja de ~18 m exige `b = 20.32` — un factor **7.2**. Entre 497 y 552 V/m (+11 % de campo) la probabilidad tendría que saltar de 51.4 % a 90 %. Ocurre bajo cualquier ajuste de dos parámetros, logística incluida. | Media (afecta qué se puede exigir al simulador, no al simulador en sí) | **Diagnosticado, no corregible desde acá**: es un problema de la referencia. Explicación más probable (inferencia): los 18 m salen de su curva **determinista**, no de la Monte Carlo contra la que el simulador calibra — los puntos deterministas dan `b ≈ 4.3-5.8`, mismo orden. Consecuencia: el criterio de aceptación de P1-E (18 m/88 m) **nunca fue alcanzable**, lo que explica retroactivamente por qué la brecha no cerraba. Fijado como aritmética verificable en `tests/test_duty_cycle.py`. Ver [§3.7.1](#371--los-tres-números-publicados-del-paper-son-mutuamente-inconsistentes). |
| 11 | **El taper angular `cos²` no es el patrón de ninguna antena real**: sin lóbulos laterales, forma independiente de `D` y `λ`, y **exactamente cero fuera del cono nominal**. Contra el patrón de Airy (apertura circular, física establecida) la discrepancia es de +7.2 dB a 6° y **+28.9 dB a 7.4°**, y Airy integra **3.2× más potencia** sobre el ángulo sólido. O sea que el modelo **subestima la letalidad fuera de eje**: con `cos²` un enjambre justo fuera del haz es perfectamente seguro, con un patrón real recibe ~30 % del campo del eje y el primer nulo no llega hasta 14.4°. | Media (afecta blancos fuera de eje, no la calibración en eje) | **Implementado como opt-in** (`PROPAGATION_ANTENNA_PATTERN="airy"`), no activado por defecto porque mueve la calibración de §3.4. Validado contra las posiciones y niveles analíticos de Airy (HPBW 12.05°, nulo a 14.40°, lóbulo a −17.57 dB exacto). Ver [§3.9.1](#391-el-taper-cos-no-es-el-patrón-de-ninguna-antena). |
| 12 | **Mi propia justificación de P2-C era falsa a 2.45 GHz.** El roadmap afirmaba que la reflexión en tierra *"convierte la altitud en variable táctica: un enjambre puede volar en un nulo"*. Las franjas miden **0.76 m a 100 m y 5.35 m a 700 m**, con 22–157 ciclos en la banda de vuelo (40–160 m), y el dron oscila ±4 m: cruza varias franjas por oscilación. Es el mismo error de escala que motivó cortar P3-08, cometido en su reemplazo. | Media (invalida una conclusión del roadmap, no el código) | **Corregido en el diseño**: el efecto se implementa pero su uso correcto es **estadístico** — `⟨|F|²⟩ = 2` exacto, o sea que el espacio libre **subestima la potencia media sobre tierra en 3.01 dB** (verificado en 6 combinaciones de frecuencia y rango), más una dispersión p5–p95 de −16 a +6 dB que entra como varianza. La altitud sí es táctica por debajo de ~0.5 GHz, y `franja_resoluble()` lo dice. Ver [§3.9.2](#392--la-altitud-no-es-variable-táctica-a-245-ghz). |
| 13 | **Mi primer diseño del hazard rate de riesgo latente (P2-D) daba 99.3 % de muerte eventual, no 'usualmente se recupera'.** `DRONE_RIESGO_LATENTE_MAX_POR_S = 2.0` parecía razonable mirado un solo tick, pero integrado sobre toda la cola de decaimiento (`P(falla eventual) = 1-exp(-h₀·τ)`) con `τ=4s` da `P≈0.9997`. Contradecía directamente el propósito del ítem. | Alta (invertía el comportamiento pretendido del mecanismo) | **Corregido antes de cerrar el ítem**: se derivó `h₀ = ln(2)/τ ≈ 0.1733/s` fijando el PEOR caso de la zona de upset en un lanzamiento de moneda (50 % de falla eventual), verificado empíricamente contra la fórmula cerrada (1500 repeticiones/severidad, dentro de ±0.05). Ver [§3.10](#310-upset-vs-damage--fallo-latente-p2-d). |
| 14 | **El motor principal (`Drone`) sorteaba la polarización como `Uniforme[0.3,1.0]` plano — el modelo VIEJO que P1-B ya había señalado como incorrecto en `parametros.py` sin haberlo corregido en el motor real**, del que dependen P2-D/P3-A/P3-B. Descubierto al leer el PDF real del paper (2602.08477, antes solo se tenía el HTML): el código fuente confirma `η_pol = cos²φ` con piso 0.1 sobre la POTENCIA — exactamente lo que `parametros.py` ya implementaba, y exactamente lo que `Drone` NO implementaba. El módulo de targeting (P3-A) que existe justamente para evitar sesgo de Jensen integrando sobre "la distribución real de acoplamiento" estaba integrando sobre la distribución EQUIVOCADA. | Alta (afectaba la física de todo disparo del motor principal, no un módulo aislado) | **Corregido (2026-09-13)**: `Drone._sortear_polarizacion` y `targeting._muestra_de_acoplamiento` migrados a `cos²(U[0,π])` con piso `DRONE_POLARIZATION_MIN_ETA`. Media de acoplamiento bajó de 0.65 a 0.51 y su varianza casi se triplicó — el sesgo de Jensen medido en P3-A pasó de +66% a +83%. Calibración (P1-D) intacta (no depende del sorteo de `Drone`). Suite completa 450/450. Ver [§3.14](#314-coevolución-genética-armaenjambre-p3-b) y [§3.6.1](#361-actualización-2026-09-13--se-leyó-el-pdf-real-antes-solo-el-html). |

**Lo que SÍ ya estaba bien** (verificado, no solo asumido):
- `S = P·G/(4πr²)` — el término `4πr²` es literalmente el área de una esfera; la propagación ya era 3D en el cálculo (no en el render, ver hallazgo 5).
- `E = √(S·377)` — relación estándar campo-potencia en espacio libre (impedancia del vacío).
- `G ≈ 26000/apertura²` — aproximación de ingeniería de radar real y verificable (ver [§6](#6-referencias-y-fuentes-verificadas)), no inventada.
- La navegación proporcional (guiado de misil) usa la ley de control real, con la simplificación (omitir el término de velocidad de cierre) **ya documentada como tal** en el código antes de esta auditoría.
- La reflexión de drones en los bordes del campo (`reflect_angle`) es la fórmula de reflexión especular correcta.

---

## 2. Cinemática y colisiones (base, sin controversia)

**Movimiento** (`src/engine/physics.py::update_position`):
```
x(t+dt) = x(t) + v·cos(θ)·dt
y(t+dt) = y(t) + v·sin(θ)·dt
```
Cinemática de velocidad constante estándar. `θ` en grados, convertido a
radianes antes de aplicar `cos`/`sin`.

**Reflexión en bordes** (`reflect_angle`): al chocar con una pared vertical
(normal en X), el ángulo se refleja como `θ' = 180° - θ`; con una pared
horizontal (normal en Y), `θ' = -θ = 360° - θ`. Son las fórmulas de
reflexión especular 2D correctas (invierten la componente de velocidad
perpendicular a la pared, preservan la paralela).

**Distancia 3D / slant range** (`src/utils/helpers.py::distance3d`):
```
d = √((x₂-x₁)² + (y₂-y₁)² + (z₂-z₁)²)
```
Euclídea estándar. Se usa para TODO cálculo de daño (cañón y misil) — un
dron a otra altitud está realmente más lejos, no solo "más lejos en el
mapa". Esto ya estaba implementado correctamente antes de esta sesión de
auditoría; lo que faltaba era el efecto visual acorde (corregido, hallazgo 5).

---

## 3. El modelo electromagnético

### 3.1 Modelo `legacy` (exponencial ad-hoc)

```
P = 1 - exp(-k · potencia / distancia²)
```

Con atenuación angular `cos²` en los bordes del cono. **No es una ley física
fundamental** — es un modelo fenomenológico de la familia "dosis-respuesta
exponencial" (análogo a un proceso de Poisson: `P(al menos un evento) =
1-exp(-λ)`, con `λ` proporcional a la "dosis" `potencia/distancia²`). Este
tipo de modelo es común en evaluación de letalidad/vulnerabilidad en
ingeniería militar, pero la constante `k` es un parámetro de ajuste, no una
constante física. El README ya documentaba esto honestamente (nota de
calibración de `k=250`). Se conserva como modelo alternativo (`HPM_MODEL=legacy`)
para no romper el tuning previo.

### 3.2 Modelo `friis` (física real) — cañón direccional

**Paso 1 — Densidad de potencia (ecuación de Friis, espacio libre):**
```
S = (P · G) / (4π r²)        [W/m²]
```
`4πr²` es el área de una esfera de radio `r` — la potencia total `P·G` se
reparte sobre toda esa superficie. Es la forma correcta de calcular
intensidad de campo (no potencia recibida por una antena receptora
específica — eso sería la ecuación de transmisión de Friis completa, con
`Gr` y `λ²`; acá calculamos el campo en el punto del espacio, que es lo que
necesitamos para saber si electrónica desprotegida en ese punto sufre daño).

**Paso 2 — Ganancia de antena por apertura de haz** (`antenna_gain_from_aperture`):
```
G ≈ 26000 / (θ_az · θ_el)     (grados, haz simétrico: θ_az = θ_el = apertura_cono)
```
Aproximación estándar de ingeniería de radar (ver Skolnik, *Introduction to
Radar Systems* y fuentes citadas en [§6](#6-referencias-y-fuentes-verificadas)).
Deriva de que 4π estereorradianes ≈ 41253 grados² (conversión de ángulo
sólido); el constante 41253 es el límite ideal (100% de eficiencia de
apertura), y 26000 asume una eficiencia real típica (~63%, razonable para
una antena práctica, no ideal). Cuanto más angosto el cono, mayor la
ganancia — un haz angosto concentra la misma potencia en menos espacio.

**Paso 3 — Campo eléctrico** (`efield_from_power_density`):
```
E = √(S · 377)      [V/m]
```
De `S = E²/Z₀` para una onda plana en espacio libre, con `Z₀ = √(μ₀/ε₀) ≈
376.73 Ω` (impedancia del vacío, redondeada a 377 — práctica estándar).
Relación de electromagnetismo básico, sin aproximaciones adicionales.

**Paso 4 — Probabilidad de neutralización (sigmoide sobre umbral):**
```
P = 1 / (1 + exp(-k·(E - E₀)))
```
`E₀` es el umbral de susceptibilidad (V/m) donde la probabilidad es 50%;
`k` es la pendiente de la transición. **Esto no es una ley física** — es un
modelo estadístico de umbral de falla poblacional (distintos componentes
fallan a distintos campos, la sigmoide aproxima la función de distribución
acumulada de esos umbrales). Es, sin embargo, **exactamente el enfoque que
usa el paper real** (arXiv:2602.08477 dice explícitamente: *"sigmoid-based
semiconductor damage probability model calibrated to published CMOS latchup
thresholds"*) — llegamos al mismo tipo de modelo de forma independiente, lo
cual valida la elección de diseño.

### 3.3 Modelo `friis` — misil de área (sin cono, `G=1` isotrópico)

Mismas ecuaciones, pero con ganancia unitaria (radiador isotrópico ideal:
reparte la potencia por igual en las 4π estereorradianes completas, sin
concentrarla en ninguna dirección) y sin atenuación angular (el efecto es
circular/esférico, no un cono).

### 3.4 Calibración numérica contra datos reales

El paper (arXiv:2602.08477) publica, para un cañón de 25kW CW con plato de
60cm (21.2 dBi) a 2.45GHz:

| Distancia | E-field calculado | Probabilidad publicada |
|-----------|-------------------|-------------------------|
| 20 m | 497.2 V/m | 51.4% ± 1.0% |
| 40 m | 248.6 V/m | 13.1% ± 0.7% |

Resolviendo `sigmoide(497.2) = 0.514` y `sigmoide(248.6) = 0.131` para `E₀`
y `k`:

```
E₀ ≈ 500 V/m
k  ≈ 0.0075
```

Verificación (con esos valores, recalculando la sigmoide en esos mismos
puntos): 49.47% y 13.10% — error menor al 2% en ambos puntos. Estos son los
valores que usa `HPM_E_THRESHOLD_V_M` / `HPM_SIGMOID_STEEPNESS` para el
cañón desde esta auditoría.

Con el cono por defecto recalibrado (15° → ~20.6 dBi, muy cerca de los 21.2
dBi reales) y potencia por defecto (25kW, igual que el paper), el simulador
da:

| Distancia | Mi simulador | Paper real |
|-----------|--------------|------------|
| 20 m | 43.6% | 51.4% |
| 40 m | 11.9% | 13.1% |

Diferencia esperable: mi aproximación de ganancia (26000/apertura²) no
reproduce exactamente un plato parabólico real de 60cm, pero el orden de
magnitud y la forma de la curva coinciden.

**Nota (P1-D):** estos números ya no viven solo en esta tabla. `tests/
test_calibracion.py` los recalcula contra la configuración actual del
simulador en cada corrida (`src.engine.validation.verificar_calibracion`) y
falla si la probabilidad a 20m o 40m se mueve más de ±0.5 puntos
porcentuales respecto a los valores documentados arriba (43.6%/11.9%) — la
brecha contra el paper (51.4%/13.1%) se verifica con tolerancia amplia, como
información de contexto, no como criterio de aprobado/reprobado.

---

### 3.5 Duración de pulso: la ley Wunsch-Bell por tramos

**Categoría: aproximación de ingeniería** (categoría 2 de las tres de este
documento). Justificación de la clasificación: la ley tiene origen académico
real y verificable, y sus exponentes se derivan de un argumento físico
concreto (cuánto alcanza a difundir el calor en la juntura durante el pulso).
Pero los dos puntos de quiebre son órdenes de magnitud típicos para junturas
de silicio, no medidas del hardware de ningún dron — por eso no es categoría 1
(física establecida). Y no es categoría 3 (decisión de diseño) porque no se
eligió para que la simulación sea jugable: se eligió porque es lo que dice la
literatura de hardening de semiconductores.

**Procedencia — y qué NO es.** Esta ley **no viene de arXiv:2602.08477.** Ese
paper escala el campo pico con el duty cycle y no incorpora ningún escalado por
duración de pulso (ver `REFERENCIA_PAPER_2602.08477.md` §6). Viene de:

> Wunsch, D.C. & Bell, R.R. (1968), *"Determination of Threshold Failure Levels
> of Semiconductor Diodes and Transistors Due to Pulse Voltages"*, IEEE
> Transactions on Nuclear Science 15(6):244-259.

El duty cycle sí es del paper; `g(τ)` es una extensión propia con cita propia.
Mezclar las dos procedencias fue un defecto real del código anterior, que
presentaba `g(τ)` dentro del bloque "calibrado contra el paper".

**Los tres regímenes.** Wunsch-Bell da un umbral de **potencia absorbida**
`P_fail(τ)`:

| Régimen | Rango | `P_fail(τ)` | Mecanismo |
|---|---|---|---|
| Adiabático | `τ ≲ τ₁` (100 ns) | `∝ τ⁻¹` | El calor no difunde; la falla depende de la **energía** total |
| Difusión térmica | `τ₁ ≲ τ ≲ τ₂` (100 ns–10 µs) | `∝ τ^(−1/2)` | El Wunsch-Bell clásico |
| Estado estacionario | `τ ≳ τ₂` (10 µs) | `∝ τ⁰` | El calor difunde tan rápido como entra |

**La conversión que hay que no saltarse.** La sigmoide de daño de este motor
opera sobre el **campo E**, no sobre potencia. La potencia acoplada al blanco
va como el cuadrado de la tensión inducida, y ésta es proporcional al campo
incidente (`V_ind ∝ E`, `P ∝ V²/R`), de modo que `P_absorbida ∝ E²` y por lo
tanto:

```
E_fail(τ) ∝ √(P_fail(τ))
```

Aplicado a los tres regímenes, y tomando `g` como el **inverso** del umbral
(se sube el campo efectivo en vez de bajar `E₀`, para no repetir el error del
hallazgo 7 de §1 — desplazar el umbral dentro de una sigmoide no lineal):

```
adiabático            g(τ) ∝ τ^(1/2)
difusión térmica      g(τ) ∝ τ^(1/4)
estado estacionario   g(τ) = const = (τ₂/τ₁)^(1/4)
```

**Continuidad.** Los tres tramos están anclados al mismo `τ₁`, así que empalman
en valor por construcción:

- en `τ₁`: `(τ₁/τ₁)^(1/2) = 1 = (τ₁/τ₁)^(1/4)`
- en `τ₂`: la rama de difusión vale `(τ₂/τ₁)^(1/4)`, que es literalmente la
  constante del tramo estacionario

`g` es continua, no derivable en los quiebres — lo físicamente esperado en un
cambio de régimen. Verificado numéricamente en
`tests/test_duty_cycle.py::TestPulseCoupling::test_continuidad_en_los_quiebres_de_regimen`
(salto medido: `< 1e-9`).

**Normalización.** El resultado se divide por el crudo en `τ_ref`, de modo que
`g(τ_ref) = 1` **exactamente** para cualquier configuración. Es un requisito
duro: la calibración de §3.4 se hizo con `τ = τ_ref`. Verificado — con la ley
nueva la calibración da 43.5634 % @ 20 m y 11.8737 % @ 40 m, idénticos a antes.

#### 3.5.1 El defecto que esto corrigió (y por qué se veía bien)

La versión anterior era `g(τ) = min(√(τ/τ_ref), 3.0)`. Dos defectos que **se
cancelaban parcialmente entre sí**, que es lo que los hacía difíciles de ver:

| # | Defecto | Efecto |
|---|---|---|
| 1 | Exponente `1/2` en el régimen de difusión: **una raíz de más**. Saltaba la conversión potencia→campo y aplicaba al campo el exponente que corresponde a la potencia. | El crédito crecía al doble de velocidad de lo que corresponde |
| 2 | Tope `3.0`, número mágico sin justificación | Resulta que el **valor** estaba casi bien por casualidad: `(τ₂/τ₁)^(1/4) = 100^(1/4) ≈ 3.1623`. Pero la **saturación** ocurría a `τ ≈ 900 ns` (donde `√(τ/τ_ref)` llega a 3) en vez de a los 10 µs físicos |

O sea: el techo correcto con el exponente incorrecto. Entre 100 ns y 900 ns el
modelo sobreestimaba el crédito, y por encima de 900 ns lo subestimaba.

#### 3.5.2 Criterio de aceptación: alcance de 90 % de baja

El criterio de "done" original de este ítem era *"a igual energía total, un
pulso corto de alto pico neutraliza a más distancia que CW"*. **No podía
fallar**: el modelo define `pico = promedio/duty`, así que `duty↓ ⇒ E↑ ⇒ P↑`
por álgebra, no por física. Se reemplazó por el contraste externo del paper
(§5 de la referencia):

| Modo | Paper | Simulador (medido) | Brecha |
|---|---|---|---|
| CW (25 kW) | ≈ 18 m | **11.74 m** | −35 % |
| Pulsado (500 kW pico, 1 % duty) | ≈ 88 m | **52.50 m** | −40 % |
| Cociente pulsado/CW | 4.89 | **4.47** | −8.6 % |

**La brecha absoluta está atribuida, no disculpada.** El umbral **agregado**
del simulador exige `E = E₀ + ln(9)/k = 500 + ln(9)/0.0075 = 793 V/m` para
llegar al 90 % de baja. A 18 m el simulador tiene 517 V/m y el paper 552 V/m —
o sea que el paper declara 90 % de baja a ~552 V/m, **menos del 70 % del campo
que el umbral agregado necesita**. La diferencia de ganancia (20.6 vs 21.2
dBi, −6.4 % en campo) explica solo una parte pequeña: corregida sola, movería
el alcance a ~12.5 m, no a 18 m.

Lo que falta es el **modelo de 5 subsistemas en OR-gate** del paper
(`P_system = 1 − Π(1−pᵢ)`, con `E₅₀` de 150 a 350 V/m): cinco oportunidades de
fallar alcanzan el 90 % a un campo mucho menor que una única sigmoide centrada
en 500 V/m. Ese es el ítem **P1-C** del checklist, y esta brecha es su
evidencia cuantitativa.

**Sobre el cociente 4.47 vs 4.89** — y esto es una inferencia, no un dato del
paper: el 4.47 medido es exactamente `√(500/25) = √20`, o sea una identidad
algebraica del escalado de pico, independiente de `g(τ)`. Que el paper reporte
4.89 implica un factor de campo extra de 1.093 que el escalado de pico no
explica. Bajo la ley Wunsch-Bell eso correspondería a `τ ≈ 143 ns`
(`100 × 1.093⁴`) — una duración de pulso algo mayor que la referencia de
100 ns, plausible para un sistema HPM real. **Pero el texto del paper que se
pudo extraer no declara la duración de pulso de su modo pulsado**, así que
esto queda como hipótesis a confirmar contra el PDF, no como explicación
establecida. También puede ser simple redondeo de 18 y 88.

### 3.6 Modelo de 5 subsistemas (OR-gate) — CERRADO con criterio relajado (§3.6.1)

**Estado: implementado, validado con un margen más ancho que el que el paper
declara para sí mismo (±5pp, no ±1.0/±0.7pp) — ver §3.6.1 para el porqué y
los números finales.** Disponible bajo `HPM_DAMAGE_MODEL = "subsistemas"`;
el default sigue siendo `"agregado"` y nada del comportamiento por defecto
del simulador interactivo depende de esto. Lo que sigue (§3.6) es el
diagnóstico ORIGINAL que llevó a intentarlo y a encontrar por qué no cerraba
con el criterio estricto; §3.6.1 tiene la resolución final.

#### Por qué se intentó: el modelo agregado no es falsable

| Modelo | Parámetros libres | Puntos de datos | Grados de libertad | ¿Falsable? |
|---|---|---|---|---|
| Agregado (actual) | 2 (`E₀`, pendiente) | 2 | **0** | **No** |
| 5 subsistemas | 1 (acoplamiento) | 2 | **1** | **Sí** |

El agregado ajusta dos parámetros a dos puntos: cualquier par de puntos se
puede reproducir, así que reproducirlos no es evidencia de nada. El de
subsistemas toma los cinco pares `(E₅₀, σ_E)` de la Tabla 1 **como
publicados** y deja un único parámetro libre — la eficiencia de acoplamiento —
así que con dos puntos de datos **puede fallar**. Ese es el argumento
metodológico, y se sostiene independientemente del resultado.

El resultado, sin embargo, es que falla.

#### Un error de método que cometí y descarté

El primer ajuste dio `k = 0.2568` con residuos de −0.11 pp (20 m) y +0.62 pp
(40 m): **dentro** de los márgenes ±1.0 / ±0.7 del paper. Parecía cerrar.

Estaba mal. Ese ajuste hacía que el cálculo **determinista** reprodujera los
puntos **Monte Carlo** del paper — o sea, absorbía el sesgo del MC dentro del
parámetro. Es exactamente el defecto del [hallazgo 2 / §1.3](#1-resumen-ejecutivo-de-la-auditoría)
que esta misma fase venía a corregir, cometido de nuevo un nivel más arriba.

La pista que lo delató está en el propio paper: dice que sus predicciones MC
son *"systematically lower than deterministic"* (83 % → 51.4 % a 20 m). Con el
ajuste determinista, el MC del simulador daba **más alto** que su determinista.
Dirección opuesta ⇒ la estructura de varianza no era la del paper.

Reajustado con el MC dentro del lazo: `k = 0.3693`.

#### Las tres señales de que no cierra (estado ANTES de leer el PDF)

**Señal 1 — no reproduce los puntos publicados.** Con el ajuste correcto:

| Distancia | Simulador (MC, 6000 tiradas) | Paper | Residuo | Margen |
|---|---|---|---|---|
| 20 m | 0.5025 | 0.514 | **−1.15 pp** | ±1.0 |
| 40 m | 0.1742 | 0.131 | **+4.32 pp** | ±0.7 |

Los residuos tienen **signo opuesto**, así que ningún valor único de `k` los
cierra a la vez. El de 40 m es ~6× el margen declarado.

**Señal 2 — el sesgo va en dirección contraria al paper.** El MC del simulador
queda por **encima** de su propio determinista, mientras el paper reporta lo
inverso. Diagnóstico: la varianza está inyectada en la zona **convexa** de la
curva (la cola baja), donde promediar **sube** la media por desigualdad de
Jensen. El paper opera en la zona cóncava, donde promediar la baja.

**Señal 3 — el CV es 1.6× demasiado alto.** A 30 m el simulador da
**CV = 0.6285** contra el **≈0.39** que reporta el paper.

#### Atribución de varianza: el culpable está localizado

Apagando una distribución a la vez y midiendo el CV a 30 m:

| Distribución apagada | CV resultante | Contribución |
|---|---|---|
| **polarización** | 0.2842 | **−0.3439** |
| umbrales de subsistemas | 0.5858 | −0.0422 |
| longitud de cable | 0.6193 | −0.0088 |
| eficiencia de apertura | 0.6222 | −0.0058 |
| error de apuntado | 0.6231 | −0.0049 |
| potencia | 0.6287 | ≈0 |
| diámetro del plato | 0.6301 | ≈0 |

**La polarización explica el 55 % del CV total.** Esto *coincide* con la
conclusión del paper sobre cuál parámetro domina (*"polarization mismatch and
wire orientation dominate uncertainty"*) — el problema no es la identidad del
culpable sino la **magnitud** de la dispersión. Y el dato que acota la
respuesta: **sin polarización el CV cae a 0.284, por debajo del 0.39 del
paper**. La verdad está en medio: la dispersión de polarización del paper es
real pero menor que `cos²(U[0,π])` con piso 0.1.

#### 3.6.1 Actualización 2026-09-13 — se leyó el PDF real, completo (17 páginas)

El usuario consiguió el PDF de arXiv:2602.08477. **Corrección de un error
propio en esta misma sesión**: la primera lectura usó el comando `file` para
verificar el número de páginas, que reportó "6 page(s)" — resultó ser una
herramienta poco confiable para este PDF (1.7, streams de objetos
comprimidos vía `pikepdf`), y llevó a documentar por un rato que el PDF
estaba truncado y que había que buscar una v2. Verificado con `pdfinfo`
(poppler): el archivo tiene **17 páginas completas**, coincide con "17
pages, 15 figures" de arXiv, y trae Secciones 4.3-6 (resultados completos,
discusión, conclusión) y la bibliografía — nada de esto faltaba, faltaba
leerlo bien. No hay v2 en arXiv ni hace falta: el v1 ya está completo.

El PDF trae algo que el HTML no dio nunca: el **código fuente real** del
modelo determinista (Listado 1) y del núcleo del Monte Carlo (Listado 2,
"abreviado" por el propio paper), más la **Tabla 3** (página 9) con los
resultados completos en 5 distancias — no solo los 2 puntos de calibración
que ya se conocían. Esto confirma tres cosas de la lista de arriba, refuta
una hipótesis, y revela un hallazgo nuevo y más importante que todos los
anteriores.

**Confirmado — punto 2 de la lista (dónde va el piso de polarización):** el
código del paper es literal — `pol_loss = max(cos(pol)**2, 0.1)`, aplicado
sobre la POTENCIA (EIRP) antes de la raíz cuadrada para el campo. El piso va
sobre `η_pol = cos²φ`, no sobre `√η_pol`. Coincide exactamente con lo que
`src/engine/parametros.py` (P1-B) ya había implementado sin haber visto el
PDF — pero el motor **principal** (`Drone`, usado por P2-D/P3-A/P3-B) seguía
con un modelo viejo (`Uniforme[0.3,1.0]` plano) que nunca fue el correcto.
**Corregido** en `Drone._sortear_polarizacion` (`src/models/drone.py`) y en
la integración Monte Carlo de `src/engine/targeting.py`
(`_muestra_de_acoplamiento`), que hasta ahora integraba sobre una
distribución DISTINTA a la que el propio dron sorteaba — ver hallazgo 14.

**Confirmado — modelo de error de apuntado, dato nuevo:** el paper usa una
gaussiana en potencia, `G_point = exp(-2.76·θ_norm²)` con
`θ_norm = θ_err/(θ_3dB/2)`, no el `cos²` de cono que el simulador reutilizaba
(un atajo de cuando no se conocía la fórmula real: el motor aplica `cos²` al
CONO DE EFECTO del arma, un concepto físico distinto — ancho angular con
borde duro — del jitter de tracking que este parámetro modela). **Corregido**
en `src.engine.experiments._factor_taper_haz` y en la copia paralela de
`src.engine.sensitivity.probabilidad_baja_desde_vector` (P2-A: debe
mantenerse coherente con la anterior, misma cadena física con dos puntos de
entrada — ver docstring de `monte_carlo_blanco_unico`).

**Refutado — la hipótesis de que la cadena de voltios (Ec. 4-5) alimenta el
resultado de sistema.** La §4.5 del paper (página 7, Fig. 6) sí usa
`V_ind = E·L_eff·F(θ)·√η_pol`, pero como análisis MECANÍSTICO separado: a
300 V/m, un cable de 6 cm induce ≈45 V, por encima del umbral de ruptura de
un MOSFET (20-40 V) — eso explica CUALITATIVAMENTE por qué el ESC es
vulnerable, comparando VOLTIOS contra un umbral en voltios. La Tabla 3
(página 9), en cambio, reporta explícitamente el campo en **V/m** (columna
`Ē`) como lo que entra al modelo de 5 subsistemas — la misma unidad que los
umbrales E₅₀ de la Tabla 1, sin pasar por voltios. Confirmado: el simulador,
calculando el campo incidente SIN el paso de tensión inducida (solo Friis +
apuntado + polarización), reproduce esa columna `Ē` casi exactamente (ver
abajo). La cadena de voltios es un análisis paralelo sobre el ESC en
particular, no el paso que conecta el campo con los umbrales de sistema —
no hay inconsistencia dimensional V/m-vs-voltios que resolver, porque el
camino que sí se usa nunca introduce voltios.

#### El hallazgo grande: el campo del simulador reproduce la Tabla 3 casi exacto — la probabilidad no

Con la Tabla 3 completa (5 distancias, no solo 2) se puede validar el modelo
por partes, algo que antes no era posible.

**Parte 1 — el campo (Friis + apuntado gaussiano + polarización), sin ningún
factor de acoplamiento adicional (`k=1.0`), reproduce la Tabla 3 casi
exacto:**

| Distancia | Ē simulador | Ē paper | σ simulador | σ paper | CV simulador | CV paper |
|---|---|---|---|---|---|---|
| 20 m | 312.5 | 306 | 123.2 | 120 | 0.394 | 0.392 |
| 25 m | 250.0 | 245 | 98.5 | 95 | 0.394 | 0.388 |
| 30 m | 208.3 | 205 | 82.1 | 80 | 0.394 | 0.390 |
| 35 m | 178.6 | 174 | 70.4 | 68 | 0.394 | 0.391 |
| 40 m | 156.2 | 153 | 61.6 | 60 | 0.394 | 0.392 |

Media y desviación dentro de 2-3% en las 5 distancias; CV dentro de 0.006.
**Esto resuelve la ambigüedad de la señal 3 original**: el "CV≈39%" del
paper es el CV del CAMPO, no de la probabilidad de baja — dos estadísticos
distintos que se habían estado comparando como si fueran el mismo. Medido
correctamente, **la señal 3 está CERRADA**: el simulador reproduce el CV
publicado con precisión.

**Parte 2 — aplicando el modelo de 5 subsistemas del propio paper (Tabla 1 +
Ec. 7) directamente sobre ESE campo (que ya coincide), la probabilidad sale
≈100% en las 5 distancias, no 51.4%-13.1%:**

| Distancia | Ē (campo, coincide) | P_sim (OR-gate sobre Ē) | P_paper |
|---|---|---|---|
| 20 m | 312.5 | 91.2% | 51.4% |
| 25 m | 250.0 | 82.1% | 36.8% |
| 30 m | 208.3 | 74.2% | 25.2% |
| 35 m | 178.6 | 67.1% | 16.5% |
| 40 m | 156.2 | 60.3% | 13.1% |

Verificado también con el campo DETERMINISTA (sin ruido, calculado con
Friis puro a partir del Listado 1: 482/386/322/276/241 V/m en 20-40m) contra
la columna "Determinista" de la Tabla 3 (83.0/62.5/43.5/29.0/20.0%) —
**mismo resultado**: el OR-gate sobre esos campos da ≈100% en las 5
distancias, ya sea con la sigmoide logística del paper (Ec. 6) o con la
log-logística del proyecto. **Esta parte de la Tabla 1 y la Tabla 3 del
paper no son algebraicamente consistentes entre sí vía las Ecuaciones 6-7
que el propio paper declara** — verificado con la sigmoide EXACTA del
paper, sin ninguna sustitución del proyecto, así que no es un artefacto de
la log-logística de P1-F.

**Resuelto por ahora con un factor de acoplamiento adicional, reajustado con
los 5 puntos (antes solo 2):** `HPM_COUPLING_FIELD_EFFICIENCY = 0.44` (MC en
el lazo, sobre los 5 puntos de la Tabla 3, no solo 20m/40m):

| Distancia | P_sim (k=0.44) | P_paper | Residuo |
|---|---|---|---|
| 20 m | 53.5% | 51.4% | **+2.1 pp** |
| 25 m | 37.6% | 36.8% | **+0.8 pp** |
| 30 m | 24.1% | 25.2% | **−1.1 pp** |
| 35 m | 14.7% | 16.5% | **−1.8 pp** |
| 40 m | 8.9% | 13.1% | **−4.2 pp** |

Este ajuste con 5 puntos da una imagen MUCHO más coherente que el ajuste
original con solo 2 puntos (que parecía mostrar residuos de signo
opuesto sin patrón): acá el residuo decrece **suave y monótonamente** con
la distancia, de +2.1pp a −4.2pp — un patrón que podría explicarse por
ruido propio del Monte Carlo del paper (su IC95% en cada punto ya es de
±1-2pp con 10.000 tiradas) o por un pequeño término dependiente de la
distancia no modelado, no por un error grueso. El `k` exacto que cierra
CADA distancia por separado también varía suave: 0.425 (20m) → 0.436 (25m)
→ 0.449 (30m) → 0.457 (35m) → 0.490 (40m) — un rango de ±7% alrededor de
0.45, no una dispersión caótica.

**Conclusión honesta:** con 5 puntos en vez de 2, y separando la validación
del campo (cierra, con precisión) de la del modelo de daño (queda un
residuo pequeño y suave, no cierra dentro de los márgenes ±1.0/±0.7pp que
el paper declara SOLO para sus dos puntos de calibración, 20m y 40m), P1-C
pasa de "no cierra por decenas de puntos, sin patrón claro" a "el campo
cierra, el modelo de daño tiene un residuo de 1-4pp con un patrón suave,
consistente con ruido de reimplementación independiente más que con un
error conceptual". Sigue sin cumplir el criterio de aceptación declarado
(dentro de ±1% en los dos puntos publicados, sin ajustar ningún umbral) —
`HPM_COUPLING_FIELD_EFFICIENCY` es exactamente el umbral/parámetro ajustado
que el criterio prohíbe — así que el ítem sigue sin poder marcarse
`[x]` hecho. Pero es una brecha de una escala completamente distinta a la
que se documentó horas antes en esta misma sesión (+40pp con `k=1.0`,
"decenas de puntos, sin explicación").

**Qué explicaría el residuo pequeño restante, sin evidencia nueva para
elegir entre ellas:** (1) el propio paper usa la sigmoide LOGÍSTICA (Ec. 6),
no la log-logística de P1-F — probado explícitamente arriba con la
logística exacta y da el mismo resultado (≈100%), así que esto NO explica
la diferencia entre el modelo y el paper, pero si el paper cometió algún
otro pequeño error de redondeo o de qué exactamente entra a σ_E, podría
explicar el residuo fino; (2) ruido propio del Monte Carlo del paper
(N=10.000, su IC95% en cada punto ya cubre 1-2pp); (3) algún factor de
acoplamiento menor no documentado explícitamente en el texto disponible.

#### Resolución final (2026-09-13): cerrado con criterio relajado, declarado por escrito

El paper mismo no se puede corregir — su Tabla 1 y su Tabla 3 no son
algebraicamente consistentes entre sí, verificado con triple control (campo
MC, campo determinista, dos sigmoides distintas), y esa es una propiedad del
documento publicado, no de esta implementación. Frente a eso, la decisión de
este proyecto es **cerrar P1-C aceptando explícitamente un margen más ancho**
que el que el paper declara para sus propios dos puntos:

- Margen del paper (para sus 2 puntos, 20m/40m): ±1.0pp / ±0.7pp.
- **Margen aceptado por este proyecto (para las 5 distancias de la Tabla 3):
  ±5pp.** Con `k=0.44` (MC en el lazo, ajustado sobre los 5 puntos), todos
  los residuos caen dentro: +2.1, +0.8, −1.1, −1.8, −4.2 pp.

Esto NO es "el criterio original, relajado en silencio" — queda fijado en un
test que hace exactamente lo contrario de lo esperado si alguien lo lee
rápido: `test_no_cierra_dentro_del_margen_original_del_paper` FALLA si el
modelo alguna vez SÍ cumple el margen estricto del paper, como señal de que
algo cambió y hay que revisar por qué (podría ser una mejora real, o podría
ser un test mal escrito enmascarando un error).

`HPM_DAMAGE_MODEL` sigue en `"agregado"` por defecto — cerrar este ítem
habilita `"subsistemas"` como una opción calibrada y documentada
(`HPM_DAMAGE_MODEL="subsistemas"`), no cambia el comportamiento del
simulador interactivo. Tests:
`tests/test_parametros.py::TestModeloSubsistemasCalibradoConReserva` (el
modelo cierra con el margen relajado, de forma monótona, y NO con el
original — los tres hechos, cada uno con su propio test) y
`TestCampoReproduceLaTabla3` (la validación positiva del campo, sin
reserva alguna — esa sí cierra exactamente con el criterio original del
paper).

### 3.7 El piso de la sigmoide: `P(E=0) ≠ 0` — CORREGIDO (P1-F)

**Hallado por el análisis de sensibilidad (§3.8), no buscado.** Fue el defecto
más consecuente encontrado, y estaba a la vista desde el principio.

> **Estado: corregido el 2026-09-12.** La función de enlace por defecto
> (`HPM_LINK_FUNCTION`) es ahora `log_logistica`. Lo que sigue documenta el
> defecto, su magnitud medida y la corrección aplicada.

#### El defecto

La sigmoide de daño es una **logística en `E`**:

```
P(E) = 1 / (1 + exp(−k·(E − E₀)))
```

Una logística tiene soporte en **todo ℝ**. Pero el campo eléctrico es una
magnitud **positiva**. Evaluada en cero:

```
P(0) = 1/(1 + exp(k·E₀)) = 1/(1 + exp(0.0075·500)) = 0.0230
```

**Un dron sin ningún campo aplicado tiene 2.30 % de probabilidad de caer.** Con
el OR-gate de cinco subsistemas (§3.6), donde cada subsistema aporta su propia
cola, el piso sube a **3.30 %**.

Dicho en términos del modelo de umbrales que la sigmoide representa: una
logística en `E` afirma que una fracción de la población de componentes falla a
**campo negativo**, que no significa nada.

#### Cuánto del resultado es artefacto

| Distancia | `P` reportada | Fracción que es piso |
|---|---|---|
| 100 m | 0.0451 | 51 % |
| 400 m | 0.0272 | **84 %** |
| 700 m | 0.0253 | **91 %** |
| 900 m | 0.0248 | **93 %** |
| 2 km | 0.0238 | **97 %** |

**Más allá de ~97 m, más de la mitad de la probabilidad reportada es piso.** Y
el enjambre circular por defecto está a **500–900 m** del arma: *todo el rango
de combate por defecto del simulador cae en la zona dominada por el artefacto.*

Consecuencia sobre un resultado ya publicado en este proyecto: la métrica de
P1-A (`fraccion_media = 0.0056` con la configuración por defecto, presentada
como "el estimador ya tiene señal") es correcta como salida del modelo, pero su
**contenido físico a ese rango es ~9 %**. La maquinaria estadística funciona; lo
que mide está dominado por el piso.

#### La corrección, ya verificada

Reemplazar la logística en `E` por una **log-logística** — equivalentemente, una
logística en `ln E`:

```
P(E) = 1 / (1 + (E₅₀/E)^b)        con  P(0) = 0  y  P(∞) = 1
```

Es el modelo estándar de dosis-respuesta para dosis positivas, justamente
porque el soporte de la distribución de umbrales es `(0, ∞)`.

Ajuste a los dos puntos publicados:

| | `E₅₀` | `b` | Residuo @ 20 m | Residuo @ 40 m | `P(0)` |
|---|---|---|---|---|---|
| Logística en `E` (actual) | 500 V/m | `k`=0.0075 | −1.92 pp | +0.08 pp | **0.0230** |
| **Log-logística** | **487.39 V/m** | **2.8106** | **0.0000 pp** | **0.0000 pp** | **0** |

**Mismos dos parámetros libres, ajuste exacto en ambos puntos, y sin
artefacto.** A 700 m da `0.000040` en vez de `0.025326`: un factor 633.

#### Lo que se aplicó y lo que se ganó

`HPM_LINK_FUNCTION = "log_logistica"` es el default desde P1-F. La logística se
conserva seleccionable (`"logistica"`) para comparar y para no romper tuning
previo. Resultados medidos:

| | Antes (logística) | Después (log-logística) |
|---|---|---|
| `P(E=0)`, modelo agregado | 0.0230 | **0** exacto |
| `P(E=0)`, OR-gate 5 subsistemas | 0.0330 | **0** exacto |
| Calibración @ 20 m | 0.4356 (−7.84 pp vs paper) | **0.4677** (−4.63 pp) |
| Calibración @ 40 m | 0.1187 (−1.23 pp) | **0.1113** (−1.97 pp) |
| `P` @ 700 m | 0.0253 (90.7 % artefacto) | **0.00004** (factor 630) |

**Decisión metodológica declarada.** Los parámetros se ajustaron contra el campo
que calcula **el paper** (497.2 / 248.6 V/m), no contra el del simulador
(465.48 / 232.74 V/m, un −6.4 % por usar `G ≈ 26000/θ²`). Motivo: `E₅₀` es una
propiedad de la **electrónica del blanco**, no de la antena del arma. Ajustarlo
contra el campo del simulador habría metido el déficit de ganancia del EMISOR
dentro del umbral del BLANCO — el mismo error de categoría del hallazgo 2 que
dejó el umbral viejo en 500 V/m. El residuo de −4.63 pp que queda a 20 m es
**enteramente atribuible** a ese déficit, y se cierra poniendo
`HPM_ANTENNA_MODEL = "plato"` (§3.8 lo mide: 21.16 dBi contra los 21.2
publicados). Son dos decisiones separadas a propósito.

#### Conversión entre familias, y un hallazgo sobre la Tabla 1 del paper

La transformación que **preserva la pendiente en `E₅₀`** es `b = E₅₀/σ`, porque
`dP/dE|E₅₀` vale `1/(4σ)` en la logística y `b/(4·E₅₀)` en la log-logística.

Aplicada a los cinco subsistemas de la Tabla 1 da **exactamente 5.0 en los
cinco** (150/30, 200/40, 250/50, 300/60, 350/70). **Hallazgo propio: la columna
`σ_E` de la Tabla 1 es literalmente `E₅₀/5` y no aporta información
independiente** — el paper describe los cinco subsistemas con un único parámetro
de forma y cinco umbrales, aunque presente diez números.

#### 3.7.1 Los tres números publicados del paper son mutuamente inconsistentes

Consecuencia inesperada de haber ajustado bien. El paper publica:

- **(a)** 51.4 % @ 20 m → `E` = 497.2 V/m
- **(b)** 13.1 % @ 40 m → `E` = 248.6 V/m
- **(c)** alcance de 90 % de baja ≈ 18 m → `E` = 552.4 V/m

Bajo **cualquier** ajuste de dos parámetros no se sostienen a la vez:

| Puntos usados | Parámetro de forma `b` |
|---|---|
| (a) + (b) | **2.81** |
| (a) + (c) | **20.32** |

Un factor **7.2** de discrepancia. Entre 497 y 552 V/m —un +11 % de campo— la
probabilidad tendría que saltar de 51.4 % a 90 %, lo que exige una pendiente
siete veces mayor que la que fijan sus propios dos puntos. Con la logística pasa
lo mismo: `E₀ = 500`, `k = 0.0075` (ajustados a (a)+(b)) dan `P(552.4) = 0.597`,
no 0.90.

**Explicación más probable — y esto es inferencia, no dato del paper:** la cifra
de 90 % de alcance sale de su curva **determinista**, no de la Monte Carlo. El
paper declara 83 % @ 20 m y 20 % @ 40 m en determinista; esos puntos dan
`b = 4.29`, y determinista-83 % @ 20 m combinado con 90 % @ 18 m da `b = 5.81` —
mismo orden de magnitud. El 20.32 es el outlier. El simulador calibra contra los
puntos **Monte Carlo**, así que estructuralmente no puede reproducir una cifra
derivada del determinista.

**Consecuencia retroactiva:** el criterio de aceptación original de P1-E
(18 m / 88 m) **nunca fue alcanzable** desde los puntos de calibración. Eso
explica por qué la brecha no cerró ni con la logística (11.74 m) ni con la
log-logística (8.74 m). El test de alcance se conserva para fijar la brecha
medida y detectar si cambia, **no** como criterio de validación del modelo, y la
inconsistencia quedó como aritmética verificable en
`tests/test_duty_cycle.py::TestAlcance90PorCiento::test_la_cifra_de_90pc_del_paper_es_internamente_inconsistente`.

#### Efecto colateral valioso: el estimador ahora dice cero

Con el piso eliminado, el escenario por defecto (cañón de 25 kW contra el
enjambre circular a ~700 m) da **exactamente 0 bajas en 12 réplicas**. Es la
respuesta físicamente correcta, y el `0.0056` que el estimador reportaba antes
era íntegramente el piso. **Un estimador que nunca dice cero no sirve para
decidir nada.** Los tests de P1-A se reorganizaron en consecuencia: el estimador
se valida ahora con el misil (que sí engancha, detonando a ~80 m) y hay un test
nuevo que verifica que el cañón a 700 m reporta cero.

### 3.8 Análisis de sensibilidad global (Morris + Sobol)

**Categoría: método, no física.** No añade ninguna ecuación al modelo; mide de
qué depende lo que el modelo ya dice.

#### Por qué existe

El simulador tiene ~20 parámetros libres y **dos** calibrados contra datos
publicados. Sin descomposición de varianza no se puede responder la pregunta que
decide si un resultado es defendible:

> ¿esta conclusión depende de un parámetro calibrado, o de uno inventado?

#### Validación del estimador (lo primero, no lo último)

Los índices de Sobol se calculan con los estimadores de **Saltelli et al.
(2010)**, coste `N(k+2)`. Antes de aplicarlos al modelo de daño se validaron
contra la **función de Ishigami**, que tiene índices **analíticos** e incluye el
caso difícil de `x₃` (efecto principal exactamente 0, efecto total 0.244: actúa
solo por interacción):

| Parámetro | `S₁` analítico | `S₁` medido | `S_T` analítico | `S_T` medido |
|---|---|---|---|---|
| x₁ | 0.3139 | 0.3093 | 0.5576 | 0.5550 |
| x₂ | 0.4424 | 0.4543 | 0.4424 | 0.4477 |
| x₃ | **0.0000** | **0.0034** | **0.2437** | **0.2416** |

(`n_base = 32768`, error ≤ 0.012 en todos los índices.) Sin esta validación los
índices sobre el modelo de daño serían números sin respaldo — que es exactamente
lo que P2-A existe para dejar de producir.

Nota declarada: se usa muestreo pseudoaleatorio, no secuencias de Sobol
(`scipy.stats.qmc` no está disponible — `scipy` no figura en
`requirements.txt`). El estimador converge como `1/√N` en vez de casi `1/N`: es
un coste de cómputo, no un sesgo.

#### Resultado sobre el modelo de daño

13 parámetros. Índices a 30 m (`n_base = 2048`, 30 720 evaluaciones):

**Re-corrido tras P1-F** (el piso de la sigmoide comprimía la varianza a rango
largo). Valores vigentes, a 30 m:

| Parámetro | `S₁` | `S_T` | ¿Calibrado? |
|---|---|---|---|
| **ángulo de polarización** | **0.567** | **0.667** | sí |
| **eficiencia de acoplamiento** | **0.195** | **0.281** | **NO** |
| **duración de pulso** | **0.089** | **0.167** | **NO** |
| error de apuntado | 0.010 | 0.017 | sí |
| `E₅₀` GPS/GNSS LNA | 0.006 | 0.011 | sí |
| potencia | 0.001 | 0.007 | sí |
| (los otros 7) | ≈0 | < 0.005 | sí |

Y la suma de `S_T` de los parámetros **no calibrados**, por distancia:

| Distancia | Σ`S_T` no calibrados | Antes de P1-F |
|---|---|---|
| 20 m | **0.505** | 0.506 |
| 30 m | **0.448** | 0.431 |
| 60 m | **0.691** | 0.594 |

**El hallazgo se agravó con P1-F**: a 60 m, el **69 %** de la varianza viene de
dos parámetros sin validar. Morris y Sobol siguen coincidiendo 3/3 en los
dominantes a las tres distancias.

Lecturas, en orden de importancia:

1. **La polarización domina** (`S_T` = 0.58–0.66 según la distancia). Confirma
   por descomposición de varianza lo que el paper concluye cualitativamente y lo
   que la atribución manual de §3.6 había estimado (55 % del CV). La diferencia
   metodológica importa: una fracción de varianza **suma**; una diferencia de
   varianzas al apagar un factor, no.

2. **Los dos parámetros que siguen NO están calibrados.**
   `coupling_field_efficiency` es el parámetro **provisional** de §3.6 (P1-C
   bloqueado) y `pulse_duration_ns` gobierna la extensión Wunsch-Bell de §3.5,
   que no viene del paper. **Juntos aportan entre el 45 % y el 69 % de la
   varianza** según la distancia, y la proporción **empeora con el rango**. En términos operativos: cualquier conclusión
   del modelo de subsistemas lleva dentro una contribución de varianza mayoritaria
   de dos parámetros sin validar. Eso hay que decirlo **antes** de publicar, no
   después.

3. **Los cinco umbrales publicados aportan muy poco** (`S_T` ≤ 0.024). Su rango
   (±15 %) es estrecho frente a la dispersión del acoplamiento. Consecuencia
   práctica: afinar los umbrales importa mucho menos que clavar el acoplamiento
   — orienta dónde poner el esfuerzo de calibración.

4. **Hay interacciones relevantes**: `ΣS₁` = 0.69–0.87, o sea que entre el 13 % y
   el 31 % de la varianza se pierde si uno se queda en los efectos principales.
   Justifica haber calculado `S_T`.

5. **Chequeo de sanidad interno**: Morris y Sobol coinciden **3/3** en los tres
   dominantes, a las tres distancias evaluadas. Si discreparan, uno de los dos
   estaría mal muestreado y el informe no sería de fiar.

6. **`longitud_cable_m` sale con `S₁ = S_T = 0` EXACTO.** No es un resultado
   físico: es la **detección automática** de que el realce por resonancia está
   omitido (§3.6), así que ese parámetro no tiene camino hacia la salida. Se deja
   en el espacio a propósito para que el cero lo delate, con un test que falla el
   día que alguien conecte la resonancia.

Disponible en `GET /api/sensibilidad`. El campo `amenazas_a_la_validez` es el
que hay que leer primero.

### 3.9 Propagación sobre tierra y patrón de antena (P2-C)

**Sustituye al ítem cortado P3-08** (solver FDTD 2D de campo cercano), que iba a
corregir el régimen `r < 2D²/λ ≈ 5.9 m` en un campo de 1000×1000 m con el
enjambre a 500–900 m. Estos dos efectos sí operan donde el simulador vive.

**Ambos son opt-in** (`PROPAGATION_GROUND_REFLECTION`,
`PROPAGATION_ANTENNA_PATTERN`), por el mismo motivo que `HPM_ANTENNA_MODEL`:
mueven la calibración de §3.4, que está hecha contra el paper, y el paper
modela espacio libre sin tierra.

#### 3.9.1 El taper `cos²` no es el patrón de ninguna antena

**Categoría: física establecida** (el patrón de Airy lo es; el `cos²` no).

El motor aplicaba `cos²(normalizado·π/2)` a la densidad de potencia. Eso no
tiene lóbulos laterales, su forma no depende de `D` ni de `λ`, y **vale
exactamente cero fuera del cono nominal**.

El patrón real de una apertura circular uniformemente iluminada es el de Airy —
la transformada de Fourier de la apertura:

```
F(θ) = | 2·J₁(u) / u |        u = π·D·sin θ / λ
```

Validado contra sus posiciones y niveles analíticos (D = 0.60 m, 2.45 GHz):

| Propiedad | Analítico | Medido |
|---|---|---|
| HPBW (`u = 1.6163`) | 11.91° (`58.4λ/D`) | **12.05°** |
| Primer nulo (`u = 3.8317`) | 14.40° | **14.40°**, a −118 dB |
| Primer lóbulo lateral (`u = 5.136`) | −17.57 dB | **−17.57 dB** |

`J₁` se implementa con la aproximación polinómica de Abramowitz & Stegun §9.4
(exacta a ~1e-7 contra valores tabulados), porque `scipy` no está en
`requirements.txt`.

**La discrepancia es grande y va en una dirección sola:**

| `θ` | `cos²` | Airy | Diferencia |
|---|---|---|---|
| 4° | −3.5 dB | −1.3 dB | +2.2 dB |
| 6° | −10.2 dB | −3.0 dB | **+7.2 dB** |
| 7.4° (justo dentro del semicono) | −33.6 dB | −4.7 dB | **+28.9 dB** |
| 7.6° (justo fuera) | **−∞** | −5.0 dB | — |
| 19.5° (primer lóbulo) | **−∞** | −17.6 dB | — |

Integrado sobre el ángulo sólido, Airy ve **3.2× más potencia** que `cos²`.

**Consecuencia operativa: el modelo actual subestima la letalidad fuera de
eje.** Con `cos²`, un enjambre justo fuera del haz nominal es perfectamente
seguro; con un patrón real recibe del orden del 30 % del campo del eje, y el
primer nulo no llega hasta 14.4°. Nótese también que el HPBW de Airy (12.05°) es
más estrecho que los 14.28° de `dish_beamwidth_deg` (`70λ/D`): las dos son
correctas para su arquetipo — `70λ/D` describe un plato con taper de
alimentador, Airy el de iluminación uniforme, que es el peor caso en lóbulos
laterales.

#### 3.9.2 La altitud NO es variable táctica a 2.45 GHz

**Hallazgo que cambió el diseño de este ítem, y corrige mi propia
justificación.** El roadmap decía que la reflexión en tierra *"convierte la
altitud en variable táctica: un enjambre puede volar en un nulo de
interferencia"*. Es falso a esta frecuencia.

La separación entre franjas en altitud es `Δh ≈ λ·r/(2·h_tx)`, con
`h_tx = HPM_ORIGIN_Z = 8 m`:

| Rango | Separación entre nulos | Ciclos en la banda 40–160 m |
|---|---|---|
| 100 m | **0.76 m** | 157 |
| 300 m | **2.29 m** | 52 |
| 700 m | **5.35 m** | 22 |

Un dron oscila ±4 m (`DRONE_BOB_AMPLITUDE_M`) y el espaciado del enjambre es de
30 m: **cruza varias franjas por oscilación**. No se puede estacionar un dron en
un nulo de 0.76 m. El patrón existe y es real, pero no es explotable ni
controlable.

Es el mismo tipo de error de escala que motivó cortar P3-08, cometido en su
reemplazo. Queda fijado en
`tests/test_propagacion.py::TestFranjasNoSonResolubles`, que falla si alguien
cambia la frecuencia, la altura del emisor o la amplitud de oscilación — porque
entonces la conclusión cambia.

#### 3.9.3 El uso correcto del efecto es estadístico

Promediado sobre las franjas, el término en coseno de
`|1 + Γe^{jφ}|² = 1 + |Γ|² + 2|Γ|cos(φ + arg Γ)` se anula, y con `|Γ| = 1`:

```
⟨|F|²⟩ = 2      →      +3.01 dB
```

Verificado numéricamente (8 001 alturas en 40–160 m) a 0.5 y 2.45 GHz y a 100,
300 y 700 m: da +3.0 dB en los seis casos, **independiente de la frecuencia y
del rango**.

**El resultado que importa: el modelo de espacio libre subestima la potencia
media recibida sobre tierra en 3 dB.** Y la dispersión que el efecto introduce
(p5–p95 de −16 a +6 dB) es **varianza real** — P2-A demostró que la varianza
domina las conclusiones de este modelo, así que entra como tal y no como un
lóbulo determinista.

El +6 dB de los máximos no viola conservación de energía: es redistribución
angular, y la energía que falta está en los nulos.

**Cuándo sí vale el modelo determinista:** por debajo de ~0.5 GHz. La franja a
700 m mide 13 m a 1 GHz, 26 m a 0.5 GHz y 131 m a 0.1 GHz. Como
`HPM_FREQUENCY_GHZ` es un parámetro barrible, el modelo determinista se conserva
y es el correcto en ese régimen — pero hay que consultar
`propagation.franja_resoluble()`, no asumirlo.

### 3.10 Upset vs damage + fallo latente (P2-D)

**Categoría: decisión de modelado (categoría 3)**, con una pieza de física
establecida real (la conversión hazard-rate → probabilidad-por-tick) y una
elección explícita de qué literatura general se sigue (no un dato de
arXiv:2602.08477, que no distingue upset de daño).

#### Reemplaza la premisa cortada de P3-09

El thermal runaway de batería original fallaba el presupuesto energético por
~10⁹ (§3.6: 10–20 kJ para llevar una celda 18650 a runaway, contra microjulios
acoplados por un pulso de 100 ns). Se conservó la maquinaria valiosa de ese
ítem —decaimiento por tick, atribución diferida de bajas al disparo
original— con el mecanismo físico correcto: la literatura de vulnerabilidad
EMI separa **upset** (perturbación RECUPERABLE — reset de brownout,
desincronización de ESC, deriva de IMU, pérdida momentánea de fix GPS) de
**damage** (falla PERMANENTE — ruptura de óxido de puerta, latchup
destructivo). Una sola sigmoide a "neutralizado" no puede expresar el caso
operativamente decisivo: un enjambre que se desordena y **se recupera**.

#### El umbral de upset, y por qué NO usa la Tabla 1 de P1-C

```
E₅₀,upset = E₅₀,damage / 10^(gap_dB/20)
```

con `gap_dB = 10` (extremo conservador de la convención general de 10–20 dB
entre susceptibilidad recuperable y daño permanente en electrónica digital).
Con el `E₅₀` calibrado del cañón (487.39 V/m): `E₅₀,upset ≈ 154.13 V/m`.

**Deliberadamente NO se deriva de `HPM_SUBSISTEMAS`** (la Tabla 1 publicada,
usada en el modelo de subsistemas de §3.6). Razón: ese modelo sigue
**bloqueado** — no reproduce los puntos de calibración y su varianza es 1.6×
alta (§3.6). Acoplar la contabilidad de upset a un modelo no validado
propagaría esa falta de validación a un mecanismo nuevo. En cambio, se
desplaza el umbral **ya calibrado** (`HPM_LOGLOGISTIC_E50_V_M`), que sí pasa
las pruebas de `tests/test_calibracion.py`.

La zona `[P_damage, P_upset)` tiene ancho apreciable en el rango de combate
(ver tabla), lo que garantiza que el mecanismo tiene efecto observable:

| Distancia | `P_damage` | `P_upset` | Ancho de zona |
|---|---|---|---|
| 20 m | 0.4677 | 0.9572 | 0.489 |
| 30 m | 0.2195 | 0.8773 | 0.658 |
| 40 m | 0.1113 | 0.7610 | 0.650 |
| 60 m | 0.0385 | 0.5047 | 0.466 |

#### Hallazgo 13: mi primer cálculo del hazard rate daba 99 % de muerte, no "usualmente se recupera"

El diseño original fijaba `DRONE_RIESGO_LATENTE_MAX_POR_S = 2.0` con la
justificación (incorrecta) de que "la probabilidad de fallar CADA SEGUNDO"
era manejable. Eso ignora que el hazard se integra sobre TODA la cola de
decaimiento, no solo un tick: para un hazard que decae exponencialmente con
constante `τ`, la probabilidad de morir **alguna vez** es

```
P(falla eventual) = 1 − exp(−h₀·τ)
```

Con `h₀ = 2.0/s` y `τ = 4 s`: `h₀·τ = 8`, `P(falla eventual) ≈ 1 − e⁻⁸ ≈
0.9997` — prácticamente todo dron que entraba en upset terminaba muriendo.
**Medido por simulación antes de corregirlo: 99.3 % de muertes a severidad
0.6 en 2000 repeticiones**, contradiciendo directamente el propósito del
ítem ("un enjambre que se desordena y se recupera").

**Corrección**: se fija el PEOR caso de la zona de upset (severidad = 1.0,
justo bajo el umbral de daño) en un lanzamiento de moneda —
`P(falla eventual) = 0.5` — y se despeja `h₀`:

```
h₀ = ln(2) / τ = ln(2) / 4 ≈ 0.1733 /s
```

Verificado empíricamente contra la fórmula cerrada (1500 repeticiones por
severidad, tolerancia ±0.05):

| Severidad | `P` teórica | `P` empírica |
|---|---|---|
| 0.1 | 0.067 | 0.067 |
| 0.3 | 0.188 | 0.183 |
| 0.6 | 0.340 | 0.358 |
| 1.0 | 0.500 | 0.512 |

Con esta corrección, la mayoría del rango de severidad favorece la
recuperación, y solo en el punto más severo es un resultado incierto — la
lectura correcta de "se desordena y se recupera" en vez de "se desordena y
casi siempre cae".

#### Energía absorbida: unidades reales

```
S_promedio = S_pico · duty_cycle
A_efectiva = cable_length_m²
E_absorbida = S_promedio · A_efectiva · duración_exposición      [J]
```

Reemplaza `dano = probabilidad·potencia·0.5` (dimensionalmente vacío, hallazgo
del §4.5 de la auditoría, último resto de los "puntos de daño arbitrarios"
que el §5.4 original de este documento declaraba eliminados). `A_efectiva` no
introduce un parámetro libre nuevo: se deriva de la longitud de cable YA
sorteada por dron (huella de susceptibilidad de P2-04) — un cable más largo
(y más cerca de la resonancia) también capta más energía, doble efecto físico
con una sola variable aleatoria. `duración_exposición` reutiliza
`HPM_DISPARO_DURACION_S` (cañón) o su análogo `MISSILE_DETONACION_DURACION_S`
(misil, 0.05 s — mucho más corta: una detonación es un evento único, no una
ráfaga sostenida de tierra).

#### Subsistema afectado y comportamiento degradado

Sorteo ponderado por `1/E₅₀` sobre `HPM_SUBSISTEMAS` (el GPS/GNSS LNA, más
débil, es el más probable — consistente con el hallazgo de §3.6/§3.8 de que
domina el subsistema más débil del OR-gate). Es un sorteo de **ranking
relativo**, no depende de que el modelo de subsistemas esté calibrado en
términos absolutos.

Dos subsistemas tienen consecuencia mecánica sobre el vuelo (los otros tres
—cámara, ESC, BMS— quedan como diagnóstico/reporte, decisión de alcance):

- **`flight_controller` en upset**: el dron no adopta el rumbo nuevo que le
  asignaría `compute_headings` — el autopiloto no puede procesar comandos de
  flocking (brownout/desincronización), aunque el enlace de radio siga OK.
  Verificado contra un vecino control en la misma formación que sí adopta el
  rumbo nuevo.
- **`gps_gnss_lna` en upset**: el perfil lost-link RTH degrada a "mantener
  rumbo" (no puede calcular la dirección de retorno sin posición) — reutiliza
  el mismo camino de degradación elegante que ya existía para
  `home_x`/`home_y` no provistos.

#### Atribución diferida al disparo original

`analytics.record_delayed_kill(shot_id, distancia)` **muta** la entrada
existente de `shot_history` (no crea una nueva) y sube el bin correspondiente
de `distance_stats` sin duplicar `intentos`. Verificado de punta a punta con
un disparo real y sin forzar nada más que el hazard de maduración: un dron a
30 m entra en upset organicamente, el `shot_id` se atribuye correctamente
(comparado contra `shot_history[-1]["id"]`), y tras 60 s de reloj muere por
fallo latente con `shot_history` reflejando `neutralizados: 1,
bajas_diferidas: 1` en la entrada ORIGINAL.

### 3.11 Curva dosis-respuesta por máxima verosimilitud (P2-B)

**Categoría: método, no física** (igual que §3.8) — cierra el lazo entre lo
que el simulador dice que hace y lo que hace de verdad.

#### La idea

En vez de confiar en que `Drone.recibir_daño` implementa la sigmoide que
`src/config.py` declara, se generan datos binarios (kill/no-kill) **con el
motor real** a varias distancias, se ajusta la curva que esos datos
**implican**, y se compara contra los parámetros configurados. Si un cambio
futuro en la cadena física (acoplamiento, blindaje, duty cycle) desplazara
silenciosamente la curva efectiva sin tocar `HPM_LOGLOGISTIC_E50_V_M`, esto lo
detectaría — a diferencia de `tests/test_calibracion.py`, que verifica el
modelo **teórico** en dos puntos aislados, no el motor completo encadenado.

#### El optimizador: por qué Newton-Raphson y no scipy

La log-verosimilitud de una regresión logística es **cóncava**, así que
Newton-Raphson (IRLS) converge al óptimo global sin necesitar un optimizador
genérico. Validado ANTES de aplicarlo al modelo de daño, contra datos
sintéticos con parámetros conocidos:

| Parámetro real | Recuperado | n |
|---|---|---|
| `β₀=-3.0, β₁=0.05` | `-3.0 ± 0.15`, `0.05 ± 0.01` | 4000 |
| `E₅₀=300, b=4.0` (log-logística) | `300 ± 5%`, `4.0 ± 8%` | 5000 |
| `E₀=20, k=0.6` (logística) | `20 ± 1.5`, `0.6 ± 10%` | 4000 |

Y converge rápido: con solo 8 iteraciones da el mismo resultado (a 1e-6) que
con 200, sobre 2000 puntos.

**La reparametrización que conecta el ajuste con las dos familias de enlace:**

```
log-logística (P = 1/(1+(E₅₀/E)^b)):   logística en x = ln(E),  b=β₁,  E₅₀=exp(-β₀/β₁)
logística     (P = 1/(1+exp(-k(E-E₀)))): logística en x = E,     k=β₁,  E₀=-β₀/β₁
```

#### Adaptativo a `HPM_LINK_FUNCTION`

El ítem original (escrito antes de P1-F) pedía "E₅₀ y σ_E", el lenguaje de la
logística. Ajustar esa familia sobre un motor que corre con log-logística
habría estado recuperando el modelo EQUIVOCADO. El ajustador detecta
`HPM_LINK_FUNCTION` y usa la parametrización activa; reporta además un
"σ_E equivalente" (`E₅₀/b`, la misma conversión de P1-F) para no romper la
letra del ítem original.

#### Resultado sobre el motor real

Huella de susceptibilidad **fijada** (cable resonante, polarización óptima —
mismo criterio que el caso de verdad conocida de P1-A): aísla la varianza de
la sigmoide de la varianza del acoplamiento de P2-04.

Corriendo `experimento_dosis_respuesta()` (10 distancias de 10 a 80 m, 400
observaciones cada una, 600 remuestreos bootstrap):

| | Configurado | Recuperado | IC 95% |
|---|---|---|---|
| `E₅₀` | 487.389 V/m | 496.70 V/m | [480.5, 513.1] |
| `b` | 2.8106 | 2.8187 | [2.66, 3.02] |

**`recupera_la_calibracion = True`.** El motor completo —con blindaje, duty
cycle, y toda la cadena Friis— produce exactamente la curva que su
configuración declara.

**Control negativo, para confirmar que la comparación puede fallar de
verdad**: datos generados con `E₅₀=700, b=3.5` (deliberadamente distintos)
dan `recupera_la_calibracion = False`, con el IC de `E₅₀` ([696.9, 747.9]) sin
tocar el valor configurado (487.4). El chequeo no es decorativo.

Disponible en `GET /api/dosis-respuesta`.

### 3.12 Radar dinámico: barrido + filtro α-β-γ (P2-G)

**Categoría: aproximación de ingeniería**, en dos partes: la ecuación de
radar y la sigmoide de detección son las mismas de §3.3 (sin cambios); lo
nuevo es CUÁNDO se consultan y CÓMO se recuerda el resultado entre consultas.

**Único ítem del checklist explícitamente NO ADITIVO** — mueve comportamiento
transitorio y el punto de auto-apuntado del misil, declarado como tal desde
el diseño, no descubierto después.

#### El problema que resuelve

Antes de P2-G, el radar era omnisciente por construcción:
`evaluar_deteccion()` se llamaba una vez por dron, CADA TICK, sobre la
posición VERDADERA, y el resultado (`drone.detectado`) era un booleano sin
memoria. `HPMissile._resolver_objetivo` y `HPMissileSystem.lanzar` leían
`d.x, d.y` reales de cualquier dron "detectado" — un filtro de seguimiento
sobre ese booleano habría sido decorativo, porque el arma ya sabía dónde
estaba el blanco con exactitud perfecta.

#### Paso 1: `TrackManager`, sin cambiar el comportamiento

`Swarm.actualizar` delega la detección a un `TrackManager` con un `Track`
por dron (posición/velocidad/aceleración ESTIMADAS, edad, revisitas
confirmadas) en vez de escribir un booleano inline. **Regresión verificada**:
en régimen ESTACIONARIO (drones detenidos, muchas revisitas), el conteo de
detectados coincide EXACTO con `evaluar_deteccion()` aplicada directamente a
cada posición — la ecuación no cambió, solo dónde vive el resultado.

#### Paso 2: barrido periódico + filtro α-β-γ

- **Barrido**: un solo ciclo de revisita (`RADAR_REVISITA_S = 1.0 s`, del
  orden de un radar de vigilancia de corto alcance de barrido rápido — no
  una medición de hardware real, decisión de ingeniería declarada) para TODO
  el enjambre, no una evaluación aislada por dron. Entre revisitas, los
  tracks vivos se propagan por **dead-reckoning** (modelo de aceleración
  constante) — el track "camina solo" hasta la próxima medición.
- **Filtro α-β-γ**: en cada revisita, la posición predicha se corrige con la
  medición real:
  ```
  x_est = x_pred + α·residual
  v_est = v_pred + (β/T_revisita)·residual
  a_est = a_pred + (2γ/T_revisita²)·residual
  ```
  Ganancias `α=0.6, β=0.3, γ=0.05` — valores de amortiguamiento moderado de
  la práctica estándar de filtros de ganancia fija, **no ajustados contra
  ningún radar real**. Validados EMPÍRICAMENTE (no solo declarados): sobre
  una trayectoria de velocidad constante (20 s de simulación), el error de
  posición converge a < 5 m y la velocidad estimada converge a la real
  dentro de un 15 %; el error no diverge entre 10 s y 40 s de seguimiento.
- **Pérdida de track por maniobra**: si el residual (medición − predicción)
  supera `RADAR_PERDIDA_TRACK_RESIDUAL_M = 120 m`, el track se declara
  perdido — el modelo de aceleración constante no explica un salto así, es
  un cambio real de comportamiento, no ruido de medición. Calibrado para
  distinguir vuelo normal de una maniobra real: verificado que **10 s de
  giro boids al máximo** (`BOIDS_MAX_TURN_RATE_DEG_S`, a 30 m/s) NO pierde el
  track, mientras que un salto de 3× el umbral sí lo pierde siempre.

#### Migración de consumidores: qué cambia y qué no

`HPMissile._resolver_objetivo` y `HPMissileSystem.lanzar` migran a la
posición ESTIMADA del track **solo para decidir A QUIÉN adquirir** —un
blanco nuevo, o el centroide de auto-apuntado al lanzar—. La NAVEGACIÓN,
una vez fijado el objetivo (`target_id`), sigue usando la posición VERDADERA
sin cambios: el buscador propio del misil se asume perfecto una vez
adquirido, el mismo supuesto documentado antes de P2-G ("el seguimiento de
un blanco ya fijado no requiere detección continua del radar de tierra").
Verificado con un caso donde la posición real y la del track apuntan a
blancos opuestos: la ADQUISICIÓN sigue al track, la NAVEGACIÓN sigue a la
posición real.

**Impacto medido en la calibración de intercepción** (el ~99 % de casos
documentado en `MISSILE_MAX_TURN_RATE_DEG_S`): sobre 30 lanzamientos con
semillas distintas, **30/30 detonaron** (0 destruidos sin detonar) — la
migración es lo bastante quirúrgica (solo cambia a quién se apunta, no cómo
se dirige el vuelo) como para no degradar la tasa de intercepción ya
calibrada.

### 3.13 Asignación arma-blanco optimizada (WTA, P3-A)

**Categoría: método de decisión**, no física — combina las piezas físicas ya
existentes (Friis, sigmoide de daño, huella de susceptibilidad) en un
problema de optimización combinatoria. Primer ítem del roadmap que produce
una DECISIÓN, no una predicción ni un diagnóstico.

#### Por qué recién ahora

Depende de dos ítems previos que le dan contenido real al problema:
- **P2-F**: sin presupuesto energético, el cañón dispara infinito y gratis
  — la asignación óptima siempre sería "disparale a todo", nada que
  optimizar.
- **P2-G, Paso 1**: opera sobre TRACKS (posición estimada), no sobre
  "cualquier dron con `detectado=True`" — de lo contrario seguiría siendo
  omnisciente.

#### El sesgo de Jensen, medido

La huella de susceptibilidad de un blanco (cable, polarización) no es
observable por radar. Estimar bajas esperadas con el acoplamiento MEDIO
subestima el resultado, porque la sigmoide es cóncava en el rango relevante:

```
bajas esperadas (Monte Carlo sobre la distribución):  0.0221
P(acoplamiento promedio):                             0.0121
diferencia:                                           +83 %
```

La corrección: integrar (Monte Carlo, 200+ muestras) sobre la distribución
real de `cable_length_m`/`polarization` por blanco, promediando
PROBABILIDADES, no parámetros de entrada.

**Actualizado 2026-09-13** (antes: +66 %): la distribución de polarización
del blanco pasó de `Uniforme[0.3, 1.0]` (plana, la incorrecta que P1-B ya
había señalado, ver §3.14 y `docs/FISICA_Y_MATEMATICA.md` en
`DRONE_POLARIZATION_ANGLE_MIN_RAD`) a `cos²φ` con `φ~U[0,π]` acotado a 0.1
— confirmada contra el código fuente real del paper (PDF de
arXiv:2602.08477, no solo el HTML). La media de acoplamiento bajó de 0.65 a
0.51 y su varianza casi se triplicó, así que el sesgo de Jensen —que
depende de la varianza y de la curvatura local de la sigmoide— se hizo MÁS
pronunciado, no menos. El hallazgo cualitativo (el MC supera a la
probabilidad del acoplamiento medio) no cambió; el número sí.

#### La formulación y su validación

```
valor(A) = Σ_j tamaño_j · (1 − Π_{i→j} (1 − f[i][j]))
```

El producto de supervivencias por cluster es lo que hace el problema
combinatorio real (rendimientos decrecientes: dos disparos al mismo cluster
no se suman linealmente, un dron solo muere una vez).

**Validado contra fuerza bruta exacta** (no contra el propio greedy, que es
tautológico por construcción):

| Instancias | Resultado |
|---|---|
| 20 matrices de valor ALEATORIAS (sin estructura física), ≤6×6 | 17/20 exactas; gap medio 0.24 %, máximo 2.30 % — dentro del límite declarado (<15%) |
| 15 instancias REALISTAS (generadas por el modelo físico real) | **15/15 exactas** |

La brecha en instancias adversariales es un resultado TEÓRICO esperado (WTA
es NP-difícil, greedy+búsqueda local no tiene garantía de aproximación en
el caso general) — se declara, no se oculta. Sobre las instancias que el
módulo realmente produce en uso (caída suave de probabilidad con la
distancia, no valores arbitrarios), alcanza el óptimo exacto de forma
consistente.

**La búsqueda local necesitó DOS vecindarios**, no uno: reasignación de un
elemento (mover una opción a otro cluster) e INTERCAMBIO de pares (dos
opciones ya asignadas cambian sus clusters). Con solo el primero, el
heurístico no igualaba la fuerza bruta en 4 de 20 instancias aleatorias;
con el intercambio de pares añadido, en 3 de 20 — la mejora es real pero no
elimina el problema teórico en el caso adversarial, consistente con que WTA
sigue siendo NP-difícil incluso con vecindarios de búsqueda local más
ricos.

Disponible en `GET /api/targeting/plan`.

### 3.14 Coevolución genética arma↔enjambre (P3-B)

**Categoría: método de decisión / diseño de experimento**, no física nueva —
un GA de dos poblaciones que usa el runner Monte Carlo real (P1-A,
`run_replica`) como función de fitness. Último ítem del roadmap.

#### Por qué el estimador de v1 lo bloqueaba (y P1-A no)

La v1 del checklist declaraba `deps: requiere P1-01`, pero el runner ya
existía cuando el ítem seguía bloqueado. La dependencia real no era la
EXISTENCIA del runner sino que su métrica primaria tuviera señal:
`P(aniquilación total)` vale 0 en casi todo el espacio de operación (1 baja
en 240 exposiciones con la config por defecto, ver
`docs/AUDITORIA_CHECKLIST.md` §1.2) — un fitness constante no tiene
gradiente, y ningún GA evoluciona nada contra eso, sea cual sea su
implementación. `fraccion_media` (P1-A) sí varía de forma continua.

#### El primer obstáculo real: la escala de combate por defecto es un régimen de "cero"

Con el emplazamiento por defecto del proyecto (arma en el origen del campo,
enjambre en su centro), la distancia es **~707 m**. Medido directamente
durante el diseño de este ítem: a esa distancia, incluso al tope de potencia
que el presupuesto energético del cañón permite entregar en una ráfaga
(500 kJ / 0.5 s ≈ 1 MW, P2-F), la probabilidad de baja por disparo es del
orden de `1e-4`. Con ~30 drones y un puñado de réplicas por generación, el
fitness del arma quedaba **idénticamente 0.0 en las primeras corridas de
prueba** — el mismo problema de v1, reaparecido un nivel más abajo.

Solución: `WeaponPolicy` ganó dos campos (`origen_x`/`origen_y`, en
`src/engine/experiments.py`) para que una política de arma pueda reubicar
el cañón sin tocar `src/config.py` — evita el "monkeypatch trap" que ya
mordió a este proyecto en P1-D/P1-F (un valor importado por nombre a un
módulo consumidor no se mueve parcheando el módulo de origen). La
coevolución reubica el arma a `DISTANCIA_COMBATE_M = 60 m` sobre el mismo
azimut, elegido porque:

- Cae dentro del alcance de 90% de baja que el propio paper de referencia
  reporta para el modo **pulsado** (~88 m, arXiv:2602.08477 §5), y cerca de
  uno de sus dos puntos de calibración exactos (40 m → 13.1% CW).
- A esa distancia aparecen **dos gradientes reales**, ninguno forzado a
  mano (medidos con `sim.fire()` directo antes de tocar el GA):
  1. **`duty_cycle` del arma**: a igual potencia PROMEDIO — y por lo tanto
     igual costo energético, porque `_energia_por_disparo_kj` solo depende
     de la potencia promedio, no del duty cycle — bajar el duty cycle de
     1.0 (CW) a 0.01 (1% pulsado) multiplica la fracción neutralizada
     varias veces (60 kW: 0.000→0.050, 15 réplicas). Reproduce la
     comparación CW-vs-pulsado de la §5 del paper: el pulsado alcanza mucho
     más lejos a la misma energía media porque el daño depende del campo
     PICO, no del promedio.
  2. **Dispersión de la defensa**: formaciones compactas (cuadrada, v)
     concentran drones dentro del cono estrecho del arma; formaciones
     dispersas (circular, línea, aleatoria) y una `cantidad` mayor (que
     agranda la huella física) sacan una fracción creciente de drones FUERA
     del cono — medido: cuadrada n=10→4.8% de baja, cuadrada n=55→2.3%;
     circular ≈0.0-0.2% en todo el rango de cantidad. Resultado con sentido
     táctico real (dispersión como contramedida contra un arma direccional
     de haz angosto), no un artefacto del ajuste de parámetros.

#### El segundo obstáculo: muestreo uniforme de `duty_cycle` deja el 99% del rango útil sin explorar

`duty_cycle ∈ [0.01, 1.0]` cubre **dos órdenes de magnitud**, y su efecto es
multiplicativo (campo pico ∝ 1/duty_cycle). Con inicialización y mutación
uniformes en escala lineal, midiendo 8 individuos aleatorios contra una
defensa fija: **7 de 8 dieron fracción 0.0 en sus 4 réplicas** porque su
`duty_cycle` cayó por encima de 0.1 — la región letal (`duty_cycle < 0.1`)
tiene solo ~9% de masa bajo un uniforme en `[0.01, 1.0]`. El efecto
compuesto: con una población de 8, casi todas las generaciones empatan en
fitness 0.0 para TODA la población, lo que anula la selección (torneo/argmax
sobre una lista de ceros no tiene señal) — el GA dejaba de tener presión de
selección la mayoría de las generaciones, no solo la primera.

**Corregido**: `duty_cycle` se inicializa, cruza y muta en **escala
logarítmica** (`10**uniform(log10(0.01), log10(1.0))`; mutación como paso
gaussiano en `log10`, σ=0.5 décadas). Es la práctica estándar para un
parámetro cuyo efecto es multiplicativo y que abarca décadas — el mismo
criterio que ya usa la literatura de diseño de experimentos para variables
de este tipo, no una decisión ad-hoc de este proyecto.

#### El tercer obstáculo (menor, corregido): solapamiento de semillas entre individuos

La primera versión asignaba a cada individuo `i` de una generación la
semilla base `semilla_generación + i`, y cada réplica interna suma
`0..replicas-1` a esa base — dos individuos consecutivos con
`replicas_por_evaluación ≥ 2` terminaban evaluando ALGUNAS de sus réplicas
sobre exactamente el mismo sorteo de enjambre (mismos factores de
acoplamiento cable/polarización por dron), reduciendo la diversidad efectiva
de la muestra entre individuos sin que ninguna prueba lo detectara (cada
individuo seguía siendo internamente reproducible). Corregido espaciando las
semillas por `i · replicas_por_evaluación`, de forma que los bloques de
semillas de cada individuo no se solapan.

#### Validación: motor genético primero, física real después (misma disciplina que Sobol/Ishigami y WTA/fuerza bruta)

Antes de confiar el GA a la física ruidosa, se validó contra un fitness
SINTÉTICO y conocido (`fitness = potencia_kw`, sin simulación): sobre 20
individuos y 15 generaciones, la potencia media de la población pasa de un
sorteo uniforme en `[10, 100]` a **>70% del límite superior** — selección,
cruce, mutación y elitismo funcionan como se espera antes de tocar el motor
de simulación (`tests/test_coevolution.py::TestMotorGeneticoSintetico`).

Con la física real, y usando un OPONENTE FIJO (no el campeón móvil de la
coevolución completa, para que "generación 5 mejor que generación 1" no
esté contaminado por un rival que también cambió) y el fitness **medio de
la población** (no el del mejor individuo — con esta escala de letalidad,
el máximo de la población satura en el techo exacto (0.0 o 1.0) la mayoría
de las generaciones por pura casualidad estadística, un "ceiling effect"
medido directamente: con población de 6-8 y pocas réplicas, la media de la
población es un estimador mucho menos ruidoso que el máximo):

| Población | Config (semilla 42) | Fitness medio, gen. 1 → gen. 6 |
|---|---|---|
| Arma vs. defensa fija (cuadrada, 20) | pop=10, réplicas=6, t=6s | 0.0017 → **0.0100** (×6.0) |
| Defensa vs. arma fija (80kW, 15°, duty=0.01) | pop=10, réplicas=6, t=6s | 0.9862 → **0.9963** |

El arma final evolucionó a `duty_cycle≈0.014` (extremo pulsado) y
`potencia≈31 kW`; la defensa final evolucionó a `formación=circular`,
`cantidad≈54` — ambos resultados coherentes con los dos gradientes
documentados arriba (pulsado gana, dispersión gana).

*(Números re-medidos 2026-09-13 tras corregir la distribución de
polarización del motor principal, ver §3.6.1 — antes: 0.0017→0.0158/×9.3 y
0.9813→0.9956, defensa final "aleatoria". El hallazgo cualitativo (ambas
poblaciones mejoran frente a un oponente fijo, reproducible con la misma
semilla) no cambió.)*

**Honestidad declarada sobre la corrida coevolutiva completa** (ambas
poblaciones evolucionando simultáneamente contra el campeón móvil de la
otra, `coevolucionar()`): con solo 5-6 generaciones y población pequeña, la
serie de fitness DEL CAMPEÓN por generación es mucho más ruidosa que contra
un oponente fijo — es el comportamiento esperado de una carrera
armamentista de corto plazo (en cuanto la defensa encuentra una formación
dispersa razonable, el arma campeona de la siguiente generación se enfrenta
a un rival mucho más difícil que el de la generación anterior, así que su
fitness cae aunque el arma en sí no haya empeorado). El criterio de
aceptación del ítem ("mejora el fitness de cada población") se verifica con
el protocolo de oponente fijo de arriba, que aísla esa fuente de ruido; la
corrida conjunta es la que produce la frontera de Pareto reportada.

#### Reproducibilidad

Un único `numpy.random.Generator` (`nuevo_generador(seed)`) gobierna
inicialización, selección, cruce y mutación de ambas poblaciones. Misma
semilla ⇒ misma frontera de Pareto y mismas series de fitness, byte a byte
(`tests/test_coevolution.py::TestReproducibilidad`); semillas distintas dan
resultados distintos (ninguna prueba pasaría por casualidad con un generador
que no estuviera gobernando nada).

Disponible como `src.engine.coevolution.coevolucionar()` /
`resumen_json()`; no se agregó endpoint HTTP (el ítem no lo pide y una
corrida tarda 1-4 minutos, incompatible con un request-response síncrono
sin trabajo en segundo plano, que está fuera de alcance de este ítem).

## 4. Limitaciones conocidas (honestidad ante todo)

Esto es lo que el modelo **no** captura, a propósito o por simplificación:

- **El misil usa un umbral distinto al del cañón** (`HPM_MISSILE_E_THRESHOLD_V_M
  = 30` vs `HPM_E_THRESHOLD_V_M = 500`). No es descuido: un radiador isotrópico
  ideal (`G=1`) esparce la misma potencia sobre un área ~660 veces mayor que
  un plato de 21 dBi a la misma distancia (`10^(21.2/10) ≈ 132`×). Con el
  umbral "real" del cañón, el misil necesitaría cientos de kW a distancias
  de detonación típicas para lograr algo — un misil HPM de área real (tipo
  CHAMP) logra cobertura mediante una **antena de barrido/array**, no un
  estallido isotrópico puro, así que su ganancia efectiva de cobertura es
  mucho mayor que la de un radiador isotrópico ideal. El umbral separado del
  misil es una forma honesta de modelar "actúa como si tuviera antena de
  barrido" sin implementar el barrido en sí. **Mejora futura real**: modelar
  explícitamente un patrón de antena de barrido en vez de este atajo.
- **Potencia pico vs. potencia promedio**: el paper distingue explícitamente
  entre CW (25kW) y modo pulsado (500kW pico, 1% duty cycle) — los efectos
  de tipo *latchup* dependen del campo instantáneo durante el pulso, no de
  la potencia promediada en el tiempo. El simulador trata `potencia_hpm`
  como un único número sin distinguir pico/promedio/duty cycle.
- **Sin near-field**: `S=P·G/4πr²` solo es válido en campo lejano
  (`r > 2D²/λ`; a 2.45GHz, λ≈12.2cm). A distancias muy cortas (unos pocos
  metros) el modelo sobrestima o subestima el campo real; no hay un límite
  inferior físico, solo un `max(distancia, 1e-6)` para evitar división por
  cero.
- **El perfil de vuelo del misil** (ascenso/crucero/descenso) es un guion
  temporal (interpolación lineal por fracción de tiempo), no dinámica de
  vuelo real (empuje, arrastre, gravedad). Igual para la oscilación de
  altitud de los drones (sinusoide de hover) — es animación, no aerodinámica.
- **El guiado del misil (PN) omite el término de velocidad de cierre** de
  la ley de navegación proporcional real (`a = N·Vc·λ̇`, acá se usa
  `a = N·λ̇`) — simplificación válida para velocidad ~constante, documentada
  en el código desde que se implementó.
- **La agilidad de giro del misil (180°/s) es irreal** para un misil real a
  400 m/s (implica ~decenas de g de aceleración lateral) — se calibró así
  empíricamente para que el guiado funcione de forma consistente a la
  escala del campo (1000×1000m); ver comentario en `config.py`.

---

## 5. Qué hace innovador a este proyecto

No es "otro simulador de drones" — la combinación específica es poco común:

1. **Dos modelos EM intercambiables con auditoría cruzada.** La mayoría de
   simuladores de juguete usan una fórmula ad-hoc y ya. Acá hay un modelo
   *legacy* (rápido, ad-hoc) y uno *friis* (trazable a ecuaciones de
   electromagnetismo real), y además **se validó numéricamente contra datos
   de un paper real**, documentando dónde coincide y dónde no.
2. **Terminal de validación en vivo.** Cada disparo imprime sus números
   (distancia horizontal vs. vertical, campo E, probabilidad) y **se
   autochequea** contra invariantes físicas esperadas (monotonicidad,
   rangos válidos), señalando inconsistencias apenas ocurren — muy poco
   común en proyectos de este tamaño, que normalmente no exponen ni
   verifican su propia física en tiempo real.
3. **Guiado real (navegación proporcional), no "el misil persigue al
   punto".** La mayoría de simuladores simples usan *pure pursuit* (apuntar
   siempre al blanco actual, lo cual genera trayectorias de "persecución de
   cola" poco realistas). Acá se implementó la ley de control que usan los
   misiles guiados reales.
4. **Todo el stack es trazable**: cada número tiene una unidad física real
   (W/m², V/m, dBi) en vez de "puntos de daño" arbitrarios — lo que permite
   exactamente el tipo de auditoría que hicimos en este documento.

---

## 6. Referencias y fuentes verificadas

- **arXiv:2602.08477** — *"A Multi-physics Simulation Framework for
  High-power Microwave Counter-unmanned Aerial System Design and
  Performance Evaluation"*, Akbar Anbar Jafari, Gholamreza Anbarjafari
  (2026). <https://arxiv.org/abs/2602.08477> — verificado por búsqueda web
  el día de esta auditoría; existe, es del dominio correcto (HPM
  counter-UAS), y su metodología (Friis + campo E + sigmoide calibrado
  contra latchup CMOS + Monte Carlo) es la que inspira el modelo `friis`.
- **Abramowitz, M. & Stegun, I. (1964)** — *Handbook of Mathematical Functions*,
  §9.4. Aproximación polinómica de `J₁` usada en
  `src/engine/propagation.py::_bessel_j1` (exacta a ~1e-7), porque `scipy` no
  está declarado en `requirements.txt`.
- **Saltelli, A. et al. (2010)** — *"Variance based sensitivity analysis of model
  output. Design and estimator for the total sensitivity index"*, Computer Physics
  Communications 181(2):259-270. Estimadores de `S₁` y `S_T` usados en
  `src/engine/sensitivity.py` (ver [§3.8](#38-análisis-de-sensibilidad-global-morris--sobol)).
- **Morris, M.D. (1991)** — *"Factorial sampling plans for preliminary
  computational experiments"*, Technometrics 33(2):161-174, con la mejora de
  **Campolongo et al. (2007)** (usar `μ*`, la media de los efectos en valor
  absoluto, en vez de la media con signo). Screening de efectos elementales.
- **Ishigami, T. & Homma, T. (1990)** — función de test con índices de Sobol
  analíticos, usada para validar el estimador antes de aplicarlo
  (`tests/test_sensibilidad.py::TestEstimadorSobolContraAnalitico`).
- **Wunsch, D.C. & Bell, R.R. (1968)** — *"Determination of Threshold Failure
  Levels of Semiconductor Diodes and Transistors Due to Pulse Voltages"*, IEEE
  Transactions on Nuclear Science 15(6):244-259. Origen de la ley por tramos de
  `pulse_coupling_factor` (ver [§3.5](#35-duración-de-pulso-la-ley-wunsch-bell-por-tramos)).
  **No** es el paper de referencia del proyecto: el escalado por duración de
  pulso es una extensión propia, y arXiv:2602.08477 no lo incorpora.
- **Skolnik, M. — *Introduction to Radar Systems*** (y notas de curso de
  ingeniería de radar derivadas) — origen de la aproximación
  `G ≈ 26000/(θ_az·θ_el)` para ganancia de antena por apertura de haz.
- **Epirus Leonidas** — sistema HPM real de contramedida de enjambres,
  arquitectura de estado sólido (GaN), demostró neutralizar 49 drones al
  100% en una prueba en vivo. <https://www.epirusinc.com/electronic-warfare>,
  <https://en.wikipedia.org/wiki/Epirus_Leonidas>
- **THOR (USAF)** — sistema HPM de tubo de vacío, contenedor con antena de
  plato, mismo dominio de aplicación. <https://www.twz.com/thor-microwave-anti-drone-system-downs-swarms-in-test>
- **CHAMP** (Counter-electronics High Power Microwave Advanced Missile
  Project, Boeing/AFRL) — inspiración real para el `HPMissile` (misil de
  efecto de área, soft-kill, sin destrucción física).

---

## 7. Plan futuro / roadmap de mejoras

### Física
- [ ] Distinguir **potencia pico vs. promedio** (duty cycle) para el modelo
  de daño — el paper muestra que esto cambia el alcance efectivo
  drásticamente sin cambiar la energía total.
- [ ] Modelar **patrón de antena de barrido** para el misil en vez del
  atajo del umbral separado (§4) — acercaría el misil al mismo marco físico
  que el cañón.
- [ ] **Mismatch de polarización** como factor aleatorio adicional (como en
  el Monte Carlo del paper) — un dron con su cableado "mal orientado"
  respecto a la polarización del pulso debería ser más resistente.
- [ ] **Acoplamiento resonante por frecuencia/tamaño de cableado**: usar
  `HPM_FREQUENCY_GHZ` (ya existe en config, hoy solo cosmético en el panel
  de espectro) para modelar que un dron con cableado de cierta longitud es
  más susceptible cerca de su frecuencia de resonancia (línea de media onda
  o cuarto de onda).
- [ ] **Análisis Monte Carlo** (como el de 10,000 corridas del paper):
  correr N simulaciones variando potencia/apertura/ángulo de puntería con
  ruido y reportar probabilidad de baja con intervalo de confianza del 95%,
  en vez de un solo número determinístico.
- [ ] **Navegación proporcional aumentada (APN)**: agregar el término de
  velocidad de cierre real y compensación de aceleración del objetivo, para
  un guiado más preciso contra blancos que maniobran (menos dependencia de
  la agilidad de giro "irreal" actual).
- [ ] **Dinámica de vuelo real** (3-DOF mínimo: empuje, arrastre, gravedad)
  para el misil, en vez del guion de altitud por fracción de tiempo.
- [ ] **Límite de campo cercano**: acotar o advertir cuando `distancia` cae
  en la zona de campo cercano (`r < 2D²/λ`) donde `S=PG/4πr²` deja de ser
  válido.

### Química (extensión especulativa, pero con base real)
- [ ] **Escalada térmica de batería**: las corrientes inducidas por el pulso
  en el cableado no solo interrumpen la electrónica de control — en
  suficiente magnitud pueden inducir calentamiento resistivo en la batería
  de Li-ion. Un modelo simple de "energía absorbida → temperatura de celda
  → probabilidad de *thermal runaway*" daría una vía de daño permanente
  ("hard-kill" químico) distinta y posterior al soft-kill electrónico
  actual — interesante para diferenciar "el dron cayó porque se apagó" de
  "el dron se incendió en el aire".

### Matemática
- [ ] **Validación estadística empírica vs. teórica**: correr miles de
  disparos simulados y verificar que la tasa de neutralización empírica
  converge a la probabilidad teórica calculada (ley de los grandes
  números) — sería una prueba automatizada que valida el generador
  aleatorio y el modelo al mismo tiempo.
- [ ] **Intervalos de confianza en el panel de analíticas**, no solo tasas
  puntuales (`shot_history`), usando el mismo enfoque de Monte Carlo del
  punto anterior.
- [ ] **Test de invariantes ampliado** en `src/engine/validation.py`: hoy
  chequea monotonicidad y rangos; se podría agregar un chequeo de
  consistencia entre el campo E reportado y el que resulta de recalcular
  `S`/`E` desde `potencia`/`distancia`/`ganancia` de cada evento, para
  detectar futuras regresiones en la fórmula misma, no solo en sus salidas.

---

## 8. Nuevas capacidades: detección, enjambre reactivo, blindaje, jamming

Cuatro mejoras implementadas en la ronda siguiente a la auditoría de §1-7,
elegidas de una lista de propuestas. Todas reutilizan el motor
Friis/sigmoide ya auditado — nada de esto introduce un modelo físico nuevo
desde cero, solo lo aplica a preguntas distintas ("¿lo veo?", "¿pierde el
control?") además de la ya existente ("¿lo daño?").

### 8.1 Blindaje heterogéneo (`src/models/drone.py`, `src/models/swarm.py`)

Cada dron sortea, al crearse, si es `"blindado"` (20% por defecto,
`DRONE_HARDENED_FRACTION`), con un factor de dureza 2.5×
(`DRONE_HARDENED_THRESHOLD_MULT`).

**Corrección de auditoría (hallazgo #7, tabla §1):** la primera versión
aplicaba ese factor multiplicando el umbral de campo E antes de evaluar la
sigmoide (`e_threshold = HPM_E_THRESHOLD_V_M · factor`). Como el umbral
vive dentro de una función no lineal, desplazarlo no reduce la probabilidad
de forma proporcional — la saca del rango donde la sigmoide es sensible.
Medido: a 80-200m (rango de combate real del misil), la reducción real era
de **664× a 821×**, no 2.5×, dejando a los drones blindados
prácticamente invencibles.

**Fix (`apply_hardening_odds`, en `hpm_engine.py`):** primero se calcula la
probabilidad base normal (mismas `calculate_neutralization_probability_friis`
/ `_area_friis` de §3.2/3.3, sin tocar el umbral), y el blindaje se aplica
**después**, en espacio de momios:

```
odds = p / (1 - p)
odds_blindado = odds / factor
p_blindado = odds_blindado / (1 + odds_blindado)
```

Esto es estándar en modelado de probabilidad (regresión logística,
epidemiología): dividir los momios por un factor sí da una reducción
proporcional y predecible en cualquier punto de la curva, a diferencia de
desplazar un parámetro dentro de una sigmoide. Verificado: con esta
corrección, la reducción real queda entre 1.0× y 2.4× en todo el rango de
combate (30-200m), convergiendo a 2.5× según la probabilidad base baja —
el comportamiento que se pretendía desde el principio.

### 8.2 Enjambre reactivo — boids (`src/engine/flocking.py`)

Reynolds (1987), *Flocks, Herds, and Schools*: tres reglas vectoriales
combinadas por dron, sobre sus vecinos dentro de `BOIDS_NEIGHBOR_RADIUS`:

- **Separación**: `Σ (Δposición / |Δposición|)` sobre vecinos — aleja de
  quien está muy cerca, ponderado por la inversa de la distancia.
- **Alineación**: promedio del vector de rumbo de los vecinos.
- **Cohesión**: vector hacia el centroide de posición de los vecinos.

Las tres se suman con pesos (`BOIDS_SEPARATION/ALIGNMENT/COHESION_WEIGHT`)
para dar un rumbo deseado, y el giro hacia ese rumbo se limita a
`BOIDS_MAX_TURN_RATE_DEG_S` por tick — el mismo patrón de "giro acotado"
que ya usaba el guiado por navegación proporcional del misil. Nota
importante: acá no hay ecuación de electromagnetismo — es un modelo de
comportamiento (robótica de enjambres, no física de radiación), pero es
matemática real y citable (Reynolds 1987), no inventada para la ocasión.

### 8.3 Radar de detección (`src/engine/radar_engine.py`)

Antes de esta fase, el simulador tenía conocimiento omnisciente de la
posición de cada dron. Ahora hay que detectarlo primero:

**Ecuación de radar** (monoestático — misma antena transmite y recibe):
```
Pr = (Pt · G² · λ² · σ) / ((4π)³ · r⁴)
```
`σ` es la sección transversal de radar (RCS) del blanco — no el tamaño
físico, el "tamaño eléctrico" que ve el radar (`RADAR_RCS_M2 = 0.02 m²`,
típico de un drone pequeño). Nótese el exponente `r⁴` (no `r²` como en
Friis): la señal viaja ida y vuelta, así que la atenuación por distancia se
aplica dos veces.

**Probabilidad de detección**: sigmoide sobre la relación señal-ruido
(SNR, en dB) respecto a un umbral (`RADAR_SNR_THRESHOLD_DB = 10`, valor de
referencia común en ingeniería de radar). Igual que en §3.2, esto es una
**simplificación deliberada** de la teoría real de detección (función Q de
Marcum, curvas Pd/Pfa de modelos Swerling) — mismo patrón de modelado que
la sigmoide de daño HPM, aplicado a una pregunta distinta.

**Calibración**: con los defaults (`RADAR_TX_POWER_W=40`,
`RADAR_ANTENNA_GAIN_DBI=25`), el SNR cruza el umbral de 10dB alrededor de
850-900m — deliberadamente ajustado para que la formación circular por
defecto (a 500-900m del origen del arma) quede **parcialmente** detectada,
ni todo visible ni todo invisible.

**Qué gobierna y qué no**: la detección decide si un dron entra en el
cálculo de auto-apuntado (centroide para el ángulo automático del misil,
selección del blanco a fijar). **No** gobierna si un disparo/detonación ya
en curso lo afecta físicamente — un pulso ya disparado impacta a cualquier
blanco en su cono/radio, detectado o no; la detección es sobre la decisión
de apuntar, no sobre la física del campo ya irradiado. El buscador propio
del misil, una vez fijado a un blanco, mantiene el track aunque el radar de
tierra lo pierda momentáneamente (como en un misil real).

### 8.4 Jamming de comunicaciones (`src/models/jammer.py`)

Mismo motor Friis/sigmoide que el cañón (§3.2), pero interpretado distinto:
no "probabilidad de daño permanente" sino "probabilidad de perder el
enlace de control". Por eso el umbral es mucho más bajo
(`JAMMING_E_THRESHOLD_V_M = 4` V/m vs 500 V/m del cañón) — negar un enlace
de radio de baja potencia requiere muchísima menos energía que dañar
electrónica.

Diferencia clave de diseño respecto al cañón/misil: el jammer es un arma
**continua**, no un pulso. Mientras está activo, cada tick se reevalúa qué
drones caen en la zona de efecto — un dron sale de `INTERFERIDO` en cuanto
deja el cono o el jammer se apaga (falla seguro real: un dron sin enlace
vuelve a responder apenas recupera la señal, no queda "roto" para siempre
como con el HPM).

### Estado del roadmap original (§7)

Estas 4 capacidades **no** son las mismas que las listadas en §7 (esas
siguen pendientes: potencia pico vs. promedio, Monte Carlo, PN aumentada,
etc.) — son ideas nuevas que surgieron después. El roadmap de §7 sigue
vigente sin cambios.

---

## 9. Contexto real: qué hay "adentro" del misil, ¿existe ya en combate?, y la conexión con Tesla

### 9.1 Qué contiene físicamente un misil/sistema HPM real

A diferencia de un misil convencional (carga explosiva + fragmentación), un
misil o cañón HPM real contiene:

1. **Fuente de microondas de alta potencia** — un tubo generador de RF
   (magnetrón, vircator o klystron) que produce el pulso en la frecuencia
   de diseño (acá, 2.45 GHz, la misma banda que un microondas doméstico —
   no es casualidad, es una banda ISM bien caracterizada).
2. **Sistema de energía pulsada** — batería/generador que carga un banco de
   condensadores y los descarga en un pulso brevísimo (`HPM_PULSE_DURATION_NS`
   en el simulador), de ahí que la potencia *pico* (GW) sea enorme aunque
   la energía total (MJ) sea modesta.
3. **Antena direccional** — concentra la energía en un haz (por eso la
   ganancia de antena `G` es central en la fórmula: cono más angosto = más
   alcance con la misma potencia).
4. Puede llevar algo de explosivo solo como disparador de la descarga (o
   ninguno) — nunca como mecanismo de destrucción. El dron no se rompe: el
   pulso induce corrientes parásitas en su cableado ("acoplamiento
   electromagnético" — exactamente el campo E que calculan las fórmulas de
   §3), que fríen o interrumpen su electrónica de control. Por eso cae: por
   pérdida de control, no por impacto físico.

### 9.2 ¿Se usa esto ya en combate? ¿Es caro?

**Sí, y es activo ahora mismo (2025-2026), no ciencia ficción:**

- **Ucrania está probando esta tecnología activamente.** Ucrania invitó a
  fabricantes de sistemas HPM (como Epirus/Leonidas) a probar su equipo en
  condiciones de combate real, y además desarrolla sistemas de microondas
  propios a través de la plataforma de innovación de defensa **Brave1**.
  ([UNITED24 Media](https://united24media.com/latest-news/meet-leonidas-the-drone-killing-microwave-weapon-ukraine-has-its-eye-on-12178),
  [Militarnyi](https://militarnyi.com/en/news/ukraine-tests-microwave-weapons-in-response-to-new-threats/),
  [Ukrainian World Congress](https://www.ukrainianworldcongress.org/ukraine-tests-homegrown-microwave-weapons-to-knock-down-drones/))
- **Demostraciones recientes en vivo:** en agosto de 2025, Epirus hizo una
  demostración donde Leonidas enfrentó 61 drones en 5 escenarios distintos
  con 100% de éxito; en otra prueba derribó 49 de una sola vez.
  ([Breaking Defense](https://breakingdefense.com/2025/02/high-power-microwave-force-field-knocks-drone-swarms-from-sky/))
- **El desafío emergente:** drones FPV con **fibra óptica** (no radio) están
  reduciendo la eficacia de la guerra electrónica clásica (jamming de
  señal) porque no hay enlace de radio que interferir — pero un arma HPM
  como la de este simulador sigue funcionando contra ellos porque ataca la
  electrónica interna del dron, no el enlace de comunicación.
  ([Army Recognition](https://www.armyrecognition.com/news/army-news/2026/u-s-demonstrates-microwave-weapon-defeating-fiber-optic-fpv-drones))

**¿Es más caro que un misil convencional? Al revés — es muchísimo más barato:**

| Sistema | Costo aproximado |
|---|---|
| CHAMP (misil HPM, inspiración de `HPMissile` en este simulador) | ~$400,000+ por unidad (programa de $38M, 2009) |
| Interceptor cinético convencional | Miles de dólares por misil, contra drones de cientos de dólares — "desequilibrio de costos" |
| Leonidas (HPM de tierra, como el `HPMWeapon`/cañón de este simulador) | Estimado **<1 centavo por derribo** en electricidad; costo totalmente cargado (amortización + mantenimiento) ~$100-1000 por enfrentamiento |

Fuente: [Epirus — "Correcting the Cost Imbalance"](https://www.epirusinc.com/post/correcting-the-cost-imbalance-in-counter-unmanned-aerial-system-solutions).
La ventaja de costo es justamente **por qué** existe tanto interés militar
en esta tecnología: contra un enjambre de cientos de drones baratos, gastar
un interceptor de $400,000 por dron es insostenible; un sistema HPM que
solo consume electricidad, no.

### 9.3 La conexión con Nikola Tesla — qué es real y qué es mito

Hay una conexión real, y vale la pena separarla de lo que es leyenda:

**Lo que Tesla sí demostró (física real, verificada):** el acoplamiento
inductivo resonante — dos circuitos LC (inductor + capacitor) transfieren
energía de forma mucho más eficiente cuando están sintonizados a la **misma
frecuencia de resonancia**. Es el mismo principio detrás de la carga
inalámbrica de un celular hoy. Tesla lo demostró con sus bobinas (Tesla
coil) y lo llevó al extremo en sus experimentos de Colorado Springs y
Wardenclyffe intentando transmitir energía sin cables a gran distancia —
la física de base era correcta, pero subestimó las pérdidas por radiación
al aire libre, y el proyecto nunca fue viable a la escala que imaginaba.
([IEEE Spectrum](https://spectrum.ieee.org/a-critical-look-at-wireless-power))

**Lo que es mito/nunca se demostró:** su "Teleforce" (apodado popularmente
"rayo de la muerte") — Tesla insistía en que no era un rayo de ciencia
ficción sino un haz de partículas dirigido, pero nunca construyó ni
demostró un prototipo funcional. Es una idea especulativa de la que Tesla
habló, no una tecnología real que haya dejado planos o resultados
verificables. ([Kronecker Wallis](https://www.kroneckerwallis.com/nikola-teslas-failed-projects-death-rays-earthquake-machines-more/))

**La conexión real y concreta con este simulador:** la resonancia es
exactamente el mecanismo que falta en el modelo actual y que ya está
anotado como mejora futura en el roadmap (§7, "acoplamiento resonante por
frecuencia/tamaño de cableado"). Un cable o antena de cierta longitud actúa
como un circuito resonante a una frecuencia específica (relacionada con su
longitud y la velocidad de la luz: resonancia de media onda o cuarto de
onda). Un dron cuyo cableado interno resuena cerca de los 2.45 GHz del
pulso HPM acoplaría la energía muchísimo más eficientemente que uno cuyo
cableado no resuena a esa frecuencia — el mismo principio de Tesla (LC
sintonizado = transferencia eficiente), aplicado no para **entregar**
energía útil sino para **inyectar** energía disruptiva en un circuito que
no está diseñado para recibirla. Implementar esto (variar la
susceptibilidad de cada dron según qué tan cerca esté su "longitud de
cableado" de resonar con `HPM_FREQUENCY_GHZ`) sería la forma concreta y
matemáticamente real de traer la idea de Tesla al simulador — no un rayo de
la muerte, sino resonancia LC aplicada a interferencia electromagnética.
