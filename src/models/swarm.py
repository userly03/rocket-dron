"""Gestión de enjambres de drones con formaciones configurables."""

from __future__ import annotations

from enum import Enum
import math

import numpy as np
from numpy.random import Generator

from src.config import (
    BOIDS_ENABLED,
    DRONE_ALTITUD_MAX,
    DRONE_ALTITUD_MIN,
    DRONE_HARDENED_FRACTION,
    DRONE_HARDENED_THRESHOLD_MULT,
    FIELD_HEIGHT,
    FIELD_WIDTH,
    HPM_ORIGIN_X,
    HPM_ORIGIN_Y,
    HPM_ORIGIN_Z,
    RADAR_ANTENNA_GAIN_DBI,
    RADAR_FREQUENCY_GHZ,
    RADAR_NOISE_FLOOR_W,
    RADAR_RCS_M2,
    RADAR_TX_POWER_W,
)
from src.engine.flocking import compute_headings
from src.engine.physics import check_boundary_collision, reflect_angle
from src.engine.radar_engine import evaluar_deteccion
from src.models.drone import Drone, DroneEstado, EstadoEnlace, EstadoSalud
from src.utils.helpers import distance3d
from src.utils.reproducibilidad import rng as global_rng


class FormacionTipo(str, Enum):
    CUADRADA = "cuadrada"
    CIRCULAR = "circular"
    ALEATORIA = "aleatoria"
    LINEA = "linea"
    V = "v"


VELOCIDAD_MIN = 10.0
VELOCIDAD_MAX = 30.0


