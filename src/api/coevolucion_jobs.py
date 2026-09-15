"""Job manager para la coevolución genética (P3-B) en background.

Por qué existe este archivo y no un endpoint síncrono más: una corrida de
``coevolucionar()`` tarda de decenas de segundos a varios minutos (es
Monte Carlo real sobre el motor de simulación completo, no una heurística
instantánea — ver ``src/engine/coevolution.py``). Un endpoint HTTP
síncrono que bloquee ese tiempo no sirve para una UI interactiva: el
usuario necesita ver progreso generación a generación, no esperar a
ciegas. La solución más simple que no requiere infraestructura nueva
(sin cola de tareas, sin Redis, sin Celery) es un hilo en background por
corrida, con un diccionario compartido protegido por lock — el mismo
patrón que ``SimulationEngine`` ya usa para su propio hilo de simulación
(ver ``src/engine/simulation.py::_run_loop``/``self._lock``).

Los jobs viven en memoria del proceso: se pierden si el servidor se
reinicia, y no hay límite de expiración (aceptable para una herramienta de
análisis de un solo usuario, no para un servicio multi-tenant en
producción — eso está fuera del alcance de este ítem).
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from src.engine.coevolution import coevolucionar, resumen_json
from src.engine.experiments import ExperimentConfig, run_replica

logger = logging.getLogger("simulador.coevolucion")

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Límites duros para que un job desde la UI no pueda tumbar el servidor
# corriendo, por accidente o a propósito, una corrida de horas — la
# validación de rango real (mensajes de error) vive en la capa de rutas
# (src/api/routes.py), acá solo se documenta el techo.
MAX_GENERACIONES = 15
MAX_POBLACION = 20
MAX_REPLICAS = 10
MAX_T_MAX_S = 15.0


def iniciar_job(
    n_generaciones: int,
    tam_poblacion: int,
    replicas_por_evaluacion: int,
    t_max_s: float,
    seed: int,
    con_mision: bool = False,
) -> str:
    """Crea un job, lanza el hilo que lo corre, y devuelve su id de
    inmediato — no espera a que termine ni una sola generación."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "estado": "ejecutando",
            "parametros": {
                "n_generaciones": n_generaciones,
                "tam_poblacion": tam_poblacion,
                "replicas_por_evaluacion": replicas_por_evaluacion,
                "t_max_s": t_max_s,
                "seed": seed,
                "con_mision": con_mision,
            },
            "progreso": [],
            "resultado": None,
            "error": None,
            # Fotogramas del enfrentamiento campeón-vs-campeón final, si se
            # pudo re-simular (ver el bloque al final de _run) — mismo
            # mecanismo de captura que Monte Carlo (P1-A). Separado de
            # "resultado" para no arrastrarlo en cada poll de progreso.
            "frames_previa": None,
        }

    def _on_generacion(generacion_idx: int, resultado_parcial) -> None:
        # Copia solo lo liviano (escalares) en cada tick de progreso — el
        # objeto ResultadoCoevolucion completo (con las poblaciones/genomas)
        # se serializa una única vez al final, en resumen_json().
        with _lock:
            job = _jobs.get(job_id)
            if job is None:  # el job fue limpiado externamente; no hay a dónde escribir
                return
            job["progreso"].append({
                "generacion": generacion_idx,
                "fitness_arma_media": round(resultado_parcial.fitness_arma_media_por_generacion[-1], 4),
                "fitness_defensa_media": round(resultado_parcial.fitness_defensa_media_por_generacion[-1], 4),
            })

    def _run() -> None:
        try:
            resultado = coevolucionar(
                n_generaciones=n_generaciones,
                tam_poblacion=tam_poblacion,
                replicas_por_evaluacion=replicas_por_evaluacion,
                t_max_s=t_max_s,
                seed=seed,
                on_generacion=_on_generacion,
                con_mision=con_mision,
            )
            with _lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job["estado"] = "completado"
                    job["resultado"] = resumen_json(resultado)

            # Réplica de muestra: el enfrentamiento final campeón-vs-campeón,
            # UNA vez, con captura de fotogramas — para poder VER cómo pelea
            # lo que el GA encontró, no solo leer sus genes. No es una de las
            # réplicas de fitness de la evolución (esas ya terminaron y no se
            # tocan): es una corrida extra, después, con los genomas ya
            # fijos — no cambia ni un número de "resultado".
            if resultado.mejor_arma_por_generacion and resultado.mejor_defensa_por_generacion:
                try:
                    campeon_arma = resultado.mejor_arma_por_generacion[-1]
                    campeon_defensa = resultado.mejor_defensa_por_generacion[-1]
                    cfg_preview = ExperimentConfig(
                        formacion=campeon_defensa.formacion,
                        cantidad=int(round(campeon_defensa.cantidad)),
                        replicas=1,
                        t_max_s=t_max_s,
                        semilla=seed,
                        arma=campeon_arma.a_weapon_policy(),
                        # Misma bandera que la corrida — si evolucionó
                        # contra la brecha, la réplica que lo muestra
                        # también debería mostrar al enjambre avanzando,
                        # no patrullando.
                        con_mision=con_mision,
                    )
                    frames: list[dict[str, Any]] = []
                    run_replica(cfg_preview, 0, frames_out=frames)
                    with _lock:
                        job = _jobs.get(job_id)
                        if job is not None:
                            job["frames_previa"] = frames
                except Exception:
                    logger.exception(
                        "No se pudo generar la réplica de muestra del job %s "
                        "(el resultado de la coevolución en sí quedó completo e intacto)",
                        job_id,
                    )
        except Exception as exc:  # noqa: BLE001 — un job roto debe reportarse, no tumbar el hilo en silencio
            with _lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job["estado"] = "error"
                    job["error"] = str(exc)

    hilo = threading.Thread(target=_run, daemon=True, name=f"coevolucion-{job_id}")
    hilo.start()
    return job_id


def obtener_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        # Copia superficial: progreso/resultado son listas/dicts que no se
        # mutan más una vez escritos (se reemplazan enteros), así que una
        # copia superficial alcanza para no exponer el dict interno vivo.
        copia = dict(job)
        # frames_previa puede tener cientos de snapshots completos — este
        # endpoint se pollea cada 1-2s mientras el job corre, así que acá
        # solo viaja la bandera; los fotogramas se piden aparte, una vez,
        # con obtener_preview().
        copia["previa_disponible"] = job["frames_previa"] is not None
        del copia["frames_previa"]
        return copia


def obtener_preview(job_id: str) -> dict[str, Any] | None:
    """Fotogramas del enfrentamiento final campeón-vs-campeón, si ya están
    listos (ver el bloque de captura al final de ``_run``)."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job_id,
            "disponible": job["frames_previa"] is not None,
            "estado": job["estado"],
            "frames": job["frames_previa"] or [],
        }
