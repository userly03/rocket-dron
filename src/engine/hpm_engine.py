"""
Motor HPM: dos modelos de probabilidad de neutralización.

- "legacy" (``calculate_neutralization_probability`` /
  ``calculate_area_neutralization_probability``): exponencial ad-hoc,
  P = 1 - exp(-k · potencia / distancia²), con atenuación angular en los
  bordes del cono. Nota de auditoría: una versión previa de este docstring
  atribuía esta fórmula a arXiv:2602.08477 — verificado (ver
  docs/FISICA_Y_MATEMATICA.md), esa atribución era incorrecta. El paper real
  usa un modelo sigmoide sobre densidad de potencia/campo E calibrado contra
  umbrales de latchup CMOS publicados, que es lo que sí implementa el modelo
  "friis" de abajo — no esta exponencial.

- "friis" (``calculate_neutralization_probability_friis`` /
  ``calculate_area_neutralization_probability_friis``): física real —
  densidad de potencia (ecuación de Friis) -> campo E (V/m) -> sigmoide
  sobre un umbral de susceptibilidad, calibrado contra los datos publicados
  en arXiv:2602.08477. Ver docs/FISICA_Y_MATEMATICA.md para el desarrollo
  completo y las fuentes.
"""

from __future__ import annotations

import numpy as np

from src.config import (
    HPM_E_THRESHOLD_V_M,
    HPM_K_CONSTANT,
    HPM_MISSILE_E_THRESHOLD_V_M,
    HPM_MISSILE_SIGMOID_STEEPNESS,
    HPM_SIGMOID_STEEPNESS,
)
from src.utils.helpers import angle_difference, distance, distance3d

VACUUM_IMPEDANCE_OHM = 377.0


def calculate_area_neutralization_probability(
    potencia: float,
    distancia: float,
    k: float = HPM_K_CONSTANT,
) -> float:
    """
    Probabilidad de neutralización por efecto HPM de área (misil CHAMP).

    P = 1 - exp(-k * potencia / distancia²)

    Sin atenuación angular — todos los blancos dentro del radio son evaluados.
    """
    if distancia <= 0:
        return 1.0
    intensidad = potencia / (distancia**2)
    return float(np.clip(1.0 - np.exp(-k * intensidad), 0.0, 1.0))


def calculate_neutralization_probability(
    potencia: float,
    distancia: float,
    angulo_offset: float,
    apertura_cono: float,
    k: float = HPM_K_CONSTANT,
) -> float:
    """
    Calcula la probabilidad de neutralización de un blanco.

    Args:
        potencia: Potencia del HPM en kW.
        distancia: Distancia al blanco en metros.
        angulo_offset: Desviación angular respecto al eje del cono (grados).
        apertura_cono: Apertura total del cono en grados.
        k: Constante del modelo exponencial.
    """
    if distancia <= 0:
        return 1.0

    half_cone = apertura_cono / 2.0
    if abs(angulo_offset) > half_cone:
        return 0.0

    intensidad = potencia / (distancia**2)
    probabilidad_base = 1.0 - np.exp(-k * intensidad)

    if half_cone > 0:
        normalized_offset = abs(angulo_offset) / half_cone
        factor_angular = np.cos(normalized_offset * (np.pi / 2.0)) ** 2
    else:
        factor_angular = 1.0

    return float(np.clip(probabilidad_base * factor_angular, 0.0, 1.0))


def antenna_gain_from_aperture(apertura_deg: float) -> float:
    """
    Ganancia aproximada de una antena direccional a partir de su apertura de
    haz (grados) — aproximación estándar de ingeniería de RF:

        G ≈ 26000 / (θ_az · θ_el)

    Se asume haz simétrico (θ_az = θ_el = apertura_cono), ya que el modelo
    solo tiene un ángulo de apertura configurado.
    """
    apertura = max(float(apertura_deg), 1.0)
    return 26000.0 / (apertura**2)


def power_density(potencia_w: float, ganancia: float, distancia_m: float) -> float:
    """
    Densidad de potencia en espacio libre (ecuación de Friis):

        S = (P · G) / (4π r²)   [W/m²]
    """
    r = max(float(distancia_m), 1e-6)
    return (potencia_w * ganancia) / (4.0 * np.pi * r**2)


def efield_from_power_density(densidad_w_m2: float) -> float:
    """
    Campo eléctrico E (V/m) a partir de la densidad de potencia, usando la
    impedancia del espacio libre (377 Ω):

        E = sqrt(S · 377)
    """
    return float(np.sqrt(max(float(densidad_w_m2), 0.0) * VACUUM_IMPEDANCE_OHM))


def friis_diagnostics(
    potencia_kw: float,
    distancia: float,
    apertura_cono: float = 360.0,
    angulo_offset: float = 0.0,
) -> dict:
    """Calcula ganancia, densidad de potencia y campo E para reporte/validación."""
    ganancia = antenna_gain_from_aperture(apertura_cono) if apertura_cono < 360 else 1.0
    potencia_w = potencia_kw * 1000.0
    densidad = power_density(potencia_w, ganancia, distancia)

    half_cone = apertura_cono / 2.0
    if 0 < apertura_cono < 360 and half_cone > 0:
        normalized_offset = min(abs(angulo_offset) / half_cone, 1.0)
        densidad *= float(np.cos(normalized_offset * (np.pi / 2.0)) ** 2)

    campo_e = efield_from_power_density(densidad)
    return {
        "ganancia_antena": round(ganancia, 4),
        "densidad_potencia_w_m2": round(densidad, 6),
        "campo_e_v_m": round(campo_e, 4),
    }


