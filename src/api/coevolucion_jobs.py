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

import threading
import uuid
from typing import Any

from src.engine.coevolution import coevolucionar, resumen_json

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
            },
            "progreso": [],
            "resultado": None,
            "error": None,
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
            )
            with _lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job["estado"] = "completado"
                    job["resultado"] = resumen_json(resultado)
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
        # Copia superficial: progreso/resultado son listas/dicts que no se
        # mutan más una vez escritos (se reemplazan enteros), así que una
        # copia superficial alcanza para no exponer el dict interno vivo.
        return dict(job) if job is not None else None
