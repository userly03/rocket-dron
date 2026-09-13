# Parámetros de referencia · arXiv:2602.08477

> **Procedencia:** originalmente extraídos del HTML de arXiv
> (`https://arxiv.org/html/2602.08477`) mediante **dos fetches independientes con
> prompts distintos**, que coincidieron exactamente en los cinco bloques de abajo.
>
> **2026-09-13 — actualización:** el usuario consiguió y se leyó el PDF real
> (`2602.08477v1.pdf`, descargado de arXiv). **Confirma exactamente las Tablas 1 y 2
> de abajo** (coinciden número a número con la extracción del HTML) y trae algo que
> el HTML no dio nunca: el código fuente del modelo determinista y del núcleo Monte
> Carlo (ver `docs/FISICA_Y_MATEMATICA.md` §3.6.1 para el detalle). **Pero el archivo
> disponible tiene solo 6 páginas** — el listado de arXiv indica 17 páginas y 15
> figuras (ver más abajo), y el contenido corta a mitad de la §4.2, antes de
> Resultados completos (§4.3+), Discusión (§5), Conclusión (§6) y bibliografía. La
> cita de "CV≈39% a 30m" de la sección 2 de abajo sigue viniendo solo del HTML — no
> se pudo confirmar contra el texto del PDF porque esa sección no está en las 6
> páginas disponibles.
>
> Paper: Akbar Anbar Jafari & Gholamreza Anbarjafari (feb-2026), *"A Multi-physics
> Simulation Framework for High-power Microwave Counter-unmanned Aerial System Design
> and Performance Evaluation"*. 17 páginas, 15 figuras (según el listado de arXiv;
> el PDF descargado solo tiene 6). Enviado a *Journal of Defence Technology*. Sistema
> modelado: HPM C-UAS a 2.45 GHz.
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

**2026-09-13 — matiz importante tras leer el PDF:** las ecuaciones de abajo (4-5 del
paper) SÍ aparecen en el texto (página 3 del PDF, confirmadas), pero el código fuente
mostrado (Listados 1-2 — el modelo determinista y el núcleo del Monte Carlo, este
último "abreviado" según el propio paper) **no las usa**: compara el campo incidente
de Friis (con pérdidas de apuntado y polarización) DIRECTAMENTE contra los umbrales
E₅₀ de la Tabla 1, sin ningún paso de tensión inducida. Puede que el listado
abreviado simplemente no muestre ese paso (es la hipótesis más probable — probado
tomando el pipeline mostrado literalmente y sobrestima fuerte, +40pp a 20m, ver
`docs/FISICA_Y_MATEMATICA.md` §3.6.1), o puede que estas ecuaciones sean motivación
teórica sin un camino directo al resultado publicado. Sigue sin poder confirmarse
del todo con lo disponible.

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
