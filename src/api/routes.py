"""Endpoints REST de la API del simulador."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.engine.simulation import SimulationEngine

router = APIRouter(prefix="/api", tags=["simulacion"])

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "scenarios"


class FireRequest(BaseModel):
    potencia: float | None = Field(default=None, ge=0, description="Potencia HPM en kW")
    direccion: float | None = Field(default=None, ge=0, lt=360, description="Dirección en grados")
    apertura_cono: float | None = Field(default=None, ge=1, le=180, description="Apertura del cono")


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


class MissileReloadRequest(BaseModel):
    cantidad: int = Field(ge=1, le=100, description="Cantidad de misiles a recargar")


class JamStartRequest(BaseModel):
    direccion: float = Field(ge=0, lt=360, description="Dirección del cono de jamming en grados")
    potencia: float | None = Field(default=None, ge=0, description="Potencia del jammer en kW")
    apertura_cono: float | None = Field(default=None, ge=1, le=180, description="Apertura del cono")


class SpeedRequest(BaseModel):
    escala: float = Field(ge=0.1, le=10, description="Multiplicador de velocidad: 1, 2, 5, 10...")


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
    return sim.fire(params.potencia, params.direccion, params.apertura_cono)


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
