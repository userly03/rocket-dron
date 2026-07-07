# Glosario: todos los conceptos, en lenguaje simple

Este documento explica, uno por uno, cada término técnico que aparece en
`FISICA_Y_MATEMATICA.md`, `ESTADO_DEL_ARTE_HPM.md` y
`PROYECTO_Y_CAPACIDADES.md`. La idea es que puedas leer los otros tres
documentos sin tener que buscar cada palabra por separado. Está organizado
por tema, no alfabéticamente, para que tenga sentido leerlo de corrido.

---

## 1. Electromagnetismo básico

**Campo electromagnético**: una perturbación que se propaga por el espacio
(sin necesitar un medio material, a diferencia del sonido) formada por un
campo eléctrico y uno magnético que se generan mutuamente. La luz, las
ondas de radio, el wifi, un rayo — todo es la misma familia de fenómeno,
solo cambia la frecuencia.

**Onda electromagnética / frecuencia / longitud de onda (λ)**: una onda se
repite cada cierta distancia (longitud de onda, λ) y cada cierto tiempo
(frecuencia). Se relacionan por `λ = c/f` (c = velocidad de la luz). Más
frecuencia = longitud de onda más corta. Nuestro simulador usa 2.45 GHz
(gigahercios, miles de millones de ciclos por segundo) — la misma
frecuencia que un microondas doméstico y que el wifi de 2.4 GHz. No es
casualidad: es una banda de frecuencia bien estudiada y con hardware
comercial disponible.

**HPM (High Power Microwave / microondas de alta potencia)**: un pulso
electromagnético en la banda de microondas (GHz), pero a potencias
enormemente mayores que un microondas doméstico — diseñado para inducir
corrientes eléctricas dañinas en circuitos electrónicos ajenos, no para
calentar comida.

**Potencia vs. energía**: la potencia (vatios, W; kilovatios, kW) es
*cuánta energía por segundo*; la energía (julios, J; megajulios, MJ) es el
total acumulado. Un pulso HPM dura nanosegundos pero puede tener una
potencia *pico* enorme (gigavatios, GW) con una energía total modesta —
como un flash de cámara: brillantísimo por una fracción de segundo, pero no
consume mucha electricidad en total.

**Acoplamiento electromagnético (coupling)**: cómo la energía de un campo
externo "entra" a un circuito. Un cable actúa como antena sin querer: capta
parte de la energía del pulso y la convierte en corriente eléctrica dentro
del circuito — esa corriente parásita es la que daña la electrónica.

**Susceptibilidad electromagnética**: qué tan fácil es dañar/alterar un
componente con un campo externo dado. Depende del diseño, blindaje y
tecnología del chip. Es lo que el simulador representa con el "umbral de
campo E" (ver §3).

**Latchup (CMOS latchup)**: una falla específica en chips CMOS donde una
corriente inducida crea un cortocircuito interno parásito que puede quemar
el chip permanentemente. Es uno de los mecanismos de daño reales que
estudia la literatura HPM (mencionado en el paper que usamos de
referencia).

**Blindaje / apantallado (shielding)**: una carcasa metálica o recubrimiento
que bloquea/atenúa el campo externo antes de que llegue a los circuitos
internos. En el simulador, el 20% de los drones son "blindados" (mayor
protección) — ver §7 sobre el bug de blindaje que corregimos.

---

## 2. Ondas, antenas y cómo se mide la "fuerza" de una señal

**Antena**: el dispositivo que convierte corriente eléctrica en ondas
electromagnéticas (al transmitir) o al revés (al recibir). Puede ser
omnidireccional (irradia por igual en todas direcciones, como una
bombilla) o direccional (concentra la energía en un haz, como un
reflector de linterna).

**Ganancia de antena (G, en dBi)**: cuánto más fuerte es la señal en la
dirección del haz, comparado con una antena isotrópica ideal (que irradia
perfectamente igual en todas direcciones — no existe en la realidad, es
una referencia matemática). "dBi" = decibelios respecto a isotrópico. Más
ganancia = haz más concentrado = más alcance con la misma potencia, pero
cubre menos área/ángulo.

**Apertura del cono / *beamwidth***: qué tan "ancho" es el haz de una
antena direccional, en grados. Cono angosto → alta ganancia, poco alcance
lateral. Cono ancho → baja ganancia, cubre más área. Es un
*trade-off* real: no se puede tener alcance largo Y cobertura amplia con la
misma potencia.

