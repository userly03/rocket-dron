"""Modelo de dron para la simulación EW."""

from __future__ import annotations

import math
from enum import Enum

from numpy.random import Generator

from src.config import (
    DRONE_BOB_AMPLITUDE_M,
    DRONE_BOB_PERIOD_S,
    DRONE_CABLE_LENGTH_MAX_M,
    DRONE_CABLE_LENGTH_MIN_M,
    DRONE_POLARIZATION_MIN,
    HPM_FREQUENCY_GHZ,
    HPM_MODEL,
)
from src.engine.hpm_engine import (
    apply_hardening_odds,
    calculate_neutralization_probability,
    calculate_neutralization_probability_friis,
    resonance_frequency_ghz,
    susceptibility_coupling_factor,
)
from src.engine.physics import update_position
from src.utils.reproducibilidad import rng as global_rng


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
        cable_length_m: float | None = None,
        polarization: float | None = None,
        rng: Generator | None = None,
    ) -> None:
        self.id = drone_id
        self.x = x
        self.y = y
        self.velocidad = velocidad
        self.angulo = angulo
        self.salud = salud
        self.estado = DroneEstado.ACTIVO

        # RNG por instancia (P0-B): None conserva el generador global (mismo
        # comportamiento que antes). Debe fijarse ANTES de los sorteos de
        # cable_length_m/polarization/_bob_phase de abajo, que dependen de
        # ``self._rng()``. Cuando ``Swarm`` construye el dron le pasa su
        # propio generador, para que una réplica de experimento y la
        # simulación interactiva nunca compartan estado aleatorio.
        self.rng = rng

        # Blindaje heterogéneo: un enjambre real no es homogéneo — algunas
        # unidades llevan mejor apantallado/protección que otras, lo que se
        # traduce en un umbral de susceptibilidad (V/m) más alto.
        self.blindaje = blindaje
        self.e_threshold_mult = e_threshold_mult

        # Huella de susceptibilidad: longitud de cableado interno (fija su
        # frecuencia de resonancia y por tanto η(f) a la frecuencia del arma)
        # y factor de mismatch de polarización [0,1]. None → sorteo al crear
        # el dron, como el blindaje.
        self.cable_length_m = (
            cable_length_m
            if cable_length_m is not None
            else float(self._rng().uniform(DRONE_CABLE_LENGTH_MIN_M, DRONE_CABLE_LENGTH_MAX_M))
        )
        self.polarization = (
            polarization
            if polarization is not None
            else float(self._rng().uniform(DRONE_POLARIZATION_MIN, 1.0))
        )

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
        self._bob_phase = float(self._rng().uniform(0, 2 * math.pi))
        self._tiempo_vuelo = 0.0

        # Última probabilidad de neutralización calculada (para reportes/validación).
        self.ultima_probabilidad = 0.0

    def _rng(self) -> Generator:
        """Generador de esta instancia, o el global si no se inyectó ninguno."""
        return self.rng if self.rng is not None else global_rng()

    def factor_acoplamiento(self, frequency_ghz: float = HPM_FREQUENCY_GHZ) -> float:
        """Factor de amplitud acoplada a esta frecuencia: √(η(f_res)·pol)."""
        return susceptibility_coupling_factor(
            self.cable_length_m, self.polarization, frequency_ghz
        )

    def frecuencia_resonancia_ghz(self) -> float:
        return resonance_frequency_ghz(self.cable_length_m)

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
        duty_cycle: float = 1.0,
    ) -> bool:
        """
        Calcula probabilidad de neutralización según el modelo HPM.

        ``duty_cycle`` separa potencia promedio de pico (daño latchup por
        campo instantáneo); 1.0 = CW, compatible con el modelo calibrado.

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
                duty_cycle=duty_cycle,
                cable_length_m=self.cable_length_m,
                polarization=self.polarization,
                frequency_ghz=HPM_FREQUENCY_GHZ,
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
        impacto = float(self._rng().random()) < probabilidad
        dano = probabilidad * potencia * 0.5
        self.salud = max(0.0, self.salud - dano)

        if impacto or self.salud <= 0:
            self.estado = DroneEstado.NEUTRALIZADO
            return True

        if self.salud < 50:
            self.estado = DroneEstado.DANADO

        return False
