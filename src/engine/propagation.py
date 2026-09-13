"""Propagación sobre tierra y patrón de antena real (P2-C).

QUÉ SUSTITUYE
=============
Este módulo reemplaza al ítem cortado P3-08 (solver FDTD 2D de campo cercano).
Ese ítem iba a corregir el régimen ``r < 2D²/λ``, que con ``D = 0.6 m`` y
2.45 GHz son **5.9 m** — y el campo del simulador es de 1000×1000 m con el
enjambre a 500–900 m, así que corregía un régimen inalcanzable (ver
docs/AUDITORIA_CHECKLIST.md §3.5).

Dos efectos que **sí** operan en el rango donde el simulador vive:

1. **Reflexión en tierra (dos rayos).** El emisor está a ``HPM_ORIGIN_Z = 8 m``
   y los drones a 40–160 m: hay un rayo directo y uno reflejado en el suelo, y
   su interferencia modula el campo entre −16 dB y +6 dB.
2. **Patrón de antena real (Airy) en vez del taper ``cos²``.** El motor aplicaba
   ``cos²`` sobre la densidad de potencia, que no es el patrón de ninguna antena
   — no tiene lóbulos laterales, y su forma no depende del diámetro ni de la
   frecuencia.

⚠ HALLAZGO QUE CAMBIÓ EL DISEÑO DE ESTE MÓDULO
==============================================
La justificación original del ítem decía que la reflexión en tierra
*"convierte la altitud en variable táctica: un enjambre puede volar en un nulo
de interferencia"*. **Eso es falso a 2.45 GHz**, y conviene decirlo antes de que
alguien construya una conclusión encima.

La separación entre franjas de interferencia en altitud es
``Δh ≈ λ·r/(2·h_tx)``:

| Rango | Separación entre nulos | Ciclos en la banda 40–160 m |
|---|---|---|
| 100 m | **0.76 m** | 157 |
| 300 m | **2.29 m** | 52 |
| 700 m | **5.35 m** | 22 |

Un dron oscila ±4 m (``DRONE_BOB_AMPLITUDE_M``) y el espaciado del enjambre es
de 30 m: **cruza varias franjas por oscilación**. No se puede "estacionar" un
dron en un nulo de 0.76 m de ancho. El patrón existe, pero no es explotable ni
controlable a esta frecuencia.

Consecuencia de modelado, que es lo que este módulo implementa:

- El uso correcto del efecto es **estadístico**, no determinista. Promediado
  sobre las franjas, ``⟨|F|²⟩ = 2`` exactamente, o sea **+3.01 dB** — el modelo
  de espacio libre **subestima** la potencia media recibida sobre tierra en
  3 dB. Verificado numéricamente a 0.1/0.5/2.45 GHz y a 100/300/700 m: sale
  3.0 dB en todos los casos.
- La dispersión que introduce (p5–p95: −16 a +6 dB) es **varianza real**, y P2-A
  demostró que la varianza domina las conclusiones de este modelo. Entra como
  tal.
- La altitud **sí** sería variable táctica a frecuencias bajas: la franja a
  700 m mide 13 m a 1 GHz, 26 m a 0.5 GHz y 131 m a 0.1 GHz. Como
  ``HPM_FREQUENCY_GHZ`` es un parámetro barrible, el modelo determinista se
  conserva y es el correcto en ese régimen — pero el criterio de
  resolubilidad hay que consultarlo (``franja_resoluble``), no asumirlo.

AMBOS EFECTOS SON OPT-IN
========================
``PROPAGATION_GROUND_REFLECTION`` y ``PROPAGATION_ANTENNA_PATTERN`` vienen
desactivados/en ``cos2`` por defecto. Motivo: los dos **mueven la calibración**
(la de docs/FISICA_Y_MATEMATICA.md §3.4 está hecha contra el paper, que modela
espacio libre sin tierra), y activarlos por defecto sería cambiar la
calibración de refilón. Mismo criterio que ``HPM_ANTENNA_MODEL`` en P1-B.
"""