class Swarm:
    """Conjunto de drones con formación y actualización colectiva."""

    def __init__(
        self,
        formacion: FormacionTipo | str = FormacionTipo.CUADRADA,
        centro_x: float | None = None,
        centro_y: float | None = None,
        rng: Generator | None = None,
    ) -> None:
        self.drones: list[Drone] = []
        self.formacion = (
            FormacionTipo(formacion)
            if isinstance(formacion, str)
            else formacion
        )
        self.centro_x = centro_x if centro_x is not None else FIELD_WIDTH / 2
        self.centro_y = centro_y if centro_y is not None else FIELD_HEIGHT / 2

        # RNG por instancia (P0-B): None conserva el comportamiento previo
        # (generador global de src.utils.reproducibilidad) — necesario para
        # que un experimento Monte Carlo pueda darle a cada réplica su propio
        # generador aislado sin afectar a la simulación interactiva ni a
        # otras réplicas corriendo en paralelo. Ver ``self._rng()``.
        self.rng = rng

    def _rng(self) -> Generator:
        """Generador de esta instancia, o el global si no se inyectó ninguno."""
        return self.rng if self.rng is not None else global_rng()

    def inicializar_formacion(self, tipo: str, cantidad: int) -> None:
        """Crea drones según el patrón de formación indicado."""
        self.formacion = FormacionTipo(tipo)
        self.drones.clear()

        if self.formacion == FormacionTipo.CUADRADA:
            self._crear_formacion_cuadrada(cantidad)
        elif self.formacion == FormacionTipo.CIRCULAR:
            self._crear_formacion_circular(cantidad)
        elif self.formacion == FormacionTipo.LINEA:
            self._crear_formacion_linea(cantidad)
        elif self.formacion == FormacionTipo.V:
            self._crear_formacion_v(cantidad)
        else:
            self._crear_formacion_aleatoria(cantidad)

    def _altitud_aleatoria(self) -> float:
        return float(self._rng().uniform(DRONE_ALTITUD_MIN, DRONE_ALTITUD_MAX))

    def _blindaje_aleatorio(self) -> tuple[str, float]:
        """Sortea si el dron es 'blindado' (umbral de susceptibilidad más alto)."""
        if self._rng().random() < DRONE_HARDENED_FRACTION:
            return "blindado", DRONE_HARDENED_THRESHOLD_MULT
        return "estandar", 1.0

    def _crear_formacion_cuadrada(self, cantidad: int) -> None:
        lado = int(math.ceil(math.sqrt(cantidad)))
        espaciado = 30.0
        inicio_x = self.centro_x - (lado - 1) * espaciado / 2
        inicio_y = self.centro_y - (lado - 1) * espaciado / 2

        for i in range(cantidad):
            fila = i // lado
            col = i % lado
            blindaje, mult = self._blindaje_aleatorio()
            drone = Drone(
                drone_id=i,
                x=inicio_x + col * espaciado,
                y=inicio_y + fila * espaciado,
                velocidad=float(self._rng().uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(self._rng().uniform(0, 360)),
                z=self._altitud_aleatoria(),
                blindaje=blindaje,
                e_threshold_mult=mult,
                rng=self.rng,
            )
            self.drones.append(drone)

    def _crear_formacion_circular(self, cantidad: int) -> None:
        radio = min(FIELD_WIDTH, FIELD_HEIGHT) * 0.2
        capas = 3
        # Solo la mitad del rango configurado: usar el rango completo (hasta
        # 120m con los defaults) separa los anillos casi tanto como el radio
        # de efecto típico de un misil, haciendo casi imposible que una sola
        # detonación alcance a más de un anillo a la vez. Con la mitad, sigue
        # habiendo relieve visual real pero el grupo es alcanzable como
        # conjunto (ver docs/FISICA_Y_MATEMATICA.md).
        rango_z = (DRONE_ALTITUD_MAX - DRONE_ALTITUD_MIN) / 2
        for i in range(cantidad):
            angulo = (2 * math.pi * i) / cantidad
            x = self.centro_x + radio * math.cos(angulo)
            y = self.centro_y + radio * math.sin(angulo)
            # Anillos escalonados en altura para que el "donut" tenga relieve real.
            capa = i % capas
            z = DRONE_ALTITUD_MIN + rango_z * (capa / max(1, capas - 1))
            blindaje, mult = self._blindaje_aleatorio()
            drone = Drone(
                drone_id=i,
                x=x,
                y=y,
                velocidad=float(self._rng().uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.degrees(angulo + math.pi / 2) % 360),
                z=z,
                blindaje=blindaje,
                e_threshold_mult=mult,
                rng=self.rng,
            )
            self.drones.append(drone)

    def _crear_formacion_aleatoria(self, cantidad: int) -> None:
        margen = 50.0
        for i in range(cantidad):
            blindaje, mult = self._blindaje_aleatorio()
            drone = Drone(
                drone_id=i,
                x=self._rng().uniform(margen, FIELD_WIDTH - margen),
                y=self._rng().uniform(margen, FIELD_HEIGHT - margen),
                velocidad=float(self._rng().uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(self._rng().uniform(0, 360)),
                z=self._altitud_aleatoria(),
                blindaje=blindaje,
                e_threshold_mult=mult,
                rng=self.rng,
            )
            self.drones.append(drone)

    def _crear_formacion_linea(self, cantidad: int) -> None:
        espaciado = 30.0
        inicio_x = self.centro_x - (cantidad - 1) * espaciado / 2
        rumbo = 0.0
        rango_z = DRONE_ALTITUD_MAX - DRONE_ALTITUD_MIN

        for i in range(cantidad):
            # Gradiente suave de altitud a lo largo de la línea.
            frac = i / max(1, cantidad - 1)
            blindaje, mult = self._blindaje_aleatorio()
            drone = Drone(
                drone_id=i,
                x=inicio_x + i * espaciado,
                y=self.centro_y,
                velocidad=float(self._rng().uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(rumbo + self._rng().uniform(-15, 15)),
                z=DRONE_ALTITUD_MIN + rango_z * frac,
                blindaje=blindaje,
                e_threshold_mult=mult,
                rng=self.rng,
            )
            self.drones.append(drone)

    def _crear_formacion_v(self, cantidad: int) -> None:
        espaciado = 35.0
        rumbo = 0.0  # avanzan hacia +x, vértice de la V al frente
        rango_z = DRONE_ALTITUD_MAX - DRONE_ALTITUD_MIN

        for i in range(cantidad):
            if i == 0:
                x, y = self.centro_x, self.centro_y
                paso = 0
            else:
                brazo = 1 if i % 2 == 1 else -1
                paso = (i + 1) // 2
                x = self.centro_x - paso * espaciado * 0.8
                y = self.centro_y + brazo * paso * espaciado * 0.6

            # Los brazos de la V ganan altitud a medida que se alejan del vértice.
            frac = paso / max(1, (cantidad + 1) // 2)
            blindaje, mult = self._blindaje_aleatorio()
            drone = Drone(
                drone_id=i,
                x=x,
                y=y,
                velocidad=float(self._rng().uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(rumbo + self._rng().uniform(-10, 10)),
                z=DRONE_ALTITUD_MIN + rango_z * frac,
                blindaje=blindaje,
                e_threshold_mult=mult,
                rng=self.rng,
            )
            self.drones.append(drone)

    def actualizar(self, dt: float) -> None:
        """Mueve todos los drones activos y resuelve colisiones con bordes."""
        if BOIDS_ENABLED:
            # Bug corregido (P2-E, auditoría §3.4): antes se excluía del
            # cálculo a los drones con enlace perdido, así que
            # desaparecían del flocking de sus VECINOS — seguían
            # físicamente ahí (compitiendo por el mismo espacio aéreo),
            # pero como si no existieran para separación/alineación/
            # cohesión. Ahora entran al cálculo igual que cualquier otro
            # dron con salud (solo se excluyen los neutralizados, que sí
            # dejaron de existir como amenaza física); lo único que
            # cambia es que el rumbo que ``compute_headings`` les asigna
            # NO se les aplica a ELLOS MISMOS: mientras el enlace está
            # perdido, su propio rumbo lo gobierna el perfil de
            # contingencia (ver ``Drone.mover``), no el flocking.
            con_flocking = [
                d for d in self.drones if d.estado_salud != EstadoSalud.NEUTRALIZADO
            ]
            nuevos_angulos = compute_headings(con_flocking, dt, self.centro_x, self.centro_y)
            for drone in con_flocking:
                # P2-D, Parte 3 — comportamiento degradado: un upset del
                # flight controller (autopiloto) significa que el dron
                # momentáneamente NO puede procesar comandos de flocking
                # nuevos (brownout/desincronización), aunque su enlace de
                # radio siga OK — causa física distinta al enlace perdido
                # (esa es interferencia externa; esta es un glitch interno),
                # pero mismo efecto observable: el rumbo queda congelado en
                # el último valor hasta que el riesgo decae o madura.
                if (
                    drone.estado_enlace == EstadoEnlace.OK
                    and drone.subsistema_en_riesgo != "flight_controller"
                ):
                    drone.angulo = nuevos_angulos[drone.id]

        for drone in self.drones:
            if drone.estado_salud == EstadoSalud.NEUTRALIZADO:
                continue

            # home_x/home_y: centro de la zona de patrulla, reutilizado
            # como punto de retorno del perfil lost-link RTH (P2-E, Parte
            # 3) — el mismo punto al que ya converge la 4ta regla de
            # boids para drones con enlace normal.
            drone.mover(dt, home_x=self.centro_x, home_y=self.centro_y)

            new_x, new_y, collided_x, collided_y = check_boundary_collision(
                drone.x, drone.y, FIELD_WIDTH, FIELD_HEIGHT, margin=10.0
            )
            if collided_x or collided_y:
                drone.x, drone.y = new_x, new_y
                drone.angulo = reflect_angle(drone.angulo, collided_x, collided_y)

            dist_radar = distance3d(
                HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, drone.x, drone.y, drone.z
            )
            drone.detectado, _ = evaluar_deteccion(
                dist_radar,
                RADAR_TX_POWER_W,
                RADAR_ANTENNA_GAIN_DBI,
                RADAR_FREQUENCY_GHZ,
                RADAR_RCS_M2,
                RADAR_NOISE_FLOOR_W,
            )

    def actualizar_amenazas(self, dt: float) -> None:
        """
        Decae la memoria de amenaza de todos los drones un paso ``dt``
        (P2-E, Parte 2) — ver ``Drone.actualizar_amenaza`` y el término de
        repulsión en ``compute_headings``. Se llama desde
        ``SimulationEngine._tick`` independientemente de si el enjambre se
        mueve por flocking este tick.
        """
        for drone in self.drones:
            drone.actualizar_amenaza(dt)

    def actualizar_riesgos_latentes(self, dt: float) -> list[dict]:
        """
        Decae el riesgo latente de todos los drones un paso ``dt`` (P2-D,
        Parte 3) y recoge las neutralizaciones DIFERIDAS que maduraron este
        tick — ver ``Drone.actualizar_riesgo_latente``. Se llama desde
        ``SimulationEngine._tick``, mismo patrón que ``actualizar_amenazas``.

        Returns:
            Lista de ``{"drone_id", "shot_id", "distancia_m"}`` por cada
            dron recién neutralizado por fallo latente — vacía la mayoría
            de los ticks. ``SimulationEngine`` la usa para atribuir la baja
            al disparo/detonación original en ``analytics``.
        """
        eventos: list[dict] = []
        for drone in self.drones:
            shot_id = drone.origen_riesgo_shot_id
            distancia = drone.origen_riesgo_distancia_m
            if drone.actualizar_riesgo_latente(dt):
                eventos.append(
                    {"drone_id": drone.id, "shot_id": shot_id, "distancia_m": distancia}
                )
        return eventos

    def drones_activos(self) -> list[Drone]:
        return [d for d in self.drones if d.estado == DroneEstado.ACTIVO]

    def contar_por_estado(self) -> dict[str, int]:
        conteo = {estado.value: 0 for estado in DroneEstado}
        for drone in self.drones:
            conteo[drone.estado.value] += 1
        return conteo

    def contar_upset_damage(self) -> dict:
        """
        Fracción de drones en cada categoría del modelo upset/damage (P2-D):
        ``en_riesgo`` (upset activo, ``riesgo_latente_por_s > 0`` — todavía
        recuperable), ``danados_permanente`` (neutralizados por daño
        inmediato o por fallo latente que maduró — indistinguibles desde
        acá, ambos son EstadoSalud.NEUTRALIZADO) e ``intactos`` (el resto).
        Expuesto en el panel físico — ver ``PhysicsAnalytics.get_physics_panel``.
        """
        total = len(self.drones)
        en_riesgo = sum(1 for d in self.drones if d.riesgo_latente_por_s > 0.0)
        neutralizados = sum(
            1 for d in self.drones if d.estado_salud == EstadoSalud.NEUTRALIZADO
        )
        por_subsistema: dict[str, int] = {}
        for d in self.drones:
            if d.subsistema_en_riesgo:
                por_subsistema[d.subsistema_en_riesgo] = (
                    por_subsistema.get(d.subsistema_en_riesgo, 0) + 1
                )
        return {
            "total": total,
            "en_riesgo_upset": en_riesgo,
            "danados_permanente": neutralizados,
            "intactos": max(0, total - en_riesgo - neutralizados),
            "fraccion_en_riesgo": round(en_riesgo / total, 4) if total else 0.0,
            "fraccion_danados_permanente": round(neutralizados / total, 4) if total else 0.0,
            "por_subsistema_en_riesgo": por_subsistema,
        }
