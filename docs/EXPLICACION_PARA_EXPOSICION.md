# Explicación simple del proyecto (para exponer)

Este documento explica el proyecto de cero, en orden, con los términos
reales del tema (no comparaciones con cosas de la vida diaria). Cada
concepto se define en el momento en que aparece, así que se puede leer de
corrido sin saltar a otro documento. Si algún término necesita más
detalle, está desarrollado en `GLOSARIO.md`.

---

### 1. Qué es el proyecto

Un simulador que representa, con fórmulas físicas reales, cómo un arma que
emite energía electromagnética puede inutilizar drones. No dispara balas
ni explosivos: emite ondas electromagnéticas de alta potencia dirigidas al
enjambre.

### 2. Qué es la energía que usa esta arma

Ondas electromagnéticas de alta potencia, en la banda de microondas, a una
frecuencia de 2.45 gigahercios (GHz) — la misma banda de frecuencia que
usan un horno microondas doméstico y el wifi de 2.4 GHz. Una onda
electromagnética transporta energía mediante un campo eléctrico y un campo
magnético que se generan mutuamente y viajan por el espacio a la velocidad
de la luz.

### 3. Qué es una antena, y por qué importa acá

Una antena es una estructura física conductora (normalmente metálica) que
cumple dos funciones relacionadas: convierte una corriente eléctrica en
una onda electromagnética que se propaga por el espacio (cuando
transmite), o convierte una onda electromagnética que le llega en una
corriente eléctrica (cuando recibe). Es la pieza de hardware real que
emite o capta la energía electromagnética de la que habla este documento
— no es un concepto abstracto, es un objeto físico que se puede tocar y
medir.

Hay antenas de formas muy distintas según qué tan concentrada quieran
dejar la energía:

- Una antena **omnidireccional** (por ejemplo, una varilla o un mástil
  metálico simple) irradia la energía por igual en todas las direcciones
  alrededor de su eje.
- Una antena **direccional** (por ejemplo, un plato parabólico, como el de
  una antena satelital) concentra la energía en una dirección específica,
  formando un haz. Cuanto más grande es el plato respecto a la longitud de
  onda que emite, más angosto y concentrado queda ese haz.

La **ganancia de la antena** (que aparece más adelante, en la ecuación de
Friis) es, justamente, la medida de cuánto más fuerte es la energía en la
dirección del haz de una antena direccional, comparada con lo que daría una
antena omnidireccional ideal con la misma potencia de entrada. Un cañón HPM
real usa un plato de este tipo — por eso el simulador calcula la ganancia a
partir del ángulo de apertura del cono configurado: cono más angosto =
plato efectivamente más concentrado = mayor ganancia.

### 4. Cómo esa energía llega a dañar un dron

Un dron tiene cableado interno y circuitos electrónicos (el controlador de
vuelo, los reguladores de los motores). Cuando una onda electromagnética de
suficiente intensidad llega hasta ese cableado, induce en él una corriente
eléctrica no deseada. Esa corriente puede alterar o dañar los componentes
electrónicos y hacer que el dron pierda el control de vuelo. El dron no
explota ni se destruye físicamente: deja de responder y cae por pérdida de
control. A este mecanismo (dañar la electrónica sin destrucción física) se
le llama **soft-kill**, en contraste con un arma que destruye el blanco por
impacto o explosión (**hard-kill**).

### 5. Primera ley física: la energía se debilita con la distancia

La energía que emite el arma se reparte sobre una superficie cada vez más
grande a medida que se aleja de la fuente — matemáticamente, sobre la
superficie de una esfera, que crece con el cuadrado del radio. Por eso, la
cantidad de energía que llega a un punto por unidad de área (la **densidad
de potencia**) disminuye con el cuadrado de la distancia. Esta relación es
la **ecuación de Friis**:

```
S = (Potencia · Ganancia de la antena) / (4 · π · distancia²)
```

`S` es la densidad de potencia (en vatios por metro cuadrado, W/m²); la
potencia es la energía emitida por segundo (en vatios, W); la ganancia de
la antena es la de la sección anterior; la distancia es qué tan lejos está
el dron del punto de emisión.