from __future__ import annotations

import math

import numpy as np

from src import config as config_mod
from src.engine.radar_engine import SPEED_OF_LIGHT_M_S


# ═══════════════════════════════════════════════════════════════════════════
# Reflexión en tierra (modelo de dos rayos)
# ═══════════════════════════════════════════════════════════════════════════


def diferencia_de_camino_m(
    rango_horizontal_m: float, altura_tx_m: float, altura_rx_m: float
) -> float:
    """
    Diferencia de camino entre el rayo reflejado en tierra y el directo.

        d_dir = √(r² + (h_rx − h_tx)²)
        d_ref = √(r² + (h_rx + h_tx)²)      (imagen especular del emisor)
        Δ = d_ref − d_dir

    Geometría exacta, no la aproximación ``Δ ≈ 2·h_tx·h_rx/r``: a los rangos
    cortos de este simulador (decenas de metros, donde el arma es efectiva) la
    aproximación de rango lejano no vale.
    """
    r = max(float(rango_horizontal_m), 0.0)
    d_dir = math.hypot(r, altura_rx_m - altura_tx_m)
    d_ref = math.hypot(r, altura_rx_m + altura_tx_m)
    return d_ref - d_dir


def factor_dos_rayos(
    rango_horizontal_m: float,
    altura_rx_m: float,
    altura_tx_m: float | None = None,
    frequency_ghz: float | None = None,
    coeficiente_reflexion: float | None = None,
) -> float:
    """
    Factor de AMPLITUD de campo por interferencia de dos rayos:

        F = | 1 + Γ·exp(j·2π·Δ/λ) |

    ``Γ`` es el coeficiente de reflexión del suelo. Por defecto −1
    (``GROUND_REFLECTION_COEFF``): en incidencia rasante sobre un suelo
    conductor la reflexión invierte la fase, que es el caso límite estándar y
    el más desfavorable. Un suelo real con pérdidas da ``|Γ| < 1`` y atenúa
    tanto los máximos como los nulos.

    Rango del resultado: ``[0, 2]`` con Γ=−1. En potencia, ``F²`` ∈ [0, 4], o
    sea de −∞ a +6 dB. El +6 dB no viola conservación de energía: es
    redistribución angular — la energía que falta está en los nulos.

    ⚠ Ver la advertencia del docstring del módulo antes de interpretar un valor
    puntual: a 2.45 GHz las franjas miden menos de 5.4 m en altitud y no son
    resolubles a la escala del simulador. Usar ``franja_resoluble`` para saber
    si el valor determinista significa algo en la configuración actual.
    """
    h_tx = config_mod.HPM_ORIGIN_Z if altura_tx_m is None else altura_tx_m
    f_ghz = config_mod.HPM_FREQUENCY_GHZ if frequency_ghz is None else frequency_ghz
    gamma = (
        config_mod.GROUND_REFLECTION_COEFF
        if coeficiente_reflexion is None
        else coeficiente_reflexion
    )

    lam = SPEED_OF_LIGHT_M_S / (max(float(f_ghz), 1e-9) * 1e9)
    delta = diferencia_de_camino_m(rango_horizontal_m, h_tx, altura_rx_m)
    fase = 2.0 * math.pi * delta / lam
    return float(abs(1.0 + gamma * complex(math.cos(fase), math.sin(fase))))


FACTOR_DOS_RAYOS_MEDIO_POTENCIA = 2.0
"""``⟨|F|²⟩`` promediado sobre las franjas, con |Γ| = 1.

Resultado analítico: ``|1 + Γe^{jφ}|² = 1 + |Γ|² + 2|Γ|cos(φ + arg Γ)``, y el
término en coseno promedia a cero cuando la fase barre muchos ciclos. Con
|Γ| = 1 queda **exactamente 2**, o sea +3.01 dB.

Verificado numéricamente (20 001 alturas en 40–160 m) a 0.1, 0.5 y 2.45 GHz y a
100, 300 y 700 m: da 3.0 dB en los nueve casos.

Es el número que importa: **el modelo de espacio libre subestima la potencia
media recibida sobre tierra en 3 dB**, independientemente de la frecuencia y
del rango, mientras haya varias franjas dentro de la incertidumbre de posición.
"""


