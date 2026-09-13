# Parámetros de referencia · arXiv:2602.08477

> **Procedencia:** originalmente extraídos del HTML de arXiv
> (`https://arxiv.org/html/2602.08477`) mediante **dos fetches independientes con
> prompts distintos**, que coincidieron exactamente en los cinco bloques de abajo.
>
> **2026-09-13 — el usuario consiguió y se leyó el PDF completo** (17 páginas —
> `2602.08477v1.pdf`, descargado de arXiv). **Corrección de una lectura previa en
> esta misma sesión**: un primer intento de leer el PDF usó el comando `file` para
> chequear el número de páginas, que reportó "6 page(s)" — poco confiable para PDF
> 1.7 con streams de objetos comprimidos (formato común en salidas de `pikepdf`,
> como esta). Verificado con `pdfinfo` (poppler, la herramienta correcta): el
> archivo tiene **17 páginas completas**, coincidiendo con el campo "Comments" de
> arXiv ("17 pages, 15 figures") y con la Sección 6 "Conclusions" y la bibliografía
> presentes. No hace falta buscar una v2 — el PDF disponible ya está completo.
>
> **Confirma exactamente las Tablas 1 y 2 de abajo** (coinciden número a número con
> la extracción del HTML) y trae el código fuente del modelo determinista y del
> núcleo Monte Carlo, más — crucial, en las páginas 7-9 — la **Tabla 3** con los
> resultados Monte Carlo completos en 5 distancias (20-40 m), incluida la media y
> desviación del CAMPO ELÉCTRICO en cada una. Esto resuelve una ambigüedad
> importante: **el "CV≈39% a 30m" citado más abajo es el CV del CAMPO E (V/m), no
> de la probabilidad de baja** — dos estadísticos distintos que se habían estado
> confundiendo. Ver `docs/FISICA_Y_MATEMATICA.md` §3.6.1 para el detalle completo
> de la validación (el campo del simulador reproduce la Tabla 3 casi exactamente:
> CV=0.394 en las 5 distancias contra ≈0.39 del paper).
>
> Paper: Akbar Anbar Jafari & Gholamreza Anbarjafari (feb-2026), *"A Multi-physics
> Simulation Framework for High-power Microwave Counter-unmanned Aerial System Design
> and Performance Evaluation"*. 17 páginas, 15 figuras. Enviado a *Journal of Defence
> Technology*. Sistema modelado: HPM C-UAS a 2.45 GHz.
>
> Este archivo existe para que las fases P1-B, P1-C y P1-E no tengan que re-derivar
> nada. Cada número que el simulador tome de acá debe citar esta referencia.

---

## 1. Umbrales de daño por subsistema (Tabla 1 del paper)

El paper **no usa un umbral agregado único**. Modela cinco subsistemas con sigmoides
independientes:

```
P_kill,i(|E|) = 1 / (1 + exp(-(|E| - E₅₀,i) / σ_E,i))
```

| Subsistema | `E₅₀` [V/m] | `σ_E` [V/m] |
|---|---|---|
| GPS/GNSS LNA | 150 | 30 |
| Flight controller | 250 | 50 |
| ESC (gate oxide) | 300 | 60 |
| Camera (CMOS) | 200 | 40 |
| BMS MOSFET | 350 | 70 |

**Contraste con el simulador:** hoy `HPM_E_THRESHOLD_V_M = 500` y
`HPM_SIGMOID_STEEPNESS = 0.0075` (→ `σ_E ≈ 133 V/m`). El umbral es **más alto que los
cinco** y la pendiente **2–4× más ancha** que cualquiera de ellas. Ver
[`AUDITORIA_CHECKLIST.md`](AUDITORIA_CHECKLIST.md) §1.3 para por qué pasó.

## 2. Combinación a probabilidad de baja del sistema (ecuación 7)

Lógica **OR-gate** (eslabón más débil): el dron cae si cae cualquier subsistema.

```
P_system(|E|) = 1 − Π_{i=1}^{N} [1 − P_kill,i(|E|)]
```

Supervivencia del sistema = producto de supervivencias individuales.

**Consecuencia de diseño para P1-C:** el subsistema dominante a campo bajo es el
GPS/GNSS LNA (`E₅₀ = 150 V/m`), no el promedio. Un umbral agregado único **no puede**
reproducir la forma de la curva de un OR-gate de cinco sigmoides con umbrales y anchos
distintos — de ahí que ajustar uno solo a dos puntos absorba el sesgo en vez de
reproducir el modelo.

## 3. Distribuciones del Monte Carlo (Tabla 2 del paper)

10.000 tiradas. Ocho fuentes de variabilidad:

| Parámetro | Distribución | En el simulador hoy |
|---|---|---|
| Potencia TX | `Normal(μ=25 kW, σ=1.25 kW)` | constante |
| Diámetro del plato | `Normal(μ=0.60 m, σ=0.005 m)` | no existe |
| Eficiencia de apertura | `Uniform[0.50, 0.60]` | no existe |
| **Error de apuntado** | **`Rayleigh(σ=1.0°)`** | **no existe** |
| Ángulo de polarización | `Uniform[0, π]` | — |
| Longitud de cable | `Uniform[5, 25] cm` | `Uniform[2, 15] cm` |
| `E₅₀` por subsistema | `Normal(±15% del nominal)` | constante |
| `σ_E` por subsistema | `Normal(±15% del nominal)` | constante |

