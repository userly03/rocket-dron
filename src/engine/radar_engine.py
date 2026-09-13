"""
Motor de radar de detección: ecuación de radar clásica + probabilidad de
detección aproximada por una sigmoide sobre la relación señal-ruido (SNR).

Complementa al motor HPM (que calcula si un pulso *daña* a un blanco ya
conocido): este módulo decide si el blanco *se conoce* en primer lugar —
antes de esta fase, el simulador tenía conocimiento omnisciente de la
posición exacta de cada dron; ahora hay que detectarlo primero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from src.config import (
    RADAR_FILTRO_ALPHA,
    RADAR_FILTRO_BETA,
    RADAR_FILTRO_GAMMA,
    RADAR_PERDIDA_TRACK_RESIDUAL_M,
    RADAR_REVISITA_S,
    RADAR_SIGMOID_STEEPNESS,
    RADAR_SNR_THRESHOLD_DB,
)

SPEED_OF_LIGHT_M_S = 299_792_458.0


def wavelength_m(frequency_ghz: float) -> float:
    """Longitud de onda: λ = c / f."""
    return SPEED_OF_LIGHT_M_S / (frequency_ghz * 1e9)


def radar_received_power_w(
    pt_w: float,
    gain_linear: float,
    wavelength_m_: float,
    rcs_m2: float,
    distancia_m: float,
) -> float:
    """
    Ecuación de radar (monoestático: misma antena transmite y recibe, de ahí G²):

        Pr = (Pt · G² · λ² · σ) / ((4π)³ · r⁴)

    `σ` (``rcs_m2``) es la sección transversal de radar del blanco — el
    "tamaño eléctrico" que ve el radar, no el tamaño físico real.
    """
    r = max(distancia_m, 1e-6)
    return (pt_w * gain_linear**2 * wavelength_m_**2 * rcs_m2) / ((4.0 * np.pi) ** 3 * r**4)


def detection_probability(
    pr_w: float,
    noise_floor_w: float,
    snr_threshold_db: float = RADAR_SNR_THRESHOLD_DB,
    steepness: float = RADAR_SIGMOID_STEEPNESS,
) -> float:
    """
    Probabilidad de detección aproximada mediante una sigmoide sobre la
    relación señal-ruido (SNR, en dB) respecto a un umbral de referencia.

    Simplificación deliberada: la teoría de detección de radar real usa la
    función Q de Marcum (curvas Pd/Pfa de modelos Swerling), bastante más
    compleja. Una sigmoide sobre el SNR en dB reproduce la misma forma
    cualitativa (transición suave alrededor de un SNR umbral) sin esa
    complejidad — mismo patrón de modelado que la sigmoide de daño HPM.
    Ver docs/FISICA_Y_MATEMATICA.md.
    """
    if pr_w <= 0 or noise_floor_w <= 0:
        return 0.0
    snr_db = 10.0 * np.log10(pr_w / noise_floor_w)
    probabilidad = 1.0 / (1.0 + np.exp(-steepness * (snr_db - snr_threshold_db)))
    return float(np.clip(probabilidad, 0.0, 1.0))


def evaluar_deteccion(
    distancia_m: float,
    pt_w: float,
    gain_dbi: float,
    frequency_ghz: float,
    rcs_m2: float,
    noise_floor_w: float,
) -> tuple[bool, float]:
    """
    Evalúa si un blanco a ``distancia_m`` queda detectado por el radar.

    Decisión determinística sobre la probabilidad (>=50%) en vez de un sorteo
    aleatorio por tick — evita parpadeo cuadro a cuadro del estado
    "detectado" cuando la probabilidad ronda el 50%; equivale a asumir que,
    una vez con SNR suficiente, el radar mantiene un track estable.

    Returns:
        Tupla ``(detectado, probabilidad)``.
    """
    gain_linear = 10.0 ** (gain_dbi / 10.0)
    wl = wavelength_m(frequency_ghz)
    pr = radar_received_power_w(pt_w, gain_linear, wl, rcs_m2, distancia_m)
    probabilidad = detection_probability(pr, noise_floor_w)
    return probabilidad >= 0.5, probabilidad


# ═══════════════════════════════════════════════════════════════════════════
# P2-G, Paso 1+2 · TrackManager — de un booleano omnisciente a tracks con
# estado propio (posición estimada, velocidad, edad) y barrido periódico con
# filtro α-β-γ
# ═══════════════════════════════════════════════════════════════════════════
#
# ANTES: ``evaluar_deteccion()`` se llamaba una vez por dron, cada tick,
# dentro de ``Swarm.actualizar`` — decisión instantánea sobre la posición
# VERDADERA, sin memoria. El booleano resultante (``drone.detectado``) era la
# única fuente de verdad, y todo lo que "sabía" del dron (incluida su
# posición) seguía siendo la real: un radar omnisciente que solo decide si
# REVELA lo que ya sabe, no un sensor con incertidumbre.
#
# AHORA: ``TrackManager`` mantiene, por dron, un ``Track`` con posición y
# velocidad ESTIMADAS (no la real) que se actualiza dos formas distintas
# según el momento:
#   - CADA TICK, por propagación (dead-reckoning) según el último estado
#     estimado — el track "camina solo" entre mediciones.
#   - SOLO EN CADA REVISITA (``RADAR_REVISITA_S``, un barrido periódico como
#     un radar rotatorio real), se toma una medición fresca y se corrige la
#     predicción con el filtro α-β-γ — o se declara el track PERDIDO si la
#     medición está demasiado lejos de lo que el filtro predecía (una
#     maniobra que el modelo de aceleración constante no explica), o si el
#     dron ya no cumple la ecuación de radar (rango/SNR).
#
# ``drone.detectado`` se conserva como el booleano de compatibilidad (True
# mientras haya un track vivo) — todo el código que ya lo consume
# (``HPMissile._resolver_objetivo``, ``HPMissileSystem.lanzar``) sigue
# funcionando sin cambios de firma, pero P2-G además expone el track
# completo (``TrackManager.get_track``) para que esos dos consumidores
# migren a la posición ESTIMADA en vez de la real (ver el comentario de
# ``HPM_REVISITA_S`` en ``src/config.py`` sobre qué números calibrados
# mueve eso).


@dataclass
class Track:
    """Estado estimado de un blanco bajo seguimiento radar."""

    drone_id: int
    x: float
    y: float
    z: float
    vx: float = 0.0
    vy: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    edad_ticks: int = 0
    tiempo_desde_revisita_s: float = 0.0
    # Cuenta cuántas revisitas CONSECUTIVAS confirmaron el track con una
    # medición real (no solo el "nacimiento" del track) — diagnóstico de
    # calidad, no gobierna ninguna decisión todavía.
    revisitas_confirmadas: int = 0

    def posicion_estimada(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class TrackManager:
    """
    Radar de barrido: mantiene un ``Track`` por dron detectado, con
    posición/velocidad ESTIMADAS y un ciclo de revisita periódico (ver el
    docstring del módulo arriba).

    Un objeto por arma-radar (igual que ``HPMWeapon``/``Jammer`` son un
    objeto por arma) — ``Swarm`` mantiene su propia instancia.
    """

    alpha: float = RADAR_FILTRO_ALPHA
    beta: float = RADAR_FILTRO_BETA
    gamma: float = RADAR_FILTRO_GAMMA
    revisita_s: float = RADAR_REVISITA_S
    umbral_perdida_m: float = RADAR_PERDIDA_TRACK_RESIDUAL_M
    tracks: dict[int, Track] = field(default_factory=dict)
    _reloj_barrido_s: float = field(default=0.0, init=False, repr=False)

    def get_track(self, drone_id: int) -> Track | None:
        return self.tracks.get(drone_id)

    def fase_barrido(self) -> float:
        """Fracción [0,1) transcurrida del ciclo de revisita actual — 0 justo
        después de un barrido, cerca de 1 justo antes del próximo. Puramente
        informativo (ej. animar el "ping" de refresco en el frontend); no
        gobierna ninguna decisión del motor."""
        if self.revisita_s <= 0:
            return 0.0
        return min(1.0, self._reloj_barrido_s / self.revisita_s)

    def tracks_activos(self) -> list[Track]:
        return list(self.tracks.values())

    def posicion_para(self, drone) -> tuple[float, float, float]:
        """
        Posición a usar para TARGETING (P2-G, Paso 2): la ESTIMADA por el
        track si existe, la VERDADERA del dron como respaldo defensivo (no
        debería hacer falta si ``drone.detectado`` ya refleja la existencia
        de un track — ver ``TrackManager.actualizar`` — pero evita que un
        consumidor externo con datos inconsistentes rompa en vez de
        degradar). Usada por ``HPMissile._resolver_objetivo`` y
        ``HPMissileSystem.lanzar`` para no apuntar con la posición real de
        un blanco que el radar de tierra solo conoce de forma aproximada.
        """
        track = self.tracks.get(drone.id)
        if track is not None:
            return track.x, track.y, track.z
        return drone.x, drone.y, drone.z

    def _propagar(self, dt: float) -> None:
        """Dead-reckoning: cada tick, todos los tracks vivos avanzan según
        su último estado estimado (aceleración constante), sin medición
        nueva. Es lo que permite que un dron siga "visto" entre revisitas.
        """
        for track in self.tracks.values():
            track.x += track.vx * dt + 0.5 * track.ax * dt * dt
            track.y += track.vy * dt + 0.5 * track.ay * dt * dt
            track.vx += track.ax * dt
            track.vy += track.ay * dt
            track.edad_ticks += 1

    def actualizar(
        self,
        drones: list,
        dt: float,
        origen_x: float,
        origen_y: float,
        origen_z: float,
        pt_w: float,
        gain_dbi: float,
        frequency_ghz: float,
        rcs_m2: float,
        noise_floor_w: float,
    ) -> None:
        """
        Avanza el radar un paso ``dt``: propaga todos los tracks vivos, y —
        solo si se cumplió el ciclo de revisita— toma una medición fresca
        por dron, actualiza el filtro α-β-γ, crea tracks nuevos y descarta
        los perdidos (por rango/SNR o por maniobra).

        Dron por dron: ``drones`` deben exponer ``.id``, ``.x``, ``.y``,
        ``.z`` y un atributo ``.detectado`` asignable — es decir, cualquier
        ``Drone`` real. Se importa ``distance3d`` acá (no al tope del
        módulo) para no crear un ciclo con ``src.utils.helpers``.
        """
        from src.utils.helpers import distance3d

        self._propagar(dt)

        for drone in drones:
            drone.detectado = drone.id in self.tracks

        self._reloj_barrido_s += dt
        if self._reloj_barrido_s < self.revisita_s:
            return
        self._reloj_barrido_s = 0.0

        for drone in drones:
            dist = distance3d(origen_x, origen_y, origen_z, drone.x, drone.y, drone.z)
            detectado, _probabilidad = evaluar_deteccion(
                dist, pt_w, gain_dbi, frequency_ghz, rcs_m2, noise_floor_w
            )
            track = self.tracks.get(drone.id)

            if not detectado:
                # Fuera de rango/SNR en esta revisita: se pierde el track
                # (si existía) — un radar real tampoco "recuerda" un blanco
                # que ya no puede ver.
                self.tracks.pop(drone.id, None)
                drone.detectado = False
                continue

            if track is None:
                # Adquisición nueva: el track nace exactamente en la
                # medición, sin velocidad estimada todavía (la primera
                # revisita no tiene con qué compararse).
                self.tracks[drone.id] = Track(
                    drone_id=drone.id, x=drone.x, y=drone.y, z=drone.z
                )
                drone.detectado = True
                continue

            residual_x = drone.x - track.x
            residual_y = drone.y - track.y
            residual_m = math.hypot(residual_x, residual_y)

            if residual_m > self.umbral_perdida_m:
                # La medición real está demasiado lejos de lo que el
                # modelo de aceleración constante predecía: una maniobra
                # así de abrupta rompe el filtro (no es ruido de medición,
                # es un cambio real de comportamiento) — se pierde el
                # track. Readquirirlo exige una revisita nueva que SÍ
                # detecte, empezando de cero (sin velocidad estimada).
                self.tracks.pop(drone.id, None)
                drone.detectado = False
                continue

            # Corrección α-β-γ estándar: la ganancia de velocidad/
            # aceleración se normaliza por el intervalo de revisita, que es
            # el ``dt`` real entre dos mediciones (no el ``dt`` de
            # simulación, que puede ser mucho más corto).
            track.x += self.alpha * residual_x
            track.y += self.alpha * residual_y
            track.vx += (self.beta / self.revisita_s) * residual_x
            track.vy += (self.beta / self.revisita_s) * residual_y
            track.ax += (2.0 * self.gamma / self.revisita_s**2) * residual_x
            track.ay += (2.0 * self.gamma / self.revisita_s**2) * residual_y
            track.revisitas_confirmadas += 1
            drone.detectado = True
