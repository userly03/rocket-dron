"""Modelo de dron para la simulación EW."""

from __future__ import annotations

import math
from enum import Enum

import numpy as np

from src.config import (
    DRONE_BOB_AMPLITUDE_M,
    DRONE_BOB_PERIOD_S,
    HPM_MODEL,
)
from src.engine.hpm_engine import (
    apply_hardening_odds,
    calculate_neutralization_probability,
    calculate_neutralization_probability_friis,
)
from src.engine.physics import update_position


class DroneEstado(str, Enum):
    ACTIVO = "activo"
    NEUTRALIZADO = "neutralizado"
    DANADO = "danado"
    INTERFERIDO = "interferido"


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
        z: float = 100.0,
        blindaje: str = "estandar",
        e_threshold_mult: float = 1.0,
    ) -> None:
        self.id = drone_id
        self.x = x
        self.y = y
        self.velocidad = velocidad
        self.angulo = angulo
        self.salud = salud
        self.estado = DroneEstado.ACTIVO

        # Blindaje heterogéneo: un enjambre real no es homogéneo — algunas
        # unidades llevan mejor apantallado/protección que otras, lo que se
        # traduce en un umbral de susceptibilidad (V/m) más alto.
        self.blindaje = blindaje
        self.e_threshold_mult = e_threshold_mult

        # Radar: si el dron fue detectado por el radar en el tick actual
        # (gobierna la selección automática de blancos, no la física del
        # daño). Default True: "conocido" hasta que Swarm.actualizar() lo
        # reevalúe con el modelo real — evita que drones recién creados (o
        # construidos directamente en tests, sin pasar por Swarm) queden
        # indetectables por omisión.
        self.detectado = True

        # Altitud: cada dron mantiene una altitud de crucero (z_base) y
        # oscila suavemente alrededor de ella (hover/patrulla), no gana ni
        # pierde altitud por su velocidad horizontal.
        self.z_base = z
        self.z = z
        self._bob_phase = float(np.random.uniform(0, 2 * math.pi))
        self._tiempo_vuelo = 0.0

        # Última probabilidad de neutralización calculada (para reportes/validación).
        self.ultima_probabilidad = 0.0

    def mover(self, dt: float) -> None:
        """Actualiza la posición según velocidad y ángulo, y la altitud (oscilación)."""
        if self.estado in (DroneEstado.NEUTRALIZADO, DroneEstado.INTERFERIDO):
            return

        self.x, self.y = update_position(
            self.x, self.y, self.velocidad, self.angulo, dt
        )

        self._tiempo_vuelo += dt
        omega = 2 * math.pi / DRONE_BOB_PERIOD_S
        self.z = self.z_base + DRONE_BOB_AMPLITUDE_M * math.sin(
            omega * self._tiempo_vuelo + self._bob_phase
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

        if HPM_MODEL == "friis":
            probabilidad = calculate_neutralization_probability_friis(
                potencia_kw=potencia,
                distancia=distancia,
                apertura_cono=apertura_cono,
                angulo_offset=angulo_offset,
            )
            # Blindaje: reducción proporcional en espacio de momios, no
            # desplazando el umbral E (ver apply_hardening_odds — desplazar
            # el umbral colapsaba la probabilidad a ~0 en casi todo el rango
            # de combate, no la reducía de forma proporcional).
            probabilidad = apply_hardening_odds(probabilidad, self.e_threshold_mult)
        else:
            probabilidad = calculate_neutralization_probability(
                potencia=potencia,
                distancia=distancia,
                angulo_offset=angulo_offset,
                apertura_cono=apertura_cono,
            )

        self.ultima_probabilidad = probabilidad
        impacto = float(np.random.random()) < probabilidad
        dano = probabilidad * potencia * 0.5
        self.salud = max(0.0, self.salud - dano)

        if impacto or self.salud <= 0:
            self.estado = DroneEstado.NEUTRALIZADO
            return True

        if self.salud < 50:
            self.estado = DroneEstado.DANADO

        return False