**Resultado de incertidumbre que reporta el paper:** las predicciones Monte Carlo son
*"systematically lower than deterministic"* en todo el rango, y **la polarización y la
orientación del cable dominan la incertidumbre (coeficiente de variación ≈ 39 % a
30 m)**.

Ese CV≈39 % @ 30 m es el criterio de aceptación de P1-B.

## 4. Acoplamiento al cableado (modelo de arnés no apantallado)

**2026-09-13 — actualizado con la §4.5 del paper (página 7 del PDF completo):** las
ecuaciones de abajo (4-5) sí se usan, pero como un análisis SEPARADO e ilustrativo, no
como parte del pipeline que genera la Tabla 3. La §4.5 (Fig. 6) grafica la tensión
inducida en el cableado en función de la longitud, para cuatro niveles de campo fijos
(100/200/300/500 V/m) — a 300 V/m, un cable de 6 cm induce ≈45 V, por encima del rango
típico de ruptura de compuerta MOSFET (20-40 V), lo que el paper usa para EXPLICAR por
qué el cableado del ESC en el rango λ/2 es la vía de acoplamiento más vulnerable
(consistente con Zhang et al. [37]). Es una pieza de análisis mecanístico — compara
VOLTIOS contra un umbral en voltios (ruptura MOSFET), un par de unidades distinto al
de la Tabla 1 (V/m contra E₅₀ en V/m).

La Tabla 3 (§8 de este documento), en cambio, reporta explícitamente el campo en
**V/m** (columna `Ē[V/m]`) como la cantidad que entra al modelo de 5 subsistemas — la
misma unidad que los umbrales E₅₀ de la Tabla 1, sin conversión a voltios. Confirmado
(`docs/FISICA_Y_MATEMATICA.md` §3.6.1): el simulador, calculando el campo incidente
SIN el paso de tensión inducida (solo Friis + pérdidas de apuntado + polarización),
reproduce esa columna `Ē[V/m]` casi exactamente. Conclusión: **la cadena de voltios
(Ec. 4-5) es un análisis paralelo sobre la vulnerabilidad del ESC en particular, NO el
paso que conecta el campo incidente con los umbrales E₅₀ de la Tabla 1** en el pipeline
que produce los números de sistema (Tabla 3) — corrige una hipótesis anterior de esta
misma sesión que especulaba lo contrario.

Tensión inducida, régimen de dipolo corto (`L < λ/2`):

```
V_ind = E_inc · L_eff · F(θ_wire) · √η_pol        con  L_eff = L/2
```

Realce por resonancia — **gaussiano en LONGITUD**, no lorentziano en frecuencia:

```
V_res = V_ind · [ 1 + (Q−1)·exp( −(L − λ₀/2)² / (2σ_L²) ) ]
```

| Parámetro | Valor (paper) | En el simulador hoy |
|---|---|---|
| `Q` | ≈ 10 | `HPM_COUPLING_Q = 5.0` |
| `σ_L` | 0.02 m | — (no aplica: lorentziana en f con ancho `f_res/Q`) |
| `λ₀/2` @ 2.45 GHz | 6.12 cm | — (usa `f_res = c/2L`) |
| `η_pol` | `cos²φ`, acotado ≥ 0.1 | `cos²φ`, acotado ≥ 0.1 (2026-09-13: corregido en `Drone` y `targeting.py`, antes `Uniform[0.3,1.0]`) |
| `L_eff` | `L/2` | **ausente** (no forma parte del pipeline real confirmado — ver nota de arriba) |

**Diferencias que quedaban por corregir en P1-C, estado actualizado:**
1. El realce es **gaussiano en `L`** alrededor de `λ₀/2`, no lorentziano en `f` alrededor
   de `c/2L`. Son parametrizaciones distintas del mismo fenómeno, pero con formas de cola
   distintas y `Q` distinto (10 vs 5). **Sigue sin implementarse** — se omitió a
   propósito: la varianza del modelo de subsistemas YA es excesiva (CV≈1.02 contra
   ≈0.39 del paper, ver FISICA_Y_MATEMATICA.md §3.6.1), agregar otra fuente de
   dispersión la empeoraría.
2. **Falta el factor `L_eff = L/2`** — mismo motivo: no está confirmado que forme
   parte del pipeline real, y agregarlo sin esa confirmación no es defendible.
3. ✅ **Corregido (2026-09-13):** la polarización ya usa `cos²(Uniform[0,π])` con
   piso 0.1 en el motor principal, no solo en `parametros.py` — ver hallazgo 14 de
   `docs/FISICA_Y_MATEMATICA.md`.

## 5. Alcance de 90 % de baja: CW vs pulsado

| Modo | Configuración | Alcance 90 % de baja |
|---|---|---|
| Continuo (CW) | 25 kW, plato de 60 cm | **≈ 18 m** |
| Pulsado | 500 kW pico, 1 % duty cycle | **≈ 88 m** |

