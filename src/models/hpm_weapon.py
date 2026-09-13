"""Arma HPM (High Power Microwave) con cono de efecto direccional."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.config import (
    HPM_CAPACIDAD_TERMICA_KJ_C,
    HPM_CONE_APERTURE,
    HPM_DEFAULT_ANGLE,
    HPM_DEFAULT_POWER,
    HPM_DISIPACION_KW_C,
    HPM_DISPARO_DURACION_S,
    HPM_DUTY_CYCLE,
    HPM_EFICIENCIA_AMPLIFICADOR,
    HPM_ENERGIA_ALMACENADA_KJ,
    HPM_ORIGIN_Z,
    HPM_RECARGA_KW,
    HPM_TEMP_AMBIENTE_C,
    HPM_TEMP_MAX_C,
)
from src.engine.hpm_engine import compute_target_parameters
from src.models.drone import Drone, DroneEstado
from src.utils.helpers import distance

# Tolerancia numérica para comparaciones de energía/temperatura contra los
# límites del presupuesto (evita rechazos espurios por error de redondeo
# de punto flotante cuando el disparo previo dejó el arma EXACTAMENTE en
# el límite).
_EPS_PRESUPUESTO = 1e-9


@dataclass
class HPMWeapon:
    """
    Cañón HPM estático de tierra (arma direccional fija).

    Dispara un pulso electromagnético en cono desde un origen fijo.
    Para armas móviles de área, ver ``HPMissile`` y ``HPMissileSystem``.
    ``duty_cycle`` separa potencia promedio de pico: con 1.0 (CW) el modelo
    es el calibrado original; con duty < 1 el pico daña como latchup real.

    Presupuesto energético y térmico (P2-F, ver ``src/config.py``): cada
    disparo consume energía de un banco finito (``energia_actual_kj``) y
    deja calor en el amplificador (``temperatura_c``). En sistemas reales
    (Epirus Leonidas, THOR) el límite operativo de la cadencia de tiro no
    es el haz sino la potencia primaria y la refrigeración — este arma lo
    modela explícitamente en vez de disparar infinito y gratis. ``enfriar``/
    ``recargar`` (o ``actualizar``, que llama a ambos) avanzan ese
    presupuesto con el tiempo; el bucle de simulación los llama en cada
    tick (ver ``SimulationEngine._tick``).
    """

    potencia: float = HPM_DEFAULT_POWER
    direccion: float = HPM_DEFAULT_ANGLE
    apertura_cono: float = HPM_CONE_APERTURE
    duty_cycle: float = HPM_DUTY_CYCLE
    origen_x: float = 0.0
    origen_y: float = 0.0
    origen_z: float = HPM_ORIGIN_Z
    # Presupuesto energético/térmico (P2-F). Un arma recién desplegada
    # arranca a plena carga y a temperatura ambiente, no agotada.
    energia_actual_kj: float = HPM_ENERGIA_ALMACENADA_KJ
    temperatura_c: float = HPM_TEMP_AMBIENTE_C
    disparos: int = field(default=0, init=False)
    # Motivo del último rechazo de disparo (energía o temperatura), o
    # ``None`` si el último ``disparar()`` se ejecutó (o si todavía no se
    # llamó nunca). Es el canal por el que ``disparar()`` "dice" por qué no
    # disparó sin usar una excepción — ver su docstring.
    ultimo_rechazo: str | None = field(default=None, init=False)

    def _energia_por_disparo_kj(self, potencia: float | None = None) -> float:
        """
        Energía que consume UN disparo (la ráfaga completa, no un pulso).

        Ver el comentario de ``HPM_DISPARO_DURACION_S`` en ``src/config.py``:
        la energía de un pulso aislado (``potencia · HPM_PULSE_DURATION_NS``)
        es del orden de mJ, irrelevante para cualquier presupuesto. Lo que
        agota el banco y calienta el amplificador es la ráfaga completa de
        pulsos que constituye "un disparo" en este simulador, cuya duración
        es una decisión de modelado (``HPM_DISPARO_DURACION_S``) y no un
        dato de arXiv:2602.08477.
        """
        p = self.potencia if potencia is None else potencia
        return p * HPM_DISPARO_DURACION_S

    def listo_para_disparar(self) -> bool:
        """True si el arma tiene margen térmico y energía para OTRO disparo."""
        return (
            self.temperatura_c < HPM_TEMP_MAX_C - _EPS_PRESUPUESTO
            and self.energia_actual_kj
            >= self._energia_por_disparo_kj() - _EPS_PRESUPUESTO
        )

    def disparar(self, drones: list[Drone]) -> list[dict]:
        """
        Aplica daño HPM a todos los drones dentro del cono de efecto.

        Antes de tocar ningún dron, verifica el presupuesto de la ráfaga
        (P2-F): si el amplificador sigue por encima del límite térmico, o si
        el banco de energía no alcanza para la ráfaga completa, el arma NO
        dispara — dispara "cero veces", no lanza una excepción, deja el
        motivo en ``self.ultimo_rechazo`` y devuelve una lista vacía de
        eventos (indistinguible en la firma de "no había drones en el
        cono", pero distinguible consultando ``ultimo_rechazo``).

        Returns:
            Lista de eventos de impacto por dron afectado (vacía si el
            disparo fue rechazado por presupuesto, o si nadie estaba en el
            cono de efecto).
        """
        self.ultimo_rechazo = None

        if self.temperatura_c >= HPM_TEMP_MAX_C - _EPS_PRESUPUESTO:
            self.ultimo_rechazo = (
                f"temperatura del amplificador ({self.temperatura_c:.1f}°C) "
                f"alcanzó el límite operativo ({HPM_TEMP_MAX_C:.1f}°C) — "
                "requiere enfriar antes de disparar de nuevo"
            )
            return []

        energia_necesaria = self._energia_por_disparo_kj()
        if self.energia_actual_kj < energia_necesaria - _EPS_PRESUPUESTO:
            self.ultimo_rechazo = (
                f"energía insuficiente: disponible {self.energia_actual_kj:.2f} kJ, "
                f"la ráfaga requiere {energia_necesaria:.2f} kJ — esperar recarga"
            )
            return []

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
                origin_z=self.origen_z,
                target_z=drone.z,
            )

            if abs(angulo_offset) > self.apertura_cono / 2.0:
                continue

            # Riesgo latente PREVIO a esta exposición: si ya estaba
            # pendiente sin id de disparo asignado (por ejemplo, un miss
            # anterior no atribuido — no debería ocurrir en la práctica,
            # pero evita atribuir por error un riesgo VIEJO a este disparo).
            tenia_riesgo_sin_atribuir_antes = (
                drone.riesgo_latente_por_s > 0.0 and drone.origen_riesgo_shot_id is None
            )

            neutralizado = drone.recibir_daño(
                potencia=self.potencia,
                distancia=distancia,
                angulo_offset=angulo_offset,
                apertura_cono=self.apertura_cono,
                duty_cycle=self.duty_cycle,
            )

            # P2-D, Parte 3: ¿esta exposición metió al dron en riesgo latente?
            # (o refrescó uno existente) — la marca ``entro_en_riesgo`` es la
            # señal que ``SimulationEngine._atribuir_riesgo_latente`` usa
            # para completar ``origen_riesgo_shot_id`` una vez que
            # ``analytics`` asigna el id real del disparo (que todavía no se
            # conoce en este punto: se asigna DESPUÉS del bucle completo).
            entro_en_riesgo = (
                drone.riesgo_latente_por_s > 0.0
                and drone.origen_riesgo_shot_id is None
                and not tenia_riesgo_sin_atribuir_antes
            )

            eventos.append(
                {
                    "drone_id": drone.id,
                    "distancia": round(distancia, 2),
                    "distancia_horizontal": round(distance(self.origen_x, self.origen_y, drone.x, drone.y), 2),
                    "delta_altitud": round(drone.z - self.origen_z, 2),
                    "angulo_offset": round(angulo_offset, 2),
                    "probabilidad": round(drone.ultima_probabilidad, 4),
                    # Factor de amplitud acoplada del blanco (P2-04): √(η·pol).
                    # Necesario para que check_shot_invariants (validation.py)
                    # pueda condicionar la monotonicidad probabilidad-vs-
                    # distancia por acoplamiento comparable, no solo por
                    # offset angular — ver deuda técnica en
                    # CHECKLIST_MEJORAS.md.
                    "factor_acoplamiento": round(drone.factor_acoplamiento(), 4),
                    "neutralizado": neutralizado,
                    "estado": drone.estado.value,
                    "salud": round(drone.salud, 2),
                    # P2-D: upset/damage — ver docstring de arriba.
                    "entro_en_riesgo": entro_en_riesgo,
                    "riesgo_latente_por_s": round(drone.riesgo_latente_por_s, 6),
                    "subsistema_en_riesgo": drone.subsistema_en_riesgo,
                }
            )

        # Presupuesto: se descuenta SIEMPRE que el disparo se ejecuta, sin
        # importar cuántos drones había en el cono (un disparo al aire
        # también gasta energía y calienta el amplificador de un arma real).
        self.energia_actual_kj -= energia_necesaria
        calor_kj = (1.0 - HPM_EFICIENCIA_AMPLIFICADOR) * energia_necesaria
        self.temperatura_c += calor_kj / HPM_CAPACIDAD_TERMICA_KJ_C

        return eventos

    def enfriar(self, dt: float) -> None:
        """
        Enfriamiento hacia el ambiente por ley de Newton, con la solución
        analítica exacta (no un paso de Euler).

        ``dT/dt = -k·(T - T_ambiente)``, con
        ``k = HPM_DISIPACION_KW_C / HPM_CAPACIDAD_TERMICA_KJ_C`` (kW/°C
        entre kJ/°C = 1/s). Para esta ODE lineal e invariante en el tiempo
        la solución cerrada ``T(t) = T_amb + (T₀-T_amb)·exp(-k·t)`` es EXACTA
        para cualquier ``dt`` — se usa esa forma en vez de integrar paso a
        paso para no introducir error de discretización ni en el tick de
        60 FPS ni en un ``dt`` grande de Monte Carlo.
        """
        if dt <= 0:
            return
        k = HPM_DISIPACION_KW_C / HPM_CAPACIDAD_TERMICA_KJ_C
        self.temperatura_c = HPM_TEMP_AMBIENTE_C + (
            self.temperatura_c - HPM_TEMP_AMBIENTE_C
        ) * math.exp(-k * dt)

    def recargar(self, dt: float) -> None:
        """Recarga lineal del banco de energía desde la potencia primaria,
        acotada al máximo del banco (P2-F)."""
        if dt <= 0:
            return
        self.energia_actual_kj = min(
            HPM_ENERGIA_ALMACENADA_KJ, self.energia_actual_kj + HPM_RECARGA_KW * dt
        )

    def actualizar(self, dt: float) -> None:
        """Avanza enfriamiento y recarga un paso ``dt`` (llamado desde el
        tick de la simulación, ver ``SimulationEngine._tick``)."""
        self.enfriar(dt)
        self.recargar(dt)

    def configurar(
        self,
        potencia: float | None = None,
        direccion: float | None = None,
        apertura_cono: float | None = None,
        duty_cycle: float | None = None,
    ) -> None:
        if potencia is not None:
            self.potencia = potencia
        if direccion is not None:
            self.direccion = direccion % 360
        if apertura_cono is not None:
            self.apertura_cono = apertura_cono
        if duty_cycle is not None:
            self.duty_cycle = float(min(max(duty_cycle, 1e-3), 1.0))

    def to_dict(self) -> dict:
        return {
            "potencia": self.potencia,
            "direccion": self.direccion,
            "apertura_cono": self.apertura_cono,
            "duty_cycle": self.duty_cycle,
            "origen_x": self.origen_x,
            "origen_y": self.origen_y,
            "origen_z": self.origen_z,
            "disparos": self.disparos,
            "energia_actual_kj": round(self.energia_actual_kj, 2),
            "energia_maxima_kj": HPM_ENERGIA_ALMACENADA_KJ,
            "temperatura_c": round(self.temperatura_c, 2),
            "temperatura_max_c": HPM_TEMP_MAX_C,
            "listo_para_disparar": self.listo_para_disparar(),
            "ultimo_rechazo": self.ultimo_rechazo,
        }
