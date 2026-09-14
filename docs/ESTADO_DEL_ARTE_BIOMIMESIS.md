# Estado del arte: biomimesis y dinámica de enjambres bajo amenaza

Mismo espíritu que `ESTADO_DEL_ARTE_HPM.md`, aplicado al lado opuesto del
problema: no la energía dirigida, sino **el enjambre que la recibe**. Motivado
por una pregunta directa: ¿el modelo de comportamiento del enjambre
(`src/engine/flocking.py`) tiene respaldo en biología/dinámica de sistemas
real, o es una intuición de ingeniería sin más? Todo lo que sigue fue
verificado ahora mismo (fetch de abstracts/resúmenes), no citado de memoria.

---

## 1. Lo que el proyecto ya tiene, con precisión

Antes de buscar qué agregar, hay que decir con exactitud qué existe, porque
una revisión rápida de `src/engine/flocking.py` corrigió una suposición
propia hecha antes de leer el código:

- **Boids clásico (Reynolds, 1987)**: separación, alineación, cohesión sobre
  vecinos dentro de radio — ya citado en el propio docstring del módulo.
- **Término "home" (zona de patrulla)**: cuarto término estándar en
  implementaciones de boids, empuja de vuelta al enjambre si se aleja del
  centro de formación — sin esto un enjambre real puede "migrar" indefinidamente
  y volverse imposible de probar.
- **Término "amenaza" (P2-E)**: ya existe evasión reactiva. Cuando un dron
  recibe daño (`Drone.registrar_impacto`), guarda la posición del impacto y una
  intensidad que decae exponencialmente (`actualizar_amenaza`), y esa memoria
  empuja al dron lejos del punto — misma forma funcional que la separación,
  aplicada a un punto en memoria en vez de a un vecino. Es condicional (pesa
  cero sin impactos previos) y transitorio (vuelve a cero solo).
- **Punto importante, verificado ahora**: `registrar_impacto` se llama sobre
  el dron que efectivamente recibió el disparo — **la memoria de amenaza NO
  se propaga a los vecinos**. Cada dron solo sabe de su propio impacto.

Esto cambia lo que vale la pena buscar: no hace falta "agregar evasión" —ya
existe—, sino evaluar si el modelo de evasión actual (reactivo, individual,
sin propagación) es consistente con lo que la literatura real documenta
sobre cómo se comportan enjambres/bandadas bajo ataque.

---

## 2. Literatura verificada

### 2.1 Ondas de agitación: la alarma se propaga MÁS RÁPIDO que el enjambre

Cuando un halcón peregrino ataca una bandada de estorninos, no todos
reaccionan a la vez ni cada uno reacciona solo a su propio riesgo: se
observa una **onda de agitación** —uno o más "pulsos" oscuros— que se
propaga a través de la bandada, alejándose del atacante, **más rápido que
el desplazamiento físico del grupo**. Está documentado en múltiples estudios
independientes sobre *Sturnus vulgaris*:

- *"Information transfer and behavioural inertia in starling flocks"*,
  Nature Physics (Attanasi et al.) — la información de un ataque se
  transfiere de forma aproximadamente lineal y sin atenuación a través de
  bandadas de hasta ~400 individuos.
- *"What underlies waves of agitation in starling flocks"*, Behavioral
  Ecology and Sociobiology (Springer).
- *"Propagating waves in starling flocks under predation"* (mismo campo,
  grupo de Hemelrijk).

**Esto es precisamente lo que el modelo actual NO tiene**: hoy, un dron que
no fue impactado directamente no se entera de que su vecino sí lo fue hasta
que el atacante lo alcanza a él también. Es una brecha concreta y acotada
—no un rediseño—, porque la maquinaria de decaimiento (P2-E) ya existe; lo
que falta es que `registrar_impacto` (o un paso posterior en
`Swarm.actualizar_amenazas`) también deposite una versión atenuada de la
misma amenaza en los vecinos cercanos, con retardo/atenuación por distancia
— literalmente la definición de una onda.

### 2.2 Régimen del enjambre según la fuerza del atacante (dinámica no lineal)