A 1 % de duty el campo pico a 40 m *"exceeds 1,100 V/m — well above all damage
thresholds"*. El mecanismo que el paper invoca es ruptura por tensión en pulsos
individuales (*voltage-driven breakdown*).

**Estos dos números son el criterio de aceptación de P1-E**, en reemplazo del criterio
tautológico de v1 ("pulsado > CW", que no puede fallar por álgebra).

## 6. Lo que el paper NO hace

Relevante para no atribuirle cosas que no dice:

- **No incorpora escalado por duración de pulso** (nada de Wunsch-Bell, nada de
  `τ^(−1/2)`). Escala el campo pico con el duty cycle y nada más. El factor
  `g(τ) = min(√(τ/τ_ref), 3.0)` del simulador es **un añadido del proyecto**. P1-E le da
  procedencia real vía Wunsch-Bell (Wunsch & Bell, 1968, IEEE Trans. Nucl. Sci.), no vía
  este paper.
- **No modela el arma de área tipo misil.** `HPM_MISSILE_E_THRESHOLD_V_M = 30` no sale de
  acá: es una concesión de jugabilidad del simulador, ya documentada como tal en
  `FISICA_Y_MATEMATICA.md` §4. Con los umbrales reales de la Tabla 1 (150–350 V/m) el
  misil isotrópico es efectivamente inútil, que es el hallazgo 3 de esa auditoría.
- **No modela propagación sobre tierra** (dos rayos / multitrayecto). P2-C es una
  extensión del proyecto más allá del paper, no una corrección hacia él.
- **No modela radar de detección ni tracks.** Todo P2-G es extensión propia.

## 7. Puntos de calibración publicados

Baseline: 25 kW CW, plato de 60 cm (21.2 dBi), 2.45 GHz.

| Distancia | Campo E | Monte Carlo (10.000 tiradas) | Determinista |
|---|---|---|---|
| 20 m | 497.2 V/m | **51.4 % ± 1.0 %** | 83 % |
| 40 m | 248.6 V/m | **13.1 % ± 0.7 %** | 20 % |

**El determinista sobreestima por un factor ≈ 1.6.** Esto es la clave de §1.3 de la
auditoría: el simulador ajustó una sigmoide **determinista** a los puntos **Monte
Carlo**, metiendo ese factor 1.6 dentro del umbral. Con el modelo de 5 subsistemas más
las distribuciones de §3, los 51.4 % / 13.1 % deben **salir** del MC, no ajustarse.

## 8. Tabla 3 completa (2026-09-13, leída del PDF) — 5 puntos, no solo 2

La Tabla 3 del paper (página 9 del PDF) da los 5 puntos completos, con la media y
desviación del CAMPO además de la probabilidad — algo que el HTML nunca dio:

| Distancia | MC kill prob. | 95% CI | Determinista | Ē [V/m] (±1σ) |
|---|---|---|---|---|
| 20 m | 51.4% | [50.4, 52.3] | 83.0% | 306 ± 120 |
| 25 m | 36.8% | [35.9, 37.8] | 62.5% | 245 ± 95 |
| 30 m | 25.2% | [24.3, 26.0] | 43.5% | 205 ± 80 |
| 35 m | 16.5% | [15.8, 17.2] | 29.0% | 174 ± 68 |
| 40 m | 13.1% | [12.4, 13.8] | 20.0% | 153 ± 60 |

**Nota importante:** el `Ē` de esta tabla (media del campo Monte Carlo, con pérdidas de
apuntado y polarización ya aplicadas) es MENOR que el campo determinista "497.2 V/m"
de la tabla de §7 (que es el campo SIN esas pérdidas, calculado directo por Friis) — no
son la misma cantidad, aunque ambas tablas hablan de "20 m". Confirmado (2026-09-13,
ver `docs/FISICA_Y_MATEMATICA.md` §3.6.1) que el simulador reproduce esta columna `Ē`
casi exactamente en las 5 distancias (dentro de 2-3%), y que el `CV≈39%` citado en §3
de este documento es el CV de ESTA columna (`σ/Ē`, ≈0.39 en las 5 filas), no el CV de
la probabilidad de baja — una distinción que no era obvia solo con el HTML.

**El hallazgo más importante de leer el PDF completo**: aplicando el modelo de 5
subsistemas del propio paper (Tabla 1 de §1 + Ecuación 7 de §2) DIRECTAMENTE sobre el
campo `Ē` de esta tabla (que el simulador ya reproduce casi exacto), la probabilidad
sale ≈100% en las 5 distancias — no el 51.4%-13.1% que el paper reporta. La brecha es
de 40-80 puntos porcentuales, muchísimo más grande que cualquier atenuación de
acoplamiento razonable explicaría de forma directa. Detalle completo y la hipótesis más
plausible (un factor de acoplamiento adicional, no documentado explícitamente en el
texto, entre el campo incidente y lo que "ve" cada subsistema) en
`docs/FISICA_Y_MATEMATICA.md` §3.6.1.
