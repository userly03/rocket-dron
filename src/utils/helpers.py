"""Funciones auxiliares para el simulador."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from src.config import DRONE_RIESGO_LATENTE_MAX_POR_S

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


def drone_to_dict(drone: Drone, track_manager=None) -> dict:
    track = track_manager.get_track(drone.id) if track_manager is not None else None
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
        "cable_length_m": round(drone.cable_length_m, 4),
        "f_res_ghz": round(drone.frecuencia_resonancia_ghz(), 4),
        "polarization": round(drone.polarization, 4),
        "acoplamiento": round(drone.factor_acoplamiento(), 4),
        # Riesgo latente (P2-D): ventana de vulnerabilidad transitoria tras un
        # impacto de "upset" — el dron puede recuperarse o caer más tarde.
        # "severidad" normaliza a [0,1] igual que Drone.actualizar_riesgo_latente
        # (fraccion_riesgo), para que el frontend pueda escalar un efecto visual
        # (ej. velocidad de pulso) sin reimplementar la fórmula del motor.
        "riesgo_latente_por_s": round(drone.riesgo_latente_por_s, 4),
        "riesgo_latente_severidad": (
            round(min(1.0, drone.riesgo_latente_por_s / DRONE_RIESGO_LATENTE_MAX_POR_S), 4)
            if drone.riesgo_latente_por_s > 0.0 else 0.0
        ),
        "subsistema_en_riesgo": drone.subsistema_en_riesgo,
        # Radar dinámico (P2-G): posición ESTIMADA por el track, si existe
        # (con la que apunta el misil — ver TrackManager.posicion_para),
        # distinta de x/y/z (la posición REAL) de arriba. None si no hay
        # track vivo para este dron (nunca se lo llamó, o se perdió).
        "track_x": round(track.x, 2) if track is not None else None,
        "track_y": round(track.y, 2) if track is not None else None,
        "track_z": round(track.z, 2) if track is not None else None,
        # P5 — qué sensor sostiene este track ahora mismo ("radar"/"rf"),
        # None si no hay track vivo. Ver Track.fuente_deteccion.
        "fuente_deteccion": track.fuente_deteccion if track is not None else None,
        # Misión ofensiva: True si este dron llegó al objetivo — una
        # BRECHA de la defensa, no una baja. Falso siempre si no hay
        # objetivo configurado (Swarm.objetivo_x is None).
        "objetivo_alcanzado": drone.objetivo_alcanzado,
    }
