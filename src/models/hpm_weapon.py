"""Arma HPM (High Power Microwave) con cono de efecto direccional."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import HPM_CONE_APERTURE, HPM_DEFAULT_ANGLE, HPM_DEFAULT_POWER
from src.engine.hpm_engine import compute_target_parameters
from src.models.drone import Drone, DroneEstado


@dataclass
class HPMWeapon:
    """
    Cañón HPM estático de tierra (arma direccional fija).

    Dispara un pulso electromagnético en cono desde un origen fijo.
    Para armas móviles de área, ver ``HPMissile`` y ``HPMissileSystem``.
    """

    potencia: float = HPM_DEFAULT_POWER
    direccion: float = HPM_DEFAULT_ANGLE
    apertura_cono: float = HPM_CONE_APERTURE
    origen_x: float = 0.0
    origen_y: float = 0.0
    disparos: int = field(default=0, init=False)

    def disparar(self, drones: list[Drone]) -> list[dict]:
        """
        Aplica daño HPM a todos los drones dentro del cono de efecto.

        Returns:
            Lista de eventos de impacto por dron afectado.
        """
        self.disparos += 1
        eventos: list[dict] = []

        for drone in drones:
            if drone.estado == DroneEstado.NEUTRALIZADO:
                continue

            distancia, angulo_offset = compute_target_parameters(
                self.origen_x,
                self.origen_y,
                self.direccion,
                drone.x,
                drone.y,
            )

            if abs(angulo_offset) > self.apertura_cono / 2.0:
                continue

            neutralizado = drone.recibir_daño(
                potencia=self.potencia,
                distancia=distancia,
                angulo_offset=angulo_offset,
                apertura_cono=self.apertura_cono,
            )

            eventos.append(
                {
                    "drone_id": drone.id,
                    "distancia": round(distancia, 2),
                    "angulo_offset": round(angulo_offset, 2),
                    "neutralizado": neutralizado,
                    "estado": drone.estado.value,
                    "salud": round(drone.salud, 2),
                }
            )

        return eventos

    def configurar(
        self,
        potencia: float | None = None,
        direccion: float | None = None,
        apertura_cono: float | None = None,
    ) -> None:
        if potencia is not None:
            self.potencia = potencia
        if direccion is not None:
            self.direccion = direccion % 360
        if apertura_cono is not None:
            self.apertura_cono = apertura_cono

    def to_dict(self) -> dict:
        return {
            "potencia": self.potencia,
            "direccion": self.direccion,
            "apertura_cono": self.apertura_cono,
            "origen_x": self.origen_x,
            "origen_y": self.origen_y,
            "disparos": self.disparos,
        }