### 6. De densidad de potencia a campo eléctrico

Lo que realmente actúa sobre los circuitos del dron no es la densidad de
potencia directamente, sino el **campo eléctrico** que esa densidad de
potencia representa, medido en voltios por metro (V/m). Se calcula así:

```
E = raíz_cuadrada(S · 377)
```

`377` ohmios es la **impedancia del vacío**, una constante física fija que
relaciona densidad de potencia y campo eléctrico en el espacio libre.

### 7. A partir de qué campo eléctrico falla un dron

Cada dron tiene un umbral de campo eléctrico a partir del cual sus
circuitos empiezan a fallar, pero ese umbral no es idéntico entre unidades
— hay variación real de fabricación y de blindaje. Por eso el sistema no
dice "todo dron que reciba más de tantos voltios por metro cae"; en cambio,
calcula la **probabilidad** de que ese dron en particular falle, mediante
una función matemática llamada **sigmoide**, que da un valor entre 0% y
100% según qué tan por encima o por debajo del umbral esté el campo E
calculado para ese dron. A mayor campo E (más cerca, o más potencia),
mayor probabilidad.

### 8. Dos armas HPM, dos formas de aplicar esto — y dos economías opuestas

- **Cañón HPM**: arma fija, en tierra, que dispara en una dirección y con
  un ángulo de apertura configurables (un cono). Solo afecta a los drones
  que están dentro de ese cono, con el campo eléctrico calculado según su
  distancia y su desviación angular respecto al eje del cono. **No se
  consume al dispararse** — es una instalación que solo gasta la
  electricidad de ese pulso y queda lista para el siguiente disparo. Es la
  categoría que representa a sistemas reales como Leonidas o THOR, y es la
  que tiene la ventaja de costo (fracciones de centavo por disparo) frente
  a un enjambre de drones baratos.
- **Misil HPM**: vuela hacia el enjambre y detona en el aire, afectando a
  todos los drones dentro de un radio esférico alrededor del punto de
  detonación, en todas las direcciones (sin cono direccional). **Se pierde
  por completo en cada uso**, exactamente como cualquier misil convencional
  — esto tiene una consecuencia económica importante que se explica en la
  sección siguiente.

**Importante para no confundir**: la ventaja de costo del HPM frente a un
enjambre de drones (la razón por la que hoy se invierte tanto en esta
tecnología) es la del **cañón**, no la del misil. Son dos arquetipos con
economías opuestas dentro del mismo simulador.

### 9. De qué está hecho un misil HPM real, y qué tan caro es

A diferencia de un misil convencional (que lleva una carga explosiva como
elemento principal), un misil HPM real — el programa **CHAMP**
(Boeing/Laboratorio de Investigación de la Fuerza Aérea de EEUU), que
inspira el `HPMissile` de este simulador — contiene estos elementos:

1. **Fuente de microondas de alta potencia**: un tubo generador de
   radiofrecuencia (un magnetrón, un vircator o un klystron, según el
   diseño específico) que produce el pulso electromagnético en la
   frecuencia de diseño. Es, dentro del misil, el componente técnicamente
   más complejo, y el que más incide en el costo total.
2. **Sistema de energía pulsada**: una batería o generador que carga un
   banco de condensadores y los descarga de golpe en un pulso brevísimo
   (nanosegundos). Permite que la potencia *pico* del pulso sea enorme
   aunque la energía total consumida sea modesta.
3. **Antena** (sección 3): dirige la energía generada hacia el blanco.
4. **Estructura/fuselaje del misil**: el cuerpo que lo hace volar — motor
   o propulsor, sistema de guiado, superficies de control — igual que
   cualquier misil de crucero convencional en esta parte.
5. **Disparador**: mecanismo que activa la descarga eléctrica en el
   momento de detonar — no es una carga explosiva destructiva, solo lo
   necesario para iniciar el pulso.

**Costo real, con cuidado de qué significa exactamente**: el programa
CHAMP completo (desarrollo, no solo unidades) costó **38 millones de
dólares** en una demostración de 3 años, y cada misil individual de ese
programa costó por encima de los **400,000 dólares**. Dos aclaraciones
importantes sobre este número:

