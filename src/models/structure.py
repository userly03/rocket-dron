"""Estructuras atacables (edificios) — objetivos alternativos al vehículo
para la misión ofensiva del enjambre (ver SimulationEngine.estructuras_
activas, Swarm.objetivo_x/y)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import (
    ESTRUCTURA_DANO_POR_DRON,
    ESTRUCTURA_RADIO_BLOQUEO_M,
    ESTRUCTURA_SALUD_MAXIMA,
)


@dataclass
class Estructura:
    """
    Un edificio con posición fija y salud propia — a diferencia del
    vehículo (HPMWeapon.destruido, un único impacto kamikaze lo
    inutiliza), acá hace falta que lleguen VARIOS drones: son drones FPV
    chicos contra una construcción real, no contra electrónica expuesta.
    Ver ESTRUCTURA_DANO_POR_DRON en src/config.py para el porqué del
    número de drones que hacen falta.

    No tiene lógica de movimiento/física propia — es un punto fijo que
    SimulationEngine ofrece como candidato a objetivo del enjambre junto
    con la posición del vehículo (ver _elegir_objetivo_enjambre), y cuya
    salud se descuenta cuando un dron marcado ``objetivo_alcanzado``
    llegó estando ESTA la estructura activa como objetivo en ese tick.
    """

    id: int
    x: float
    y: float
    nombre: str = ""
    salud_maxima: float = ESTRUCTURA_SALUD_MAXIMA
    salud: float = field(init=False)
    # Línea de vista (ver hpm_engine.linea_de_vista_bloqueada): el radio
    # del círculo que bloquea el haz. Una estructura destruida deja de
    # bloquear (ver SimulationEngine._obstaculos_activos) — un edificio
    # caído ya no es un obstáculo sólido.
    radio_bloqueo: float = ESTRUCTURA_RADIO_BLOQUEO_M
    destruida: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.salud = self.salud_maxima

    def recibir_impacto_kamikaze(self, dano: float = ESTRUCTURA_DANO_POR_DRON) -> bool:
        """Un dron que llegó la daña. Devuelve True si este impacto la
        destruyó (transición, no repite en impactos posteriores sobre
        una estructura ya destruida — no-op silencioso, mismo criterio
        que HPMWeapon.disparar sobre un arma ya destruida)."""
        if self.destruida:
            return False
        self.salud = max(0.0, self.salud - dano)
        if self.salud <= 0.0:
            self.destruida = True
            return True
        return False

    def reset(self) -> None:
        self.salud = self.salud_maxima
        self.destruida = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "nombre": self.nombre,
            "salud": round(self.salud, 1),
            "salud_maxima": self.salud_maxima,
            "destruida": self.destruida,
        }
