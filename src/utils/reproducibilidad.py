"""Gestión centralizada del generador aleatorio y manifiestos de corrida.

Toda la aleatoriedad de la simulación pasa por un único ``numpy.random.Generator``
(PCG64) en vez del estado global de numpy, de modo que:

- ``SIM_SEED`` en el entorno (o ``seed_simulacion()``) hace cualquier corrida
  bit a bit reproducible;
- los experimentos Monte Carlo (``src/engine/experiments.py``) pueden sembrar
  por réplica sin depender del estado global;
- cada corrida/experimento puede adjuntar un manifiesto con la semilla y el
  snapshot de configuración que la produjo.

Uso desde los modelos: ``from src.utils.reproducibilidad import rng`` y luego
``rng().uniform(...)`` / ``rng().random()`` en lugar de ``np.random.*``.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from src import config as config_mod

_rng: np.random.Generator | None = None
_current_seed: int | None = None

# Claves de configuración que entran al manifiesto de corrida: las que afectan
# los resultados numéricos de la simulación (no el bind del servidor, CORS, etc.).
_MANIFEST_KEYS = (
    "SIMULATION_FPS",
    "HPM_MODEL",
    "HPM_CONE_APERTURE",
    "HPM_LINK_FUNCTION",
    "HPM_E_THRESHOLD_V_M",
    "HPM_LOGLOGISTIC_E50_V_M",
    "HPM_UPSET_DB_GAP_FIELD",
    "MISSILE_DETONACION_DURACION_S",
    "DRONE_RIESGO_LATENTE_MAX_POR_S",
    "DRONE_RIESGO_LATENTE_DECAY_TAU_S",
    "HPM_LOGLOGISTIC_B",
    "HPM_MISSILE_LOGLOGISTIC_E50_V_M",
    "HPM_MISSILE_LOGLOGISTIC_B",
    "HPM_SUBSISTEMAS_LOGLOGISTIC_B",
    "HPM_SIGMOID_STEEPNESS",
    "HPM_MISSILE_E_THRESHOLD_V_M",
    "HPM_MISSILE_SIGMOID_STEEPNESS",
    "HPM_K_CONSTANT",
    "HPM_FREQUENCY_GHZ",
    "HPM_COUPLING_K",
    "HPM_PULSE_DURATION_NS",
    "HPM_BEAM_SIGMA",
    "PROPAGATION_GROUND_REFLECTION",
    "GROUND_REFLECTION_COEFF",
    "PROPAGATION_ANTENNA_PATTERN",
    "HPM_DUTY_CYCLE",
    "HPM_PULSE_TAU_ADIABATICO_NS",
    "HPM_PULSE_TAU_ESTACIONARIO_NS",
    "HPM_COUPLING_Q",
    "DRONE_HARDENED_FRACTION",
    "DRONE_HARDENED_THRESHOLD_MULT",
    "DRONE_CABLE_LENGTH_MIN_M",
    "DRONE_CABLE_LENGTH_MAX_M",
    "DRONE_POLARIZATION_MIN",
    "DRONE_ALTITUD_MIN",
    "DRONE_ALTITUD_MAX",
    "FIELD_WIDTH",
    "FIELD_HEIGHT",
    "MISSILE_SPEED",
    "MISSILE_DEFAULT_POWER",
    "MISSILE_DEFAULT_RADIUS",
    "MISSILE_DETONATION_DISTANCE",
    "MISSILE_MAX_TURN_RATE_DEG_S",
    "MISSILE_PN_GAIN",
    "BOIDS_ENABLED",
    "BOIDS_NEIGHBOR_RADIUS",
    "BOIDS_SEPARATION_WEIGHT",
    "BOIDS_ALIGNMENT_WEIGHT",
    "BOIDS_COHESION_WEIGHT",
    "BOIDS_HOME_RADIUS",
    "BOIDS_HOME_WEIGHT",
    "RADAR_FREQUENCY_GHZ",
    "RADAR_TX_POWER_W",
    "RADAR_ANTENNA_GAIN_DBI",
    "RADAR_RCS_M2",
    "RADAR_NOISE_FLOOR_W",
    "RADAR_SNR_THRESHOLD_DB",
    "JAMMING_DEFAULT_POWER",
    "JAMMING_CONE_APERTURE",
    "JAMMING_E_THRESHOLD_V_M",
    # Presupuesto energético/térmico del arma (P2-F, ver src/config.py).
    "HPM_DISPARO_DURACION_S",
    "HPM_ENERGIA_ALMACENADA_KJ",
    "HPM_RECARGA_KW",
    "HPM_EFICIENCIA_AMPLIFICADOR",
    "HPM_TEMP_MAX_C",
    "HPM_TEMP_AMBIENTE_C",
    "HPM_CAPACIDAD_TERMICA_KJ_C",
    "HPM_DISIPACION_KW_C",
    # OPFOR reactivo: memoria de amenaza + perfiles lost-link (P2-E, ver
    # src/config.py).
    "THREAT_MEMORY_DECAY_TAU_S",
    "BOIDS_THREAT_WEIGHT",
    "DRONE_LOST_LINK_RTH_FRACTION",
    "DRONE_LOST_LINK_HOVER_FRACTION",
    "DRONE_LOST_LINK_ATERRIZAR_FRACTION",
    "DRONE_LOST_LINK_FLYAWAY_FRACTION",
    "DRONE_LOST_LINK_DESCENT_RATE_M_S",
)


def seed_simulacion(seed: int | None = None) -> None:
    """Siembra el generador global de la simulación. ``None`` = no determinista."""
    global _rng, _current_seed
    _current_seed = seed
    _rng = np.random.default_rng(seed)


def rng() -> np.random.Generator:
    """Devuelve el generador global, inicializándolo con ``SIM_SEED`` si hace falta."""
    global _rng
    if _rng is None:
        seed_simulacion(config_mod.SIM_SEED)
    assert _rng is not None
    return _rng


def nuevo_generador(seed: int | None) -> np.random.Generator:
    """Crea y devuelve un ``Generator`` NUEVO e independiente, sin tocar el global.

    Antes (P0-B), cada réplica de un experimento Monte Carlo llamaba
    ``seed_simulacion(cfg.semilla + i)``, que reescribe el ``_rng`` global de
    módulo — el mismo objeto del que sortea el hilo de la simulación
    interactiva (``SimulationEngine._run_loop``) y cualquier otro experimento
    corriendo en paralelo. Dos consumidores del mismo generador mutable se
    corrompen mutuamente (ver docs/AUDITORIA_CHECKLIST.md §3.1).

    Esta función es la base de la inyección de RNG: cada réplica (o cada
    ``SimulationEngine`` que lo pida explícitamente) recibe su propio
    ``np.random.Generator`` (PCG64) aislado, con la misma garantía de
    reproducibilidad bit a bit que ``seed_simulacion`` pero sin compartir
    estado con nadie más. ``rng()``/``seed_simulacion()``/``semilla_actual()``
    se conservan sin cambios para la simulación interactiva y los tests que
    ya dependen del generador global.
    """
    return np.random.default_rng(seed)


def semilla_actual() -> int | None:
    return _current_seed


def build_manifest(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Manifiesto de corrida: semilla, instante y snapshot de la config relevante."""
    manifest: dict[str, Any] = {
        "version": "1.0.0",
        "timestamp": time.time(),
        "sim_seed": _current_seed,
        "hpm_model": config_mod.HPM_MODEL,
        "config": {
            key: getattr(config_mod, key)
            for key in _MANIFEST_KEYS
            if hasattr(config_mod, key)
        },
    }
    if extra:
        manifest.update(extra)
    return manifest


# Estado inicial según la configuración del entorno.
seed_simulacion(config_mod.SIM_SEED)
