# El estimador ciego: por qué un Monte Carlo con 100% de tests en verde puede medir la pregunta equivocada

**Un caso de pseudorreplicación y elección de estadístico en simulación de efectividad de armas contra enjambres**

Autor: proyecto `simulador-ew` (repositorio de investigación, no institucional)
Fecha: 2026-09-13
Estado: nota técnica independiente, no revisada por pares. No depende de la validez de ninguna fuente externa citada como motivación — es autocontenida.

---

## Resumen

Al auditar un simulador Monte Carlo de efectividad de armas de microondas de alta
potencia (HPM) contra enjambres de drones, encontramos que el estimador principal
reportaba `p̂ = 0` con un intervalo de confianza del 95% de ancho 0.32, **incluso
cuando el arma sí había causado bajas** (1 en 240 exposiciones). El código no tenía
ningún error aritmético: los 123 tests de la suite pasaban, el cálculo del intervalo
de Wilson era correcto, y la semilla era reproducible. El defecto estaba en **qué
estadístico se eligió medir** y en **qué se trató como unidad de muestreo
independiente** — dos errores de diseño experimental, no de implementación, que no
tiene ningún test unitario que pueda detectar por sí solo, porque el código hace
exactamente lo que se le pidió. Documentamos el diagnóstico, la corrección
(reemplazar un indicador binario raro por un estadístico continuo por réplica, con
intervalo por bootstrap de percentiles), y el efecto medido: en un escenario con
bajas reales, el intervalo pasó de un ancho de 0.32 a uno de 0.03 (≈10 veces más
angosto) y el punto estimado dejó de estar forzado a cero. Generalizamos el
hallazgo a una lista de verificación para cualquier simulación Monte Carlo de
efectividad de armas contra sistemas de múltiples unidades (enjambres, formaciones,
salvas), donde el mismo par de errores es estructuralmente fácil de cometer.

---

## 1. El problema, en abstracto

Cualquier simulación Monte Carlo de "¿funciona esta arma contra este enjambre?"
tiene que responder dos preguntas de diseño antes de escribir una sola línea de
código de física:

1. **¿Qué estadístico por corrida (réplica) es la variable de interés?**
2. **¿Cuál es la unidad que se trata como independiente al calcular incertidumbre?**

Errar la primera produce un estimador que existe, corre, y **no tiene señal** en la
región de operación que importa. Errar la segunda produce un intervalo de confianza
que existe, se calcula con una fórmula de libro de texto, y **está mal
—generalmente demasiado angosto o directamente inaplicable— porque asume
independencia donde no la hay.** Ninguno de los dos errores rompe un test
unitario: el código es internamente consistente con la pregunta que le hicieron,
solo que la pregunta era la incorrecta. Es un modo de falla silencioso.

### 1.1 Estadístico incorrecto: evento raro todo-o-nada en vez de respuesta graduada

Si la cantidad físicamente interesante es "¿cuántas unidades del enjambre quedaron
neutralizadas?", definir el éxito de una réplica como *"¿se neutralizó el 100% del
enjambre?"* colapsa una respuesta graduada (0 a N bajas) en un indicador binario
que, fuera de un régimen degenerado de saturación total, vale 0 casi en todo el
espacio de parámetros de interés operativo. El estimador entonces reporta
`p̂ ≈ 0` con intervalos anchos no porque el arma no tenga efecto, sino porque **se
le preguntó por el evento equivocado.**

### 1.2 Unidad de independencia incorrecta: pseudorreplicación