def separacion_franjas_m(
    rango_horizontal_m: float,
    altura_tx_m: float | None = None,
    frequency_ghz: float | None = None,
) -> float:
    """
    Separación en altitud entre nulos consecutivos: ``Δh ≈ λ·r/(2·h_tx)``.

    Sale de que ``Δ ≈ 2·h_tx·h_rx/r`` en rango lejano, así que la fase avanza
    ``2π`` cada vez que ``h_rx`` crece en ``λ·r/(2·h_tx)``.
    """
    h_tx = config_mod.HPM_ORIGIN_Z if altura_tx_m is None else altura_tx_m
    f_ghz = config_mod.HPM_FREQUENCY_GHZ if frequency_ghz is None else frequency_ghz
    lam = SPEED_OF_LIGHT_M_S / (max(float(f_ghz), 1e-9) * 1e9)
    return float(lam * max(float(rango_horizontal_m), 0.0) / (2.0 * max(h_tx, 1e-9)))


def franja_resoluble(
    rango_horizontal_m: float,
    incertidumbre_altitud_m: float | None = None,
    altura_tx_m: float | None = None,
    frequency_ghz: float | None = None,
) -> bool:
    """
    ¿Tiene sentido físico usar el factor de dos rayos de forma DETERMINISTA?

    Criterio: la separación entre franjas debe superar la incertidumbre de
    altitud del blanco. Si no, el valor puntual es en la práctica un sorteo de
    la distribución de franjas y hay que tratarlo como varianza, no como un
    lóbulo controlable.

    La incertidumbre por defecto es la amplitud de oscilación del dron
    (``DRONE_BOB_AMPLITUDE_M``, 4 m): un dron que oscila ±4 m no puede
    mantenerse en un nulo más estrecho que eso. A 2.45 GHz la franja mide
    0.76 m a 100 m y 5.35 m a 700 m, así que este criterio devuelve False en
    casi todo el campo — que es justamente el hallazgo documentado arriba.
    """
    incert = (
        config_mod.DRONE_BOB_AMPLITUDE_M
        if incertidumbre_altitud_m is None
        else incertidumbre_altitud_m
    )
    return separacion_franjas_m(rango_horizontal_m, altura_tx_m, frequency_ghz) > incert


# ═══════════════════════════════════════════════════════════════════════════
# Patrón de antena de apertura circular (Airy)
# ═══════════════════════════════════════════════════════════════════════════


def _bessel_j1(x: float) -> float:
    """Función de Bessel de primera especie, orden 1.

    Aproximación polinómica de Abramowitz & Stegun (§9.4), exacta a ~1e-7 —
    suficiente de sobra para un patrón de antena. Se implementa a mano porque
    ``scipy`` está en el venv pero **no** en ``requirements.txt``, así que el
    entorno no es reproducible desde él (docs/AUDITORIA_CHECKLIST.md §4.6).
    """
    ax = abs(x)
    if ax < 8.0:
        y = x * x
        num = x * (
            72362614232.0
            + y * (-7895059235.0 + y * (242396853.1 + y * (-2972611.439
                + y * (15704.48260 + y * (-30.16036606)))))
        )
        den = (
            144725228442.0
            + y * (2300535178.0 + y * (18583304.74 + y * (99447.43394
                + y * (376.9991397 + y))))
        )
        return num / den
    z = 8.0 / ax
    y = z * z
    xx = ax - 2.356194491
    p = (
        1.0
        + y * (0.183105e-2 + y * (-0.3516396496e-4
            + y * (0.2457520174e-5 + y * (-0.240337019e-6))))
    )
    q = (
        0.04687499995
        + y * (-0.2002690873e-3 + y * (0.8449199096e-5
            + y * (-0.88228987e-6 + y * 0.105787412e-6)))
    )
    resultado = math.sqrt(0.636619772 / ax) * (
        math.cos(xx) * p - z * math.sin(xx) * q
    )
    return resultado if x >= 0.0 else -resultado