**Decibelio (dB) / dBi / dBm**: una escala logarítmica para comparar
potencias o ganancias (porque las diferencias reales son de muchos
órdenes de magnitud y en escala lineal serían números incómodos). dBi =
ganancia de antena respecto a isotrópico. dBm = potencia respecto a 1
milivatio. La fórmula es `dB = 10·log₁₀(razón)`.

**Densidad de potencia (S, en W/m²)**: cuánta potencia atraviesa cada metro
cuadrado a cierta distancia de la fuente. Como la misma energía total se
reparte sobre una esfera cada vez más grande al alejarse, `S` cae con el
cuadrado de la distancia (`S ∝ 1/r²`) — la **ley del inverso del
cuadrado**, la misma razón por la que una lámpara se ve más tenue cuanto
más lejos estás.

**Campo eléctrico (E, en V/m)**: la magnitud que realmente "siente" un
circuito expuesto — se relaciona con la densidad de potencia por
`E = √(S · 377)`, donde 377 Ω es la **impedancia del vacío** (una
constante física real, `√(μ₀/ε₀)`, sale de las ecuaciones de Maxwell). Es
la unidad en la que se suelen expresar los umbrales de daño en literatura
HPM real.

**Campo cercano / campo lejano (*near-field* / *far-field*)**: muy cerca de
una antena (distancia menor a `2D²/λ`, con D el tamaño de la antena), el
campo se comporta de forma más compleja y las fórmulas simples (como
`S=P·G/4πr²`) no son válidas todavía. A distancias mayores ("campo
lejano"), sí. Nuestro simulador usa siempre las fórmulas de campo lejano,
lo cual es una simplificación reconocida a muy corta distancia (ver
`FISICA_Y_MATEMATICA.md` §4).

**Polarización**: la orientación del campo eléctrico oscilante (horizontal,
vertical, circular). Si el emisor y el receptor (o el cable que actúa como
antena accidental) no están alineados en polarización, se pierde
eficiencia de acoplamiento. No lo modelamos todavía (anotado como mejora
futura).

**RCS — sección transversal de radar** (*Radar Cross Section*, en m²):
qué tan "grande" ve un radar a un objeto — no es el tamaño físico real,
es una medida de cuánta energía de radar refleja de vuelta. Un dron
pequeño tiene un RCS muy chico (~0.02 m² en nuestro simulador), lo que lo
hace difícil de detectar a distancia — al igual que en la realidad.

---

## 3. El modelo de daño, paso a paso (de la fórmula a la probabilidad)

**Ecuación de Friis**: la fórmula `S = P·G/(4πr²)` — cuánta densidad de
potencia llega a distancia `r` desde una fuente de potencia `P` y ganancia
`G`. El `4πr²` es literalmente el área de una esfera de radio `r` — de ahí
sale la ley del inverso del cuadrado.

**Ecuación de radar**: versión "ida y vuelta" de Friis —
`Pr = Pt·G²·λ²·σ/(4π)³r⁴` — usada para saber si un radar puede *detectar*
un objeto (a diferencia de Friis, que es para saber cuánta energía *daña*
un objetivo). Cae con `r⁴` (no `r²`) porque la señal viaja ida y vuelta,
así que la atenuación por distancia se aplica dos veces.

**Sigmoide / función logística**: una curva en forma de "S" que va de 0 a
1 suavemente, típicamente centrada en algún valor umbral. Se usa en
estadística y en modelos de "dosis-respuesta" (¿a qué dosis de algo la
mitad de una población reacciona?). En nuestro simulador, convierte "campo
E calculado" en "probabilidad de que ESTE dron en particular falle" — no
todos los drones fallan exactamente al mismo campo E (hay variación real
de fabricación/blindaje entre unidades), la sigmoide modela esa variación
poblacional.

**Probabilidad vs. determinismo**: el simulador NO dice "a 50 metros
siempre cae" — calcula una probabilidad (p. ej. 30%) y después hace un
sorteo aleatorio. Por eso disparar el mismo tiro dos veces puede dar
resultados distintos — es intencional, refleja que un arma de área real
no es 100% consistente disparo a disparo.

**Espacio de "momios" (odds)**: en vez de trabajar directamente con
probabilidad (0 a 1), a veces conviene trabajar con `odds = p/(1-p)` (la
razón entre "pasa" y "no pasa" — como en las apuestas: "3 a 1"). Es útil
porque reducir probabilidad de forma *proporcional* funciona mejor
dividiendo los momios que desplazando un parámetro dentro de la sigmoide
(ver el bug del blindaje corregido, `FISICA_Y_MATEMATICA.md` hallazgo #7).

**Umbral de susceptibilidad (E₀)**: el valor de campo E (V/m) donde la
probabilidad de daño es exactamente 50% en la sigmoide. Por debajo, poco
probable; por encima, muy probable. Es el parámetro más "sensible" del
modelo — y el que menos confianza real tenemos en su valor exacto (ver §9
sobre confianza simulación-realidad).

---

## 4. Guiado, movimiento y detección

**Navegación proporcional (PN)**: la ley de control real que usan los
misiles guiados de verdad. En vez de "apuntar siempre al blanco actual"
(lo que se llama *pure pursuit*, y genera trayectorias de persecución poco
realistas), la PN gira proporcionalmente a qué tan rápido cambia el
**ángulo de línea de visión** (LOS) hacia el blanco — si ese ángulo no
cambia, el misil ya está en curso de colisión y no necesita corregir.

**LOS (*Line of Sight* / línea de visión)**: el ángulo, visto desde el
misil, hacia dónde está el blanco en este instante. La PN mide qué tan
rápido *cambia* ese ángulo (tasa de LOS), no el ángulo en sí.

**Slant range (distancia 3D real)**: la distancia en línea recta entre dos
puntos en el espacio (`√(Δx²+Δy²+Δz²)`), a diferencia de la distancia
proyectada solo en el plano horizontal (x,y). Un dron a otra altitud está
realmente más lejos de lo que parece mirando el mapa desde arriba.

**Fusible de proximidad (*VT fuze*)**: un mecanismo de detonación real
(usado desde la Segunda Guerra Mundial) que no espera un impacto directo —
detona cuando detecta que el blanco está en su punto de máxima cercanía
(justo antes de empezar a alejarse), maximizando el efecto de un arma de
área. Es el mecanismo que corregimos en el misil de este simulador (antes
detonaba apenas cruzaba un umbral, no en el punto óptimo real).

**Soft-kill vs. hard-kill**: *hard-kill* = destruir físicamente el blanco
(explosión, impacto). *Soft-kill* = neutralizar sin destruir (interferir
electrónica o el enlace de control, como hace el HPM y el jamming en este
simulador) — el dron cae porque pierde control, no porque algo lo rompió.

**Boids** (Reynolds, 1987): un modelo de comportamiento de enjambre con
tres reglas simples por individuo — alejarse de vecinos muy cerca
(separación), igualar el rumbo de los vecinos (alineación), acercarse al
centro del grupo cercano (cohesión) — que en conjunto producen movimiento
de bandada realista sin que nadie "controle" al grupo desde arriba.
Le agregamos una 4ª regla (volver a una zona de patrulla si se aleja
demasiado, ver `FISICA_Y_MATEMATICA.md` §8.2).

**SNR (*Signal-to-Noise Ratio* / relación señal-ruido)**: cuánto más fuerte
es la señal útil comparada con el ruido de fondo, normalmente en dB. Un
radar necesita cierto SNR mínimo para poder distinguir un blanco real del
ruido — es el concepto detrás del umbral de detección del radar del
simulador.

---

## 5. Drones y contramedidas (el panorama que preguntaste)

**FPV (*First Person View*)**: un dron controlado en tiempo real por un
operador que ve la imagen de una cámara a bordo, como si "estuviera adentro"
del dron — el estilo de dron más usado hoy en conflictos como el de
Ucrania, por ser barato y preciso.

**Dron controlado por radio (RF)**: el modo tradicional — el operador
envía comandos y recibe video por ondas de radio (2.4 GHz, 5.8 GHz, etc.),
igual que un control remoto de juguete pero más sofisticado. Este es el
tipo de dron que el `Jammer` de nuestro simulador sí puede afectar.

**Dron de fibra óptica**: en vez de radio, el dron va conectado a su
operador por un cable de **fibra óptica** finísimo que se va desenrollando
de un carrete mientras vuela (parecido a un cable de teléfono viejo, pero
de vidrio/plástico, no de cobre). Se volvió común específicamente porque
es **inmune al jamming de radio** — no hay ninguna señal inalámbrica que
interferir, los comandos viajan como luz dentro del cable físico.

### La duda que quedó sin aclarar bien: ¿por qué el jammer no funciona contra esto, pero el HPM sí?

Son dos mecanismos completamente distintos, y por eso uno funciona y el
otro no:

- **El `Jammer` (guerra electrónica clásica) ataca el *canal de
  comunicación*** — inunda el aire con ruido de radio para que el receptor
  del dron no pueda distinguir los comandos reales de su operador entre
  el ruido. Es como gritar tan fuerte en un cuarto que nadie escucha lo
  que dice otra persona. **Si no hay canal de radio** (porque los comandos
  van por un cable de fibra óptica), no hay nada que "ahogar" — el jammer
  simplemente no tiene nada sobre qué actuar. Por eso, contra un dron de
  fibra óptica, un jammer de radio es completamente inútil, sin importar
  cuánta potencia tenga.

- **El HPM (`HPMWeapon`/`HPMissile` de este simulador) ataca el
  *hardware*, no el canal.** No le importa cómo el dron recibe sus
  órdenes — el pulso induce corrientes eléctricas dañinas directamente en
  el cableado y los circuitos internos del dron (el controlador de vuelo,
  el ESC que maneja los motores, etc.), sin importar si esos circuitos
  reciben sus comandos por radio, por fibra óptica, o si el dron es
  totalmente autónomo (con IA a bordo, sin ningún operador humano en
  tiempo real). Es como la diferencia entre interferir la señal del
  celular de alguien (solo funciona si está usando el celular en ese
  momento) contra un pulso que fría directamente los circuitos del
  celular (funciona esté llamando, en wifi, o apagado — mientras tenga
  electrónica expuesta).

Por eso, en la doctrina militar real (ver `ESTADO_DEL_ARTE_HPM.md` §2, caso
Ucrania), el HPM se está volviendo más relevante justo *porque* los drones
de fibra óptica volvieron obsoleto al jamming clásico — pero no al HPM.
**Tipos de drones y qué los afecta, resumen:**

| Tipo de dron | ¿Lo afecta el Jammer? | ¿Lo afecta el HPM (cañón/misil)? |
|---|---|---|
| Radio-controlado (FPV clásico) | Sí | Sí |
| Fibra óptica | **No** — no hay señal que interferir | Sí — ataca el hardware, no el canal |
| Autónomo (IA a bordo, sin operador en vivo) | No — no depende de un enlace continuo | Sí, mientras tenga electrónica expuesta |

---

## 6. Investigación y validación (lo que aparece en la sección de obstáculos)

**Monte Carlo**: correr una simulación miles de veces con variaciones
aleatorias (potencia, ángulo, umbral) para obtener una distribución de
resultados con incertidumbre, en vez de un único número determinístico. Es
lo que hace el paper que usamos de referencia (10,000 corridas) y lo que
todavía NO hace nuestro simulador de forma sistemática (anotado como
pendiente).

**Ley de los grandes números**: si repetís un experimento aleatorio muchas
veces, el promedio de los resultados converge al valor teórico esperado.
Es la base para poder decir "corrí 1000 simulaciones y el 30% cayó, lo cual
coincide con la probabilidad teórica calculada" — una forma de
autovalidación que todavía no implementamos de forma automatizada.

**Intervalo de confianza**: en vez de decir "51.4% de probabilidad", decir
"51.4% ± 1.0%" — reconociendo que hay incertidumbre en la medición/
estimación. El paper de referencia sí reporta esto; nuestro simulador
todavía no.

**FDTD / Método de Momentos**: técnicas de simulación electromagnética
"de verdad" (resuelven numéricamente las ecuaciones de Maxwell sobre una
malla del espacio 3D) — mucho más precisas pero muchísimo más lentas
(horas/días de cómputo para una sola geometría) que las fórmulas
simplificadas que usamos acá (que corren en microsegundos). Software real
para esto: CST Studio Suite, COMSOL, ANSYS HFSS. No están integrados en
este proyecto — es la comparación que falta para validar cuantitativamente
el modelo (ver `PROYECTO_Y_CAPACIDADES.md` §5, obstáculo 3).

---

¿Sigue habiendo algo puntual que no quedó claro? Decime el término o la
fórmula exacta (aunque sea copiando y pegando la línea de otro documento)
y lo agrego acá con más detalle.
