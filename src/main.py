"""Punto de entrada: servidor FastAPI del simulador EW."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.api.websocket import attach_simulation_listener, router as ws_router
from src.config import CORS_ORIGINS, HOST, PORT, SIM_LOG_LEVEL, SWARM_SIZE
from src.engine.simulation import SimulationEngine

simulation: SimulationEngine | None = None


def _configure_validation_logging() -> None:
    """Logger de validación física — imprime en la terminal los números de
    cada disparo/detonación (distancia, campo E, probabilidad...) y cualquier
    inconsistencia detectada, para validar y pulir el modelo con evidencia."""
    logger = logging.getLogger("simulador.validacion")
    logger.setLevel(SIM_LOG_LEVEL)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    logger.propagate = False


_configure_validation_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global simulation

    simulation = SimulationEngine(swarm_size=SWARM_SIZE)
    loop = asyncio.get_running_loop()
    attach_simulation_listener(simulation, loop)

    yield

    if simulation is not None:
        simulation.shutdown()


app = FastAPI(
    title="Simulador EW",
    description="Simulador de guerra electromagnética con HPM y enjambres de drones",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_wildcard = CORS_ORIGINS == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    # Un origen comodín ("*") con credenciales es una combinación inválida
    # según el spec CORS: los navegadores la rechazan. Solo se habilitan
    # credenciales cuando CORS_ORIGINS lista orígenes explícitos.
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/")
def root() -> dict:
    return {
        "nombre": "Simulador de Guerra Electromagnética",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /api/health",
            "status": "GET /api/status",
            "start": "POST /api/start",
            "stop": "POST /api/stop",
            "reset": "POST /api/reset",
            "speed": "POST /api/speed",
            "fire": "POST /api/fire",
            "drones": "GET /api/drones",
            "missile_launch": "POST /api/missile/launch",
            "missile_status": "GET /api/missile/status",
            "missile_munition": "GET /api/missile/munition",
            "missile_reload": "POST /api/missile/reload",
            "jam_start": "POST /api/jam/start",
            "jam_stop": "POST /api/jam/stop",
            "analytics": "GET /api/analytics",
            "scenarios": "GET /api/scenarios",
            "scenario_load": "POST /api/scenarios/{scenario_id}/load",
            "demo_start": "POST /api/demo/start",
            "websocket": "WS /ws",
            "docs": "/docs",
        },
    }


def main() -> None:
    uvicorn.run(
        "src.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
