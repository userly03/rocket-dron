"""Endpoints REST de la API del simulador."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.engine.experiments import (
    ExperimentConfig,
    WeaponPolicy,
    experiment_manager,
    experimento_dosis_respuesta,
)
from src.api.coevolucion_jobs import (
    MAX_GENERACIONES,
    MAX_POBLACION,
    MAX_REPLICAS,
    MAX_T_MAX_S,
    iniciar_job,
    obtener_job,
    obtener_preview,
)
from src.engine.simulation import SimulationEngine
from src.engine.sensitivity import informe_sensibilidad
from src.engine.targeting import planificar_asignacion
from src.engine.validation import verificar_calibracion
from src.utils.reproducibilidad import build_manifest

router = APIRouter(prefix="/api", tags=["simulacion"])

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "scenarios"


class FireRequest(BaseModel):
    potencia: float | None = Field(default=None, ge=0, description="Potencia HPM en kW")
    direccion: float | None = Field(default=None, ge=0, lt=360, description="Dirección en grados")
    apertura_cono: float | None = Field(default=None, ge=1, le=180, description="Apertura del cono")
    duty_cycle: float | None = Field(
        default=None, ge=0.001, le=1.0,
        description="Duty cycle (pico/promedio): 1.0 = CW, <1 = pulsado",
    )


class StartRequest(BaseModel):
    formacion: str | None = Field(default=None, description="cuadrada, circular, aleatoria, linea o v")
    cantidad: int | None = Field(default=None, ge=1, le=500, description="Número de drones")


class MissileLaunchRequest(BaseModel):
    x: float = Field(description="Posición X de lanzamiento")
    y: float = Field(description="Posición Y de lanzamiento")
    angulo: float | None = Field(default=None, ge=0, lt=360, description="Dirección de vuelo en grados")
    potencia: float | None = Field(default=None, ge=10, le=100, description="Potencia HPM en kW")
    radio: float | None = Field(default=None, ge=50, le=200, description="Radio de efecto en metros")
    guiado: bool = Field(default=True, description="Guiado por navegación proporcional en vuelo (False = balístico)")
    duty_cycle: float | None = Field(
        default=None, ge=0.001, le=1.0,
        description="Duty cycle del pulso del misil: 1.0 = CW, <1 = pulsado",
    )


class MissileReloadRequest(BaseModel):
    cantidad: int = Field(ge=1, le=100, description="Cantidad de misiles a recargar")


class JamStartRequest(BaseModel):
    direccion: float = Field(ge=0, lt=360, description="Dirección del cono de jamming en grados")
    potencia: float | None = Field(default=None, ge=0, description="Potencia del jammer en kW")
    apertura_cono: float | None = Field(default=None, ge=1, le=180, description="Apertura del cono")


class SpeedRequest(BaseModel):
    escala: float = Field(ge=0.1, le=10, description="Multiplicador de velocidad: 1, 2, 5, 10...")


class ExperimentRequest(BaseModel):
    formacion: Literal["cuadrada", "circular", "aleatoria", "linea", "v"] = Field(
        default="circular", description="Formación del enjambre"
    )
    cantidad: int = Field(default=30, ge=1, le=500, description="Drones por réplica")
    replicas: int = Field(default=50, ge=2, le=2000, description="Réplicas Monte Carlo")
    t_max_s: float = Field(default=60.0, gt=0, le=600, description="Tiempo simulado por réplica (s)")
    semilla: int = Field(default=1234, description="Semilla base (réplica i usa semilla + i)")
    arma_tipo: Literal["canion", "misil", "ninguna"] = Field(
        default="canion", description="Política de arma de la réplica"
    )
    arma_delay_s: float = Field(default=1.0, ge=0, description="Instante del disparo/lanzamiento (s)")
    potencia: float | None = Field(default=None, ge=1, le=1000, description="Potencia del cañón (kW)")
    direccion: float | None = Field(default=None, ge=0, lt=360, description="Azimut (None = auto/valor por defecto)")
    misil_potencia: float | None = Field(default=None, ge=10, le=100, description="Potencia HPM del misil (kW)")
    misil_radio: float | None = Field(default=None, ge=50, le=200, description="Radio de efecto del misil (m)")
    con_preview: bool = Field(
        default=False,
        description="Captura fotogramas de la réplica 0 para reproducirla luego (GET .../preview)",
    )
    con_mision: bool = Field(
        default=False,
        description=(
            "El enjambre avanza hacia el arma en vez de patrullar — expone "
            "probabilidad_brecha/fraccion_alcanzo_objetivo_media en el resumen. "
            "Apagado por defecto: no altera la calibración de distancia/potencia "
            "existente salvo que se pida a propósito."
        ),
    )


def get_simulation() -> SimulationEngine:
    from src.main import simulation

    if simulation is None:
        raise HTTPException(status_code=503, detail="Simulación no inicializada")
    return simulation


SimulationDep = Annotated[SimulationEngine, Depends(get_simulation)]


@router.get("/health")
def health() -> dict:
    """Liveness check — no depende de que la simulación esté inicializada."""
    return {"status": "ok"}


@router.get("/status")
def get_status(sim: SimulationDep) -> dict:
    """Devuelve el estado actual de la simulación."""
    return sim.get_status()


@router.post("/start")
def start_simulation(sim: SimulationDep, body: StartRequest | None = None) -> dict:
    """Inicia la simulación."""
    if body:
        sim.configure_swarm(body.formacion, body.cantidad)
    return sim.start()


@router.post("/stop")
def stop_simulation(sim: SimulationDep) -> dict:
    """Pausa la simulación."""
    return sim.stop()


@router.post("/reset")
def reset_simulation(sim: SimulationDep) -> dict:
    """Reinicia la simulación al estado inicial."""
    return sim.reset()


@router.post("/speed")
def set_speed(sim: SimulationDep, body: SpeedRequest) -> dict:
    """Ajusta el multiplicador de velocidad de la simulación (1x, 2x, 5x, 10x)."""
    return sim.set_speed(body.escala)


@router.post("/fire")
def fire_hpm(sim: SimulationDep, body: FireRequest | None = None) -> dict:
    """Dispara el cañón HPM estático de tierra (cono direccional)."""
    params = body or FireRequest()
    return sim.fire(params.potencia, params.direccion, params.apertura_cono, params.duty_cycle)


@router.get("/drones")
def get_drones(sim: SimulationDep) -> dict:
    """Devuelve la lista de drones con posiciones y estados."""
    return {
        "total": len(sim.swarm.drones),
        "drones": sim.get_drones(),
        "conteo_estados": sim.swarm.contar_por_estado(),
    }


@router.get("/logs")
def get_logs(sim: SimulationDep, limit: int = 50) -> dict:
    """Devuelve los últimos eventos registrados."""
    logs = list(sim.logs)[-limit:]
    return {"total": len(logs), "logs": logs}


@router.post("/missile/launch")
def launch_missile(sim: SimulationDep, body: MissileLaunchRequest) -> dict:
    """Lanza un misil HPM con los parámetros indicados."""
    result = sim.launch_missile(
        x=body.x,
        y=body.y,
        angulo=body.angulo,
        potencia=body.potencia,
        radio=body.radio,
        guiado=body.guiado,
        duty_cycle=body.duty_cycle,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Error al lanzar"))
    return result


@router.get("/missile/status")
def get_missile_status(sim: SimulationDep) -> dict:
    """Devuelve el estado de misiles activos."""
    return sim.get_missile_status()


@router.get("/missile/munition")
def get_missile_munition(sim: SimulationDep) -> dict:
    """Devuelve la munición disponible."""
    return sim.get_missile_munition()


@router.post("/missile/reload")
def reload_missiles(sim: SimulationDep, body: MissileReloadRequest) -> dict:
    """Recarga munición de misiles HPM."""
    return sim.reload_missiles(body.cantidad)


@router.post("/jam/start")
def start_jamming(sim: SimulationDep, body: JamStartRequest) -> dict:
    """Activa el jammer de comunicaciones (arma continua de negación de enlace)."""
    return sim.start_jamming(body.direccion, body.potencia, body.apertura_cono)


@router.post("/jam/stop")
def stop_jamming(sim: SimulationDep) -> dict:
    """Desactiva el jammer de comunicaciones."""
    return sim.stop_jamming()


@router.get("/analytics")
def get_analytics(sim: SimulationDep) -> dict:
    """Devuelve panel físico, métricas, efectividad, heatmap y espectro."""
    return sim.get_analytics()


@router.get("/analytics/effectiveness")
def get_effectiveness(sim: SimulationDep) -> dict:
    return {"curve": sim.analytics.get_effectiveness_curve()}


@router.get("/analytics/heatmap")
def get_heatmap(sim: SimulationDep) -> dict:
    hpm = sim.hpm.to_dict()
    return sim.analytics.get_heatmap(
        hpm["origen_x"], hpm["origen_y"], hpm["direccion"],
        hpm["potencia"], hpm["apertura_cono"],
        missile_zones=[m.to_dict() for m in sim.missile_system.misiles],
    )


@router.get("/analytics/shots")
def get_shot_history(sim: SimulationDep, limit: int = 20) -> dict:
    return {
        "total": len(sim.analytics.shot_history),
        "shots": sim.analytics.get_shot_history(limit),
    }


@router.get("/demo/config")
def get_demo_config() -> dict:
    from src.config import (
        AUTO_DEMO_ENABLED,
        DEMO_FORMATION,
        DEMO_MISSILE_DELAY_S,
        DEMO_SWARM_SIZE,
    )
    return {
        "enabled": AUTO_DEMO_ENABLED,
        "formacion": DEMO_FORMATION,
        "drones": DEMO_SWARM_SIZE,
        "missile_delay_s": DEMO_MISSILE_DELAY_S,
    }


@router.get("/scenarios")
def list_scenarios() -> dict:
    """Lista los escenarios predefinidos disponibles en data/scenarios/."""
    escenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        escenarios.append(
            {
                "id": path.stem,
                "nombre": data.get("nombre", path.stem),
                "descripcion": data.get("descripcion", ""),
                "formacion": data.get("formacion"),
                "cantidad": data.get("cantidad"),
            }
        )
    return {"total": len(escenarios), "escenarios": escenarios}


@router.post("/scenarios/{scenario_id}/load")
def load_scenario(scenario_id: str, sim: SimulationDep) -> dict:
    """Carga un escenario predefinido: formación, cantidad y parámetros HPM."""
    if "/" in scenario_id or "\\" in scenario_id or scenario_id in (".", ".."):
        raise HTTPException(status_code=400, detail="Id de escenario inválido")

    path = (SCENARIOS_DIR / f"{scenario_id}.json").resolve()
    if not path.is_file() or SCENARIOS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail=f"Escenario '{scenario_id}' no encontrado")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Escenario inválido: {exc}") from exc

    return sim.load_scenario(data)


@router.post("/demo/start")
def start_demo(sim: SimulationDep) -> dict:
    """Inicia la demo automática con enjambre circular."""
    return sim.run_demo()


@router.post("/experiments")
def start_experiment(body: ExperimentRequest) -> dict:
    """Lanza un experimento Monte Carlo en background (réplicas headless)."""
    cfg = ExperimentConfig(
        formacion=body.formacion,
        cantidad=body.cantidad,
        replicas=body.replicas,
        t_max_s=body.t_max_s,
        semilla=body.semilla,
        arma=WeaponPolicy(
            tipo=body.arma_tipo,
            delay_s=body.arma_delay_s,
            potencia=body.potencia,
            direccion=body.direccion,
            misil_potencia=body.misil_potencia,
            misil_radio=body.misil_radio,
        ),
        con_mision=body.con_mision,
    )
    exp_id = experiment_manager.start(cfg, con_preview=body.con_preview)
    return {"experiment_id": exp_id, "status": "corriendo"}


@router.get("/experiments")
def list_experiments() -> dict:
    """Lista los experimentos registrados con su estado y progreso."""
    registros = experiment_manager.list()
    return {
        "total": len(registros),
        "experimentos": [
            {
                "id": r["id"],
                "status": r["status"],
                "completadas": r["completadas"],
                "replicas": r["replicas"],
                "config": r["config"],
            }
            for r in registros
        ],
    }


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: str) -> dict:
    """Estado, progreso y estadística de un experimento.

    Métrica primaria: ``resumen.fraccion_media`` (fracción neutralizada media
    por réplica) con ``ic95_bootstrap`` e ``ic95_t``, más ``cv``, percentiles y
    la serie de ``convergencia``. La réplica es la unidad de muestreo.

    Métrica secundaria: ``resumen.aniquilacion_total`` — proporción de réplicas
    en que cayó el enjambre completo, con IC de Wilson. Antes de P1-A esto se
    publicaba como ``p_hat``/``ic95``, o sea como si fuera la probabilidad de
    baja; no lo era y valía 0 en casi todo el espacio de operación (ver
    docs/AUDITORIA_CHECKLIST.md §1.2).

    Misión ofensiva (solo si el experimento se lanzó con ``con_mision=true``,
    apagado por defecto): ``resumen.probabilidad_brecha`` — proporción de
    réplicas en que AL MENOS UN dron llegó al objetivo (Bernoulli por
    réplica, Wilson), y ``resumen.fraccion_alcanzo_objetivo_media`` —
    fracción media del enjambre que llegó por réplica (continua, bootstrap,
    mismo criterio que ``fraccion_media``). 0/IC en [0,0] si la misión
    estaba apagada.
    """
    registro = experiment_manager.get(exp_id)
    if registro is None:
        raise HTTPException(status_code=404, detail=f"Experimento '{exp_id}' no encontrado")
    return registro


@router.get("/experiments/{exp_id}/preview")
def get_experiment_preview(exp_id: str) -> dict:
    """Fotogramas de la réplica 0 (solo si se lanzó con ``con_preview=true``).

    Cada fotograma es un ``_build_snapshot()`` completo — mismo formato que
    ``/ws`` en vivo — pensado para reproducirse client-side con el mismo
    código de render que usa la pestaña Operación, no para verse en tiempo
    real: la réplica ya terminó de calcularse (dura milisegundos) para
    cuando este endpoint tiene algo que devolver.
    """
    preview = experiment_manager.get_preview(exp_id)
    if preview is None:
        raise HTTPException(status_code=404, detail=f"Experimento '{exp_id}' no encontrado")
    return preview


@router.get("/sensibilidad")
def get_sensibilidad(
    distancia_m: float = 30.0,
    n_base: int = 512,
    r_morris: int = 30,
) -> dict:
    """Análisis de sensibilidad global del modelo de daño (Morris + Sobol).

    Devuelve ``S₁`` (efecto principal) y ``S_T`` (efecto total, con
    interacciones) por parámetro, el screening de Morris, y —lo que de verdad
    importa— ``amenazas_a_la_validez``: los parámetros que dominan la varianza
    **y no están calibrados** contra datos publicados.

    Coste: ``n_base·(k+2)`` evaluaciones para Sobol (k = 13 parámetros) más
    ``r_morris·(k+1)`` para Morris. Con los defaults son ~8 mil evaluaciones,
    del orden de un segundo. Subir ``n_base`` reduce el error como 1/√N.
    """
    if not (32 <= n_base <= 8192):
        raise HTTPException(status_code=400, detail="n_base debe estar entre 32 y 8192")
    if not (4 <= r_morris <= 200):
        raise HTTPException(status_code=400, detail="r_morris debe estar entre 4 y 200")
    if not (0.1 <= distancia_m <= 100_000):
        raise HTTPException(status_code=400, detail="distancia_m fuera de rango")
    return informe_sensibilidad(
        distancia_m=distancia_m, n_base=n_base, r_morris=r_morris
    )


@router.get("/dosis-respuesta")
def get_dosis_respuesta(
    n_por_distancia: int = 300,
    n_bootstrap: int = 1000,
    seed: int = 2026,
) -> dict:
    """
    Curva dosis-respuesta recuperada de datos simulados con el motor real
    (P2-B): ajuste por máxima verosimilitud (Newton-Raphson/IRLS, sin
    scipy) de la familia de enlace ACTIVA (``HPM_LINK_FUNCTION``), con IC
    del 95 % por bootstrap, y comparación automática contra los parámetros
    configurados.

    Cierra el lazo: en vez de confiar en que el modelo hace lo que su
    configuración dice, se recupera la curva que el motor completo (con
    huella de susceptibilidad, blindaje, duty cycle) IMPLICA, y se contrasta
    con la que se le metió. ``comparacion.recupera_la_calibracion`` es el
    campo que hay que leer primero.
    """
    if not (20 <= n_por_distancia <= 5000):
        raise HTTPException(status_code=400, detail="n_por_distancia debe estar entre 20 y 5000")
    if not (100 <= n_bootstrap <= 5000):
        raise HTTPException(status_code=400, detail="n_bootstrap debe estar entre 100 y 5000")
    return experimento_dosis_respuesta(
        n_por_distancia=n_por_distancia, n_bootstrap=n_bootstrap, seed=seed
    )


@router.get("/subsistemas")
def get_desglose_subsistemas(
    distancia_m: float = 30.0,
    potencia_kw: float = 25.0,
    apertura_cono: float = 15.0,
    duty_cycle: float = 1.0,
) -> dict:
    """
    Desglose de probabilidad de daño POR SUBSISTEMA (Tabla 1 del paper,
    P1-C) al campo que resulta de disparar con estos parámetros a
    ``distancia_m``, en el eje (offset angular cero) — misma cadena Friis
    que usa el motor interactivo (``HPM_MODEL="friis"``), no la del
    pipeline de reproducción del paper (P1-B/P1-C, que usa un modelo de
    ganancia de plato distinto).

    Puramente informativo: NO cambia ``HPM_DAMAGE_MODEL`` del motor
    interactivo, que sigue decidiendo bajas con el modelo agregado por
    defecto. Sirve para responder "a esta distancia, ¿qué subsistema
    fallaría primero?" sin tocar el estado de la simulación en vivo.
    """
    if not (0.1 <= distancia_m <= 5000.0):
        raise HTTPException(status_code=400, detail="distancia_m fuera de rango")
    if not (0.1 <= potencia_kw <= 10_000.0):
        raise HTTPException(status_code=400, detail="potencia_kw fuera de rango")
    if not (1.0 <= apertura_cono <= 360.0):
        raise HTTPException(status_code=400, detail="apertura_cono fuera de rango")
    if not (0.001 <= duty_cycle <= 1.0):
        raise HTTPException(status_code=400, detail="duty_cycle fuera de rango")

    from src.engine.hpm_engine import desglose_por_subsistema, friis_diagnostics, probabilidad_dano_sistema

    diag = friis_diagnostics(potencia_kw, distancia_m, apertura_cono, 0.0, duty_cycle)
    campo = diag["campo_e_efectivo_v_m"]
    return {
        "distancia_m": distancia_m,
        "campo_v_m": round(campo, 2),
        "subsistemas": [
            {**fila, "e50_v_m": round(fila["e50_v_m"], 1), "sigma_e_v_m": round(fila["sigma_e_v_m"], 1),
             "probabilidad": round(fila["probabilidad"], 4)}
            for fila in desglose_por_subsistema(campo)
        ],
        "probabilidad_sistema_or_gate": round(probabilidad_dano_sistema(campo), 4),
    }


class CoevolucionStartRequest(BaseModel):
    n_generaciones: int = Field(default=6, ge=1, le=MAX_GENERACIONES)
    tam_poblacion: int = Field(default=8, ge=2, le=MAX_POBLACION)
    replicas_por_evaluacion: int = Field(default=4, ge=1, le=MAX_REPLICAS)
    t_max_s: float = Field(default=6.0, ge=1.0, le=MAX_T_MAX_S)
    seed: int = Field(default=2026)
    con_mision: bool = Field(
        default=False,
        description=(
            "El arma también evoluciona contra impedir la brecha, y el enjambre "
            "también evoluciona contra llegar al objetivo — no solo neutralizar/"
            "sobrevivir. Apagado por defecto: no cambia el fitness de ninguna "
            "corrida existente."
        ),
    )


@router.post("/coevolucion/start")
def start_coevolucion(body: CoevolucionStartRequest) -> dict:
    """
    Arranca una corrida de coevolución genética arma↔enjambre (P3-B) en un
    hilo de background y devuelve de inmediato un ``job_id`` — la corrida
    en sí tarda de decenas de segundos a unos minutos (Monte Carlo real
    sobre el motor de simulación, no una heurística instantánea), así que
    NO se espera acá: pollear ``GET /coevolucion/status/{job_id}``.

    Los límites de los parámetros (``MAX_*`` en
    ``src/api/coevolucion_jobs.py``) acotan el peor caso a algo razonable
    para una herramienta interactiva — no son el límite que el algoritmo
    en sí soporta, que puede correr con parámetros mucho más grandes desde
    un script directo.
    """
    job_id = iniciar_job(
        n_generaciones=body.n_generaciones,
        tam_poblacion=body.tam_poblacion,
        replicas_por_evaluacion=body.replicas_por_evaluacion,
        t_max_s=body.t_max_s,
        seed=body.seed,
        con_mision=body.con_mision,
    )
    return {"job_id": job_id}


@router.get("/coevolucion/status/{job_id}")
def get_coevolucion_status(job_id: str) -> dict:
    """Estado de un job de coevolución: progreso generación a generación
    mientras corre, resultado completo (frontera de Pareto incluida)
    cuando ``estado == "completado"``."""
    job = obtener_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job de coevolución no encontrado")
    return job


@router.get("/coevolucion/preview/{job_id}")
def get_coevolucion_preview(job_id: str) -> dict:
    """Fotogramas del enfrentamiento final campeón-vs-campeón (mejor arma
    encontrada vs. mejor defensa encontrada), UNA réplica, capturada después
    de que el job termina — mismo mecanismo y mismo formato de fotograma que
    ``GET /experiments/{id}/preview``. Puede tardar unos segundos en estar
    ``disponible`` incluso con ``estado == "completado"``: es una corrida
    extra que se dispara al final, no bloquea el resultado en sí.
    """
    preview = obtener_preview(job_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Job de coevolución no encontrado")
    return preview


@router.get("/targeting/plan")
def get_targeting_plan(
    sim: SimulationDep,
    radio_cluster_m: float = 100.0,
    n_muestras: int = 200,
    seed: int = 2026,
) -> dict:
    """
    Asignación arma-blanco optimizada (WTA, P3-A): agrupa los TRACKS
    detectados (P2-G, no la posición omnisciente) en clusters, y calcula
    qué disparo de cañón o misil disponible (según el presupuesto real de
    energía/munición, P2-F) apunta a cuál cluster para maximizar las bajas
    esperadas totales.

    Greedy + búsqueda local, validado contra fuerza bruta exacta en
    instancias pequeñas (ver tests/test_targeting.py) — no contra el propio
    greedy, que sería un criterio tautológico.
    """
    if not (10.0 <= radio_cluster_m <= 2000.0):
        raise HTTPException(status_code=400, detail="radio_cluster_m fuera de rango")
    if not (10 <= n_muestras <= 5000):
        raise HTTPException(status_code=400, detail="n_muestras debe estar entre 10 y 5000")
    return planificar_asignacion(
        sim.swarm, sim.hpm, sim.missile_system,
        radio_cluster_m=radio_cluster_m, n_muestras=n_muestras, seed=seed,
    )


@router.get("/manifest")
def get_manifest() -> dict:
    """Manifiesto de corrida: semilla activa y snapshot de la configuración relevante."""
    return build_manifest()


@router.get("/calibracion")
def get_calibracion() -> dict:
    """
    Verifica en caliente, con la configuración de ESTA instancia corriendo,
    que la calibración contra arXiv:2602.08477 (docs/FISICA_Y_MATEMATICA.md
    §3.4) sigue vigente. No depende de que la simulación esté inicializada
    — es una consulta directa al modelo físico (P1-D, CHECKLIST_MEJORAS.md).
    Ver ``src.engine.validation.verificar_calibracion``.
    """
    return verificar_calibracion()


@router.get("/export")
def export_csv(sim: SimulationDep, tipo: str = "disparos", limit: int = 500) -> PlainTextResponse:
    """Exporta el historial de disparos o los eventos del log en formato CSV."""
    if tipo == "disparos":
        filas: list[dict] = list(sim.analytics.shot_history)[-limit:]
    elif tipo == "eventos":
        filas = [dict(e) for e in list(sim.logs)[-limit:]]
        for fila in filas:
            fila["datos"] = json.dumps(fila.get("datos", {}), ensure_ascii=False)
    else:
        raise HTTPException(status_code=400, detail="tipo debe ser 'disparos' o 'eventos'")

    salida = io.StringIO()
    if filas:
        campos: list[str] = []
        for fila in filas:
            for clave in fila:
                if clave not in campos:
                    campos.append(clave)
        writer = csv.DictWriter(salida, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    return PlainTextResponse(
        salida.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{tipo}.csv"'},
    )
