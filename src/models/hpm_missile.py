"""Misil HPM móvil (estilo CHAMP) — arma de área con detonación electromagnética."""

from __future__ import annotations

import uuid
from enum import Enum

import numpy as np

from src.config import HPM_K_CONSTANT, MISSILE_DETONATION_DISTANCE, MISSILE_SPEED
from src.engine.hpm_engine import calculate_area_neutralization_probability
from src.engine.physics import update_position
from src.models.drone import Drone, DroneEstado
from src.utils.helpers import distance


class MissileEstado(str, Enum):
    LANZADO = "lanzado"
    VOLANDO = "volando"
    DETONADO = "detonado"
    DESTRUIDO = "destruido"


class HPMissile:
    """
    Proyectil HPM que vuela hacia el enjambre y detona a distancia óptima.

    A diferencia del cañón HPM estático (HPMWeapon), este misil produce un
    efecto de área circular (soft-kill) sin destrucción física del blanco.
    """

    def __init__(
        self,
        x: float,
        y: float,
        angulo: float,
        potencia_hpm: float,
        radio_efecto: float,
        velocidad: float = MISSILE_SPEED,
        tiempo_detonacion: float | None = None,
        detonacion_distancia: float = MISSILE_DETONATION_DISTANCE,
        missile_id: str | None = None,
    ) -> None:
        self.id = missile_id or f"missile-{uuid.uuid4().hex[:8]}"
        self.x = x
        self.y = y
        self.velocidad = float(velocidad)
        self.angulo = angulo % 360
        self.estado = MissileEstado.LANZADO
        self.potencia_hpm = potencia_hpm
        self.radio_efecto = float(np.clip(radio_efecto, 50.0, 200.0))
        self.tiempo_detonacion = tiempo_detonacion or 30.0
        self.tiempo_vuelo = 0.0
        self.detonacion_distancia = detonacion_distancia
        self.tiempo_post_detonacion = 0.0

    def mover(self, dt: float) -> None:
        """Actualiza posición según velocidad y ángulo de vuelo."""
        if self.estado not in (MissileEstado.LANZADO, MissileEstado.VOLANDO):
            return

        self.x, self.y = update_position(
            self.x, self.y, self.velocidad, self.angulo, dt
        )
        self.tiempo_vuelo += dt
        self.tiempo_detonacion = max(0.0, self.tiempo_detonacion - dt)

        if self.estado == MissileEstado.LANZADO:
            self.estado = MissileEstado.VOLANDO

    def calcular_daño(self, dron: Drone, distancia: float) -> float:
        """
        Probabilidad de neutralización por efecto HPM de área (modelo CHAMP).

        P = 1 - exp(-k * potencia / distancia²)
        """
        if distancia > self.radio_efecto:
            return 0.0
        return calculate_area_neutralization_probability(
            potencia=self.potencia_hpm,
            distancia=distancia,
            k=HPM_K_CONSTANT,
        )

    def detonar(self, drones: list[Drone]) -> list[dict]:
        """
        Detona el pulso HPM en área. Soft-kill: paraliza drones sin explosión física.

        Returns:
            Lista de eventos de impacto por dron afectado.
        """
        if self.estado == MissileEstado.DETONADO:
            return []

        self.estado = MissileEstado.DETONADO
        self.tiempo_post_detonacion = 0.0
        eventos: list[dict] = []

        for drone in drones:
            if drone.estado == DroneEstado.NEUTRALIZADO:
                continue

            dist = distance(self.x, self.y, drone.x, drone.y)
            if dist > self.radio_efecto:
                continue

            probabilidad = self.calcular_daño(drone, dist)
            neutralizado = False

            if float(np.random.random()) < probabilidad:
                drone.estado = DroneEstado.NEUTRALIZADO
                drone.salud = 0.0
                drone.velocidad = 0.0
                neutralizado = True
            elif probabilidad > 0:
                dano = probabilidad * self.potencia_hpm * 0.5
                drone.salud = max(0.0, drone.salud - dano)
                if drone.salud < 50:
                    drone.estado = DroneEstado.DANADO

            eventos.append(
                {
                    "drone_id": drone.id,
                    "distancia": round(dist, 2),
                    "probabilidad": round(probabilidad, 4),
                    "neutralizado": neutralizado,
                    "estado": drone.estado.value,
                    "salud": round(drone.salud, 2),
                    "tipo": "soft_kill",
                }
            )

        return eventos

    def debe_detonar(self, drones: list[Drone]) -> bool:
        """Verifica si el misil alcanzó la distancia óptima de detonación."""
        if self.tiempo_detonacion <= 0:
            return True

        activos = [d for d in drones if d.estado != DroneEstado.NEUTRALIZADO]
        if not activos:
            return self.tiempo_vuelo > 5.0

        distancias = [distance(self.x, self.y, d.x, d.y) for d in activos]
        min_dist = min(distancias)
        return min_dist <= self.detonacion_distancia

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "velocidad": round(self.velocidad, 2),
            "angulo": round(self.angulo, 2),
            "estado": self.estado.value,
            "potencia_hpm": self.potencia_hpm,
            "radio_efecto": self.radio_efecto,
            "tiempo_detonacion": round(self.tiempo_detonacion, 3),
            "tiempo_vuelo": round(self.tiempo_vuelo, 3),
        }