Un segundo error, relacionado pero distinto, aparece si se intenta arreglar 1.1
agregando los resultados individuales de cada unidad del enjambre (p. ej. "bajas
por dron") y calculando un intervalo binomial estándar (Wilson, Clopper-Pearson)
tratando cada dron como un ensayo de Bernoulli independiente. **No lo son**: dentro
de una misma réplica, todas las unidades comparten geometría, semilla aleatoria y
configuración del arma. Esto es una instancia directa de lo que la literatura
ecológica llama **pseudorreplicación**: tratar sub-muestras correlacionadas como si
fueran repeticiones independientes del experimento (Hurlbert, 1984). La unidad de
muestreo genuinamente independiente es **la réplica completa**, no cada unidad
dentro de ella.

---

## 2. Caso de estudio: lo que encontramos en nuestro propio instrumento

### 2.1 El sistema

Un simulador de efectividad de un arma HPM (cañón continuo o misil) contra un
enjambre de drones, con física de propagación (ecuación de Friis), acoplamiento por
cableado, y un modelo de daño por subsistema calibrado contra literatura publicada.
El detalle del modelo de daño **no es relevante para esta nota** — el defecto
descrito aquí es puramente de diseño del experimento Monte Carlo y es independiente
de si la física subyacente está bien calibrada o no.

### 2.2 El estimador original y su falla, medida

```
run_replica() → éxito = (neutralizados == total_drones)   # todo-o-nada
```

Configuración de referencia: cañón de 25 kW, azimut 45°, enjambre circular de 30
drones a ~700 m, 8 réplicas (240 exposiciones dron-réplica en total).

```
neutralizados por réplica:  0 0 0 0 0 1 0 0
p̂ (todo-o-nada)  = 0.0
IC95% (Wilson)    = [0.0, 0.3244]
```

**Hubo una baja real en 240 exposiciones, y el estimador reportó exactamente cero.**
El cálculo de Wilson sobre 8 réplicas Bernoulli (¿se aniquiló el 100%? sí/no) es en
sí mismo estadísticamente válido — cada réplica sí es independiente para esa
pregunta particular. El defecto no está en la aritmética: está en que la pregunta
"¿se aniquiló TODO el enjambre?" es la incorrecta para un arma que degrada
gradualmente la fuerza atacante. La información sobre esa única baja existía en
`neutralizados_por_replica` y se descartaba antes de llegar al reporte final.

### 2.3 La corrección

Se redefinió la métrica primaria y la unidad de remuestreo:

- **Unidad de muestreo:** la réplica (no el dron individual).
- **Estadístico primario:** `fraccion_media` — la media, sobre réplicas, de la
  fracción de drones neutralizados en cada réplica. Es una variable continua en
  [0,1], no un indicador binario.
- **Incertidumbre:** intervalo de confianza del 95% por **bootstrap de
  percentiles** (10.000 remuestreos, semilla fija para reproducibilidad exacta),
  remuestreando las fracciones por réplica — nunca los drones individuales. Se
  reporta además un intervalo por t de Student como contraste barato: si ambos
  difieren mucho, la distribución subyacente es asimétrica, y eso es información,
  no ruido.
- **El indicador todo-o-nada se conserva**, pero degradado a métrica secundaria
  explícita (`aniquilacion_total`), con su Wilson calculado correctamente sobre la
  réplica como unidad — que es, precisamente, donde esa fórmula sí aplica.

### 2.4 El efecto medido

Con el estimador corregido, la misma configuración de referencia (cañón a ~700 m)
da hoy `fraccion_media = 0.0`, `IC95% = [0.0, 0.0]` — un cero *correcto*: una
corrección posterior e independiente del modelo de daño (retirar un artefacto de
piso en la sigmoide, fuera del alcance de esta nota) eliminó las bajas espurias que
antes se producían incluso a campo eléctrico nulo. Es un cero distinto en
naturaleza del `p̂ = 0.0` de §2.2: ahí el cero ocultaba información descartada; acá
el cero es la respuesta física correcta, y el estimador lo dice con un intervalo
que colapsa a un punto en vez de abarcar `[0, 0.32]`.

Para exhibir el caso en que sí hay efecto, se corrió el mismo instrumento con un
arma que sí engancha al enjambre (misil, detonación a ~80 m), 10 réplicas, 30
drones por réplica:

```
neutralizados por réplica:  1 0 0 0 2 0 0 0 0 1        (4 bajas en 300 exposiciones)

Métrica nueva  — fraccion_media   = 0.0133   IC95% (bootstrap) = [0.0000, 0.0267]
Métrica vieja  — aniquilación total = 0.0     IC95% (Wilson)    = [0.0000, 0.2775]
```

**En el mismo escenario, con las mismas 4 bajas reales, la métrica vieja sigue
reportando `p̂ = 0` con un intervalo de ancho 0.28** — porque ninguna réplica tuvo
el enjambre 100% aniquilado. La métrica nueva sí distingue este escenario (con
efecto real, aunque chico) del anterior (sin ningún efecto): `0.0133 > 0`, con un
intervalo diez veces más angosto que el que reportaba la métrica vieja. Ambos
números, viejo y nuevo, se calculan sobre las mismas 10 réplicas — la diferencia es
enteramente la elección de qué medir, no una diferencia de datos.

### 2.5 Validación del estimador nuevo contra verdad conocida

Que el intervalo se haya angostado no prueba por sí solo que esté bien calculado
—un intervalo mal calculado también puede ser angosto—, así que se verificó contra
dos casos con probabilidad teórica conocida:

1. **Sintético:** 60 réplicas de `Bernoulli(p=0.35)` simulado directamente (sin
   pasar por el motor físico). El IC bootstrap cubre 0.35 con ancho < 0.15.
2. **A través del motor físico real:** un escenario construido para que cada dron
   tenga *exactamente* la misma probabilidad teórica `p` — todos a 20 m, sobre el
   eje del haz (offset angular 0°), con cableado sintonizado a la frecuencia del
   arma (acoplamiento de longitud = 1) y polarización = 1 (acoplamiento total = 1,
   sin variables de confusión). `p` se calcula de forma cerrada con la misma
   fórmula de acoplamiento de Friis que usa el motor. Sobre 40 réplicas, el IC
   bootstrap cubre ese `p` teórico.

Ninguno de los dos casos depende de que el modelo de daño esté bien calibrado
contra literatura externa — son verdad conocida por construcción matemática, no por
autoridad de una fuente citada.

---

## 3. Por qué ningún test unitario preexistente lo atrapó

Los 123 tests de la suite pasaban antes, durante y después de encontrar el defecto,
porque todos verificaban que el código hiciera **lo que se le pidió** (aritmética
de Wilson correcta, semillas reproducibles, agregación correcta del indicador
todo-o-nada). Ninguno preguntaba si **lo que se le pedía calcular** era la cantidad
correcta. Esto generaliza: un test de regresión protege contra cambios accidentales
en un cálculo ya decidido; no protege contra haber decidido calcular la cosa
equivocada desde el principio. Esa decisión solo se audita comparando el estimador
contra **casos con verdad conocida por fuera del propio código** (§2.5), no
corriendo la suite existente más veces.

---

## 4. Lista de verificación generalizable

Para cualquiera que diseñe una simulación Monte Carlo de efectividad de un arma,
sensor, o intervención contra un sistema de múltiples unidades (enjambres,
formaciones, redes, salvas):

1. **¿El estadístico de interés es graduado o todo-o-nada?** Si en la mayor parte
   del espacio de operación relevante el evento todo-o-nada va a valer 0 (o 1),
   mida la respuesta graduada (fracción, conteo, dosis) en su lugar, y reserve el
   indicador extremo como métrica secundaria declarada.
2. **¿Cuál es la unidad genuinamente independiente?** Si las sub-observaciones
   dentro de una corrida comparten semilla, geometría o configuración, esa corrida
   —no la sub-observación— es la unidad de remuestreo. Aplicar una fórmula de
   intervalo binomial a sub-observaciones correlacionadas es pseudorreplicación,
   sin importar cuán simple o "estándar" parezca la fórmula.
3. **Valide el estimador contra un caso con verdad conocida construido
   matemáticamente**, no solo contra que el código no arroje excepciones. Un
   escenario degenerado (todas las unidades con la misma probabilidad teórica
   exacta) es barato de construir y no depende de ninguna fuente externa.
4. **Un 100% de tests en verde es evidencia de consistencia interna, no de que se
   esté midiendo la pregunta correcta.** Son afirmaciones distintas y la primera no
   implica la segunda.

---

## 5. Alcance y limitaciones

Esta nota trata exclusivamente el **diseño del estimador y de la unidad de
muestreo**. No afirma nada sobre si el modelo físico de daño subyacente (umbrales
de acoplamiento, calibración contra literatura publicada) es correcto — esa es una
pregunta distinta, no resuelta, y no se apoya en esta nota ni la nota se apoya en
ella. Los valores numéricos concretos (`fraccion_media = 0.0133`, etc.) son salida
del modelo de daño particular de este proyecto en su estado actual y **no deben
citarse como una probabilidad de efectividad real de ningún sistema HPM** — sirven
únicamente para ilustrar la magnitud del cambio en el estimador, no como resultado
operativo.

No se contactó a ningún autor externo ni se depende de la validez de ninguna
publicación de terceros para sostener el argumento de esta nota: el defecto y su
corrección se verifican con matemática autocontenida (§2.5) y son reproducibles
íntegramente desde el propio código.

---

## 6. Reproducibilidad

- Repositorio: `simulador-ew` (proyecto de investigación independiente).
- Commit donde se introduce la corrección (P1-A): `a408a39`.
- Implementación: `src/engine/experiments.py` (función `run_replica`, clase
  `ExperimentManager._summarize`, funciones `intervalo_bootstrap` / `wilson_interval`).
- Tests que codifican los casos de este documento como regresión permanente:
  `tests/test_experiments.py::TestIntervaloBootstrap::test_cubre_la_verdad_conocida`
  (caso sintético, §2.5), `tests/test_experiments.py::TestEstimadorTieneSenalEnElMotorReal::test_a_quemarropa_contra_verdad_conocida_del_motor`
  (caso a través del motor físico, §2.5),
  `tests/test_experiments.py::TestEstimadorTieneSenalEnElMotorReal::test_reporta_el_efecto_y_un_ic_mucho_mas_estrecho_que_v1`
  (comparación numérica directa contra el estimador v1, §2.4), y
  `tests/test_experiments.py::TestEstimadorTieneSenalEnElMotorReal::test_el_canion_a_700m_no_hace_nada_y_el_estimador_lo_dice`
  (el cero correcto, §2.4).
- Todos los números de este documento se pueden reproducir corriendo esos tests
  directamente; ninguno requiere acceso a datos ni dependencias externas al
  repositorio.

---

## Referencias

- Hurlbert, S.H. (1984). *Pseudoreplication and the design of ecological field
  experiments.* Ecological Monographs, 54(2), 187–211.
- Efron, B. & Tibshirani, R.J. (1993). *An Introduction to the Bootstrap.*
  Chapman & Hall/CRC.
- Wilson, E.B. (1927). *Probable inference, the law of succession, and statistical
  inference.* Journal of the American Statistical Association, 22(158), 209–212.
