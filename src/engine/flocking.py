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

Nota de diseño — propagación de la memoria de amenaza (P2-E, Parte 4, ver
``propagate_alarm``): hasta acá, la memoria de amenaza solo la sembraba
``registrar_impacto`` en el dron IMPACTADO DIRECTAMENTE — un enjambre bajo
ataque real, salvo ESE dron, volaba exactamente igual que uno en patrulla.
Es un hueco real de literatura encontrado en el barrido de biomimesis (ver
docs/ESTADO_DEL_ARTE_BIOMIMESIS.md §2): Attanasi et al. miden que en
bandadas reales la alarma se propaga de vecino a vecino MÁS RÁPIDO que el
reposicionamiento físico del grupo — un estornino reacciona al ver a su
vecino asustarse, no al depredador en sí. ``propagate_alarm`` no es un
término nuevo en ``compute_headings`` (que sigue leyendo, nunca escribiendo,
``amenaza_*``): es una nueva operación del ciclo de vida de la memoria
existente (sembrar → **propagar** → decaer), reutilizando la misma red de
vecinos de ``BOIDS_NEIGHBOR_RADIUS`` que ya usan separación/alineación/
cohesión.
"""

from __future__ import annotations

import math

import numpy as np

from src.config import (
    BOIDS_ALARM_PROPAGATION_GAIN,
    BOIDS_ALIGNMENT_WEIGHT,
    BOIDS_COHESION_WEIGHT,
    BOIDS_HOME_RADIUS,
    BOIDS_HOME_WEIGHT,
    BOIDS_MAX_TURN_RATE_DEG_S,
    BOIDS_MISSION_WEIGHT,
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


def _final_approach_vector(
    drone: Drone, objetivo_x: float | None, objetivo_y: float | None
) -> tuple[float, float]:
    """
    Vector unitario directo hacia el objetivo de la misión, activo SOLO
    dentro de ``BOIDS_HOME_RADIUS`` de él — ver ``BOIDS_MISSION_WEIGHT`` en
    src/config.py para el porqué: sin esto, avanzar solo el ancla de
    cohesión (``formacion_x/y`` hacia ``objetivo_x/y``, ver
    ``Swarm._avanzar_formacion_hacia_objetivo``) no alcanza, porque
    ``_home_vector`` da fuerza CERO dentro de su propio radio — es un
    límite de "no te alejes de acá", no una meta de "andá hacia allá". Este
    término agarra exactamente donde home suelta: complementa, no
    reemplaza, la convergencia de la formación completa.

    A diferencia de separación/amenaza (que SE FORTALECEN cuanto más cerca,
    1/distancia — tiene sentido para algo de lo que hay que alejarse), acá
    la magnitud es constante (vector unitario): no hace falta que la
    atracción crezca sin límite cerca del objetivo, alcanza con que nunca
    sea cero mientras no se llegó.
    """
    if objetivo_x is None or objetivo_y is None:
        return 0.0, 0.0

    dx = objetivo_x - drone.x
    dy = objetivo_y - drone.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6 or dist > BOIDS_HOME_RADIUS:
        return 0.0, 0.0

    return dx / dist, dy / dist


def propagate_alarm(drones: list[Drone]) -> None:
    """
    Propaga la memoria de amenaza a los vecinos inmediatos (P2-E, Parte 4
    — biomimesis, ver ``BOIDS_ALARM_PROPAGATION_GAIN`` en ``src/config.py``
    para el hallazgo de literatura y el racional completo de la ganancia).

    A diferencia de ``compute_headings`` (de lectura pura: nunca escribe
    ``amenaza_*``), esta función MUTA ``Drone.amenaza_x/y/intensidad``
    directamente — mismo patrón que ``Drone.actualizar_amenaza`` (decaimiento)
    y ``Drone.registrar_impacto`` (siembra): la memoria de amenaza tiene tres
    operaciones de ciclo de vida (sembrar, decaer, propagar), todas mutan
    estado, y ``compute_headings``/``_threat_vector`` solo LEEN el resultado
    para convertirlo en fuerza de repulsión.

    Un dron sin amenaza propia (o con una más débil que la de su vecino)
    ADOPTA la posición y una fracción (``BOIDS_ALARM_PROPAGATION_GAIN``) de
    la intensidad del vecino MÁS alarmado dentro de ``BOIDS_NEIGHBOR_RADIUS``
    — la misma red de vecinos que ya usa ``compute_headings`` para
    separación/alineación/cohesión, no una topología nueva.

    Actualización SINCRÓNICA, no secuencial: todas las intensidades nuevas
    se calculan a partir de un snapshot de las intensidades ANTES de llamar
    a esta función, y se aplican recién al final. Si se aplicaran una por
    una a medida que se recorre la lista, la alarma podría saltar varios
    vecinos en una sola llamada según el orden de iteración — un artefacto
    del código, no una propiedad del modelo. Con la actualización sincrónica,
    la onda avanza exactamente UN salto por llamada (una por tick, ver
    ``Swarm.actualizar_amenazas``): la velocidad de propagación depende solo
    de ``BOIDS_NEIGHBOR_RADIUS`` y de cada cuánto se llama, ambos explícitos.

    Un dron nunca pierde SU PROPIA amenaza por esto (siempre
    ``max(propia, contagiada)``): el dron impactado directamente sigue
    siendo el epicentro real de la onda que ven sus vecinos, no un nodo más
    que la propagación podría sobrescribir con un valor menor.
    """
    n = len(drones)
    if n < 2:
        return

    intensidad0 = np.array([d.amenaza_intensidad for d in drones])
    if not np.any(intensidad0 > 0.0):
        return  # nadie tiene amenaza activa: nada que propagar, salida barata

    x0 = np.array([d.amenaza_x for d in drones])
    y0 = np.array([d.amenaza_y for d in drones])

    xs = np.array([d.x for d in drones])
    ys = np.array([d.y for d in drones])
    dist = np.hypot(xs[:, None] - xs[None, :], ys[:, None] - ys[None, :])
    np.fill_diagonal(dist, np.inf)
    vecinos = dist < BOIDS_NEIGHBOR_RADIUS

    nueva_intensidad = intensidad0.copy()
    nueva_x = x0.copy()
    nueva_y = y0.copy()

    for i in range(n):
        idx_vecinos = np.where(vecinos[i])[0]
        if idx_vecinos.size == 0:
            continue
        j = idx_vecinos[int(np.argmax(intensidad0[idx_vecinos]))]
        contagiada = intensidad0[j] * BOIDS_ALARM_PROPAGATION_GAIN
        if contagiada > nueva_intensidad[i]:
            nueva_intensidad[i] = contagiada
            nueva_x[i] = x0[j]
            nueva_y[i] = y0[j]

    for i, drone in enumerate(drones):
        if nueva_intensidad[i] > intensidad0[i]:
            drone.amenaza_x = float(nueva_x[i])
            drone.amenaza_y = float(nueva_y[i])
            drone.amenaza_intensidad = float(nueva_intensidad[i])


def compute_headings(
    drones: list[Drone],
    dt: float,
    home_x: float | None = None,
    home_y: float | None = None,
    objetivo_x: float | None = None,
    objetivo_y: float | None = None,
) -> dict[int, float]:
    """
    Calcula el nuevo ángulo de vuelo de cada dron aplicando separación,
    alineación y cohesión sobre sus vecinos dentro de
    ``BOIDS_NEIGHBOR_RADIUS``, más una tendencia a volver a
    ``(home_x, home_y)`` si se aleja más de ``BOIDS_HOME_RADIUS``, más un
    repulsor de la última posición de impacto que cada dron recuerda (P2-E,
    ver ``_threat_vector`` y la nota de diseño del módulo), con intensidad
    que decae con el tiempo, más una atracción de acercamiento final hacia
    ``(objetivo_x, objetivo_y)`` dentro de ``BOIDS_HOME_RADIUS`` de ese
    punto (ver ``_final_approach_vector`` y ``BOIDS_MISSION_WEIGHT`` en
    src/config.py). Se mezcla con el rumbo actual y se limita a
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
            ancla de formación, ``Swarm.formacion_x/y``); si se omiten, no
            hay regla de retorno.
        objetivo_x, objetivo_y: objetivo de la misión ofensiva (típicamente
            ``Swarm.objetivo_x/y``, el punto real, no el ancla que avanza
            hacia él); si se omiten, no hay término de acercamiento final.

    Returns:
        Diccionario ``{drone_id: nuevo_angulo_grados}``.
    """
    n = len(drones)
    max_giro = BOIDS_MAX_TURN_RATE_DEG_S * dt

    def _girar_hacia(drone: Drone, total_x: float, total_y: float) -> float:
        if total_x == 0 and total_y == 0:
            return drone.angulo
        angulo_deseado = math.degrees(math.atan2(total_y, total_x)) % 360
        # min/max de Python, no np.clip: angle_difference siempre devuelve
        # un float plano (ver helpers.py), así que acotarlo es un clip
        # ESCALAR — np.clip paga el despacho completo de un ufunc de numpy
        # (validación de tipo, maquinaria de reduce) por un solo número,
        # más caro que el cálculo en sí. Llamado una vez POR DRON, por
        # tick: con 500 drones era, después de vectorizar separación/
        # alineación/cohesión, el costo dominante que quedaba (auditoría
        # de backend, ronda 2, medido con cProfile).
        giro = angle_difference(drone.angulo, angulo_deseado)
        giro = max(-max_giro, min(max_giro, giro))
        return (drone.angulo + giro) % 360

    if n < 2:
        resultado_sin_vecinos: dict[int, float] = {}
        for d in drones:
            home_dx, home_dy = _home_vector(d, home_x, home_y)
            threat_dx, threat_dy = _threat_vector(d)
            mision_dx, mision_dy = _final_approach_vector(d, objetivo_x, objetivo_y)
            resultado_sin_vecinos[d.id] = _girar_hacia(
                d,
                BOIDS_HOME_WEIGHT * home_dx + BOIDS_THREAT_WEIGHT * threat_dx + BOIDS_MISSION_WEIGHT * mision_dx,
                BOIDS_HOME_WEIGHT * home_dy + BOIDS_THREAT_WEIGHT * threat_dy + BOIDS_MISSION_WEIGHT * mision_dy,
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

    # Separación/alineación/cohesión, VECTORIZADAS sobre todos los drones a
    # la vez (matriz n×n de vecinos × producto matricial), no un np.mean/
    # np.sum por dron dentro del loop de abajo. Antes de esto, con 500
    # drones (el máximo de StartRequest.cantidad), un tick tardaba ~235ms
    # contra un presupuesto de 16.7ms a 60fps — ~14x sobre presupuesto,
    # medido con cProfile: 2000 llamadas a np.mean por tick (4 por dron),
    # cada una pagando el overhead de despacho de numpy sobre un array
    # chico, que para ese tamaño es mayor que el cálculo en sí (auditoría
    # de backend, ronda 2). La red de vecinos (matriz `vecinos`) y la
    # física de cada término son EXACTAMENTE las mismas — esto es una
    # reescritura de CÓMO se suma/promedia, no de QUÉ se suma/promedia.
    vecinos_f = vecinos.astype(np.float64)
    n_vecinos = vecinos_f.sum(axis=1)
    # Evita 0/0 en las filas sin vecinos — el resultado ahí no se usa
    # (esas filas van por la rama "sin vecinos" del loop de abajo).
    n_vecinos_seguro = np.where(n_vecinos > 0, n_vecinos, 1.0)

    inv_dist = 1.0 / np.maximum(dist, 1e-6)
    sep_dx_todos = np.sum(dx * inv_dist * vecinos_f, axis=1)
    sep_dy_todos = np.sum(dy * inv_dist * vecinos_f, axis=1)

    align_dx_todos = (vecinos_f @ vx) / n_vecinos_seguro
    align_dy_todos = (vecinos_f @ vy) / n_vecinos_seguro

    centroide_x_todos = (vecinos_f @ xs) / n_vecinos_seguro
    centroide_y_todos = (vecinos_f @ ys) / n_vecinos_seguro
    coh_dx_todos = centroide_x_todos - xs
    coh_dy_todos = centroide_y_todos - ys

    resultado: dict[int, float] = {}

    for i, drone in enumerate(drones):
        home_dx, home_dy = _home_vector(drone, home_x, home_y)
        threat_dx, threat_dy = _threat_vector(drone)
        mision_dx, mision_dy = _final_approach_vector(drone, objetivo_x, objetivo_y)

        if n_vecinos[i] == 0:
            resultado[drone.id] = _girar_hacia(
                drone,
                BOIDS_HOME_WEIGHT * home_dx + BOIDS_THREAT_WEIGHT * threat_dx + BOIDS_MISSION_WEIGHT * mision_dx,
                BOIDS_HOME_WEIGHT * home_dy + BOIDS_THREAT_WEIGHT * threat_dy + BOIDS_MISSION_WEIGHT * mision_dy,
            )
            continue

        total_x = (
            BOIDS_SEPARATION_WEIGHT * sep_dx_todos[i]
            + BOIDS_ALIGNMENT_WEIGHT * align_dx_todos[i]
            + BOIDS_COHESION_WEIGHT * coh_dx_todos[i]
            + BOIDS_HOME_WEIGHT * home_dx
            + BOIDS_THREAT_WEIGHT * threat_dx
            + BOIDS_MISSION_WEIGHT * mision_dx
        )
        total_y = (
            BOIDS_SEPARATION_WEIGHT * sep_dy_todos[i]
            + BOIDS_ALIGNMENT_WEIGHT * align_dy_todos[i]
            + BOIDS_COHESION_WEIGHT * coh_dy_todos[i]
            + BOIDS_HOME_WEIGHT * home_dy
            + BOIDS_THREAT_WEIGHT * threat_dy
            + BOIDS_MISSION_WEIGHT * mision_dy
        )

        resultado[drone.id] = _girar_hacia(drone, total_x, total_y)

    return resultado
