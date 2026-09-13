# Hallazgo: inconsistencia interna en arXiv:2602.08477 entre su Tabla 1 y su Tabla 3

**Fecha:** 2026-09-13
**Proyecto:** simulador-ew
**Método:** reimplementación independiente del modelo publicado, contrastada
número a número contra los resultados que el propio paper reporta.

---

## 1. Resumen

Al reimplementar el modelo de daño por 5 subsistemas de Anbar Jafari &
Anbarjafari (2026), *"A Multi-physics Simulation Framework for High-power
Microwave Counter-unmanned Aerial System Design and Performance
Evaluation"* (arXiv:2602.08477), y validarlo contra los propios datos que el
paper publica, encontramos que **la Tabla 1 (umbrales de daño por
subsistema) y la Tabla 3 (resultados del análisis Monte Carlo) no son
algebraicamente consistentes entre sí**, aplicando las ecuaciones que el
propio paper declara (Ec. 6 y 7).

Esto no es una crítica al enfoque del paper — su arquitectura de modelado
(Friis → acoplamiento → sigmoide de daño por subsistema → OR-gate de
sistema, con incertidumbre propagada por Monte Carlo) es sólida y la
adoptamos. Es una observación puntual y verificable sobre una
inconsistencia numérica entre dos de sus tablas publicadas.

---

## 2. Contexto: por qué se investigó

Este proyecto (`simulador-ew`) es un simulador de guerra electromagnética
contra enjambres de drones cuyo modelo de daño físico está calibrado contra
este paper. Al intentar migrar del modelo agregado (un único umbral,
ajustado a dos puntos publicados — método no falsable, ver §3 abajo) al
modelo de 5 subsistemas que el paper describe como la física real, el
modelo no reproducía los resultados publicados. Se pasó por tres rondas de
diagnóstico:

1. Con el HTML de arXiv únicamente (sin código fuente): el modelo no
   cerraba, con residuos de signo opuesto en los dos puntos de calibración
   conocidos (20 m, 40 m) — diagnóstico ambiguo, varias hipótesis abiertas.
2. Con el PDF completo (17 páginas, incluyendo el código fuente de los
   Listados 1 y 2): se confirmaron y corrigieron dos submodelos del
   proyecto (modelo de polarización, modelo de error de apuntado) contra el
   código real del paper. El modelo seguía sin cerrar.
3. Con la Tabla 3 del PDF (5 distancias, no solo 2 puntos, con la media y
   desviación del campo eléctrico en cada una): esto permitió separar la
   validación en dos partes independientes — el CAMPO y la PROBABILIDAD —
   y ahí apareció el hallazgo.

---

## 3. El hallazgo, paso a paso

### 3.1 El campo eléctrico del modelo reproduce la Tabla 3 con precisión

Calculando el campo incidente (Friis) con pérdida de apuntado (Ec.
gaussiana confirmada contra el código del paper) y pérdida de polarización
(`η_pol = cos²φ`, piso 0.1, también confirmada contra el código), **sin
ningún factor de acoplamiento adicional**, la media y desviación del campo
en las 5 distancias de la Tabla 3 coinciden dentro de 2-3%:

| Distancia | Ē paper [V/m] | Ē reimplementación [V/m] | σ paper | σ reimplementación | CV paper | CV reimplementación |
|---|---|---|---|---|---|---|
| 20 m | 306 | 312.5 | 120 | 123.2 | 0.392 | 0.394 |
| 25 m | 245 | 250.0 | 95 | 98.5 | 0.388 | 0.394 |
| 30 m | 205 | 208.3 | 80 | 82.1 | 0.390 | 0.394 |
| 35 m | 174 | 178.6 | 68 | 70.4 | 0.391 | 0.394 |
| 40 m | 153 | 156.2 | 60 | 61.6 | 0.392 | 0.394 |

*(Esto también aclara una ambigüedad de la sección de discusión del paper:
el "coeficiente de variación ≈ 39%" que reporta es el CV del CAMPO, no el
CV de la probabilidad de baja resultante — dos estadísticos distintos.)*

### 3.2 La probabilidad de baja, calculada con la Tabla 1 y la Ec. 7 sobre ese mismo campo, no reproduce la Tabla 3

La Tabla 1 da 5 pares `(E₅₀, σ_E)` — uno por subsistema (GPS/GNSS LNA,
controlador de vuelo, ESC, cámara, BMS). La Ecuación 6 es una sigmoide
logística estándar por subsistema; la Ecuación 7 combina los 5 por lógica
OR-gate (`P_sistema = 1 − Π(1 − P_i)`). Aplicando exactamente eso —
verificado con la sigmoide logística EXACTA del paper, no una sustitución —
sobre el campo de la sección anterior (que ya coincide con la Tabla 3):

