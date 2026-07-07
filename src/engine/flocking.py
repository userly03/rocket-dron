"""
Comportamiento de enjambre (boids — Reynolds, 1987): separación, alineación,
cohesión y una cuarta regla de "zona de patrulla". Reemplaza el vuelo en
línea recta rígido por un enjambre que reacciona a sus vecinos, igual que un
enjambre real de drones autónomos.

Las formaciones (``Swarm.inicializar_formacion``) siguen fijando solo la
posición y el rumbo iniciales; a partir del primer tick el movimiento lo
gobiernan estas reglas.

Nota de diseño — la cuarta regla (``home``): separación/alineación/cohesión
puras no tienen ninguna tendencia a permanecer en una zona — un enjambre
real puede "migrar" completo en una dirección emergente (una vez alineados,
todos giran juntos) y alejarse indefinidamente del alcance de radar/armas,
lo cual hace casi imposible probar el resto del simulador. La regla de
"zona de patrulla" es un cuarto término estándar en implementaciones de
boids (a veces llamado "bound position" o "tendency to a particular
place"), no un parche ad-hoc: solo empuja de vuelta cuando el dron se aleja
más de ``BOIDS_HOME_RADIUS`` de su centro de formación, y no hace nada
dentro de ese radio — no interfiere con el comportamiento local reactivo.
"""

from __future__ import annotations

import math

import numpy as np

from src.config import (
    BOIDS_ALIGNMENT_WEIGHT,
    BOIDS_COHESION_WEIGHT,
    BOIDS_HOME_RADIUS,
    BOIDS_HOME_WEIGHT,
    BOIDS_MAX_TURN_RATE_DEG_S,
    BOIDS_NEIGHBOR_RADIUS,
    BOIDS_SEPARATION_WEIGHT,
)
from src.models.drone import Drone
from src.utils.helpers import angle_difference


def _home_vector(drone: Drone, home_x: float | None, home_y: float | None) -> tuple[float, float]:
    """Vector hacia el centro de la zona de patrulla, cero si ya está dentro de BOIDS_HOME_RADIUS."""
    if home_x is None or home_y is None:
        return 0.0, 0.0

    dx = home_x - drone.x
    dy = home_y - drone.y
    dist = math.hypot(dx, dy)
    if dist <= BOIDS_HOME_RADIUS:
        return 0.0, 0.0

    # Magnitud acotada a la escala de BOIDS_NEIGHBOR_RADIUS (mismo orden que
    # la cohesión) — el empuje de vuelta no depende de cuán lejos se fue,
    # solo de la dirección; evita que un drone muy lejano gire de golpe.
    escala = BOIDS_NEIGHBOR_RADIUS / dist
    return dx * escala, dy * escala


def compute_headings(
    drones: list[Drone],
    dt: float,
    home_x: float | None = None,
    home_y: float | None = None,
) -> dict[int, float]:
    """
    Calcula el nuevo ángulo de vuelo de cada dron aplicando separación,
    alineación y cohesión sobre sus vecinos dentro de
    ``BOIDS_NEIGHBOR_RADIUS``, más una tendencia a volver a
    ``(home_x, home_y)`` si se aleja más de ``BOIDS_HOME_RADIUS``. Se mezcla
    con el rumbo actual y se limita a ``BOIDS_MAX_TURN_RATE_DEG_S`` (mismo
    patrón de giro acotado que el guiado por navegación proporcional del
    misil — el rumbo cambia gradualmente, no de golpe).

    Args:
        drones: drones a considerar (normalmente solo los activos).
        dt: paso de tiempo de la simulación.
        home_x, home_y: centro de la zona de patrulla (típicamente el
            centro de la formación); si se omiten, no hay regla de retorno.

    Returns:
        Diccionario ``{drone_id: nuevo_angulo_grados}``.
    """
    n = len(drones)
    max_giro = BOIDS_MAX_TURN_RATE_DEG_S * dt

    def _girar_hacia(drone: Drone, total_x: float, total_y: float) -> float:
        if total_x == 0 and total_y == 0:
            return drone.angulo
        angulo_deseado = math.degrees(math.atan2(total_y, total_x)) % 360
        giro = float(np.clip(angle_difference(drone.angulo, angulo_deseado), -max_giro, max_giro))
        return (drone.angulo + giro) % 360

    if n < 2:
        return {
            d.id: _girar_hacia(d, *_home_vector(d, home_x, home_y))
            for d in drones
        }

    xs = np.array([d.x for d in drones])
    ys = np.array([d.y for d in drones])
    angulos = np.array([d.angulo for d in drones])
    rad = np.radians(angulos)
    vx = np.cos(rad)
    vy = np.sin(rad)

    dx = xs[:, None] - xs[None, :]
    dy = ys[:, None] - ys[None, :]
    dist = np.hypot(dx, dy)
    np.fill_diagonal(dist, np.inf)
    vecinos = dist < BOIDS_NEIGHBOR_RADIUS

    resultado: dict[int, float] = {}

    for i, drone in enumerate(drones):
        home_dx, home_dy = _home_vector(drone, home_x, home_y)
        mask = vecinos[i]

        if not np.any(mask):
            resultado[drone.id] = _girar_hacia(drone, BOIDS_HOME_WEIGHT * home_dx, BOIDS_HOME_WEIGHT * home_dy)
            continue

        # Separación: vector que aleja del vecino, ponderado por 1/distancia
        # (empuje más fuerte cuanto más cerca — evita colisiones).
        inv_dist = 1.0 / np.maximum(dist[i, mask], 1e-6)
        sep_dx = float(np.sum(dx[i, mask] * inv_dist))
        sep_dy = float(np.sum(dy[i, mask] * inv_dist))

        # Alineación: promedio del vector de velocidad (rumbo) de los vecinos.
        align_dx = float(np.mean(vx[mask]))
        align_dy = float(np.mean(vy[mask]))

        # Cohesión: dirección hacia el centroide de posición de los vecinos.
        coh_dx = float(np.mean(xs[mask])) - drone.x
        coh_dy = float(np.mean(ys[mask])) - drone.y

        total_x = (
            BOIDS_SEPARATION_WEIGHT * sep_dx
            + BOIDS_ALIGNMENT_WEIGHT * align_dx
            + BOIDS_COHESION_WEIGHT * coh_dx
            + BOIDS_HOME_WEIGHT * home_dx
        )
        total_y = (
            BOIDS_SEPARATION_WEIGHT * sep_dy
            + BOIDS_ALIGNMENT_WEIGHT * align_dy
            + BOIDS_COHESION_WEIGHT * coh_dy
            + BOIDS_HOME_WEIGHT * home_dy
        )

        resultado[drone.id] = _girar_hacia(drone, total_x, total_y)

    return resultado
