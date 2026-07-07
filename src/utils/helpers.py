"""Funciones auxiliares para el simulador."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.models.drone import Drone


def degrees_to_radians(degrees: float) -> float:
    return math.radians(degrees)


def radians_to_degrees(radians: float) -> float:
    return math.degrees(radians)


def normalize_angle(degrees: float) -> float:
    """Normaliza un ángulo al rango [0, 360)."""
    return float(degrees % 360)


def angle_difference(from_deg: float, to_deg: float) -> float:
    """Diferencia angular mínima entre dos direcciones en grados."""
    diff = (to_deg - from_deg + 180) % 360 - 180
    return float(diff)


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return float(np.hypot(x2 - x1, y2 - y1))


def distance3d(
    x1: float, y1: float, z1: float, x2: float, y2: float, z2: float
) -> float:
    """Distancia euclídea 3D (slant range). El pulso HPM se propaga
    esféricamente, no solo en el plano horizontal, así que la distancia
    real a un blanco a otra altitud es mayor que la distancia 2D."""
    return float(np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return float(np.clip(value, minimum, maximum))


def drone_to_dict(drone: Drone) -> dict:
    return {
        "id": drone.id,
        "x": round(drone.x, 2),
        "y": round(drone.y, 2),
        "z": round(drone.z, 2),
        "velocidad": round(drone.velocidad, 2),
        "angulo": round(drone.angulo, 2),
        "estado": drone.estado,
        "salud": round(drone.salud, 2),
        "blindaje": drone.blindaje,
        "detectado": drone.detectado,
    }
