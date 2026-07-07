"""Gestión de enjambres de drones con formaciones configurables."""

from __future__ import annotations

from enum import Enum
import math
import random

import numpy as np

from src.config import (
    BOIDS_ENABLED,
    DRONE_ALTITUD_MAX,
    DRONE_ALTITUD_MIN,
    DRONE_HARDENED_FRACTION,
    DRONE_HARDENED_THRESHOLD_MULT,
    FIELD_HEIGHT,
    FIELD_WIDTH,
    HPM_FREQUENCY_GHZ,
    HPM_ORIGIN_X,
    HPM_ORIGIN_Y,
    HPM_ORIGIN_Z,
    RADAR_ANTENNA_GAIN_DBI,
    RADAR_NOISE_FLOOR_W,
    RADAR_RCS_M2,
    RADAR_TX_POWER_W,
)
from src.engine.flocking import compute_headings
from src.engine.physics import check_boundary_collision, reflect_angle
from src.engine.radar_engine import evaluar_deteccion
from src.models.drone import Drone, DroneEstado
from src.utils.helpers import distance3d


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
    ) -> None:
        self.drones: list[Drone] = []
        self.formacion = (
            FormacionTipo(formacion)
            if isinstance(formacion, str)
            else formacion
        )
        self.centro_x = centro_x if centro_x is not None else FIELD_WIDTH / 2
        self.centro_y = centro_y if centro_y is not None else FIELD_HEIGHT / 2

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

    @staticmethod
    def _altitud_aleatoria() -> float:
        return float(np.random.uniform(DRONE_ALTITUD_MIN, DRONE_ALTITUD_MAX))

    @staticmethod
    def _blindaje_aleatorio() -> tuple[str, float]:
        """Sortea si el dron es 'blindado' (umbral de susceptibilidad más alto)."""
        if np.random.random() < DRONE_HARDENED_FRACTION:
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
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.random.uniform(0, 360)),
                z=self._altitud_aleatoria(),
                blindaje=blindaje,
                e_threshold_mult=mult,
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
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.degrees(angulo + math.pi / 2) % 360),
                z=z,
                blindaje=blindaje,
                e_threshold_mult=mult,
            )
            self.drones.append(drone)

    def _crear_formacion_aleatoria(self, cantidad: int) -> None:
        margen = 50.0
        for i in range(cantidad):
            blindaje, mult = self._blindaje_aleatorio()
            drone = Drone(
                drone_id=i,
                x=random.uniform(margen, FIELD_WIDTH - margen),
                y=random.uniform(margen, FIELD_HEIGHT - margen),
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.random.uniform(0, 360)),
                z=self._altitud_aleatoria(),
                blindaje=blindaje,
                e_threshold_mult=mult,
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
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(rumbo + np.random.uniform(-15, 15)),
                z=DRONE_ALTITUD_MIN + rango_z * frac,
                blindaje=blindaje,
                e_threshold_mult=mult,
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
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(rumbo + np.random.uniform(-10, 10)),
                z=DRONE_ALTITUD_MIN + rango_z * frac,
                blindaje=blindaje,
                e_threshold_mult=mult,
            )
            self.drones.append(drone)

    def actualizar(self, dt: float) -> None:
        """Mueve todos los drones activos y resuelve colisiones con bordes."""
        if BOIDS_ENABLED:
            activos = [
                d for d in self.drones
                if d.estado not in (DroneEstado.NEUTRALIZADO, DroneEstado.INTERFERIDO)
            ]
            nuevos_angulos = compute_headings(activos, dt, self.centro_x, self.centro_y)
            for drone in activos:
                drone.angulo = nuevos_angulos[drone.id]

        for drone in self.drones:
            if drone.estado == DroneEstado.NEUTRALIZADO:
                continue

            drone.mover(dt)

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
                HPM_FREQUENCY_GHZ,
                RADAR_RCS_M2,
                RADAR_NOISE_FLOOR_W,
            )

    def drones_activos(self) -> list[Drone]:
        return [d for d in self.drones if d.estado == DroneEstado.ACTIVO]

    def contar_por_estado(self) -> dict[str, int]:
        conteo = {estado.value: 0 for estado in DroneEstado}
        for drone in self.drones:
            conteo[drone.estado.value] += 1
        return conteo