def patron_apertura_circular(
    angulo_offset_deg: float,
    diametro_m: float | None = None,
    frequency_ghz: float | None = None,
) -> float:
    """
    Patrón de AMPLITUD de una apertura circular uniformemente iluminada
    (patrón de Airy) — **física establecida**, no aproximación:

        F(θ) = | 2·J₁(u) / u |,      u = π·D·sin θ / λ

    Es la transformada de Fourier de una apertura circular. Propiedades que el
    taper ``cos²`` del motor no tiene:

    - **Lóbulos laterales reales**: el primero a −17.6 dB en potencia. El
      ``cos²`` decae monótonamente a cero en el borde del cono, así que dice
      que fuera del haz no llega **nada** — y sí llega: un enjambre justo fuera
      del haz nominal recibe del orden del 2 % de la potencia del eje, no 0.
    - **Depende de D y λ**: el ancho del haz sale de la física de la apertura,
      no de un parámetro de configuración independiente.
    - **Nulos en posiciones fijas** (los ceros de J₁), no un decaimiento suave.

    Nota de modelado: una apertura uniformemente iluminada es el caso ideal. Un
    plato real con taper de alimentador tiene lóbulos laterales más bajos
    (−25 dB o menos) y un haz algo más ancho. Airy es el límite "peor caso en
    lóbulos laterales" y el textbook estándar; se declara como tal.
    """
    d = config_mod.HPM_DISH_DIAMETER_M if diametro_m is None else diametro_m
    f_ghz = config_mod.HPM_FREQUENCY_GHZ if frequency_ghz is None else frequency_ghz
    lam = SPEED_OF_LIGHT_M_S / (max(float(f_ghz), 1e-9) * 1e9)

    seno = math.sin(math.radians(abs(float(angulo_offset_deg))))
    u = math.pi * max(float(d), 1e-9) * seno / lam
    if abs(u) < 1e-9:
        return 1.0
    return float(abs(2.0 * _bessel_j1(u) / u))


def patron_cos2(angulo_offset_deg: float, apertura_cono_deg: float) -> float:
    """
    Taper de AMPLITUD equivalente al que aplica el motor hoy.

    ``friis_diagnostics`` aplica ``cos²(normalizado·π/2)`` a la **densidad de
    potencia**, así que en amplitud de campo el taper es ``cos¹`` — la raíz. Se
    replica exactamente eso acá para que la comparación entre patrones sea
    honesta y para tener el modelo viejo disponible como control.

    No es el patrón de ninguna antena real: no tiene lóbulos laterales y su
    forma no depende de ``D`` ni de ``λ``. Se conserva porque la calibración de
    §3.4 se hizo con él.
    """
    semi = float(apertura_cono_deg) / 2.0
    if semi <= 0:
        return 1.0
    if abs(angulo_offset_deg) >= semi:
        return 0.0
    normalizado = abs(float(angulo_offset_deg)) / semi
    return float(math.cos(normalizado * (math.pi / 2.0)))


