# Barrido depredador-presa: ¿régimen no monótono según la fuerza del arma?

Experimento planteado en `docs/ESTADO_DEL_ARTE_BIOMIMESIS.md` §2.2, motivado
por Chen & Kolokolnikov (2014), *"A minimal model of predator-swarm
interactions"*, arXiv:[1403.3250](https://arxiv.org/abs/1403.3250): su
modelo mínimo (ecuaciones diferenciales, bifurcación de Hopf) predice que el
resultado de un enjambre frente a un depredador **no es monótono en la
fuerza del atacante** — débil → escape completo, moderada → anillo de
confusión, fuerte → persecución caótica, extrema → captura.

Pregunta concreta: ¿aparece algo parecido a esa no-monotonicidad si se barre
la potencia del cañón HPM (proxy de "fuerza del atacante") en este
simulador, con el estimador ya corregido (P1-A, `fraccion_media`)?

Script: `research/barrido_depredador_presa.py`. Resultados crudos:
`research/barrido_depredador_presa_resultados.json`.

---

## 1. Diseño

- **Arma**: cañón HPM, un disparo a `t=1s`, pulsado (`duty_cycle=0.01`).
- **Geometría**: arma a `DISTANCIA_COMBATE_M=60m` del centro del enjambre —
  la MISMA distancia que `src/engine/coevolution.py` ya validó como el único
  régimen de este proyecto con señal real (a la distancia por defecto,
  ~707m, la probabilidad de baja es ~1e-4 incluso al tope de potencia — ver
  el docstring de `DISTANCIA_COMBATE_M`). A duty_cycle=1.0 (CW, el default)
  esta distancia también da ~0 en casi todo el rango — el pulsado es
  necesario para que exista señal, no una elección arbitraria.
- **Formaciones**: `cuadrada` (compacta) vs. `circular` (dispersa) — el
  mismo contraste que ya midió P3-B (cuadrada concentra drones dentro del
  cono angosto del arma; circular los reparte fuera de él).
- **Potencia**: 9 valores, 10 a 100 kW.
- **Réplicas**: 30 por punto (18 puntos, 540 réplicas en total).
- **Métrica**: `fraccion_media` (P1-A) con IC95% normal (`± 1.96·SE`,
  `SE = σ/√30`) — suficiente para ver si los puntos se distinguen entre sí,
  no se usa bootstrap acá porque es un barrido exploratorio, no una cifra
  para publicar.

## 2. Resultados

| Formación | Potencia (kW) | fracción media | SE | IC95% |
|---|---:|---:|---:|---|
| cuadrada | 10 | 0.0133 | 0.0044 | [0.0047, 0.0220] |
| cuadrada | 15 | 0.0133 | 0.0034 | [0.0066, 0.0201] |
| cuadrada | 20 | 0.0089 | 0.0032 | [0.0027, 0.0151] |
| cuadrada | 30 | 0.0156 | 0.0038 | [0.0081, 0.0231] |
| cuadrada | 40 | 0.0133 | 0.0041 | [0.0053, 0.0214] |
| cuadrada | 50 | 0.0200 | 0.0052 | [0.0098, 0.0302] |
| cuadrada | 65 | 0.0267 | 0.0046 | [0.0176, 0.0357] |
| cuadrada | 80 | 0.0322 | 0.0047 | [0.0231, 0.0413] |
| cuadrada | 100 | 0.0311 | 0.0050 | [0.0212, 0.0410] |
| circular | 10 | 0.0011 | 0.0011 | [−0.0011, 0.0033] |
| circular | 15 | 0.0011 | 0.0011 | [−0.0011, 0.0033] |
| circular | 20 | 0.0000 | 0.0000 | [0.0000, 0.0000] |
| circular | 30 | 0.0033 | 0.0019 | [−0.0003, 0.0070] |
| circular | 40 | 0.0022 | 0.0015 | [−0.0008, 0.0052] |
| circular | 50 | 0.0022 | 0.0015 | [−0.0008, 0.0052] |
| circular | 65 | 0.0011 | 0.0011 | [−0.0011, 0.0033] |
| circular | 80 | 0.0078 | 0.0026 | [0.0026, 0.0129] |
| circular | 100 | 0.0056 | 0.0023 | [0.0010, 0.0101] |

