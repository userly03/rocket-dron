"""
Motor de radar de detección: ecuación de radar clásica + probabilidad de
detección aproximada por una sigmoide sobre la relación señal-ruido (SNR).

Complementa al motor HPM (que calcula si un pulso *daña* a un blanco ya
conocido): este módulo decide si el blanco *se conoce* en primer lugar —
antes de esta fase, el simulador tenía conocimiento omnisciente de la
posición exacta de cada dron; ahora hay que detectarlo primero.
"""

from __future__ import annotations

import numpy as np

from src.config import RADAR_SIGMOID_STEEPNESS, RADAR_SNR_THRESHOLD_DB

SPEED_OF_LIGHT_M_S = 299_792_458.0


def wavelength_m(frequency_ghz: float) -> float:
    """Longitud de onda: λ = c / f."""
    return SPEED_OF_LIGHT_M_S / (frequency_ghz * 1e9)


def radar_received_power_w(
    pt_w: float,
    gain_linear: float,
    wavelength_m_: float,
    rcs_m2: float,
    distancia_m: float,
) -> float:
    """
    Ecuación de radar (monoestático: misma antena transmite y recibe, de ahí G²):

        Pr = (Pt · G² · λ² · σ) / ((4π)³ · r⁴)

    `σ` (``rcs_m2``) es la sección transversal de radar del blanco — el
    "tamaño eléctrico" que ve el radar, no el tamaño físico real.
    """
    r = max(distancia_m, 1e-6)
    return (pt_w * gain_linear**2 * wavelength_m_**2 * rcs_m2) / ((4.0 * np.pi) ** 3 * r**4)


def detection_probability(
    pr_w: float,
    noise_floor_w: float,
    snr_threshold_db: float = RADAR_SNR_THRESHOLD_DB,
    steepness: float = RADAR_SIGMOID_STEEPNESS,
) -> float:
    """
    Probabilidad de detección aproximada mediante una sigmoide sobre la
    relación señal-ruido (SNR, en dB) respecto a un umbral de referencia.

    Simplificación deliberada: la teoría de detección de radar real usa la
    función Q de Marcum (curvas Pd/Pfa de modelos Swerling), bastante más
    compleja. Una sigmoide sobre el SNR en dB reproduce la misma forma
    cualitativa (transición suave alrededor de un SNR umbral) sin esa
    complejidad — mismo patrón de modelado que la sigmoide de daño HPM.
    Ver docs/FISICA_Y_MATEMATICA.md.
    """
    if pr_w <= 0 or noise_floor_w <= 0:
        return 0.0
    snr_db = 10.0 * np.log10(pr_w / noise_floor_w)
    probabilidad = 1.0 / (1.0 + np.exp(-steepness * (snr_db - snr_threshold_db)))
    return float(np.clip(probabilidad, 0.0, 1.0))


def evaluar_deteccion(
    distancia_m: float,
    pt_w: float,
    gain_dbi: float,
    frequency_ghz: float,
    rcs_m2: float,
    noise_floor_w: float,
) -> tuple[bool, float]:
    """
    Evalúa si un blanco a ``distancia_m`` queda detectado por el radar.

    Decisión determinística sobre la probabilidad (>=50%) en vez de un sorteo
    aleatorio por tick — evita parpadeo cuadro a cuadro del estado
    "detectado" cuando la probabilidad ronda el 50%; equivale a asumir que,
    una vez con SNR suficiente, el radar mantiene un track estable.

    Returns:
        Tupla ``(detectado, probabilidad)``.
    """
    gain_linear = 10.0 ** (gain_dbi / 10.0)
    wl = wavelength_m(frequency_ghz)
    pr = radar_received_power_w(pt_w, gain_linear, wl, rcs_m2, distancia_m)
    probabilidad = detection_probability(pr, noise_floor_w)
    return probabilidad >= 0.5, probabilidad
