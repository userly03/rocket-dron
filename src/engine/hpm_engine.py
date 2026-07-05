"""
Motor HPM basado en el modelo del paper arXiv:2602.08477.

Probabilidad de neutralización:
    P = 1 - exp(-k * potencia / distancia^2)

Con atenuación angular en los bordes del cono de efecto.
"""

from __future__ import annotations

import numpy as np

from src.config import HPM_K_CONSTANT
from src.utils.helpers import angle_difference, distance


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
) -> tuple[float, float]:
    """
    Calcula distancia y offset angular de un blanco respecto al HPM.

    Returns:
        Tupla (distancia, angulo_offset).
    """
    dist = distance(origin_x, origin_y, target_x, target_y)
    bearing = target_angle_from_origin(origin_x, origin_y, target_x, target_y)
    offset = angle_difference(weapon_direction, bearing)
    return dist, offset
