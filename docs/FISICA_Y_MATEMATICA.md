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

---

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
- **Sin polarización**: el paper varía "polarization mismatch" como fuente
  de incertidumbre en su Monte Carlo. Acá no existe el concepto — se asume
  acoplamiento óptimo siempre.
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
