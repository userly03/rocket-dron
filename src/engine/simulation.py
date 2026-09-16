"""Motor principal de simulación a 60 FPS."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from numpy.random import Generator

from src.config import (
    FIELD_HEIGHT,
    FIELD_WIDTH,
    HPM_ORIGIN_X,
    HPM_ORIGIN_Y,
    HPM_ORIGIN_Z,
    SIMULATION_FPS,
    SWARM_SIZE,
)
from src.engine.analytics import PhysicsAnalytics
from src.engine.validation import log_shot
from src.models.hpm_weapon import HPMWeapon
from src.models.hpm_missile import MissileEstado
from src.models.hpm_system import HPMissileSystem
from src.models.jammer import Jammer
from src.models.structure import Estructura
from src.models.swarm import FormacionTipo, Swarm
from src.utils.helpers import drone_to_dict
from src.utils.reproducibilidad import rng as global_rng

validacion_logger = logging.getLogger("simulador.validacion")


class SimulationState(str, Enum):
    DETENIDA = "detenida"
    EJECUTANDO = "ejecutando"
    PAUSADA = "pausada"


@dataclass
class SimulationEngine:
    """Bucle de simulación con estado, logs y callbacks de actualización."""

    fps: int = SIMULATION_FPS
    swarm_size: int = SWARM_SIZE
    swarm: Swarm = field(default_factory=Swarm)
    hpm: HPMWeapon = field(default_factory=HPMWeapon)
    missile_system: HPMissileSystem = field(default_factory=HPMissileSystem)
    jammer: Jammer = field(default_factory=Jammer)
    analytics: PhysicsAnalytics = field(default_factory=PhysicsAnalytics)
    # RNG por instancia (P0-B): None (default) conserva el comportamiento
    # previo a esta fase — swarm/misiles/dron sortean del generador global
    # de src.utils.reproducibilidad. Un valor no-None (típicamente
    # ``nuevo_generador(seed)``) aísla por completo la aleatoriedad de esta
    # instancia: es lo que usa cada réplica de un experimento Monte Carlo
    # (src/engine/experiments.py) para no compartir estado con el hilo de
    # la simulación interactiva ni con otras réplicas/experimentos
    # corriendo en paralelo. Ver docs/AUDITORIA_CHECKLIST.md §3.1.
    rng: Generator | None = None
    # Misión ofensiva del enjambre (ver el bloque de comentarios en
    # src/config.py): False (default) conserva el comportamiento previo a
    # este ítem — el enjambre patrulla, no avanza hacia nada. La app en
    # vivo (src/main.py) lo activa explícitamente; los runners de Monte
    # Carlo/coevolución (src/engine/experiments.py) NO, para no invalidar
    # en silencio la calibración de distancia/potencia ya hecha con el
    # enjambre estático.
    mision_activa: bool = False
    # Kamikaze: el primer dron que llega al objetivo (ver mision_activa)
    # inutiliza la plataforma (cañón Y lanzador de misiles — comparten
    # vehículo) en vez de solo registrarse como "brecha" estadística.
    # False (default) conserva el comportamiento de antes de este ítem —
    # necesita mision_activa=True para poder disparar siquiera (sin
    # misión nadie llega a ningún lado), pero es un flag APARTE, no
    # implícito en mision_activa: los experimentos Monte Carlo/
    # coevolución que ya usan con_mision=True (ver src/engine/
    # experiments.py) miden fraccion_alcanzo_objetivo/probabilidad_brecha
    # asumiendo que el arma sigue disparando el resto de la réplica
    # después de una brecha — activar esto ahí cambiaría esos resultados
    # en silencio. Solo la app en vivo (src/main.py) lo activa.
    kamikaze_activo: bool = False
    # Edificios atacables (ver src/models/structure.py): objetivos
    # ALTERNATIVOS al vehículo — el enjambre elige el más cercano entre
    # el vehículo (si no está destruido) y cada estructura no destruida
    # (ver _elegir_objetivo_enjambre). Mismo criterio que kamikaze_activo:
    # flag APARTE de mision_activa, no implícito — con_mision=True en
    # Monte Carlo/coevolución asume UN solo objetivo posible (el arma);
    # agregar estructuras ahí cambiaría en silencio qué mide
    # fraccion_alcanzo_objetivo/probabilidad_brecha. Solo la app en vivo
    # lo activa. Requiere mision_activa=True (si no, nadie tiene
    # objetivo, con o sin estructuras).
    estructuras_activas: bool = False
    estructuras: list[Estructura] = field(default_factory=list, init=False)
    # Qué objetivo está activo ESTE tick — ("vehiculo", None) o
    # ("estructura", id). Lo fija _elegir_objetivo_enjambre, lo consume
    # _registrar_impactos_en_objetivo para saber a quién dañar cuando
    # llega un dron (sin esto, "llegó al objetivo" no dice a CUÁL).
    _objetivo_actual: tuple[str, int | None] = field(
        default=("vehiculo", None), init=False, repr=False
    )
    estado: SimulationState = SimulationState.DETENIDA
    tiempo: float = 0.0
    tick: int = 0
    time_scale: float = 1.0
    logs: deque = field(default_factory=lambda: deque(maxlen=500))
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _listeners: list[Callable[[dict[str, Any]], None]] = field(
        default_factory=list, init=False, repr=False
    )
    _async_listeners: list[Callable[[dict[str, Any]], Any]] = field(
        default_factory=list, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.hpm.origen_x = HPM_ORIGIN_X
        self.hpm.origen_y = HPM_ORIGIN_Y
        self.jammer.origen_x = HPM_ORIGIN_X
        self.jammer.origen_y = HPM_ORIGIN_Y
        self.jammer.origen_z = HPM_ORIGIN_Z

        # Misión ofensiva: el objetivo por defecto es el propio origen del
        # arma — el motivo más simple de que el enjambre esté ahí es que
        # va contra la batería que lo enfrenta. Si algún día se quiere un
        # objetivo distinto (un activo defendido en otra posición), esto
        # es lo único que hay que cambiar.
        if self.mision_activa:
            self.swarm.objetivo_x = HPM_ORIGIN_X
            self.swarm.objetivo_y = HPM_ORIGIN_Y

        # Edificios atacables: un pueblito chico (4 casas/depósito) en la
        # esquina OPUESTA al vehículo (que arranca en HPM_ORIGIN=(0,0)) —
        # a propósito, para que el enjambre tenga una elección táctica
        # real entre dos direcciones distintas, no un objetivo "de
        # paso" camino al vehículo. Layout propio, no medido — ver
        # docs/SEGUIMIENTO_SESION.md por el criterio.
        if self.estructuras_activas:
            self.estructuras = [
                Estructura(id=0, x=780.0, y=800.0, nombre="Casa 1"),
                Estructura(id=1, x=820.0, y=795.0, nombre="Casa 2"),
                Estructura(id=2, x=800.0, y=830.0, nombre="Depósito"),
                Estructura(id=3, x=835.0, y=825.0, nombre="Casa 3"),
            ]

        # Propagar el generador de esta instancia a los sub-sistemas que lo
        # consumen. ``swarm``/``missile_system`` llegan construidos por su
        # ``default_factory`` (sin generador, self.rng aún no existía) —
        # hay que reasignarlo ANTES de poblar el enjambre, para que hasta el
        # primer sorteo (posiciones/blindaje/cableado/polarización de los
        # drones iniciales) quede aislado cuando se inyectó un generador.
        # El jammer no sortea nada (umbral determinístico, ver Jammer), así
        # que no tiene generador que propagar.
        self.swarm.rng = self.rng
        self.missile_system.rng = self.rng

        self.swarm.inicializar_formacion(FormacionTipo.CUADRADA.value, self.swarm_size)
        self._log("simulacion_inicializada", {"drones": self.swarm_size})

    def _rng(self) -> Generator:
        """Generador de esta instancia, o el global si no se inyectó ninguno."""
        return self.rng if self.rng is not None else global_rng()

    def _log(self, evento: str, datos: dict | None = None) -> None:
        entrada = {
            "timestamp": round(self.tiempo, 3),
            "tick": self.tick,
            "evento": evento,
            "datos": datos or {},
        }
        self.logs.append(entrada)

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(callback)

    def add_async_listener(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        self._async_listeners.append(callback)

    def _notify_listeners(self, payload: dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(payload)
            except Exception:
                pass

    def _notify_async_listeners(self, payload: dict[str, Any]) -> None:
        for listener in self._async_listeners:
            try:
                result = listener(payload)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                pass

    def _build_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "estado": self.estado.value,
                "tiempo": round(self.tiempo, 3),
                "tick": self.tick,
                "fps": self.fps,
                "time_scale": self.time_scale,
                "field": {"width": FIELD_WIDTH, "height": FIELD_HEIGHT},
                "drones": [
                    drone_to_dict(d, track_manager=self.swarm.track_manager)
                    for d in self.swarm.drones
                ],
                "conteo_estados": self.swarm.contar_por_estado(),
                "mision": {
                    "activa": self.swarm.objetivo_x is not None,
                    "objetivo_x": self.swarm.objetivo_x,
                    "objetivo_y": self.swarm.objetivo_y,
                    "objetivo_tipo": self._objetivo_actual[0],
                    "objetivo_id": self._objetivo_actual[1],
                    "brechas": self.swarm.contar_objetivo_alcanzado(),
                },
                "estructuras": [e.to_dict() for e in self.estructuras],
                "radar": {
                    # Posición ACTUAL del vehículo, no el origen fijo — el
                    # radar comparte emplazamiento con el cañón y ya sigue
                    # su posición real tras "shoot and scoot" (ver
                    # Swarm.actualizar/origen_radar_x/y en _tick). Antes
                    # este campo del snapshot se había quedado con las
                    # constantes fijas HPM_ORIGIN_X/Y mientras la física de
                    # detección ya usaba la posición viva — el anillo de
                    # barrido del frontend se dibujaba en el punto viejo
                    # aunque la detección real siguiera al vehículo movido
                    # (bug encontrado en auditoría de backend, no de física:
                    # el mismo patrón "seguir al vehículo" se corrigió en
                    # un lugar y no se buscó en los demás).
                    "origen_x": self.hpm.origen_x,
                    "origen_y": self.hpm.origen_y,
                    "revisita_s": self.swarm.track_manager.revisita_s,
                    "fase_barrido": round(self.swarm.track_manager.fase_barrido(), 4),
                },
                "hpm": self.hpm.to_dict(),
                "missiles": self.missile_system.get_status(),
                "jammer": self.jammer.to_dict(),
                "analytics": self.analytics.to_snapshot(
                    self.hpm.to_dict(),
                    self.missile_system.misiles,
                    swarm=self.swarm,
                ),
            }

    def load_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """Aplica un escenario predefinido: formación, cantidad y parámetros HPM."""
        self.configure_swarm(scenario.get("formacion"), scenario.get("cantidad"))

        hpm_cfg = scenario.get("hpm") or {}
        with self._lock:
            self.hpm.configurar(
                potencia=hpm_cfg.get("potencia"),
                direccion=hpm_cfg.get("direccion"),
                apertura_cono=hpm_cfg.get("apertura_cono"),
            )
            if "origen_x" in hpm_cfg:
                self.hpm.origen_x = hpm_cfg["origen_x"]
            if "origen_y" in hpm_cfg:
                self.hpm.origen_y = hpm_cfg["origen_y"]

        self._log("escenario_cargado", {"nombre": scenario.get("nombre", "?")})
        return self.get_status()

    def set_speed(self, escala: float) -> dict[str, Any]:
        """Ajusta el multiplicador de velocidad de la simulación (1x, 2x, 5x, 10x...)."""
        escala = max(0.1, min(10.0, escala))
        with self._lock:
            self.time_scale = escala
        self._log("velocidad_cambiada", {"escala": escala})
        return {"message": f"Velocidad de simulación: {escala}x", "time_scale": escala}

    def configure_swarm(self, formacion: str | None, cantidad: int | None) -> None:
        """Reconfigura formación y/o cantidad del enjambre de forma independiente."""
        if not formacion and not cantidad:
            return

        with self._lock:
            formacion = formacion or self.swarm.formacion.value
            cantidad = cantidad or self.swarm_size
            self.swarm.inicializar_formacion(formacion, cantidad)
            self.swarm_size = cantidad

    def start(self) -> dict[str, str]:
        with self._lock:
            if self.estado == SimulationState.EJECUTANDO:
                return {"message": "La simulación ya está en ejecución"}

            self.estado = SimulationState.EJECUTANDO
            self._stop_event.clear()

            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run_loop, daemon=True, name="simulation-loop"
                )
                self._thread.start()

        self._log("simulacion_iniciada")
        return {"message": "Simulación iniciada", "estado": self.estado.value}

    def stop(self) -> dict[str, str]:
        with self._lock:
            self.estado = SimulationState.PAUSADA

        self._log("simulacion_pausada")
        return {"message": "Simulación pausada", "estado": self.estado.value}

    def reset(self) -> dict[str, str]:
        self.stop()
        with self._lock:
            self.tiempo = 0.0
            self.tick = 0
            self.logs.clear()
            self.swarm.inicializar_formacion(
                self.swarm.formacion.value, self.swarm_size
            )
            self.hpm.disparos = 0
            self.hpm.destruido = False
            self.hpm.detener_movimiento()
            self.hpm.origen_x = HPM_ORIGIN_X
            self.hpm.origen_y = HPM_ORIGIN_Y
            self.missile_system.reset()
            self.jammer.detener()
            self.jammer.origen_x = HPM_ORIGIN_X
            self.jammer.origen_y = HPM_ORIGIN_Y
            for estructura in self.estructuras:
                estructura.reset()
            self._objetivo_actual = ("vehiculo", None)
            # Sin esto, swarm.objetivo_x/y quedan con el valor de la
            # corrida anterior (solo se recalculan dentro de _tick, que no
            # corre mientras está detenida) — cualquiera que consulte
            # /api/status entre este reset() y el próximo start() vería un
            # objetivo de misión viejo, inconsistente con _objetivo_actual
            # de la línea de arriba (bug encontrado en auditoría de
            # backend). Se autocuraba en el primer tick si mision_activa,
            # pero el snapshot podía mentir mientras tanto.
            self.swarm.objetivo_x = None
            self.swarm.objetivo_y = None
            self.analytics.reset()
            self.estado = SimulationState.DETENIDA

        self._log("simulacion_reiniciada")
        return {"message": "Simulación reiniciada", "estado": self.estado.value}

    def start_jamming(
        self,
        direccion: float,
        potencia: float | None = None,
        apertura_cono: float | None = None,
    ) -> dict[str, Any]:
        """Activa el jammer de comunicaciones (arma continua, no un pulso único)."""
        with self._lock:
            self.jammer.iniciar(direccion, potencia, apertura_cono)
            self._ensure_thread_running()

        self._log(
            "jamming_iniciado",
            {
                "direccion": self.jammer.direccion,
                "potencia": self.jammer.potencia,
                "apertura_cono": self.jammer.apertura_cono,
            },
        )
        return {"message": "Jamming activado", "jammer": self.jammer.to_dict()}

    def stop_jamming(self) -> dict[str, Any]:
        with self._lock:
            self.jammer.detener()
        self._log("jamming_detenido")
        return {"message": "Jamming desactivado", "jammer": self.jammer.to_dict()}

    def mover_plataforma(self, x: float, y: float) -> dict[str, Any]:
        """Ordena al vehículo (cañón + misil + jammer, mismo emplazamiento)
        reposicionarse a (x, y) — "shoot and scoot": mientras viaja no
        puede disparar (ver HPMWeapon.listo_para_disparar), llega solo,
        ver HPMWeapon.actualizar_movimiento en cada tick."""
        x = float(min(max(x, 0.0), FIELD_WIDTH))
        y = float(min(max(y, 0.0), FIELD_HEIGHT))
        with self._lock:
            if self.hpm.destruido:
                return {
                    "success": False,
                    "message": "plataforma destruida — no puede moverse",
                }
            # Un destino DENTRO del radio de bloqueo de una estructura activa
            # deja al vehículo dentro de su propio obstáculo: la geometría de
            # linea_de_vista_bloqueada da bloqueado=True para CUALQUIER
            # dirección cuando el origen del segmento cae dentro del círculo
            # (el "disparo a través de su propio escombro"), así que cañón,
            # misil y radar quedarían ciegos hacia todo el mapa, en silencio,
            # sin ningún mensaje — bug encontrado en auditoría de backend
            # (ronda 2). Se rechaza en vez de recortar el destino: no hay un
            # borde "correcto" obvio del círculo hacia el que recortar sin
            # más contexto de hacia dónde venía el vehículo.
            for estructura in self.estructuras:
                if estructura.destruida:
                    continue
                dist = math.hypot(x - estructura.x, y - estructura.y)
                if dist <= estructura.radio_bloqueo:
                    return {
                        "success": False,
                        "message": (
                            f"destino a {dist:.0f}m del centro de "
                            f"'{estructura.nombre or estructura.id}' — dentro de "
                            f"su radio de bloqueo ({estructura.radio_bloqueo:.0f}m), "
                            "el vehículo quedaría ciego hacia todo el mapa"
                        ),
                    }
            self.hpm.iniciar_movimiento(x, y)
        self._log("plataforma_en_movimiento", {"destino_x": x, "destino_y": y})
        return {"success": True, "message": f"Reposicionando a ({x:.0f}, {y:.0f})", "hpm": self.hpm.to_dict()}

    def fire(
        self,
        potencia: float | None = None,
        direccion: float | None = None,
        apertura_cono: float | None = None,
        duty_cycle: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self.hpm.configurar(potencia, direccion, apertura_cono, duty_cycle)
            eventos = self.hpm.disparar(self.swarm.drones, obstaculos=self._obstaculos_activos())
            rechazo = self.hpm.ultimo_rechazo

            if rechazo is not None:
                # Presupuesto energético/térmico (P2-F): el arma rechazó el
                # disparo ANTES de tocar el enjambre. Camino limpio, sin
                # excepción — no hay evento de disparo que registrar en
                # analíticas/log porque el disparo no ocurrió.
                self._log("hpm_disparo_rechazado", {"motivo": rechazo})
                return {
                    "message": f"Disparo rechazado: {rechazo}",
                    "eventos": [],
                    "hpm": self.hpm.to_dict(),
                    "conteo_estados": self.swarm.contar_por_estado(),
                }

            shot = self.analytics.record_cannon_shot(
                self.hpm.potencia,
                self.hpm.direccion,
                eventos,
                self.tiempo,
                self.hpm.origen_x,
                self.hpm.origen_y,
            )

            self._sembrar_memoria_amenaza(eventos, self.hpm.origen_x, self.hpm.origen_y)
            self._atribuir_riesgo_latente(eventos, shot["id"])

        self._log(
            "hpm_disparo",
            {
                "potencia": self.hpm.potencia,
                "direccion": self.hpm.direccion,
                "afectados": len(eventos),
                "neutralizados": sum(1 for e in eventos if e["neutralizado"]),
                "shot_id": shot["id"],
                "impactos": [
                    {"drone_id": e["drone_id"], "neutralizado": e["neutralizado"]}
                    for e in eventos
                ],
            },
        )
        log_shot(
            "CAÑÓN HPM",
            {
                "tiempo": self.tiempo,
                "potencia_kw": self.hpm.potencia,
                "direccion": round(self.hpm.direccion, 1),
                "apertura_cono": self.hpm.apertura_cono,
            },
            eventos,
        )

        snapshot = self._build_snapshot()
        self._notify_listeners(snapshot)
        self._notify_async_listeners(snapshot)

        return {
            "message": "HPM disparado",
            "eventos": eventos,
            "hpm": self.hpm.to_dict(),
            "conteo_estados": self.swarm.contar_por_estado(),
        }

    def _ensure_thread_running(self) -> None:
        """Arranca el hilo de simulación si no está activo (p. ej. misil en vuelo)."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._run_loop, daemon=True, name="simulation-loop"
                )
                self._thread.start()

    def launch_missile(
        self,
        x: float,
        y: float,
        angulo: float | None = None,
        potencia: float | None = None,
        radio: float | None = None,
        guiado: bool = True,
        duty_cycle: float | None = None,
    ) -> dict[str, Any]:
        """Lanza un misil HPM hacia el enjambre."""
        with self._lock:
            if self.hpm.en_movimiento:
                # Mismo criterio "shoot and scoot" que el cañón (ver
                # HPMWeapon.listo_para_disparar) — el lanzador comparte
                # vehículo, tampoco dispara en tránsito. HPMissileSystem
                # no conoce el estado de movimiento del cañón (son clases
                # separadas), así que se rechaza acá, no adentro de
                # missile_system.lanzar().
                return {
                    "success": False,
                    "message": "plataforma en movimiento — no puede lanzar en tránsito",
                }
            result = self.missile_system.lanzar(
                x=x,
                y=y,
                angulo=angulo,
                potencia=potencia,
                radio=radio,
                drones=self.swarm.drones,
                guiado=guiado,
                duty_cycle=duty_cycle,
                track_manager=self.swarm.track_manager,
            )

        if result.get("success"):
            self._ensure_thread_running()
            self._log(
                "misil_lanzado",
                {
                    "misil_id": result["misil"]["id"],
                    "x": x,
                    "y": y,
                    "angulo": result["misil"]["angulo"],
                    "potencia": result["misil"]["potencia_hpm"],
                    "radio": result["misil"]["radio_efecto"],
                    "guiado": result["misil"]["guiado"],
                    "municion_restante": result["municion_restante"],
                },
            )
            snapshot = self._build_snapshot()
            self._notify_listeners(snapshot)
            self._notify_async_listeners(snapshot)

        return result

    def get_missile_status(self) -> dict[str, Any]:
        with self._lock:
            return self.missile_system.get_status()

    def get_missile_munition(self) -> dict[str, Any]:
        with self._lock:
            return self.missile_system.get_munition()

    def reload_missiles(self, cantidad: int) -> dict[str, Any]:
        with self._lock:
            result = self.missile_system.recargar(cantidad)
        self._log(
            "misil_recarga",
            {
                "añadido": result.get("añadido", 0),
                "municion_restante": result["municion_restante"],
            },
        )
        return result

    def _obstaculos_activos(self) -> list[tuple[float, float, float]]:
        """Círculos ``(x, y, radio)`` que bloquean línea de vista este
        tick — cada estructura NO destruida (ver ``Estructura.
        radio_bloqueo``; una vez destruida deja de bloquear, un edificio
        caído no es un obstáculo sólido). Lista vacía si
        ``estructuras_activas`` está apagado (comportamiento idéntico al
        de antes de que existiera esto) o si no queda ninguna en pie."""
        return [
            (e.x, e.y, e.radio_bloqueo) for e in self.estructuras if not e.destruida
        ]

    def _elegir_objetivo_enjambre(self) -> None:
        """Elige, cada tick, cuál es el objetivo ACTUAL del enjambre entre
        los candidatos vivos: el vehículo (si no está destruido) y cada
        estructura no destruida (si ``estructuras_activas``) — el más
        cercano al ancla de cohesión del enjambre (``formacion_x/y``, no
        la posición de un dron individual: es el punto que el modelo de
        movimiento realmente usa, ver ``Swarm._avanzar_formacion_hacia_
        objetivo``). Sin estructuras activas (o con todas ya destruidas),
        esto se reduce exactamente al comportamiento de antes de este
        ítem: siempre el vehículo.

        Guarda cuál quedó activo en ``self._objetivo_actual`` para que
        ``_registrar_impactos_en_objetivo`` sepa a quién dañar cuando un
        dron llega — un dron YA marcado ``objetivo_alcanzado`` no se ve
        afectado si el objetivo cambia después (ver ``Swarm.actualizar``):
        siguió atacando lo que tenía delante cuando llegó.
        """
        candidatos: list[tuple[str, int | None, float, float]] = []
        if not self.hpm.destruido:
            candidatos.append(("vehiculo", None, self.hpm.origen_x, self.hpm.origen_y))
        if self.estructuras_activas:
            for e in self.estructuras:
                if not e.destruida:
                    candidatos.append(("estructura", e.id, e.x, e.y))

        if not candidatos:
            # Todo destruido — no queda nada que atacar. Mismo estado que
            # mision_activa=False: Swarm ya maneja objetivo_x/y=None sin
            # romper nada (ver _avanzar_formacion_hacia_objetivo/
            # _detectar_impactos_en_objetivo).
            self.swarm.objetivo_x = None
            self.swarm.objetivo_y = None
            return

        cx, cy = self.swarm.formacion_x, self.swarm.formacion_y
        tipo, id_, x, y = min(
            candidatos, key=lambda c: (c[2] - cx) ** 2 + (c[3] - cy) ** 2
        )
        self._objetivo_actual = (tipo, id_)
        self.swarm.objetivo_x = x
        self.swarm.objetivo_y = y

    def _registrar_impactos_en_objetivo(self, llegaron: list[Any]) -> None:
        """Logea una brecha de la defensa: uno o más drones llegaron al
        objetivo este tick (ver ``Swarm.actualizar``/``_detectar_impactos_
        en_objetivo``). Mismo formato que ``hpm_disparo``/``misil_detonado``
        — un evento agregado con la lista de ids, no uno por dron."""
        self._log(
            "objetivo_alcanzado",
            {
                "drones": [d.id for d in llegaron],
                "cantidad": len(llegaron),
                "objetivo_x": self.swarm.objetivo_x,
                "objetivo_y": self.swarm.objetivo_y,
            },
        )
        validacion_logger.warning(
            "--- BRECHA — t=%.2fs --- %d dron(es) llegaron al objetivo: %s",
            self.tiempo, len(llegaron), [d.id for d in llegaron],
        )

        tipo_objetivo, id_objetivo = self._objetivo_actual

        # Kamikaze (ver kamikaze_activo): el PRIMER dron que llega ya
        # inutiliza la plataforma — no hace falta que lleguen más para
        # que "importe" (una vez destruida, sigue destruida hasta reset).
        # Solo si el objetivo ACTIVO este tick era el vehículo — si el
        # enjambre estaba atacando una estructura, esto no aplica.
        if tipo_objetivo == "vehiculo" and self.kamikaze_activo and not self.hpm.destruido:
            self.hpm.destruido = True
            self.missile_system.destruido = True
            self._log(
                "plataforma_destruida",
                {
                    "drone_id": llegaron[0].id,
                    "objetivo_x": self.swarm.objetivo_x,
                    "objetivo_y": self.swarm.objetivo_y,
                },
            )
            validacion_logger.warning(
                "--- PLATAFORMA DESTRUIDA — t=%.2fs --- dron %s impactó en "
                "modo kamikaze — cañón y lanzador de misiles fuera de "
                "servicio hasta reiniciar la simulación",
                self.tiempo, llegaron[0].id,
            )

        # Edificios atacables (ver estructuras_activas): a diferencia del
        # vehículo, acá CADA dron que llega daña la estructura — tiene
        # salud propia, no es un único impacto kamikaze (ver
        # Estructura.recibir_impacto_kamikaze / ESTRUCTURA_DANO_POR_DRON).
        elif tipo_objetivo == "estructura":
            estructura = next((e for e in self.estructuras if e.id == id_objetivo), None)
            if estructura is not None:
                for drone in llegaron:
                    if estructura.destruida:
                        break
                    destruida_ahora = estructura.recibir_impacto_kamikaze()
                    self._log(
                        "estructura_impactada",
                        {
                            "estructura_id": estructura.id,
                            "nombre": estructura.nombre,
                            "drone_id": drone.id,
                            "salud_restante": estructura.salud,
                            "destruida": estructura.destruida,
                        },
                    )
                    if destruida_ahora:
                        validacion_logger.warning(
                            "--- ESTRUCTURA DESTRUIDA — t=%.2fs --- '%s' cayó tras "
                            "el impacto del dron %s",
                            self.tiempo, estructura.nombre, drone.id,
                        )

    def _sembrar_memoria_amenaza(
        self, eventos: list[dict], impacto_x: float, impacto_y: float
    ) -> None:
        """
        Memoria de amenaza (P2-E, Parte 2): siembra en cada dron afectado la
        posición del impacto que acaba de recibir, para el repulsor con
        decaimiento de ``compute_headings`` (ver ``Drone.registrar_impacto``).

        ``impacto_x``/``impacto_y`` es la posición del origen físico del
        evento, no necesariamente la posición del dron:
        - Detonación de misil (``_process_missile_events``): el punto de
          detonación real — hay una explosión con una posición concreta.
        - Disparo de cañón (``fire``): el cañón es un haz DIRECCIONAL
          continuo, no una explosión puntual — no existe un "punto de
          impacto" independiente del propio dron. Se usa el origen del
          arma como proxy: la reacción natural a "algo me está irradiando
          desde allá" es alejarse de esa dirección, no de un punto
          arbitrario en el aire.

        Se siembra memoria para TODO dron que aparece en ``eventos`` (todo
        dron dentro del cono/radio de efecto estuvo expuesto al pulso),
        neutralizado o no — un dron neutralizado nunca vuelve a llamar a
        ``compute_headings`` de todos modos, así que es inocuo.
        """
        if not eventos:
            return
        by_id = {d.id: d for d in self.swarm.drones}
        for evento in eventos:
            drone = by_id.get(evento["drone_id"])
            if drone is not None:
                drone.registrar_impacto(impacto_x, impacto_y)

    def _atribuir_riesgo_latente(self, eventos: list[dict], shot_id: int) -> None:
        """
        Completa ``Drone.origen_riesgo_shot_id`` con el id REAL del disparo
        una vez que ``analytics`` lo asignó (P2-D, Parte 3).

        Por qué es un paso aparte y no algo que ``HPMWeapon.disparar``/
        ``HPMissile.detonar`` puedan hacer ellos mismos: el id de
        ``shot_history`` recién se conoce DESPUÉS de recorrer todos los
        drones (``analytics.record_cannon_shot``/``record_missile_detonation``
        se llaman con la lista de eventos ya completa) — en el momento en
        que cada dron entra en riesgo latente, todavía no existe ningún id
        que asignarle. ``evento["entro_en_riesgo"]`` (puesto por el arma) es
        la señal de qué drones necesitan esta atribución; mismo patrón de
        lookup por id que ``_sembrar_memoria_amenaza``.
        """
        by_id = {d.id: d for d in self.swarm.drones}
        for evento in eventos:
            if not evento.get("entro_en_riesgo"):
                continue
            drone = by_id.get(evento["drone_id"])
            if drone is not None and drone.riesgo_latente_por_s > 0.0:
                drone.origen_riesgo_shot_id = shot_id

    def _process_jamming_events(self, eventos: list[dict]) -> None:
        interferidos = [e["drone_id"] for e in eventos if e["tipo"] == "dron_interferido"]
        recuperados = [e["drone_id"] for e in eventos if e["tipo"] == "dron_recuperado"]
        if interferidos:
            self._log("dron_interferido", {"drones": interferidos})
            validacion_logger.info(
                "--- JAMMING — t=%.2fs --- drones interferidos (enlace perdido): %s",
                self.tiempo, interferidos,
            )
        if recuperados:
            self._log("dron_recuperado", {"drones": recuperados})
            validacion_logger.info(
                "--- JAMMING — t=%.2fs --- drones recuperaron enlace: %s",
                self.tiempo, recuperados,
            )

    def _process_missile_events(self, eventos: list[dict]) -> None:
        for evento in eventos:
            if evento["tipo"] == "misil_detonado":
                shot = self.analytics.record_missile_detonation(
                    evento["potencia_hpm"],
                    evento["radio_efecto"],
                    evento["impactos"],
                    self.tiempo,
                    evento["misil_id"],
                )
                # Memoria de amenaza (P2-E, Parte 2): a diferencia del cañón,
                # una detonación de misil SÍ tiene un punto de explosión
                # real y concreto (evento["x"]/["y"]) — se usa directamente,
                # sin necesidad del proxy que hace falta para el cañón (ver
                # ``_sembrar_memoria_amenaza``).
                self._sembrar_memoria_amenaza(
                    evento["impactos"], evento["x"], evento["y"]
                )
                self._atribuir_riesgo_latente(evento["impactos"], shot["id"])
                self._log(
                    "misil_detonado",
                    {
                        "misil_id": evento["misil_id"],
                        "x": evento["x"],
                        "y": evento["y"],
                        "radio_efecto": evento["radio_efecto"],
                        "potencia_hpm": evento["potencia_hpm"],
                        "neutralizados": evento["neutralizados"],
                        "afectados": len(evento["impactos"]),
                        "impactos": [
                            {"drone_id": i["drone_id"], "neutralizado": i["neutralizado"]}
                            for i in evento["impactos"]
                        ],
                    },
                )
                log_shot(
                    f"MISIL HPM {evento['misil_id']}",
                    {
                        "tiempo": self.tiempo,
                        "potencia_kw": evento["potencia_hpm"],
                        "radio_efecto": evento["radio_efecto"],
                    },
                    evento["impactos"],
                )
            elif evento["tipo"] == "misil_destruido":
                self._log(
                    "misil_destruido",
                    {
                        "misil_id": evento["misil_id"],
                        "razon": evento["razon"],
                    },
                )
                validacion_logger.warning(
                    "[VALIDACIÓN] ⚠ misil %s destruido sin detonar (%s) — salió del "
                    "campo persiguiendo al objetivo sin alcanzar la distancia de "
                    "detonación; revisar MISSILE_MAX_TURN_RATE_DEG_S/MISSILE_PN_GAIN "
                    "si esto se repite con frecuencia",
                    evento["misil_id"],
                    evento["razon"],
                )

    def run_demo(self) -> dict[str, Any]:
        """Configura y arranca la demo automática (enjambre circular + simulación)."""
        from src.config import DEMO_FORMATION, DEMO_SWARM_SIZE

        with self._lock:
            self.swarm.inicializar_formacion(DEMO_FORMATION, DEMO_SWARM_SIZE)
            self.swarm_size = DEMO_SWARM_SIZE

        self.start()
        self._log("demo_iniciada", {"formacion": DEMO_FORMATION, "drones": DEMO_SWARM_SIZE})
        return {
            "message": "Demo iniciada",
            "formacion": DEMO_FORMATION,
            "drones": DEMO_SWARM_SIZE,
            "missile_delay_s": 3,
        }

    def get_analytics(self) -> dict[str, Any]:
        with self._lock:
            return self.analytics.to_snapshot(
                self.hpm.to_dict(),
                self.missile_system.misiles,
                swarm=self.swarm,
            )

    def get_status(self) -> dict[str, Any]:
        snapshot = self._build_snapshot()
        snapshot["logs_recientes"] = list(self.logs)[-10:]
        return snapshot

    def get_drones(self) -> list[dict]:
        with self._lock:
            return [
                drone_to_dict(d, track_manager=self.swarm.track_manager)
                for d in self.swarm.drones
            ]

    def _tick(self, dt: float, mover_enjambre: bool = True) -> tuple[list[dict], list[dict]]:
        """Avanza la simulación un paso, de forma síncrona y sin hilo.

        Extraído del bucle para que el runner de experimentos Monte Carlo
        (``src/engine/experiments.py``) pueda avanzar la simulación headless
        y determinista. ``mover_enjambre=False`` reproduce la rama "pausada
        con misiles en vuelo": solo actualiza misiles y reloj, sin tocar el
        enjambre.

        Returns:
            Tupla (eventos_jamming, eventos_misil) para procesar por el llamador.
        """
        # Presupuesto energético/térmico del cañón (P2-F): enfriamiento y
        # recarga avanzan con el reloj de la simulación, tanto en el bucle
        # de 60 FPS como en el runner de experimentos Monte Carlo (única
        # razón de ser de este método extraído) — un arma que nunca corre
        # este tick nunca se enfría ni recarga. Movimiento incluido (ver
        # HPMWeapon.actualizar) — mismo motivo.
        self.hpm.actualizar(dt)

        # El jammer comparte vehículo con el cañón (mismo emplazamiento,
        # ver __post_init__) — si el vehículo se reposicionó, el jammer
        # se mueve con él, no se queda atrás en el punto viejo.
        self.jammer.origen_x = self.hpm.origen_x
        self.jammer.origen_y = self.hpm.origen_y

        if self.mision_activa:
            self._elegir_objetivo_enjambre()

        # Memoria de amenaza (P2-E, Parte 2): el decaimiento es una función
        # del tiempo transcurrido, no del flocking — avanza siempre que
        # avanza el reloj de la simulación, tanto si el enjambre se mueve
        # este tick (``mover_enjambre=True``) como si está en la rama
        # "pausada con misiles en vuelo" (la memoria de un dron no se
        # "congela" solo porque no se esté recalculando su rumbo).
        self.swarm.actualizar_amenazas(dt)

        # Fallo latente (P2-D, Parte 3): mismo criterio que la memoria de
        # amenaza — el hazard rate de un dron en riesgo es una función del
        # tiempo transcurrido, no del flocking, así que decae (y puede
        # madurar en una neutralización DIFERIDA) tanto si el enjambre se
        # mueve este tick como en la rama "pausada con misiles en vuelo".
        for evento_riesgo in self.swarm.actualizar_riesgos_latentes(dt):
            atribuido = False
            if evento_riesgo["shot_id"] is not None:
                atribuido = self.analytics.record_delayed_kill(
                    evento_riesgo["shot_id"], evento_riesgo["distancia_m"]
                )
            self._log(
                "baja_diferida",
                {
                    "drone_id": evento_riesgo["drone_id"],
                    "shot_id": evento_riesgo["shot_id"],
                    "atribuido": atribuido,
                },
            )
            validacion_logger.info(
                "--- FALLO LATENTE — t=%.2fs --- dron %s neutralizado por "
                "fallo latente (disparo original: %s, atribuido=%s)",
                self.tiempo, evento_riesgo["drone_id"],
                evento_riesgo["shot_id"], atribuido,
            )

        obstaculos = self._obstaculos_activos()

        eventos_jamming: list[dict] = []
        if mover_enjambre:
            impactos_objetivo = self.swarm.actualizar(
                dt, self.hpm.origen_x, self.hpm.origen_y, obstaculos=obstaculos
            )
            if impactos_objetivo:
                self._registrar_impactos_en_objetivo(impactos_objetivo)
            eventos_jamming = self.jammer.actualizar(self.swarm.drones)
        # Recalculado, NO la variable `obstaculos` de la línea 909: swarm.
        # actualizar() de arriba puede haber destruido una estructura recién
        # (impacto kamikaze registrado en _registrar_impactos_en_objetivo) —
        # reusar la lista vieja dejaba a esa estructura bloqueando línea de
        # vista para el misil durante el resto de ESTE mismo tick, aunque
        # `estructura.destruida` ya fuera True (bug encontrado en auditoría
        # de backend, ronda 2).
        eventos_misil = self.missile_system.actualizar_misiles(
            self.swarm.drones, dt, track_manager=self.swarm.track_manager,
            obstaculos=self._obstaculos_activos(),
        )
        self.tiempo += dt
        self.tick += 1
        return eventos_jamming, eventos_misil

    def _run_loop(self) -> None:
        dt = 1.0 / self.fps
        last_time = time.perf_counter()

        while not self._stop_event.is_set():
            if self.estado != SimulationState.EJECUTANDO:
                now = time.perf_counter()
                elapsed = now - last_time
                if elapsed >= dt:
                    ticked = False
                    eventos_misil: list[dict] = []
                    with self._lock:
                        hay_misiles = any(
                            m.estado in (MissileEstado.LANZADO, MissileEstado.VOLANDO)
                            for m in self.missile_system.misiles
                        )
                        if hay_misiles:
                            sim_dt = dt * self.time_scale
                            _, eventos_misil = self._tick(
                                sim_dt, mover_enjambre=False
                            )
                            ticked = True
                            last_time = now
                    if eventos_misil:
                        self._process_missile_events(eventos_misil)
                    if ticked:
                        snapshot = self._build_snapshot()
                        self._notify_listeners(snapshot)
                        self._notify_async_listeners(snapshot)
                time.sleep(max(0.001, dt - elapsed if elapsed < dt else 0.05))
                continue

            now = time.perf_counter()
            elapsed = now - last_time

            if elapsed >= dt:
                with self._lock:
                    sim_dt = dt * self.time_scale
                    eventos_jamming, eventos_misil = self._tick(sim_dt)
                    last_time = now

                if eventos_jamming:
                    self._process_jamming_events(eventos_jamming)

                if eventos_misil:
                    self._process_missile_events(eventos_misil)

                snapshot = self._build_snapshot()
                self._notify_listeners(snapshot)
                self._notify_async_listeners(snapshot)
            else:
                time.sleep(max(0.001, dt - elapsed))

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
