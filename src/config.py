"""Configuración del simulador desde variables de entorno."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SIMULATION_FPS: int = int(os.getenv("SIMULATION_FPS", "60"))
HPM_DEFAULT_POWER: float = float(os.getenv("HPM_DEFAULT_POWER", "25"))
HPM_DEFAULT_ANGLE: float = float(os.getenv("HPM_DEFAULT_ANGLE", "45"))
HPM_CONE_APERTURE: float = float(os.getenv("HPM_CONE_APERTURE", "30"))
SWARM_SIZE: int = int(os.getenv("SWARM_SIZE", "50"))
HPM_K_CONSTANT: float = float(os.getenv("HPM_K_CONSTANT", "250"))

HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

FIELD_WIDTH: float = float(os.getenv("FIELD_WIDTH", "1000"))
FIELD_HEIGHT: float = float(os.getenv("FIELD_HEIGHT", "1000"))
HPM_ORIGIN_X: float = float(os.getenv("HPM_ORIGIN_X", "0"))
HPM_ORIGIN_Y: float = float(os.getenv("HPM_ORIGIN_Y", "0"))

MISSILE_SPEED: float = float(os.getenv("MISSILE_SPEED", "400"))
MISSILE_DEFAULT_POWER: float = float(os.getenv("MISSILE_DEFAULT_POWER", "50"))
MISSILE_DEFAULT_RADIUS: float = float(os.getenv("MISSILE_DEFAULT_RADIUS", "100"))
MISSILE_MUNITION_TOTAL: int = int(os.getenv("MISSILE_MUNITION_TOTAL", "10"))
MISSILE_DETONATION_DISTANCE: float = float(os.getenv("MISSILE_DETONATION_DISTANCE", "80"))

HPM_FREQUENCY_GHZ: float = float(os.getenv("HPM_FREQUENCY_GHZ", "2.45"))
HPM_COUPLING_K: float = float(os.getenv("HPM_COUPLING_K", "0.42"))
HPM_PULSE_DURATION_NS: float = float(os.getenv("HPM_PULSE_DURATION_NS", "100"))
HPM_BEAM_SIGMA: float = float(os.getenv("HPM_BEAM_SIGMA", "50"))
AUTO_DEMO_ENABLED: bool = os.getenv("AUTO_DEMO_ENABLED", "true").lower() in ("true", "1", "yes")
DEMO_SWARM_SIZE: int = int(os.getenv("DEMO_SWARM_SIZE", "50"))
DEMO_FORMATION: str = os.getenv("DEMO_FORMATION", "circular")
DEMO_MISSILE_DELAY_S: float = float(os.getenv("DEMO_MISSILE_DELAY_S", "3"))