def factor_patron_antena(
    angulo_offset_deg: float,
    apertura_cono_deg: float,
    modelo: str | None = None,
    diametro_m: float | None = None,
    frequency_ghz: float | None = None,
) -> float:
    """Factor de amplitud por patrón de antena, según ``PROPAGATION_ANTENNA_PATTERN``."""
    m = config_mod.PROPAGATION_ANTENNA_PATTERN if modelo is None else modelo
    if m == "cos2":
        return patron_cos2(angulo_offset_deg, apertura_cono_deg)
    if m == "airy":
        return patron_apertura_circular(angulo_offset_deg, diametro_m, frequency_ghz)
    raise ValueError(
        f"PROPAGATION_ANTENNA_PATTERN debe ser 'cos2' o 'airy', no {m!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Informe
# ═══════════════════════════════════════════════════════════════════════════


def informe_propagacion(
    rango_horizontal_m: float = 300.0,
    altura_rx_m: float = 100.0,
    altitud_min_m: float | None = None,
    altitud_max_m: float | None = None,
    muestras: int = 4001,
) -> dict:
    """
    Diagnóstico de propagación en una geometría concreta.

    ``estadistica_en_banda`` es la parte que hay que leer: el factor de dos
    rayos promediado y sus percentiles sobre toda la banda de altitud de los
    drones. Es la forma **correcta** de usar el efecto a 2.45 GHz, donde el
    valor puntual no es resoluble (ver ``franja_resoluble``).
    """
    h_min = config_mod.DRONE_ALTITUD_MIN if altitud_min_m is None else altitud_min_m
    h_max = config_mod.DRONE_ALTITUD_MAX if altitud_max_m is None else altitud_max_m

    alturas = np.linspace(h_min, h_max, muestras)
    factores = np.array(
        [factor_dos_rayos(rango_horizontal_m, float(h)) for h in alturas]
    )
    potencias = factores**2

    def a_db(x: float) -> float:
        return float(10.0 * math.log10(x)) if x > 1e-12 else -99.0

    p5, p50, p95 = (float(v) for v in np.percentile(potencias, [5, 50, 95]))
    franja = separacion_franjas_m(rango_horizontal_m)

    return {
        "rango_horizontal_m": float(rango_horizontal_m),
        "altura_tx_m": float(config_mod.HPM_ORIGIN_Z),
        "frecuencia_ghz": float(config_mod.HPM_FREQUENCY_GHZ),
        "puntual": {
            "altura_rx_m": float(altura_rx_m),
            "diferencia_camino_m": round(
                diferencia_de_camino_m(
                    rango_horizontal_m, config_mod.HPM_ORIGIN_Z, altura_rx_m
                ), 6
            ),
            "factor_amplitud": round(
                factor_dos_rayos(rango_horizontal_m, altura_rx_m), 6
            ),
            "ganancia_db": round(
                a_db(factor_dos_rayos(rango_horizontal_m, altura_rx_m) ** 2), 3
            ),
        },
        "franjas": {
            "separacion_altitud_m": round(franja, 4),
            "ciclos_en_banda": round((h_max - h_min) / franja, 2) if franja > 0 else None,
            "resoluble": franja_resoluble(rango_horizontal_m),
            "incertidumbre_altitud_m": float(config_mod.DRONE_BOB_AMPLITUDE_M),
        },
        "estadistica_en_banda": {
            "banda_altitud_m": [float(h_min), float(h_max)],
            "media_potencia_db": round(a_db(float(potencias.mean())), 3),
            "media_potencia_teorica_db": round(
                a_db(FACTOR_DOS_RAYOS_MEDIO_POTENCIA), 3
            ),
            "p5_db": round(a_db(p5), 2),
            "p50_db": round(a_db(p50), 2),
            "p95_db": round(a_db(p95), 2),
        },
        "patron_antena": {
            "modelo_activo": config_mod.PROPAGATION_ANTENNA_PATTERN,
            "primer_lobulo_lateral_db": round(
                a_db(patron_apertura_circular(_ANGULO_PRIMER_LOBULO_DEG) ** 2), 2
            ),
        },
    }


# Ángulo del primer lóbulo lateral de un patrón de Airy: u ≈ 5.136 (primer
# máximo de |2J₁(u)/u| tras el lóbulo principal). Se resuelve al importar para
# la geometría por defecto y se usa solo en el informe.
def _angulo_primer_lobulo_deg() -> float:
    u_objetivo = 5.136
    lam = SPEED_OF_LIGHT_M_S / (config_mod.HPM_FREQUENCY_GHZ * 1e9)
    seno = u_objetivo * lam / (math.pi * config_mod.HPM_DISH_DIAMETER_M)
    return math.degrees(math.asin(min(1.0, seno)))


_ANGULO_PRIMER_LOBULO_DEG = _angulo_primer_lobulo_deg()
