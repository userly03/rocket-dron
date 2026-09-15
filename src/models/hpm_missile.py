"""Misil HPM móvil (estilo CHAMP) — arma de área con detonación electromagnética."""

from __future__ import annotations

import uuid
from enum import Enum

import numpy as np
from numpy.random import Generator

from src.config import (
    HPM_DUTY_CYCLE,
    HPM_K_CONSTANT,
    HPM_MISSILE_LOGLOGISTIC_B,
    HPM_MISSILE_LOGLOGISTIC_E50_V_M,
    HPM_MODEL,
    MISSILE_CRUISE_ALTITUDE_M,
    MISSILE_DETONACION_DURACION_S,
    MISSILE_DETONATION_DISTANCE,
    MISSILE_LAUNCH_ALTITUDE_M,
    MISSILE_MAX_TURN_RATE_DEG_S,
    MISSILE_PN_GAIN,
    MISSILE_SPEED,
)
from src.engine.hpm_engine import (
    apply_hardening_odds,
    calculate_area_neutralization_probability,
    calculate_area_neutralization_probability_friis,
    e50_upset_desde_damage,
    energia_absorbida_j,
    linea_de_vista_bloqueada,
    target_angle_from_origin,
)
from src.engine.physics import update_position
from src.models.drone import Drone, DroneEstado, EstadoSalud
from src.utils.helpers import angle_difference, distance, distance3d
from src.utils.reproducibilidad import rng as global_rng


class MissileEstado(str, Enum):
    LANZADO = "lanzado"
    VOLANDO = "volando"
    DETONADO = "detonado"
    DESTRUIDO = "destruido"


# Perfil de altitud: la altitud "deseada" en cada tick es crucero mientras
# el blanco más cercano esté lejos, y se interpola hacia SU altitud a medida
# que la distancia horizontal se acerca a la de detonación. El misil
# converge hacia esa altitud deseada a una tasa limitada (m/s), no de golpe
# ni por una fracción de un tiempo ESTIMADO al lanzar — con guiado activo y
# un enjambre que maniobra (boids), la detonación real puede ocurrir mucho
# antes o después de lo estimado, y un perfil atado al tiempo dejaba al
# misil detonando aún en altitud de crucero muy por encima de los drones
# (ver docs/FISICA_Y_MATEMATICA.md). Para blancos muy cercanos al lanzar,
# el misil simplemente no alcanza a subir/bajar del todo — físicamente
# correcto para un sistema con tasa de cambio de altitud limitada.
_DESCENT_START_DISTANCE_MULT = 4.0
# Tasa de cambio de altitud del mismo orden que la velocidad horizontal —
# consistente con la agilidad ya elevada del interceptor (ver
# MISSILE_MAX_TURN_RATE_DEG_S en config.py): sin esto, cerrar el hueco de
# altitud completo (crucero -> blanco) en la ventana de descenso requeriría
# una tasa mayor a la aquí elegida cuando la distancia horizontal se cierra
# a máxima velocidad.
_ALTITUDE_RATE_M_S = 400.0


