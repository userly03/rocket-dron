"""Modelo de dron para la simulación EW."""

from __future__ import annotations

from enum import Enum

import numpy as np

from src.engine.hpm_engine import calculate_neutralization_probability
from src.engine.physics import update_position


class DroneEstado(str, Enum):
    ACTIVO = "activo"
    NEUTRALIZADO = "neutralizado"
    DANADO = "danado"


class Drone:
    """Representa un dron con posición, movimiento y resistencia al HPM."""

    def __init__(
        self,
        drone_id: int,
        x: float = 0.0,
        y: float = 0.0,
        velocidad: float = 5.0,
        angulo: float = 0.0,
        salud: float = 100.0,
    ) -> None:
        self.id = drone_id
        self.x = x
        self.y = y
        self.velocidad = velocidad
        self.angulo = angulo
        self.salud = salud
        self.estado = DroneEstado.ACTIVO

    def mover(self, dt: float) -> None:
        """Actualiza la posición según velocidad y ángulo."""
        if self.estado == DroneEstado.NEUTRALIZADO:
            return

        self.x, self.y = update_position(
            self.x, self.y, self.velocidad, self.angulo, dt
        )

    def recibir_daño(
        self,
        potencia: float,
        distancia: float,
        angulo_offset: float = 0.0,
        apertura_cono: float = 30.0,
    ) -> bool:
        """
        Calcula probabilidad de neutralización según el modelo HPM.

        Returns:
            True si el dron fue neutralizado en este impacto.
        """
        if self.estado == DroneEstado.NEUTRALIZADO:
            return False

        probabilidad = calculate_neutralization_probability(
            potencia=potencia,
            distancia=distancia,
            angulo_offset=angulo_offset,
            apertura_cono=apertura_cono,
        )

        impacto = float(np.random.random()) < probabilidad
        dano = probabilidad * potencia * 0.5
        self.salud = max(0.0, self.salud - dano)

        if impacto or self.salud <= 0:
            self.estado = DroneEstado.NEUTRALIZADO
            return True

        if self.salud < 50:
            self.estado = DroneEstado.DANADO

        return False