**Chen & Kolokolnikov (2014)**, *"A minimal model of predator-swarm
interactions"*, arXiv:[1403.3250](https://arxiv.org/abs/1403.3250). Modelo
matemático mínimo (ecuaciones diferenciales, análisis de bifurcación de
Hopf) que muestra que el resultado del enjambre frente a un depredador
**no es monótono en la fuerza del atacante**: depredador débil → escape
completo; fuerza moderada → el enjambre se agrupa en un anillo de
"confusión"; fuerza alta → persecución caótica; fuerza extrema → captura.
Hallazgo notable del propio paper: *"el comportamiento de enjambre no
necesariamente ayuda a evadir al depredador"* — no es una ventaja automática,
depende del régimen.

**Por qué importa para este proyecto, concretamente**: esto es una hipótesis
**testeable hoy mismo con las herramientas que ya existen** —
`src/engine/experiments.py` + el estimador corregido (`fraccion_media`)—,
barriendo la potencia del arma contra formación compacta vs. dispersa y
viendo si aparece una transición no monótona parecida a la del paper, en vez
de una relación simple "más potencia = más bajas". Es un experimento, no una
línea de código nueva.

### 2.3 Fundamento evolutivo: la confusión del depredador basta para que evolucione el enjambramiento

**Olson, Hintze, Dyer, Knoester, Adami (2013)**, *"Predator confusion is
sufficient to evolve swarming behavior"*, arXiv:[1209.3330](https://arxiv.org/abs/1209.3330).
Con un algoritmo evolutivo presa-depredador, muestran que la sola presión de
selección de "el depredador se confunde con más presas juntas" alcanza para
que evolucione comportamiento de enjambre — y que a su vez eso presiona a
los depredadores hacia sistemas de visión frontal de alta resolución.

**Por qué importa**: es el mismo tipo de metodología que ya usa `P3-B`
(coevolución genética arma↔enjambre) — no valida ningún número del proyecto,
pero le da un anclaje teórico real en biología evolutiva computacional a un
método que ya está implementado. Útil como cita si la coevolución se escribe
alguna vez como nota separada (mismo espíritu que `research/NOTA_ESTIMADOR_CIEGO.md`).

### 2.4 Los depredadores reales no persiguen individuos — apuntan a un punto fijo

**Hallazgo real, verificado**: rapaces atacando enjambres de presas aéreas
densas dirigen su ataque a un **punto fijo en el espacio** dentro del
enjambre, no a la persecución de un individuo específico (PMC:
[9399121](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9399121/), *"Raptors
avoid the confusion effect by targeting fixed points in dense aerial prey
aggregations"*).

**Esto no sugiere nada nuevo — valida algo que el proyecto ya decidió
independientemente**: `HPMissileSystem.lanzar` ya apunta al **centroide**
del grupo objetivo, no a un dron individual en movimiento. Es una
coincidencia real con estrategia de caza documentada en depredadores
aéreos reales, y vale la pena anotarla como tal en `FISICA_Y_MATEMATICA.md`
si se quiere reforzar esa decisión de diseño con literatura biológica, no
solo con la lógica de ingeniería que la motivó originalmente.

---

## 3. Resumen: qué valida, qué sugiere, qué no toca nada todavía

| Fuente | Tipo de aporte | Acción concreta |
|---|---|---|
| Ondas de agitación (starlings) | Brecha real encontrada | Propagar amenaza a vecinos con atenuación — extensión acotada de P2-E, no implementada aún |
| Chen & Kolokolnikov 2014 | Hipótesis testeable | Barrido de potencia × formación con el estimador ya corregido — experimento, no código nuevo |
| Olson et al. 2013 | Anclaje teórico | Cita para cuando P3-B se documente como hallazgo propio — no cambia código |
| Raptores / punto fijo | Validación retroactiva | Anotar en `FISICA_Y_MATEMATICA.md` que el targeting por centroide coincide con estrategia de caza real — no cambia código |

Nada de esto se implementó todavía. Es exactamente lo que pediste: literatura
real, verificada, catalogada, para decidir con criterio qué vale la pena
portar al proyecto — no una lista de ideas sueltas.