class HPMissile:
    """
    Proyectil HPM que vuela hacia el enjambre y detona a distancia óptima.

    A diferencia del cañón HPM estático (HPMWeapon), este misil produce un
    efecto de área circular (soft-kill) sin destrucción física del blanco.

    Tiene un perfil de vuelo con altitud real (ascenso/crucero/descenso) y,
    si ``guiado=True``, corrige su rumbo en cada tick mediante navegación
    proporcional (PN) hacia un blanco fijado ("lock-on"), en vez de volar en
    línea recta balística.
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
        guiado: bool = True,
        target_id: int | None = None,
        duty_cycle: float = HPM_DUTY_CYCLE,
        rng: Generator | None = None,
    ) -> None:
        self.id = missile_id or f"missile-{uuid.uuid4().hex[:8]}"
        self.x = x
        self.y = y
        self.velocidad = float(velocidad)
        self.angulo = angulo % 360
        self.estado = MissileEstado.LANZADO
        self.potencia_hpm = potencia_hpm
        self.duty_cycle = float(np.clip(duty_cycle, 1e-3, 1.0))
        self.radio_efecto = float(np.clip(radio_efecto, 50.0, 200.0))
        self.tiempo_detonacion = tiempo_detonacion or 30.0
        self.tiempo_vuelo = 0.0
        self.detonacion_distancia = detonacion_distancia
        self.tiempo_post_detonacion = 0.0

        # Altitud: perfil ascenso -> crucero -> descenso hacia el objetivo.
        self.z = MISSILE_LAUNCH_ALTITUDE_M

        # Guiado por navegación proporcional (PN).
        self.guiado = guiado
        self.target_id = target_id
        self._prev_los_angle: float | None = None

        # Detonación por punto de máxima cercanía (ver debe_detonar).
        self._prev_min_dist: float | None = None

        # RNG por instancia (P0-B): None conserva el generador global. El
        # sistema de lanzamiento (``HPMissileSystem``) le pasa su propio
        # generador a cada misil que crea, igual que ``Swarm`` a sus drones.
        self.rng = rng

    def _rng(self) -> Generator:
        """Generador de esta instancia, o el global si no se inyectó ninguno."""
        return self.rng if self.rng is not None else global_rng()

    def mover(
        self,
        dt: float,
        drones: list[Drone] | None = None,
        track_manager=None,
    ) -> None:
        """
        Actualiza posición, altitud y (si está guiado) rumbo del misil.

        ``drones`` es opcional y retrocompatible: sin lista de drones el
        misil vuela balístico (ángulo fijo), igual que antes.

        ``track_manager`` (P2-G, Paso 2): el ``TrackManager`` del radar de
        tierra, para que la ADQUISICIÓN de un blanco NUEVO (``
        _resolver_objetivo``) use la posición ESTIMADA del track en vez de
        la verdadera. ``None`` (default) conserva el comportamiento previo
        a P2-G — retrocompatible para quien llame a ``mover`` sin él.
        """
        if self.estado not in (MissileEstado.LANZADO, MissileEstado.VOLANDO):
            return

        if self.guiado and drones:
            self._aplicar_guiado(dt, drones, track_manager)

        self.x, self.y = update_position(
            self.x, self.y, self.velocidad, self.angulo, dt
        )
        self.tiempo_vuelo += dt
        self.tiempo_detonacion = max(0.0, self.tiempo_detonacion - dt)
        self._actualizar_altitud(drones, dt)

        if self.estado == MissileEstado.LANZADO:
            self.estado = MissileEstado.VOLANDO

    def _resolver_objetivo(self, drones: list[Drone], track_manager=None) -> Drone | None:
        """
        Devuelve el dron fijado, o re-engancha al detectado más cercano si
        el objetivo previo fue neutralizado.

        El seguimiento de un blanco YA fijado ("lock-on") no requiere
        detección continua del radar de tierra (el buscador propio del
        misil mantiene el track, como en un misil real) — este método
        sigue devolviendo el ``Drone`` directamente, y la navegación en
        ``_aplicar_guiado`` sigue usando su posición VERDADERA sin importar
        cómo se resolvió acá: el buscador propio del misil se asume
        perfecto una vez adquirido, un supuesto que P2-G no toca.

        Re-enganchar a un blanco *nuevo* sí requiere que esté detectado —no
        se puede adquirir lo que no se ve— y ACÁ es donde P2-G, Paso 2 sí
        cambia algo: entre los candidatos detectados, el "más cercano" se
        decide por la posición ESTIMADA del track (``track_manager``), no la
        verdadera — es la posición que el radar de tierra realmente conoce
        en el momento de la adquisición. Con ``track_manager=None``
        (retrocompatible) se usa la posición verdadera, igual que antes de
        P2-G.
        """
        activos = [d for d in drones if d.estado != DroneEstado.NEUTRALIZADO]
        if not activos:
            return None

        if self.target_id is not None:
            for d in activos:
                if d.id == self.target_id:
                    return d

        detectados = [d for d in activos if d.detectado]
        if not detectados:
            return None

        if track_manager is not None:
            def _distancia_estimada(d: Drone) -> float:
                tx, ty, _tz = track_manager.posicion_para(d)
                return distance(self.x, self.y, tx, ty)

            objetivo = min(detectados, key=_distancia_estimada)
        else:
            objetivo = min(detectados, key=lambda d: distance(self.x, self.y, d.x, d.y))
        self.target_id = objetivo.id
        return objetivo

    def _aplicar_guiado(self, dt: float, drones: list[Drone], track_manager=None) -> None:
        """
        Ley de navegación proporcional (PN) simplificada:

            tasa_LOS = Δ(ángulo línea-de-visión) / dt
            comando_giro = N · tasa_LOS   (N = MISSILE_PN_GAIN)

        Se omite el término de velocidad de cierre (simplificación válida
        para un misil de velocidad ~constante) y el giro se limita a
        MISSILE_MAX_TURN_RATE_DEG_S para que la corrección de rumbo sea
        físicamente plausible (no un "snap" instantáneo al objetivo).
        """
        if dt <= 0:
            return

        objetivo = self._resolver_objetivo(drones, track_manager)
        if objetivo is None:
            return

        # Navegación: SIEMPRE con la posición VERDADERA del objetivo, una
        # vez resuelto — el buscador propio del misil (no el radar de
        # tierra) es lo que lo guía en vuelo, con o sin track_manager. Solo
        # la ADQUISICIÓN de arriba (_resolver_objetivo) consulta el track.
        los_angle = target_angle_from_origin(self.x, self.y, objetivo.x, objetivo.y)

        if self._prev_los_angle is None:
            self._prev_los_angle = los_angle
            return

        tasa_los = angle_difference(self._prev_los_angle, los_angle) / dt
        self._prev_los_angle = los_angle

        comando_giro_deg_s = MISSILE_PN_GAIN * tasa_los
        max_giro = MISSILE_MAX_TURN_RATE_DEG_S * dt
        giro = float(np.clip(comando_giro_deg_s * dt, -max_giro, max_giro))
        self.angulo = (self.angulo + giro) % 360

    def _actualizar_altitud(self, drones: list[Drone] | None, dt: float) -> None:
        activos = [d for d in (drones or []) if d.estado != DroneEstado.NEUTRALIZADO]

        if not activos:
            z_deseado = MISSILE_CRUISE_ALTITUDE_M
        else:
            # Distancia horizontal al dron activo más cercano — misma
            # componente que usa ``debe_detonar`` para decidir la detonación
            # por cercanía — gobierna CUÁNDO empezar a descender.
            objetivo = min(activos, key=lambda d: distance(self.x, self.y, d.x, d.y))
            dist_horizontal = distance(self.x, self.y, objetivo.x, objetivo.y)
            descent_start = self.detonacion_distancia * _DESCENT_START_DISTANCE_MULT

            if dist_horizontal >= descent_start:
                z_deseado = MISSILE_CRUISE_ALTITUDE_M
            else:
                # A QUÉ altitud descender: el promedio de altitud de TODOS
                # los drones activos dentro del rango de descenso —
                # ponderado por la inversa de su distancia horizontal — no
                # solo la del más cercano. Con formaciones que escalonan
                # altitud (p. ej. la circular, en anillos), apuntar a un
                # único dron deja al resto del grupo fuera del radio 3D
                # aunque estén horizontalmente cerca; centrar la detonación
                # en el promedio del grupo maximiza cuántos caen dentro.
                cercanos = [
                    d for d in activos
                    if distance(self.x, self.y, d.x, d.y) <= descent_start
                ]
                pesos = [
                    1.0 / max(distance(self.x, self.y, d.x, d.y), 1.0)
                    for d in cercanos
                ]
                z_grupo = sum(p * d.z for p, d in zip(pesos, cercanos)) / sum(pesos)

                t = 1.0 - float(
                    np.clip(
                        (dist_horizontal - self.detonacion_distancia)
                        / max(descent_start - self.detonacion_distancia, 1e-6),
                        0.0,
                        1.0,
                    )
                )
                z_deseado = MISSILE_CRUISE_ALTITUDE_M + (z_grupo - MISSILE_CRUISE_ALTITUDE_M) * t

        max_delta = _ALTITUDE_RATE_M_S * dt
        self.z += float(np.clip(z_deseado - self.z, -max_delta, max_delta))

    def calcular_daño(
        self,
        dron: Drone,
        distancia: float,
        e50: float | None = None,
        b: float | None = None,
    ) -> float:
        """
        Probabilidad de neutralización por efecto HPM de área (modelo CHAMP).

        Modelo "friis" (por defecto): física real vía densidad de potencia
        y campo E (ver ``calculate_area_neutralization_probability_friis``).
        Modelo "legacy": exponencial ad-hoc original — P = 1 - exp(-k·P/d²).

        ``e50``/``b`` (P2-D): permiten pedir la probabilidad con un umbral
        DISTINTO al de daño calibrado — usado por ``detonar`` para calcular
        también ``p_upset`` con el mismo campo pero un umbral más bajo (ver
        ``e50_upset_desde_damage``). ``None`` (default) usa los umbrales
        calibrados del misil, comportamiento idéntico al de antes de P2-D.
        """
        if distancia > self.radio_efecto:
            return 0.0

        if HPM_MODEL == "friis":
            kwargs = dict(
                potencia_kw=self.potencia_hpm,
                distancia=distancia,
                duty_cycle=self.duty_cycle,
                cable_length_m=dron.cable_length_m,
                polarization=dron.polarization,
            )
            if e50 is not None:
                kwargs["e50"] = e50
            if b is not None:
                kwargs["b"] = b
            probabilidad = calculate_area_neutralization_probability_friis(**kwargs)
            # Blindaje: reducción proporcional en espacio de momios (ver
            # apply_hardening_odds) — NO desplazar el umbral E, eso colapsaba
            # la probabilidad de los drones blindados a ~0 en casi todo el
            # rango de combate en vez de reducirla proporcionalmente.
            return apply_hardening_odds(probabilidad, dron.e_threshold_mult)

        return calculate_area_neutralization_probability(
            potencia=self.potencia_hpm,
            distancia=distancia,
            k=HPM_K_CONSTANT,
        )

    def detonar(
        self,
        drones: list[Drone],
        obstaculos: list[tuple[float, float, float]] | None = None,
    ) -> list[dict]:
        """
        Detona el pulso HPM en área. Soft-kill: paraliza drones sin explosión física.

        ``obstaculos`` (línea de vista, ver ``HPMWeapon.disparar`` para el
        mismo mecanismo): un dron dentro del radio de efecto pero detrás
        de un obstáculo no recibe daño — aparece en ``eventos`` con
        ``"bloqueado": True``, ``probabilidad``/``neutralizado`` en 0/False,
        sin tocar ``drone.recibir_daño``. ``None`` (default) es CERO
        obstáculos, comportamiento idéntico al de antes de esto.

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

            dist = distance3d(self.x, self.y, self.z, drone.x, drone.y, drone.z)
            if dist > self.radio_efecto:
                continue

            if linea_de_vista_bloqueada(self.x, self.y, drone.x, drone.y, obstaculos):
                eventos.append(
                    {
                        "drone_id": drone.id,
                        "distancia": round(dist, 2),
                        "distancia_horizontal": round(distance(self.x, self.y, drone.x, drone.y), 2),
                        "delta_altitud": round(drone.z - self.z, 2),
                        "probabilidad": 0.0,
                        "factor_acoplamiento": round(drone.factor_acoplamiento(), 4),
                        "neutralizado": False,
                        "estado": drone.estado.value,
                        "salud": round(drone.salud, 2),
                        "tipo": "soft_kill",
                        "entro_en_riesgo": False,
                        "riesgo_latente_por_s": round(drone.riesgo_latente_por_s, 6),
                        "subsistema_en_riesgo": drone.subsistema_en_riesgo,
                        "bloqueado": True,
                    }
                )
                continue

            probabilidad = self.calcular_daño(drone, dist)
            neutralizado = False
            entro_en_riesgo = False

            # P2-D, Parte 2: energía absorbida en unidades reales (solo modelo
            # "friis" — ver el razonamiento en Drone.recibir_daño sobre por
            # qué el modelo "legacy" ad-hoc conserva su aritmética original).
            # Apertura 360°/offset 0: el misil es un radiador de área, sin
            # cono direccional (ver calcular_daño / friis_diagnostics).
            if HPM_MODEL == "friis":
                drone.energia_absorbida_j += energia_absorbida_j(
                    potencia_kw=self.potencia_hpm,
                    distancia=dist,
                    apertura_cono=360.0,
                    angulo_offset=0.0,
                    duty_cycle=self.duty_cycle,
                    cable_length_m=drone.cable_length_m,
                    duracion_exposicion_s=MISSILE_DETONACION_DURACION_S,
                )

            # Umbral de UPSET (P2-D, Parte 3): mismo campo, umbral del misil
            # más bajo. Ver Drone.recibir_daño para el razonamiento completo
            # — acá el misil es un objeto EXTERNO al dron, así que no puede
            # reutilizar la lógica interna de recibir_daño; usa el método
            # público compartido ``entrar_en_riesgo_latente``.
            p_upset = probabilidad
            if HPM_MODEL == "friis":
                p_upset = self.calcular_daño(
                    drone, dist,
                    e50=e50_upset_desde_damage(HPM_MISSILE_LOGLOGISTIC_E50_V_M),
                    b=HPM_MISSILE_LOGLOGISTIC_B,
                )

            tenia_riesgo_sin_atribuir_antes = (
                drone.riesgo_latente_por_s > 0.0 and drone.origen_riesgo_shot_id is None
            )

            u = float(self._rng().random())

            if u < probabilidad:
                drone.estado = DroneEstado.NEUTRALIZADO
                drone.salud = 0.0
                drone.velocidad = 0.0
                drone.riesgo_latente_por_s = 0.0
                drone.subsistema_en_riesgo = None
                neutralizado = True
            elif HPM_MODEL == "friis" and u < p_upset:
                ancho_zona = max(p_upset - probabilidad, 1e-12)
                severidad = (p_upset - u) / ancho_zona
                drone.entrar_en_riesgo_latente(severidad, dist)
                entro_en_riesgo = not tenia_riesgo_sin_atribuir_antes
            elif HPM_MODEL != "friis" and probabilidad > 0:
                # Modelo "legacy": misma aritmética ad-hoc de siempre, sin
                # zona de upset (ver Drone.recibir_daño para el razonamiento
                # de por qué no se toca el camino ad-hoc).
                dano = probabilidad * self.potencia_hpm * 0.5
                drone.salud = max(0.0, drone.salud - dano)
                if drone.salud < 50:
                    drone.estado = DroneEstado.DANADO

            eventos.append(
                {
                    "drone_id": drone.id,
                    "distancia": round(dist, 2),
                    "distancia_horizontal": round(distance(self.x, self.y, drone.x, drone.y), 2),
                    "delta_altitud": round(drone.z - self.z, 2),
                    "probabilidad": round(probabilidad, 4),
                    # Factor de amplitud acoplada del blanco (P2-04), igual
                    # que en HPMWeapon.disparar() — ver ese comentario. Sin
                    # esto, check_shot_invariants no puede distinguir "misma
                    # distancia, distinto cableado/polarización" de una
                    # verdadera violación de monotonía.
                    "factor_acoplamiento": round(drone.factor_acoplamiento(), 4),
                    "neutralizado": neutralizado,
                    "estado": drone.estado.value,
                    "salud": round(drone.salud, 2),
                    "tipo": "soft_kill",
                    # P2-D: upset/damage — ver hpm_weapon.py para el mismo patrón.
                    "entro_en_riesgo": entro_en_riesgo,
                    "riesgo_latente_por_s": round(drone.riesgo_latente_por_s, 6),
                    "subsistema_en_riesgo": drone.subsistema_en_riesgo,
                    "bloqueado": False,
                }
            )

        return eventos

    def debe_detonar(self, drones: list[Drone]) -> bool:
        """
        Verifica si el misil alcanzó el punto óptimo de detonación.

        ``detonacion_distancia`` es la distancia de "armado" (a partir de
        ahí el fusible de proximidad empieza a vigilar), no el gatillo
        inmediato: mientras la distancia al dron activo más cercano siga
        DISMINUYENDO, el misil sigue acercándose (más cerca = campo E mucho
        más intenso, ver §3 de docs/FISICA_Y_MATEMATICA.md). Recién cuando
        esa distancia empieza a AUMENTAR (pasó el punto de máxima cercanía y
        se está alejando) detona — así, no lo hace en el peor momento
        posible (justo al cruzar el umbral) sino en el mejor momento
        posible dentro del vuelo real. Es el mismo principio que un fusible
        de proximidad real (VT fuze): detona en el punto de aproximación
        más cercana, no en el primer cruce de un radio.

        Regresión encontrada por el usuario: antes se detonaba apenas
        cruzaba ``detonacion_distancia`` (p. ej. a 80m si el umbral era 80),
        incluso si el misil seguía cerrando distancia y podría haber llegado
        mucho más cerca (con muchísima más probabilidad de derribo) un
        instante después.
        """
        if self.tiempo_detonacion <= 0:
            return True

        activos = [d for d in drones if d.estado != DroneEstado.NEUTRALIZADO]
        if not activos:
            return self.tiempo_vuelo > 5.0

        distancias = [
            distance3d(self.x, self.y, self.z, d.x, d.y, d.z) for d in activos
        ]
        min_dist = min(distancias)

        if min_dist > self.detonacion_distancia:
            self._prev_min_dist = min_dist
            return False

        alejandose = self._prev_min_dist is not None and min_dist > self._prev_min_dist
        self._prev_min_dist = min_dist
        return alejandose

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "z": round(self.z, 2),
            "velocidad": round(self.velocidad, 2),
            "angulo": round(self.angulo, 2),
            "estado": self.estado.value,
            "potencia_hpm": self.potencia_hpm,
            "duty_cycle": self.duty_cycle,
            "radio_efecto": self.radio_efecto,
            "tiempo_detonacion": round(self.tiempo_detonacion, 3),
            "tiempo_vuelo": round(self.tiempo_vuelo, 3),
            "guiado": self.guiado,
            "target_id": self.target_id,
        }
