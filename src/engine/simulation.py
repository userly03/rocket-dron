"""Motor principal de simulación a 60 FPS."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from src.config import (
    FIELD_HEIGHT,
    FIELD_WIDTH,
    HPM_ORIGIN_X,
    HPM_ORIGIN_Y,
    SIMULATION_FPS,
    SWARM_SIZE,
)
from src.engine.analytics import PhysicsAnalytics
from src.models.hpm_weapon import HPMWeapon
from src.models.hpm_missile import MissileEstado
from src.models.hpm_system import HPMissileSystem
from src.models.swarm import FormacionTipo, Swarm
from src.utils.helpers import drone_to_dict


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
    analytics: PhysicsAnalytics = field(default_factory=PhysicsAnalytics)
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
        self.swarm.inicializar_formacion(FormacionTipo.CUADRADA.value, self.swarm_size)
        self._log("simulacion_inicializada", {"drones": self.swarm_size})

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
                "drones": [drone_to_dict(d) for d in self.swarm.drones],
                "conteo_estados": self.swarm.contar_por_estado(),
                "hpm": self.hpm.to_dict(),
                "missiles": self.missile_system.get_status(),
                "analytics": self.analytics.to_snapshot(
                    self.hpm.to_dict(),
                    self.missile_system.misiles,
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
            self.missile_system.reset()
            self.analytics.reset()
            self.estado = SimulationState.DETENIDA

        self._log("simulacion_reiniciada")
        return {"message": "Simulación reiniciada", "estado": self.estado.value}

    def fire(
        self,
        potencia: float | None = None,
        direccion: float | None = None,
        apertura_cono: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self.hpm.configurar(potencia, direccion, apertura_cono)
            eventos = self.hpm.disparar(self.swarm.drones)

            shot = self.analytics.record_cannon_shot(
                self.hpm.potencia,
                self.hpm.direccion,
                eventos,
                self.tiempo,
                self.hpm.origen_x,
                self.hpm.origen_y,
            )

        self._log(
            "hpm_disparo",
            {
                "potencia": self.hpm.potencia,
                "direccion": self.hpm.direccion,
                "afectados": len(eventos),
                "neutralizados": sum(1 for e in eventos if e["neutralizado"]),
                "shot_id": shot["id"],
            },
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
    ) -> dict[str, Any]:
        """Lanza un misil HPM hacia el enjambre."""
        with self._lock:
            result = self.missile_system.lanzar(
                x=x,
                y=y,
                angulo=angulo,
                potencia=potencia,
                radio=radio,
                drones=self.swarm.drones,
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

    def _process_missile_events(self, eventos: list[dict]) -> None:
        for evento in eventos:
            if evento["tipo"] == "misil_detonado":
                self.analytics.record_missile_detonation(
                    evento["potencia_hpm"],
                    evento["radio_efecto"],
                    evento["impactos"],
                    self.tiempo,
                    evento["misil_id"],
                )
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
                    },
                )
            elif evento["tipo"] == "misil_destruido":
                self._log(
                    "misil_destruido",
                    {
                        "misil_id": evento["misil_id"],
                        "razon": evento["razon"],
                    },
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
            )

    def get_status(self) -> dict[str, Any]:
        snapshot = self._build_snapshot()
        snapshot["logs_recientes"] = list(self.logs)[-10:]
        return snapshot

    def get_drones(self) -> list[dict]:
        with self._lock:
            return [drone_to_dict(d) for d in self.swarm.drones]

    def _run_loop(self) -> None:
        dt = 1.0 / self.fps
        last_time = time.perf_counter()

        while not self._stop_event.is_set():
            if self.estado != SimulationState.EJECUTANDO:
                now = time.perf_counter()
                elapsed = now - last_time
                if elapsed >= dt:
                    with self._lock:
                        hay_misiles = any(
                            m.estado in (MissileEstado.LANZADO, MissileEstado.VOLANDO)
                            for m in self.missile_system.misiles
                        )
                        if hay_misiles:
                            sim_dt = dt * self.time_scale
                            eventos_misil = self.missile_system.actualizar_misiles(
                                self.swarm.drones, sim_dt
                            )
                            self.tiempo += sim_dt
                            self.tick += 1
                            if eventos_misil:
                                self._process_missile_events(eventos_misil)
                            snapshot = self._build_snapshot()
                            self._notify_listeners(snapshot)
                            self._notify_async_listeners(snapshot)
                            last_time = now
                time.sleep(max(0.001, dt - elapsed if elapsed < dt else 0.05))
                continue

            now = time.perf_counter()
            elapsed = now - last_time

            if elapsed >= dt:
                with self._lock:
                    sim_dt = dt * self.time_scale
                    self.swarm.actualizar(sim_dt)
                    eventos_misil = self.missile_system.actualizar_misiles(
                        self.swarm.drones, sim_dt
                    )
                    self.tiempo += sim_dt
                    self.tick += 1

                if eventos_misil:
                    self._process_missile_events(eventos_misil)

                snapshot = self._build_snapshot()
                self._notify_listeners(snapshot)
                self._notify_async_listeners(snapshot)
                last_time = now
            else:
                time.sleep(max(0.001, dt - elapsed))

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