1. **Es un dato de un demostrador de investigación, no de un producto
   masivo.** CHAMP se construyó en muy pocas unidades, para probar el
   concepto, no para producción en serie — y en esa etapa (poca cantidad,
   mucha ingeniería a medida) casi cualquier vehículo aéreo es caro. No es
   una ley universal de "cuánto cuesta un misil HPM" — si se rediseñara
   específicamente para producirse en masa y ser desechable barato (como
   pasó con municiones merodeadoras tipo Switchblade, que cuestan decenas
   de miles de dólares, no millones, porque se diseñaron desde el inicio
   para eso), el costo real de un misil equivalente hoy podría ser mucho
   menor. Es el único dato público real que tenemos, no una cifra que se
   pueda dar por segura para "nuestro" misil simulado en cualquier
   escenario futuro.
2. **Por eso, económicamente, este misil NO es la respuesta "barata"
   contra un enjambre de drones de bajo costo** (drones de cientos de
   dólares cada uno) — usar un arma de +$400,000 para derribar, aunque
   sea, a varios drones de una vez, sigue sin cerrar la cuenta. De hecho,
   la prueba histórica real de CHAMP (2012) fue contra los sistemas
   electrónicos de un edificio/instalación fija, no contra un enjambre de
   drones — en este simulador lo reinterpretamos como arma anti-enjambre,
   que es una extrapolación razonable de la tecnología, pero no
   necesariamente el uso para el que ese programa específico se costeó
   originalmente.

Los fabricantes no publican un desglose de "este componente cuesta
tanto", pero la fuente de microondas de alta potencia (punto 1) es, en
general, el componente individual más caro de fabricar — es tecnología
especializada, no una pieza de uso masivo como las de un misil
convencional.

**Para no confundir dos costos distintos**: esto es el costo de **un
misil**, que se pierde por completo en cada uso (como cualquier misil
convencional). Es distinto del costo *por disparo* de un sistema de tierra
como Leonidas (`ESTADO_DEL_ARTE_HPM.md`), que cuesta fracciones de centavo
de electricidad cada vez que dispara, porque ese sistema no se consume a sí
mismo — solo gasta la electricidad de ese pulso y queda listo para el
siguiente. El cañón HPM de este simulador representa esa segunda
categoría; el misil, la primera.

### 10. El misil corrige su rumbo en vuelo

El misil no vuela en línea recta fija: corrige su dirección constantemente
para interceptar a un dron específico, fijado como blanco al lanzarse. Esta
corrección usa la ley de **navegación proporcional**: el misil mide qué
tan rápido cambia el ángulo hacia el que se ve el blanco (el ángulo de
**línea de visión**, LOS) y gira proporcionalmente a esa velocidad de
cambio. Si ese ángulo no cambia, el misil ya va en curso de intercepción
directa y no necesita corregir nada.

### 11. El misil detona en el punto de máxima cercanía

El misil no detona apenas se acerca a un dron: mientras la distancia hacia
el dron activo más cercano siga disminuyendo, el misil sigue acercándose.
Detona exactamente en el instante en que esa distancia empieza a aumentar
de nuevo — el punto de máxima cercanía real de todo el vuelo — porque ahí
el campo eléctrico sobre los drones cercanos es más intenso, y por lo
tanto la probabilidad de neutralización es la más alta posible en ese
encuentro.

### 12. Antes de atacar, hay que detectar

El sistema no conoce automáticamente la posición de cada dron para elegir
un blanco: un radar calcula, para cada dron, si la señal reflejada de
vuelta es suficientemente fuerte respecto al ruido de fondo como para
distinguirlo (la **relación señal-ruido**, SNR). Esto se calcula con la
**ecuación de radar**, similar a la de Friis pero con la energía viajando
de ida y de vuelta (del radar al dron, y de vuelta al radar), por lo que la
señal recibida cae con la distancia elevada a la cuarta potencia, no al
cuadrado. Solo los drones detectados entran en el cálculo de a qué dron
apuntar automáticamente. Un disparo ya en curso, en cambio, sigue afectando
físicamente a cualquier dron dentro de su cono/radio, esté detectado o no
— la detección gobierna la decisión de apuntado, no la física del pulso ya
emitido.