def calculate_neutralization_probability_friis(
    potencia_kw: float,
    distancia: float,
    apertura_cono: float,
    angulo_offset: float = 0.0,
    e_threshold: float = HPM_E_THRESHOLD_V_M,
    steepness: float = HPM_SIGMOID_STEEPNESS,
) -> float:
    """
    Probabilidad de neutralización basada en física real (modelo Friis):

        S = P·G / (4πr²)  ->  E = sqrt(S·377)  ->  P_neutralizacion = sigmoide(E, E_umbral)

    Reemplaza la exponencial ad-hoc (ver ``calculate_neutralization_probability``)
    por un modelo donde cada magnitud intermedia tiene unidades físicas reales
    (W/m², V/m) verificables contra literatura de efectos HPM.
    """
    if distancia <= 0:
        return 1.0

    half_cone = apertura_cono / 2.0
    if half_cone > 0 and abs(angulo_offset) > half_cone:
        return 0.0

    diag = friis_diagnostics(potencia_kw, distancia, apertura_cono, angulo_offset)
    exponent = -steepness * (diag["campo_e_v_m"] - e_threshold)
    probabilidad = 1.0 / (1.0 + np.exp(exponent))
    return float(np.clip(probabilidad, 0.0, 1.0))


def calculate_area_neutralization_probability_friis(
    potencia_kw: float,
    distancia: float,
    e_threshold: float = HPM_MISSILE_E_THRESHOLD_V_M,
    steepness: float = HPM_MISSILE_SIGMOID_STEEPNESS,
) -> float:
    """
    Variante omnidireccional (ganancia isotrópica G=1) del modelo Friis para
    el misil de área (detonación soft-kill circular, sin cono direccional).

    Usa un umbral/pendiente propios (``HPM_MISSILE_E_THRESHOLD_V_M``), NO los
    del cañón: un radiador isotrópico esparce la potencia sobre 4π
    estereorradianes en vez de concentrarla en un haz, así que reutilizar el
    umbral calibrado contra un plato de alta ganancia (ver
    ``calculate_neutralization_probability_friis``) haría al misil casi
    inefectivo salvo con potencias de MW. Ver docs/FISICA_Y_MATEMATICA.md.
    """
    if distancia <= 0:
        return 1.0

    diag = friis_diagnostics(potencia_kw, distancia, apertura_cono=360.0)
    exponent = -steepness * (diag["campo_e_v_m"] - e_threshold)
    probabilidad = 1.0 / (1.0 + np.exp(exponent))
    return float(np.clip(probabilidad, 0.0, 1.0))


def apply_hardening_odds(probabilidad: float, factor: float) -> float:
    """
    Reduce una probabilidad de neutralización según un factor de blindaje,
    operando en espacio de "momios" (odds = p/(1-p)), no multiplicando el
    umbral de campo E.

    Nota de auditoría — bug encontrado y corregido: multiplicar el umbral
    E₀ por un factor (p. ej. 2.5×) para simular blindaje daba una reducción
    real de probabilidad de 14× a 821× según la distancia (no 2.5×),
    porque el umbral vive dentro de una sigmoide no lineal — desplazarlo
    saca el punto de operación fuera del rango donde la sigmoide es
    sensible, y la probabilidad colapsa a ~0 en casi todo el rango de
    combate útil. En espacio de momios, dividir por ``factor`` sí da una
    reducción proporcional y predecible en cualquier punto de la curva:

        odds = p / (1 - p)
        odds_blindado = odds / factor
        p_blindado = odds_blindado / (1 + odds_blindado)

    Ver docs/FISICA_Y_MATEMATICA.md.
    """
    if factor <= 1.0 or probabilidad <= 0.0:
        return float(np.clip(probabilidad, 0.0, 1.0))
    if probabilidad >= 1.0:
        probabilidad = 1.0 - 1e-9

    odds = probabilidad / (1.0 - probabilidad)
    odds_reducidos = odds / factor
    return float(np.clip(odds_reducidos / (1.0 + odds_reducidos), 0.0, 1.0))


def target_angle_from_origin(
    origin_x: float,
    origin_y: float,
    target_x: float,
    target_y: float,
) -> float:
    """Ángulo hacia el blanco desde el origen del HPM (grados)."""
    dx = target_x - origin_x
    dy = target_y - origin_y
    return float(np.degrees(np.arctan2(dy, dx)) % 360)


def compute_target_parameters(
    origin_x: float,
    origin_y: float,
    weapon_direction: float,
    target_x: float,
    target_y: float,
    origin_z: float = 0.0,
    target_z: float = 0.0,
) -> tuple[float, float]:
    """
    Calcula distancia y offset angular de un blanco respecto al HPM.

    La distancia es 3D (slant range): el cañón HPM apunta su cono en azimut
    (rotación horizontal), pero un dron a otra altitud está físicamente más
    lejos que la distancia proyectada en el plano X-Y.

    Returns:
        Tupla (distancia, angulo_offset).
    """
    dist = distance3d(origin_x, origin_y, origin_z, target_x, target_y, target_z)
    bearing = target_angle_from_origin(origin_x, origin_y, target_x, target_y)
    offset = angle_difference(weapon_direction, bearing)
    return dist, offset
