"""Sistema de lanzamiento y gestión de misiles HPM."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.config import (
    FIELD_HEIGHT,
    FIELD_WIDTH,
    MISSILE_DEFAULT_POWER,
    MISSILE_DEFAULT_RADIUS,
    MISSILE_DETONATION_DISTANCE,
    MISSILE_MUNITION_TOTAL,
    MISSILE_SPEED,
)
from src.models.drone import Drone, DroneEstado
from src.models.hpm_missile import HPMissile, MissileEstado
from src.engine.hpm_engine import target_angle_from_origin
from src.utils.helpers import distance


DETONATION_DISPLAY_TIME = 2.0


@dataclass
class HPMissileSystem:
    """
    Gestiona la munición y el ciclo de vida de misiles HPM en vuelo.

    Complementa al HPMWeapon (cañón estático de tierra); los misiles son
    proyectiles móviles con efecto de área circular.
    """

    misiles: list[HPMissile] = field(default_factory=list)
    municion_total: int = MISSILE_MUNITION_TOTAL
    municion_restante: int = MISSILE_MUNITION_TOTAL
    _contador: int = field(default=0, init=False, repr=False)

    def lanzar(
        self,
        x: float,
        y: float,
        angulo: float | None,
        potencia: float | None = None,
        radio: float | None = None,
        drones: list[Drone] | None = None,
        guiado: bool = True,
    ) -> dict:
        """
        Crea y lanza un misil HPM hacia el enjambre.

        Si no se indica ángulo, apunta automáticamente al centroide del
        enjambre **detectado por radar** (drones fuera de alcance/probabilidad
        de detección no entran en el cálculo — no se puede apuntar a lo que
        no se ve). Si ``guiado`` es True (por defecto), el misil fija
        ("lock-on") el dron detectado más cercano al centroide como objetivo
        y corrige su rumbo en vuelo (ver ``HPMissile._aplicar_guiado``); si es
        False, vuela balístico con el ángulo inicial fijo.
        """
        if self.municion_restante <= 0:
            return {"success": False, "message": "Sin munición disponible"}

        potencia_hpm = potencia if potencia is not None else MISSILE_DEFAULT_POWER
        radio_efecto = radio if radio is not None else MISSILE_DEFAULT_RADIUS
        activos = [d for d in (drones or []) if d.estado != DroneEstado.NEUTRALIZADO]
        detectados = [d for d in activos if d.detectado]

        if angulo is None:
            if detectados:
                cx = sum(d.x for d in detectados) / len(detectados)
                cy = sum(d.y for d in detectados) / len(detectados)
                angulo = target_angle_from_origin(x, y, cx, cy)
            else:
                angulo = 0.0

        target_id = None
        if detectados:
            objetivo = min(detectados, key=lambda d: distance(x, y, d.x, d.y))
            target_id = objetivo.id

        dist_objetivo = self._estimar_distancia_objetivo(x, y, angulo, drones or [])
        tiempo_detonacion = dist_objetivo / MISSILE_SPEED + 5.0

        self._contador += 1
        misil = HPMissile(
            x=x,
            y=y,
            angulo=angulo,
            potencia_hpm=potencia_hpm,
            radio_efecto=radio_efecto,
            velocidad=MISSILE_SPEED,
            tiempo_detonacion=tiempo_detonacion,
            detonacion_distancia=MISSILE_DETONATION_DISTANCE,
            guiado=guiado,
            target_id=target_id,
        )

        self.misiles.append(misil)
        self.municion_restante -= 1

        return {
            "success": True,
            "message": "Misil HPM lanzado",
            "misil": misil.to_dict(),
            "municion_restante": self.municion_restante,
        }

    def actualizar_misiles(
        self, drones: list[Drone], dt: float
    ) -> list[dict]:
        """
        Actualiza posición de misiles activos y procesa detonaciones.

        Returns:
            Lista de eventos (detonaciones, destrucciones).
        """
        eventos: list[dict] = []
        activos: list[HPMissile] = []

        for misil in self.misiles:
            if misil.estado == MissileEstado.DETONADO:
                misil.tiempo_post_detonacion += dt
                if misil.tiempo_post_detonacion < DETONATION_DISPLAY_TIME:
                    activos.append(misil)
                continue

            if misil.estado == MissileEstado.DESTRUIDO:
                continue

            misil.mover(dt, drones)

            if self._fuera_de_campo(misil):
                misil.estado = MissileEstado.DESTRUIDO
                eventos.append(
                    {
                        "tipo": "misil_destruido",
                        "misil_id": misil.id,
                        "razon": "fuera_de_campo",
                        "x": round(misil.x, 2),
                        "y": round(misil.y, 2),
                    }
                )
                continue

            if misil.debe_detonar(drones):
                impactos = misil.detonar(drones)
                eventos.append(
                    {
                        "tipo": "misil_detonado",
                        "misil_id": misil.id,
                        "x": round(misil.x, 2),
                        "y": round(misil.y, 2),
                        "radio_efecto": misil.radio_efecto,
                        "potencia_hpm": misil.potencia_hpm,
                        "impactos": impactos,
                        "neutralizados": sum(1 for i in impactos if i["neutralizado"]),
                    }
                )
                activos.append(misil)
                continue

            activos.append(misil)

        self.misiles = activos
        return eventos

    def recargar(self, cantidad: int) -> dict:
        """Añade munición al sistema (sin superar el máximo total)."""
        if cantidad <= 0:
            return {
                "message": "Cantidad inválida",
                "municion_restante": self.municion_restante,
            }

        espacio = self.municion_total - self.municion_restante
        añadido = min(cantidad, espacio)
        self.municion_restante += añadido

        return {
            "message": f"Recargados {añadido} misiles",
            "añadido": añadido,
            "municion_restante": self.municion_restante,
            "municion_total": self.municion_total,
        }

    def get_status(self) -> dict:
        return {
            "municion_total": self.municion_total,
            "municion_restante": self.municion_restante,
            "misiles_activos": sum(
                1 for m in self.misiles if m.estado in (MissileEstado.LANZADO, MissileEstado.VOLANDO)
            ),
            "misiles": [m.to_dict() for m in self.misiles],
        }

    def get_munition(self) -> dict:
        return {
            "municion_total": self.municion_total,
            "municion_restante": self.municion_restante,
        }

    def reset(self) -> None:
        self.misiles.clear()
        self.municion_restante = self.municion_total

    def _estimar_distancia_objetivo(
        self,
        x: float,
        y: float,
        angulo: float,
        drones: list[Drone],
    ) -> float:
        activos = [d for d in drones if d.estado != DroneEstado.NEUTRALIZADO]
        if not activos:
            return float(np.hypot(FIELD_WIDTH, FIELD_HEIGHT) * 0.5)

        cx = sum(d.x for d in activos) / len(activos)
        cy = sum(d.y for d in activos) / len(activos)
        dist_centro = distance(x, y, cx, cy)
        return max(MISSILE_DETONATION_DISTANCE, dist_centro - MISSILE_DETONATION_DISTANCE)

    @staticmethod
    def _fuera_de_campo(misil: HPMissile) -> bool:
        margen = 20.0
        return (
            misil.x < -margen
            or misil.x > FIELD_WIDTH + margen
            or misil.y < -margen
            or misil.y > FIELD_HEIGHT + margen
        )
