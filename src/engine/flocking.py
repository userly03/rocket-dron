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

Nota de diseño — el quinto término (``amenaza``, P2-E): mismo criterio de
legitimidad que la nota de arriba, aplicado al mismo problema desde el otro
extremo. Un cuarto término se justificó porque separación/alineación/
cohesión no tienen tendencia a la COHESIÓN GLOBAL con el terreno; la
amenaza se justifica porque NINGUNO de los cuatro términos existentes tiene
ninguna noción de "algo malo acaba de pasar acá" — sin él, un enjambre bajo
ataque real vuela exactamente igual que uno en patrulla tranquila, lo cual
no es un enjambre con "control reactivo" (el propósito explícito de este
ítem, OPFOR reactivo), es un enjambre ciego a su propia historia de
combate. Igual que el término ``home``, es estándar en la práctica de
robótica de enjambres (repulsión de "zona de peligro"/obstáculo dinámico,
formalmente idéntica a la separación de vecinos pero desde un punto fijo en
vez de otro boid) y no un parche porque:

1. Es CONDICIONAL y se apaga solo: con ``amenaza_intensidad = 0`` (el
   default, sin impactos previos) el término aporta exactamente cero al
   cálculo — un enjambre nunca atacado vuela idéntico a como volaba antes
   de este ítem, byte a byte.
2. Decae con el tiempo (``Drone.actualizar_amenaza``): es una reacción
   TRANSITORIA de dispersión post-impacto, no una fuerza permanente que
   reemplaza al resto del comportamiento — en el orden de
   ``THREAT_MEMORY_DECAY_TAU_S`` segundos vuelve a pesar cero y el enjambre
   retoma flocking normal.
3. Es la MISMA forma funcional que la separación (vector que aleja,
   ponderado por 1/distancia) aplicada a un punto en memoria en vez de a un
   vecino en tiempo real — no introduce mecánica nueva, reutiliza la que ya
   existe.
4. Es falsable por construcción (ver ``tests/test_opfor.py``): con el
   término activo, la distancia media del enjambre al punto de impacto
   debe aumentar más que en un control idéntico (misma semilla, mismo
   escenario) con el término desactivado — si no lo hiciera, sería un
   parche decorativo y el test lo detectaría.
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
    BOIDS_THREAT_WEIGHT,
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


def _threat_vector(drone: Drone) -> tuple[float, float]:
    """
    Vector que aleja al dron de la última posición de impacto que recuerda
    (``drone.amenaza_x/y``), escalado por 1/distancia (mismo criterio que
    separación y ``_home_vector``: empuje más fuerte cuanto más cerca del
    punto de amenaza) y por la intensidad remanente de la memoria, que
    decae con el tiempo (``Drone.actualizar_amenaza``). Cero si no hay
    memoria de amenaza activa (``amenaza_intensidad == 0``, el caso por
    defecto para un dron nunca atacado).
    """
    intensidad = drone.amenaza_intensidad
    if intensidad <= 0.0:
        return 0.0, 0.0

    dx = drone.x - drone.amenaza_x
    dy = drone.y - drone.amenaza_y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        # Impacto registrado exactamente sobre la posición actual: dirección
        # de escape arbitraria pero determinista, en vez de indefinida.
        dx, dy = 1.0, 0.0
        dist = 1.0

    escala = BOIDS_NEIGHBOR_RADIUS / dist
    return dx * escala * intensidad, dy * escala * intensidad


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
    ``(home_x, home_y)`` si se aleja más de ``BOIDS_HOME_RADIUS``, más un
    repulsor de la última posición de impacto que cada dron recuerda (P2-E,
    ver ``_threat_vector`` y la nota de diseño del módulo), con intensidad
    que decae con el tiempo. Se mezcla con el rumbo actual y se limita a
    ``BOIDS_MAX_TURN_RATE_DEG_S`` (mismo patrón de giro acotado que el
    guiado por navegación proporcional del misil — el rumbo cambia
    gradualmente, no de golpe).

    Args:
        drones: drones a considerar. Incluye a los que tienen el enlace de
            control perdido (P2-E: siguen físicamente ahí y deben seguir
            afectando el flocking de sus VECINOS vía separación/alineación/
            cohesión, aunque el rumbo que este cálculo les asigna no se les
            aplique a ellos mismos — ver ``Swarm.actualizar``).
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
        resultado_sin_vecinos: dict[int, float] = {}
        for d in drones:
            home_dx, home_dy = _home_vector(d, home_x, home_y)
            threat_dx, threat_dy = _threat_vector(d)
            resultado_sin_vecinos[d.id] = _girar_hacia(
                d,
                BOIDS_HOME_WEIGHT * home_dx + BOIDS_THREAT_WEIGHT * threat_dx,
                BOIDS_HOME_WEIGHT * home_dy + BOIDS_THREAT_WEIGHT * threat_dy,
            )
        return resultado_sin_vecinos

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
        threat_dx, threat_dy = _threat_vector(drone)
        mask = vecinos[i]

        if not np.any(mask):
            resultado[drone.id] = _girar_hacia(
                drone,
                BOIDS_HOME_WEIGHT * home_dx + BOIDS_THREAT_WEIGHT * threat_dx,
                BOIDS_HOME_WEIGHT * home_dy + BOIDS_THREAT_WEIGHT * threat_dy,
            )
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
            + BOIDS_THREAT_WEIGHT * threat_dx
        )
        total_y = (
            BOIDS_SEPARATION_WEIGHT * sep_dy
            + BOIDS_ALIGNMENT_WEIGHT * align_dy
            + BOIDS_COHESION_WEIGHT * coh_dy
            + BOIDS_HOME_WEIGHT * home_dy
            + BOIDS_THREAT_WEIGHT * threat_dy
        )

        resultado[drone.id] = _girar_hacia(drone, total_x, total_y)

    return resultado
