"""Jammer de comunicaciones — arma continua de negación de enlace (no daño físico)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.config import (
    JAMMING_CONE_APERTURE,
    JAMMING_DEFAULT_POWER,
    JAMMING_E_THRESHOLD_V_M,
    JAMMING_SIGMOID_STEEPNESS,
)
from src.engine.hpm_engine import compute_target_parameters, friis_diagnostics
from src.models.drone import Drone, DroneEstado


@dataclass
class Jammer:
    """
    Jammer de comunicaciones: cono direccional que niega el enlace de
    control de drones dentro de su zona de efecto, sin dañar su electrónica
    (a diferencia del cañón/misil HPM — mismo motor Friis/sigmoide, pero un
    umbral y una interpretación distintos: "probabilidad de perder el
    enlace", no "probabilidad de daño permanente").

    A diferencia del cañón (pulso único) o el misil (detonación única), el
    jammer es un arma **continua**: mientras ``activo``, se reevalúa cada
    tick — un dron sale de ``INTERFERIDO`` en cuanto deja la zona de efecto
    o el jammer se apaga (falla segura real: un dron sin enlace vuelve a
    responder apenas recupera la señal).
    """

    activo: bool = False
    potencia: float = JAMMING_DEFAULT_POWER
    direccion: float = 0.0
    apertura_cono: float = JAMMING_CONE_APERTURE
    origen_x: float = 0.0
    origen_y: float = 0.0
    origen_z: float = 0.0

    def iniciar(
        self,
        direccion: float,
        potencia: float | None = None,
        apertura_cono: float | None = None,
    ) -> None:
        self.activo = True
        self.direccion = direccion % 360
        if potencia is not None:
            self.potencia = potencia
        if apertura_cono is not None:
            self.apertura_cono = apertura_cono

    def detener(self) -> None:
        self.activo = False

    def _en_zona_de_efecto(self, drone: Drone) -> bool:
        if not self.activo:
            return False

        distancia, angulo_offset = compute_target_parameters(
            self.origen_x,
            self.origen_y,
            self.direccion,
            drone.x,
            drone.y,
            origin_z=self.origen_z,
            target_z=drone.z,
        )
        if abs(angulo_offset) > self.apertura_cono / 2.0:
            return False

        diag = friis_diagnostics(self.potencia, distancia, self.apertura_cono, angulo_offset)
        exponent = -JAMMING_SIGMOID_STEEPNESS * (diag["campo_e_v_m"] - JAMMING_E_THRESHOLD_V_M)
        probabilidad = 1.0 / (1.0 + np.exp(exponent))
        return bool(probabilidad >= 0.5)

    def actualizar(self, drones: list[Drone]) -> list[dict]:
        """
        Reevalúa, para cada dron no neutralizado, si queda (o deja de
        estar) ``INTERFERIDO``.

        Returns:
            Lista de eventos de cambio de estado (para log/terminal).
        """
        eventos: list[dict] = []

        for drone in drones:
            if drone.estado == DroneEstado.NEUTRALIZADO:
                continue

            en_zona = self._en_zona_de_efecto(drone)
            estaba_interferido = drone.estado == DroneEstado.INTERFERIDO

            if en_zona and not estaba_interferido:
                drone.estado = DroneEstado.INTERFERIDO
                eventos.append({"tipo": "dron_interferido", "drone_id": drone.id})
            elif not en_zona and estaba_interferido:
                drone.estado = DroneEstado.DANADO if drone.salud < 50 else DroneEstado.ACTIVO
                eventos.append({"tipo": "dron_recuperado", "drone_id": drone.id})

        return eventos

    def to_dict(self) -> dict:
        return {
            "activo": self.activo,
            "potencia": self.potencia,
            "direccion": self.direccion,
            "apertura_cono": self.apertura_cono,
            "origen_x": self.origen_x,
            "origen_y": self.origen_y,
            "origen_z": self.origen_z,
        }