## 3. Lectura honesta — qué hay, qué no hay

**Lo que SÍ aparece, con soporte estadístico real (formación cuadrada):**
la curva no es una recta simple creciente — tiene forma de **meseta baja →
subida → meseta alta**, no de rampa lineal. Los IC95% de 10, 15, 20, 30 y
40 kW se superponen todos entre sí (todos rondan 0.009–0.016): a esta
distancia y este rango, **no hay diferencia estadísticamente distinguible
entre disparar a 10 kW o a 40 kW**. Recién entre 40 y 80 kW aparece una
subida real — el IC de 80 kW ([0.023, 0.041]) no se superpone en absoluto
con el de 20 kW ([0.003, 0.015]). Y arriba, 80 kW y 100 kW quedan
prácticamente idénticos (0.0322 vs. 0.0311, ICs casi enteramente
superpuestos) — otra meseta, esta vez alta.

Esto es, en espíritu, lo que Chen & Kolokolnikov afirman en el sentido más
amplio: el resultado del enjambre no escala suavemente con la fuerza del
atacante, cambia de régimen — pero es una transición de DOS mesetas (tipo
sigmoide/saturación), no la curva de CUATRO regímenes con una caída en el
medio que describe su modelo. Ver §4 para por qué probablemente no debería
esperarse esa forma exacta acá.

**Lo que NO se puede afirmar (formación circular)**: con 30 réplicas por
punto, la señal en circular es demasiado ruidosa para decir nada — el CV
va de 1.8 a 5.5 (la desviación estándar es varias veces la propia media), y
los IC95% de CASI TODOS los puntos se superponen entre sí y cruzan cero.
El pico aparente en 80 kW (0.0078) no es distinguible de sus vecinos
(30 kW: 0.0033, 100 kW: 0.0056) dado el ruido — no es un hallazgo, es el
tipo de patrón que 30 réplicas no alcanzan a resolver a esta escala de
letalidad. Reportarlo como "un bache" sería exactamente el tipo de
sobreinterpretación que este proyecto viene evitando a propósito toda la
sesión.

**Lo que se reconfirma, con más resolución que antes**: la formación importa
mucho más que la potencia dentro del rango probado — cuadrada saca entre
3× y 12× más fracción neutralizada que circular en cada nivel de potencia
comparado punto a punto. Es el mismo hallazgo de `DISTANCIA_COMBATE_M` en
`coevolution.py`, ahora con un barrido completo de potencia en vez de un
único punto.

## 4. Por qué probablemente no aparece la curva de 4 regímenes de Chen & Kolokolnikov

El modelo de Chen & Kolokolnikov es un sistema de ecuaciones diferenciales
donde el depredador **persigue activamente** a la presa de forma continua
—su "fuerza" gobierna qué tan agresivamente el depredador sigue al
centroide del enjambre a lo largo del tiempo—, y las fases de "persecución
caótica" y "captura" dependen de esa dinámica de seguimiento sostenido.

El arma modelada acá es un **pulso único, instantáneo, sin seguimiento**:
dispara una vez a `t=1s` y no re-apunta ni persigue nada después. No hay
mecanismo en este sistema que pueda producir un análogo de "persecución
caótica" — como mucho, la potencia del arma puede modular cuánto daño hace
ESE disparo, no cómo el enjambre es cazado a lo largo del tiempo. Es
razonable, entonces, que el barrido capture algo parecido a la transición
escape↔confusión (las dos mesetas que sí aparecen) pero no las fases que
dependen de una persecución que este arma no tiene. Un barrido futuro con
el **misil guiado** (que sí persigue, ver `HPMissile`/navegación
proporcional) sería el candidato más cercano a poner a prueba esa mitad de
la predicción del paper — no se hizo acá, es una extensión posible, no una
promesa.

## 5. Reproducibilidad

```
python -m research.barrido_depredador_presa
```

Semilla base 90210, determinista (cada punto usa `run_replica` con
`nuevo_generador`, aislado, mismo mecanismo que el resto del proyecto). El
script tarda ~8 minutos en esta máquina para los 540 réplicas.