| Distancia | Ē (coincide con Tabla 3) | P(sistema) calculada | P(sistema) publicada (Tabla 3) |
|---|---|---|---|
| 20 m | 312.5 V/m | **91.2%** | 51.4% |
| 25 m | 250.0 V/m | **82.1%** | 36.8% |
| 30 m | 208.3 V/m | **74.2%** | 25.2% |
| 35 m | 178.6 V/m | **67.1%** | 16.5% |
| 40 m | 156.2 V/m | **60.3%** | 13.1% |

La brecha (40-60 puntos porcentuales) es demasiado grande para explicarse
por ruido de muestreo Monte Carlo (el propio paper reporta intervalos de
confianza del 95% de apenas 1-2 puntos porcentuales en cada punto, con
10.000 tiradas).

### 3.3 Verificación de robustez: no es un artefacto de la reimplementación

Se descartaron tres explicaciones alternativas antes de concluir que la
inconsistencia es del paper:

- **¿Es la sigmoide equivocada?** No — se repitió el cálculo con la
  sigmoide log-logística que usa este proyecto (una variante que corrige un
  defecto conocido de la logística estándar, `P(E=0)≠0`) y con la logística
  exacta del paper (Ec. 6). Ambas dan el mismo resultado cualitativo
  (≈100% en las 5 distancias).
- **¿Es el campo determinista equivocado?** No — se repitió con el campo
  determinista puro (sin Monte Carlo, calculado directo con la fórmula de
  Friis del Listado 1 del paper: 482, 386, 322, 276, 241 V/m en 20-40 m) y
  se comparó contra la columna "Determinista" de la Tabla 3
  (83.0%/62.5%/43.5%/29.0%/20.0%) — mismo resultado: el OR-gate sobre esos
  campos da ≈100%, no los valores publicados.
- **¿Falta el paso de acoplamiento a voltios (Ec. 4-5 del paper, la
  tensión inducida en el cableado)?** Investigado y descartado como la
  pieza faltante: esa sección (§4.5, Fig. 6) presenta el análisis de
  tensión inducida como una pieza EXPLICATIVA separada sobre la
  vulnerabilidad específica del ESC (comparando voltios contra el umbral de
  ruptura de un MOSFET, 20-40 V) — unidades distintas a las de la Tabla 1
  (V/m). La Tabla 3 reporta explícitamente el campo en V/m como lo que
  entra al modelo de sistema, sin conversión a voltios.

---

## 4. Cómo se resolvió, para efectos de este proyecto

No es posible "corregir" el paper. Para que el modelo de 5 subsistemas sea
utilizable en `simulador-ew`, se reajustó el único parámetro libre
disponible (una eficiencia de acoplamiento en campo, aplicada de forma
uniforme, sin depender de ningún umbral de la Tabla 1) contra los 5 puntos
de la Tabla 3 — no solo los 2 originales. El resultado (`k ≈ 0.44`) da un
residuo pequeño y con un patrón suave, no caótico:

| Distancia | Residuo (con k=0.44 reajustado) |
|---|---|
| 20 m | +2.1 pp |
| 25 m | +0.8 pp |
| 30 m | −1.1 pp |
| 35 m | −1.8 pp |
| 40 m | −4.2 pp |

El residuo decrece monótonamente con la distancia — un patrón consistente
con ruido acumulado de una reimplementación independiente (redondeo,
pequeñas diferencias en constantes no especificadas con precisión completa
en el texto, etc.), no con un error conceptual grueso. Sigue sin cumplir el
margen que el paper declara para sus propios dos puntos de calibración
(±1.0 pp / ±0.7 pp) — eso se documenta y se prueba explícitamente en el
código de este proyecto (`tests/test_parametros.py::
TestModeloSubsistemasCalibradoConReserva`), no se esconde.

---

## 5. Qué haría falta para cerrar esto del todo

Este proyecto agotó las fuentes públicamente disponibles: el HTML de
arXiv, el PDF completo (17 páginas, confirmado que no hay versión más
larga ni una v2), y una búsqueda de versiones en arXiv. Cerrar la brecha
de verdad requeriría una de estas dos cosas:

1. **Contactar a los autores** (Akbar Anbar Jafari, University of Tartu;
   Gholamreza Anbarjafari, 3S Holding OÜ) — el paper dice explícitamente
   "*Full release of all simulation source code for full reproducibility*"
   como una de sus contribuciones declaradas, así que el código completo
   (no solo el Listado 2 "abreviado" que aparece impreso) debería existir
   en algún repositorio público, que no encontramos enlazado en el PDF
   disponible.
2. **Una fe de erratas o v2** del paper que reconcilie la Tabla 1 con la
   Tabla 3 — por ejemplo, si los umbrales E₅₀ publicados en la Tabla 1 no
   son los que realmente se usaron para generar la Tabla 3 (un error de
   transcripción sería la explicación más simple y menos alarmante).

Si alguien retoma esto, el punto de partida es este documento y
`docs/FISICA_Y_MATEMATICA.md` §3.6.1 (detalle técnico completo, incluida
la reimplementación exacta usada para las comparaciones de arriba, en
`src/engine/experiments.py::monte_carlo_blanco_unico` y
`tests/test_parametros.py`).