### 13. Negar el control sin dañar la electrónica

Además del arma que daña la electrónica, el sistema modela un **jammer**:
un emisor que satura con energía de radio la frecuencia que el operador
del dron usa para enviarle órdenes, de forma que el receptor del dron ya no
puede distinguir las órdenes reales entre esa energía de saturación. El
dron pierde el control mientras esté dentro de la zona de efecto del
jammer, y lo recupera apenas sale de esa zona o el jammer se apaga — no
sufre ningún daño físico ni electrónico permanente. Este mecanismo solo
funciona contra drones que reciben órdenes por señal de radio; un dron
conectado por un cable de fibra óptica no tiene ninguna señal de radio que
saturar, así que el jammer no tiene ningún efecto sobre él (en cambio, el
arma HPM sí lo afectaría, porque actúa sobre el cableado interno, no sobre
la señal de control).

### 14. El enjambre no es un conjunto de blancos fijos

Los drones del enjambre ajustan su rumbo en cada instante según tres
reglas, aplicadas sobre los drones vecinos dentro de cierto radio:
mantenerse separado de quienes están demasiado cerca, alinear su rumbo con
el rumbo promedio del grupo cercano, y dirigirse hacia el centro de
posición del grupo cercano. Además, si el conjunto del enjambre se aleja
demasiado del centro de su zona de formación original, una regla adicional
lo hace virar de vuelta hacia esa zona.

### 15. No todos los drones tienen la misma resistencia

Una parte de los drones del enjambre tiene mejor protección electrónica
(blindaje). Esto eleva su umbral efectivo de falla: necesitan un campo
eléctrico más intenso (más potencia del arma, o menor distancia) para
tener la misma probabilidad de falla que un dron sin blindaje.

### 16. Cómo se junta todo en un disparo

Cada disparo o detonación, para cada dron dentro del alcance geométrico
del arma (el cono o el radio), calcula en este orden: la distancia real en
tres dimensiones (no solo la distancia proyectada en el plano horizontal —
un dron a otra altitud está realmente más lejos), la densidad de potencia
según esa distancia (§5), el campo eléctrico resultante (§6), la
probabilidad de falla según ese campo y el blindaje del dron (§7, §15), y
finalmente un sorteo aleatorio con esa probabilidad exacta que decide si
el dron falla o no en ese impacto puntual.

### 17. Por qué el resultado no es siempre el mismo

El resultado de un disparo no es determinístico: la misma configuración de
disparo, repetida, puede no neutralizar siempre a los mismos drones,
porque el último paso (§16) es un sorteo aleatorio sobre una probabilidad,
no una regla de "sí" o "no" fija. Esto refleja que un arma real de este
tipo tampoco tiene un efecto idéntico disparo a disparo, porque cada dron
individual tiene variación real de fabricación y de exposición al campo.

---

## Guion resumido 

1. El arma emite energía electromagnética (microondas), no proyectiles —
   irradiada por una antena, física, real, direccional o no.
2. Esa energía se debilita con el cuadrado de la distancia (ecuación de
   Friis) y se traduce en un campo eléctrico sobre el dron.
3. Ese campo eléctrico induce corrientes dañinas en el cableado interno
   del dron — no lo destruye, lo deja sin control (soft-kill).
4. La probabilidad de que un dron en particular falle depende del campo
   eléctrico recibido y de su nivel de blindaje — se calcula, no se
   asume binario.
5. Hay dos armas: el cañón (no se consume, solo gasta electricidad — la
   respuesta realmente barata contra un enjambre) y el misil (se pierde
   por completo en cada uso, cientos de miles de dólares — no es la
   opción económica contra drones baratos). Además, un radar de detección
   previo al ataque y un jammer que niega el control sin dañar nada.
6. El enjambre se mueve solo, de forma reactiva, no como blancos fijos.
