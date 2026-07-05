"""Gestión de enjambres de drones con formaciones configurables."""

from __future__ import annotations

from enum import Enum
import math
import random

import numpy as np

from src.config import FIELD_HEIGHT, FIELD_WIDTH
from src.engine.physics import check_boundary_collision, reflect_angle
from src.models.drone import Drone, DroneEstado


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

    def _crear_formacion_cuadrada(self, cantidad: int) -> None:
        lado = int(math.ceil(math.sqrt(cantidad)))
        espaciado = 30.0
        inicio_x = self.centro_x - (lado - 1) * espaciado / 2
        inicio_y = self.centro_y - (lado - 1) * espaciado / 2

        for i in range(cantidad):
            fila = i // lado
            col = i % lado
            drone = Drone(
                drone_id=i,
                x=inicio_x + col * espaciado,
                y=inicio_y + fila * espaciado,
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.random.uniform(0, 360)),
            )
            self.drones.append(drone)

    def _crear_formacion_circular(self, cantidad: int) -> None:
        radio = min(FIELD_WIDTH, FIELD_HEIGHT) * 0.2
        for i in range(cantidad):
            angulo = (2 * math.pi * i) / cantidad
            x = self.centro_x + radio * math.cos(angulo)
            y = self.centro_y + radio * math.sin(angulo)
            drone = Drone(
                drone_id=i,
                x=x,
                y=y,
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.degrees(angulo + math.pi / 2) % 360),
            )
            self.drones.append(drone)

    def _crear_formacion_aleatoria(self, cantidad: int) -> None:
        margen = 50.0
        for i in range(cantidad):
            drone = Drone(
                drone_id=i,
                x=random.uniform(margen, FIELD_WIDTH - margen),
                y=random.uniform(margen, FIELD_HEIGHT - margen),
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(np.random.uniform(0, 360)),
            )
            self.drones.append(drone)

    def _crear_formacion_linea(self, cantidad: int) -> None:
        espaciado = 30.0
        inicio_x = self.centro_x - (cantidad - 1) * espaciado / 2
        rumbo = 0.0

        for i in range(cantidad):
            drone = Drone(
                drone_id=i,
                x=inicio_x + i * espaciado,
                y=self.centro_y,
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(rumbo + np.random.uniform(-15, 15)),
            )
            self.drones.append(drone)

    def _crear_formacion_v(self, cantidad: int) -> None:
        espaciado = 35.0
        rumbo = 0.0  # avanzan hacia +x, vértice de la V al frente

        for i in range(cantidad):
            if i == 0:
                x, y = self.centro_x, self.centro_y
            else:
                brazo = 1 if i % 2 == 1 else -1
                paso = (i + 1) // 2
                x = self.centro_x - paso * espaciado * 0.8
                y = self.centro_y + brazo * paso * espaciado * 0.6

            drone = Drone(
                drone_id=i,
                x=x,
                y=y,
                velocidad=float(np.random.uniform(VELOCIDAD_MIN, VELOCIDAD_MAX)),
                angulo=float(rumbo + np.random.uniform(-10, 10)),
            )
            self.drones.append(drone)

    def actualizar(self, dt: float) -> None:
        """Mueve todos los drones activos y resuelve colisiones con bordes."""
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

    def drones_activos(self) -> list[Drone]:
        return [d for d in self.drones if d.estado == DroneEstado.ACTIVO]

    def contar_por_estado(self) -> dict[str, int]:
        conteo = {estado.value: 0 for estado in DroneEstado}
        for drone in self.drones:
            conteo[drone.estado.value] += 1
        return conteo
