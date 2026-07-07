# Nuestro proyecto: arquitectura, fórmulas y qué puede (y no puede) derribar

Este es el tercer documento. Los otros dos cubren: **la física verificada
contra literatura real y las auditorías/correcciones**
(`FISICA_Y_MATEMATICA.md`) y **el panorama real de la industria/programas
militares** (`ESTADO_DEL_ARTE_HPM.md`). Este cubre algo distinto: **nuestro
propio proyecto**, de punta a punta — qué hace cada pieza, qué fórmula usa
cada una, qué puede derribar y por qué, qué no puede y por qué, y qué le
falta para ser una investigación completa (no solo un simulador que
funciona, sino uno cuyos resultados alguien podría citar).

---

## 1. Resumen ejecutivo del proyecto

Es un simulador de guerra electromagnética contra enjambres de drones, con
tres capas de armas (cañón HPM direccional, misil HPM de área, jammer de
comunicaciones), una capa de detección (radar), un enjambre con
comportamiento reactivo (boids) y heterogeneidad de blindaje entre drones.
Cada resultado (¿cae?, ¿se detecta?, ¿pierde el enlace?) sale de una
fórmula con unidades físicas reales (W/m², V/m, dBi) — no de "puntos de
daño" arbitrarios — auditada contra un paper real
([arXiv:2602.08477](https://arxiv.org/abs/2602.08477)) y corregida varias
veces cuando la auditoría encontró errores (ver el historial completo en
`FISICA_Y_MATEMATICA.md` §1).

---

## 2. Arquitectura completa (el recorrido de principio a fin)

```
1. Se crea el enjambre (Swarm.inicializar_formacion)
   └─ cada dron sortea: posición, velocidad, altitud, blindaje (20% "blindado")

2. Cada tick de simulación (60/seg, src/engine/simulation.py::_run_loop):
   a) Swarm.actualizar():
      ├─ Boids (src/engine/flocking.py): separación + alineación + cohesión
      │  + regla de "zona de patrulla" → nuevo rumbo de cada dron
      ├─ Drone.mover(): nueva posición x,y,z (oscilación de altitud)
      ├─ Radar (src/engine/radar_engine.py): ¿cada dron queda "detectado"?
      └─ Jammer, si está activo (src/models/jammer.py): ¿queda "interferido"?
   b) Si hay un misil en vuelo (src/models/hpm_missile.py):
      ├─ Guiado PN hacia el blanco fijado (si guiado=True)
      ├─ Actualiza altitud (perfil ascenso/crucero/descenso)
      └─ ¿debe_detonar? (fusible de proximidad — detona en el punto de
         máxima cercanía real, no en el primer cruce del umbral)

3. Disparo (cañón, src/models/hpm_weapon.py) o detonación (misil):
   ├─ Por cada dron: distancia 3D real + ángulo respecto al eje del arma
   ├─ Densidad de potencia (Friis) → campo E (V/m) → sigmoide → probabilidad
   ├─ Si el dron es "blindado": se reduce la probabilidad (espacio de momios)
   └─ Sorteo aleatorio: ¿cae o no?

4. Todo esto se transmite al frontend por WebSocket cada tick, y cada
   evento importante se imprime en la terminal con sus números reales
   (src/engine/validation.py) — incluye autochequeos de consistencia física.
```

---

## 3. Todas las fórmulas, en un solo lugar

(Derivación completa y fuentes en `FISICA_Y_MATEMATICA.md` §3; acá el
resumen operativo — qué fórmula corre en cada situación.)

| # | Fórmula | Dónde se usa | Archivo |
|---|---|---|---|
| 1 | `x(t+dt) = x(t) + v·cos(θ)·dt` (cinemática) | Movimiento de drones y misiles | `physics.py` |
| 2 | `S = P·G/(4πr²)` (densidad de potencia, Friis) | Base de todo cálculo de daño/detección | `hpm_engine.py` |
| 3 | `G ≈ 26000/apertura²` (ganancia de antena) | Cono del cañón | `hpm_engine.py` |
| 4 | `E = √(S·377)` (campo eléctrico) | Todo cálculo de daño | `hpm_engine.py` |
| 5 | `P = 1/(1+e^{-k(E-E₀)})` (sigmoide de daño) | Probabilidad de derribo (cañón y misil, umbrales distintos) | `hpm_engine.py` |
| 6 | `odds/factor` (blindaje) | Reduce la probabilidad de un dron "blindado" sin colapsarla | `hpm_engine.py::apply_hardening_odds` |
| 7 | `Pr = Pt·G²·λ²·σ/(4π)³r⁴` (ecuación de radar) | Si un dron es detectado | `radar_engine.py` |
| 8 | Reynolds 1987 (separación+alineación+cohesión+patrulla) | Rumbo del enjambre | `flocking.py` |
| 9 | Navegación proporcional: `giro = N·(Δángulo_LOS/dt)` | Guiado del misil | `hpm_missile.py` |
| 10 | Distancia 3D (`√(Δx²+Δy²+Δz²)`) | Toda evaluación de daño/detección (slant range) | `helpers.py::distance3d` |

---

## 4. ¿Qué puede derribar y qué no? — la matriz de capacidad real

Esto es lo que probablemente más curiosidad te generaba: acá están los
números reales, recién verificados contra el código actual.

### 4.1 Por distancia y tipo de dron (cañón, 25kW, cono de 15°)

| Distancia | Dron estándar | Dron blindado |
|---|---|---|
| 20m | 43.6% | 23.6% |
| 40m | 11.9% | 5.1% |
| 80m | 5.3% | 2.2% |

### 4.2 Por distancia y tipo de dron (misil, 50kW, tras el fix del fusible de proximidad — el misil real hoy detona típicamente a 10-30m)

| Distancia | Dron estándar | Dron blindado |
|---|---|---|
| 10m | 100% | 100% |
| 30m | 83.5% | 67.0% |
| 50m | 30.5% | 14.9% |
| 80m | 9.9% | 4.2% |

### 4.3 Alcance de detección del radar

| Distancia | ¿Detectado? | Probabilidad |
|---|---|---|
| ≤500m | Sí | >95% |
| 700m | Sí (al límite) | 80% |
| 900m | No | 47% |
| 1200m+ | No | <15% |

### 4.4 Resumen en palabras — qué SÍ puede derribar

- **Drones estándar a corta distancia** (≤30-50m del punto de detonación/
  disparo): probabilidad alta a muy alta.
- **Múltiples drones a la vez** con el misil, si están agrupados dentro del
  radio de efecto y a altitud similar (el descenso del misil apunta al
  promedio ponderado de altitud del grupo cercano, no a un único dron —
  ver `FISICA_Y_MATEMATICA.md` §8.2 y el hallazgo de esta sesión sobre el
  fusible de proximidad).
- **Drones no detectados por radar** — igual pueden ser dañados si están
  dentro del cono/radio de un disparo ya en curso (la detección gobierna a
  qué le apuntás automáticamente, no la física del pulso ya disparado).

### 4.5 Qué NO puede derribar bien (limitaciones reales, no ocultas)

- **Drones blindados a media/larga distancia**: la reducción de
  probabilidad (~2-2.5×) los hace notablemente más resistentes; a 80m+
  prácticamente no caen con potencias moderadas.
- **Drones fuera del alcance de radar** (>900-1000m): el sistema no los
  puede fijar automáticamente como blanco (aunque el operador podría
  apuntar manualmente a ciegas).
- **Drones en un anillo de altitud muy distinto al del grupo objetivo**: si
  la formación tiene mucha dispersión vertical, una sola detonación no
  cubre bien a los que están muy por encima/debajo del centro del grupo.
- **Drones con enlace de control por fibra óptica** (no modelado en este
  simulador): el `Jammer` no tendría ningún efecto sobre ellos en la
  realidad, porque no hay señal de radio que interferir — ver
  `ESTADO_DEL_ARTE_HPM.md` §2 (caso Ucrania) y §6 (limitación reconocida).
- **A distancias largas en general**: todas las fórmulas caen con `1/r²`
  a `1/r⁴` según el arma — es física real, no un límite arbitrario, pero
  significa que este tipo de arma es de **defensa de punto/corto alcance**,
  no de largo alcance (coincide con cómo se despliegan los sistemas reales,
  ver `ESTADO_DEL_ARTE_HPM.md` §3).

---

## 5. Obstáculos para que esto sea una investigación completa (no solo un simulador que "funciona")

Un simulador que corre y da números razonables no es lo mismo que un
trabajo de investigación citable. Esto es lo que falta, honestamente:

1. **Validación contra más de un punto de datos reales.** Hoy el modelo del
   cañón está ajustado contra exactamente 2 puntos publicados (20m y 40m,
   un solo paper). Para ser robusto, necesitaría contrastarse contra
   múltiples fuentes independientes, idealmente con barras de error.
2. **Validación estadística propia** (ya anotada en el roadmap,
   `FISICA_Y_MATEMATICA.md` §7): correr miles de simulaciones y confirmar
   que la tasa de derribo empírica converge a la probabilidad teórica
   (ley de los grandes números) — hoy no hay ninguna prueba automatizada
   de esto.
3. **Comparación contra una simulación electromagnética de campo completo**
   (FDTD o método de momentos, con software como CST Studio o COMSOL) para
   al menos un caso simple — nuestras fórmulas son aproximaciones de
   ingeniería (ver categorías en `FISICA_Y_MATEMATICA.md`), no una
   solución de las ecuaciones de Maxwell; sin ese contraste, no se puede
   afirmar que el modelo sea cuantitativamente preciso, solo que es
   *cualitativamente razonable* y consistente internamente.
4. **Datos reales de umbral de daño por tipo de componente** — usamos un
   umbral genérico (V/m) calibrado a la baja o al alza según el arma; un
   estudio real necesitaría datos de laboratorio sobre qué campo E daña
   específicamente un ESC, un receptor GPS, un controlador de vuelo, etc.
   (líneas de investigación reales, ver `ESTADO_DEL_ARTE_HPM.md` §5).
5. **Revisión por pares** — nada de esto pasó por revisión externa; es
   auditoría propia (que ya encontró y corrigió varios errores reales,
   pero sigue siendo un solo punto de vista).
6. **Caracterización de incertidumbre** — hoy cada corrida da un número
   determinístico (con aleatoriedad interna, pero sin reportar intervalos
   de confianza); el paper que usamos como referencia sí reporta ±1% en
   sus resultados — nuestro simulador debería poder hacer lo mismo
   (Monte Carlo, ítem 2).
7. **Definir el alcance del "producto final"**: ¿esto busca ser una
   herramienta educativa (ya lo es), un pre-estudio de factibilidad para
   una decisión de adquisición real, o la base de una publicación
   académica? Cada objetivo exige un nivel distinto de rigor adicional.

---

## 6. ¿Y en el Perú, cómo serviría esto?

Investigué el contexto real (no es una respuesta genérica) — esto es lo
que encontré:

### 6.1 El problema ya existe en el Perú

- **VRAEM**: la compra reciente de 12 aviones subsónicos de patrullaje
  responde a la necesidad de vigilar los 7,000 km de frontera y las zonas
  de selva/valle donde operan el narcotráfico, la minería ilegal y la tala
  ilegal — exactamente el tipo de escenario (baja altitud, vegetación
  densa, actores no estatales) donde los drones (de ambos lados) ya son
  relevantes.
  ([Infobae](https://www.infobae.com/peru/2025/09/24/por-que-peru-elige-aviones-subsonicos-la-razon-detras-de-la-anunciada-compra-de-12-aeronaves-de-ese-tipo/))
- **Minería ilegal (Pataz, La Libertad)**: SUNAT ya despliega drones con
  sensores térmicos/infrarrojos contra la minería ilegal, con planes de
  intervenir 250 plantas de procesamiento en 2025 y 300 en 2026. Es
  esperable (y ya documentado en otros países de la región) que grupos de
  minería ilegal adopten drones propios para vigilancia/evasión de
  operativos — lo que crearía una necesidad de contramedidas, no solo de
  drones propios.
  ([Gestión](https://gestion.pe/peru/pataz-despliegan-drones-de-alta-tecnologia-para-reforzar-control-contra-la-mineria-ilegal-noticia/))
- **Amenaza regional de drones criminales**: un informe del CSIS señala
  que **América Latina no está preparada para enfrentar drones
  criminales** — en Colombia hubo el primer ataque letal con drones en
  julio de 2024, y al menos 11 muertes por ataques con drones en los
  primeros cinco meses de 2025 en la región. El Perú no es una excepción
  aislada del fenómeno regional.
  ([CSIS](https://www.csis.org/analysis/illicit-innovation-latin-america-not-prepared-fight-criminal-drones))
- **Fuerzas Armadas del Perú**: ya iniciaron la adquisición de equipo
  anti-drone y el Ministerio de Defensa entrenó personal en drones CW-15 en
  China (2024) — hay interés institucional activo, aunque la información
  pública sobre programas específicos de contramedidas HPM es escasa (no
  encontré evidencia de que el Perú tenga o esté evaluando sistemas HPM
  como Leonidas — el interés documentado es más bien en drones propios y
  aeronaves de patrullaje).

### 6.2 Caminos concretos para este proyecto en el Perú

- **CONCYTEC — financiamiento activo**: en mayo de 2026, CONCYTEC lanzó un
  concurso ("Ciencia contra el crimen") para financiar proyectos de
  investigación sobre seguridad ciudadana — es un canal de financiamiento
  real y vigente donde un proyecto como este (adaptado a un caso de uso de
  seguridad ciudadana, no necesariamente militar) podría aplicar.
  ([Infobae](https://www.infobae.com/peru/2026/05/02/ciencia-contra-el-crimen-concytec-lanza-concurso-para-financiar-proyectos-de-investigacion-sobre-seguridad-ciudadana/))
- **RECIDE (Revista de Ciencia e Investigación en Defensa, CAEN)**: revista
  académica peruana que publica específicamente sobre adquisiciones
  militares, drones y el potencial de la industria de defensa nacional —
  un canal de publicación real y ya existente para este tipo de trabajo,
  con líneas de investigación explícitas en seguridad y defensa nacional.
  ([RECIDE](https://recide.caen.edu.pe/index.php/recide/article/view/224))
- **Universidades con antecedentes relevantes**: la UPC tiene un programa
  activo de innovación en drones (Ingeniería Mecatrónica); el Instituto
  Geofísico del Perú (IGP) ya construye drones y sensores propios y hace
  investigación en electromagnetismo (monitoreo de la ionósfera) — hay
  capacidad técnica local instalada con la que un proyecto así podría
  conectar (colaboración, revisión, coautoría).

### 6.3 Qué rol sería realista (y cuál no)

**Realista**: herramienta educativa/de entrenamiento para familiarizar a
personal técnico o militar con los conceptos de guerra electrónica;
insumo para un **estudio de pre-factibilidad** (antes de evaluar comprar
un sistema real, entender qué parámetros importan y por qué, con qué
enjambre de amenaza específico del Perú calibrar el análisis — p. ej.
drones FPV baratos sobre el VRAEM, no cazas rusos); base de una
publicación en un canal como RECIDE o una postulación al fondo CONCYTEC
mencionado arriba, siempre que se aborden los obstáculos de la §5
(especialmente validación estadística y comparación con literatura).

**No realista todavía**: que esto sea la base de un sistema desplegable
real — eso requeriría todo lo de la §5, más el hardware real (fuente de
microondas, antena, sistema de energía pulsada — ver
`FISICA_Y_MATEMATICA.md` §9.1), certificación y presupuesto de un programa
militar/estatal, no un simulador de escritorio.

---

## 7. ¿Qué tan confiable es esto? Simulación en PC vs. realidad

Pregunta directa: "si funciona en teoría (código), ¿debería suceder lo
mismo en la realidad?" Respuesta honesta: **no es 50/50 al azar — es un
gradiente**, y depende de a CUÁL número te referís. No todos los números
de este simulador tienen el mismo nivel de confianza. Ordenados de más a
menos confiable:

### Nivel 1 — Leyes físicas (confianza muy alta, esto SÍ va a pasar igual en la realidad)

La ley del inverso del cuadrado (`S ∝ 1/r²`), la relación campo-potencia
(`E=√(S·377)`), el inverso a la cuarta del radar (`Pr ∝ 1/r⁴`) — estas
salen directamente de las ecuaciones de Maxwell, están confirmadas hace más
de un siglo y no hay ninguna duda científica sobre ellas. Si en el
simulador algo se debilita al doble de distancia según estas fórmulas, en
la realidad se va a debilitar exactamente igual. Esto es física, no
opinión de diseño.

### Nivel 2 — Aproximaciones de ingeniería (confianza media: la FORMA es correcta, el número exacto no)

La fórmula de ganancia de antena (`G≈26000/apertura²`) es una aproximación
estándar de ingeniería de radar — es verdad que un cono más angosto da más
ganancia (eso va a pasar siempre), pero el número exacto (26000 en vez de,
digamos, 30000) depende de la eficiencia real de una antena específica, que
solo se conoce midiendo la antena real. Con hardware real, la TENDENCIA se
mantiene, el número puede correrse un poco.

### Nivel 3 — Parámetros calibrados/ajustados (confianza baja en el número exacto, media en el orden de magnitud)

El umbral de campo E al que un dron falla (30 V/m, 500 V/m según el arma) es
lo menos confiable numéricamente de todo el proyecto: lo ajustamos contra
**dos puntos de datos de un solo paper** (cañón) o lo elegimos para que la
jugabilidad funcionara razonablemente (misil, jammer). Un dron real
específico (marca, modelo, blindaje real) podría fallar a 15 V/m o a 150
V/m — un orden de magnitud de diferencia es totalmente posible. Lo que SÍ
es confiable: que más cerca / más potencia / menos blindaje siempre va a
significar más probabilidad de falla — esa dirección no cambia. El
número exacto donde "cae la mitad" sí necesitaría un dron real y una
cámara anecoica para medirlo con confianza.

### Nivel 4 — Decisiones de jugabilidad (cero confianza — no representan nada real, y no pretenden hacerlo)

La velocidad de giro del misil (180°/s), la oscilación de altitud de los
drones, los pesos de los boids — estos números se eligieron para que la
simulación se sintiera bien y funcionara de forma consistente, no para
representar un misil o un dron real. Están documentados como tales en
`FISICA_Y_MATEMATICA.md` §4 — no esperes que un misil real gire así.

### En resumen

No es "todo funciona igual" ni "nada se traduce" — es: **las leyes físicas
sí se van a repetir igual en la realidad; los números calibrados son una
estimación razonable de orden de magnitud que necesitaría un dron y un
laboratorio real para afinar; las decisiones de jugabilidad no pretenden
representar nada real.** Cualquier conclusión que saques de este simulador
sobre "a qué distancia funciona esto" hay que presentarla siempre con esa
salvedad — es una estimación basada en física real, no una medición de
hardware real.

---

## 8. ¿Esto es un proyecto de investigación valioso, o "uno más del montón"?

Pregunta justa, y merece una respuesta calibrada, no un elogio automático.

**Lo que NO es**: no descubrimos física nueva. Cada ecuación que usamos
(Friis, ecuación de radar, campo-potencia, navegación proporcional, boids)
es de hace décadas, de libros de texto o papers ya publicados. Si buscás
"innovación" en el sentido de "una ley física que nadie conocía antes",
no es eso.

**Lo que SÍ es, y es genuinamente menos común de lo que pensás**:

1. **El nivel de auditoría propia.** La mayoría de los proyectos de este
   tamaño (simuladores hechos por una persona o un equipo chico) no
   verifican sus propias fórmulas contra literatura real, y mucho menos
   documentan cuándo se equivocaron y cómo lo corrigieron. En esta sesión
   encontramos y corregimos **7 errores reales** (una cita mal atribuida,
   un umbral 15-20x mal calibrado, una fórmula de blindaje que colapsaba
   la probabilidad 800x en vez de 2.5x, un fusible de proximidad que
   detonaba en el peor momento posible, entre otros) — todo documentado
   con el número exacto del error y la corrección. Eso es más riguroso que
   la mayoría de los prototipos de este tipo, sean o no militares.
2. **La integración coherente de varias capas** (detección, daño
   direccional, daño de área, negación de enlace, comportamiento de
   enjambre reactivo, heterogeneidad de blindaje) que interactúan de forma
   físicamente consistente entre sí, no como sistemas aislados pegados con
   cinta adhesiva.
3. **Que cada resultado tenga trazabilidad completa**: podés preguntar "¿por
   qué este dron no cayó?" y la respuesta siempre es un número con
   unidades físicas (V/m, W/m², dBi), no "porque el juego lo decidió así".
   Eso permite exactamente el tipo de auditoría que hicimos en esta sesión
   — y es poco común incluso en simuladores comerciales.

**Conclusión honesta**: no es una investigación que vaya a cambiar el
campo del electromagnetismo. Es un ejercicio de **ingeniería aplicada
sólido y bien documentado** — el tipo de trabajo que sí tiene valor real
como herramienta educativa, como base de una publicación aplicada (ver §6,
RECIDE/CONCYTEC), o como ejercicio de portafolio/tesis que demuestra
capacidad real de modelar, auditar y corregir un sistema complejo. Vas por
buen camino en el sentido de que el proceso (modelar → auditar contra
literatura real → encontrar errores → corregir → documentar) es
exactamente el proceso correcto de investigación aplicada — lo que falta
para que sea "investigación completa" en el sentido académico está en la
§5, no es que el trabajo hecho hasta ahora esté mal encarado.
