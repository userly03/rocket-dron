"""Configuración del simulador desde variables de entorno."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SIMULATION_FPS: int = int(os.getenv("SIMULATION_FPS", "60"))
HPM_DEFAULT_POWER: float = float(os.getenv("HPM_DEFAULT_POWER", "25"))
HPM_DEFAULT_ANGLE: float = float(os.getenv("HPM_DEFAULT_ANGLE", "45"))
# 15°: un cañón HPM real es un plato parabólico de alta ganancia (el paper
# arXiv:2602.08477 reporta 21.2 dBi con un plato de 60cm a 2.45GHz). Con la
# aproximación G≈26000/apertura² (ver hpm_engine.antenna_gain_from_aperture),
# 15° da ~20.6 dBi — del mismo orden que un plato real. Un cono de 30-90°
# (como estaba antes) es irreal para un arma de este tipo: cualquier antena
# de esa apertura tendría muy poca ganancia y un alcance efectivo mínimo.
HPM_CONE_APERTURE: float = float(os.getenv("HPM_CONE_APERTURE", "15"))
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

# --- Altitud (eje Z) ---
DRONE_ALTITUD_MIN: float = float(os.getenv("DRONE_ALTITUD_MIN", "40"))
DRONE_ALTITUD_MAX: float = float(os.getenv("DRONE_ALTITUD_MAX", "160"))
DRONE_BOB_AMPLITUDE_M: float = float(os.getenv("DRONE_BOB_AMPLITUDE_M", "4"))
DRONE_BOB_PERIOD_S: float = float(os.getenv("DRONE_BOB_PERIOD_S", "6"))
MISSILE_LAUNCH_ALTITUDE_M: float = float(os.getenv("MISSILE_LAUNCH_ALTITUDE_M", "5"))
MISSILE_CRUISE_ALTITUDE_M: float = float(os.getenv("MISSILE_CRUISE_ALTITUDE_M", "220"))
HPM_ORIGIN_Z: float = float(os.getenv("HPM_ORIGIN_Z", "8"))

# --- Guiado de misil (navegación proporcional) ---
# Nota de calibración: a la velocidad del misil (400 m/s) y la escala del
# campo (1000x1000 m), un límite de giro "realista" (~30-45°/s, propio de un
# misil aire-aire típico) hace que el misil pase de largo (overshoot) frente
# a un enjambre que orbita/maniobra, saliéndose del campo sin detonar. Se
# calibró empíricamente (barrido de semillas contra las 5 formaciones) hasta
# encontrar el par que intercepta de forma consistente (~99% de los casos);
# implica una agilidad de interceptor muy alta (decenas de g), una concesión
# deliberada de jugabilidad frente a la física de un misil real a esta escala.
MISSILE_MAX_TURN_RATE_DEG_S: float = float(os.getenv("MISSILE_MAX_TURN_RATE_DEG_S", "180"))
MISSILE_PN_GAIN: float = float(os.getenv("MISSILE_PN_GAIN", "4.0"))

# --- Modelo electromagnético ---
# "friis": modelo físico (densidad de potencia + campo E + umbral de susceptibilidad).
# "legacy": modelo exponencial ad-hoc original (se conserva para no romper tuning/tests previos).
HPM_MODEL: str = os.getenv("HPM_MODEL", "friis")

# Umbral de susceptibilidad del CAÑÓN (arma direccional, plato de alta ganancia).
# Calibrado por ajuste numérico directo contra los dos puntos de datos publicados
# en arXiv:2602.08477 (25kW CW, plato de 60cm/21.2dBi @ 2.45GHz):
#   51.4% de neutralización a 20m (E≈497 V/m) y 13.1% a 40m (E≈249 V/m).
# Resolviendo sigmoide(E497)=0.514 y sigmoide(E249)=0.131 da E0≈500V/m,
# steepness≈0.0075 — el ajuste reproduce ambos puntos con <2% de error.
# Ver docs/FISICA_Y_MATEMATICA.md para el desarrollo completo.
HPM_E_THRESHOLD_V_M: float = float(os.getenv("HPM_E_THRESHOLD_V_M", "500"))
HPM_SIGMOID_STEEPNESS: float = float(os.getenv("HPM_SIGMOID_STEEPNESS", "0.0075"))

# Umbral de susceptibilidad del MISIL (arma de área, sin plato — antena
# omnidireccional/de barrido). NO reutiliza el umbral del cañón: un radiador
# isotrópico esparce la misma potencia sobre 4π estereorradianes en vez de
# concentrarla en un haz estrecho (decenas de dB menos ganancia), por lo que
# con el umbral "real" del cañón el misil necesitaría potencias de MW para
# ser mínimamente efectivo. Un misil HPM real de área (tipo CHAMP) logra
# cobertura de área mediante una antena de barrido/array, no un estallido
# isotrópico puro — su ganancia efectiva de cobertura es mucho mayor que la
# de un radiador isotrópico ideal. Se modela con un umbral separado, más bajo,
# como abstracción de ese barrido (mismas ecuaciones físicas, arquetipo de
# antena distinto). Ver docs/FISICA_Y_MATEMATICA.md, sección "Limitaciones".
HPM_MISSILE_E_THRESHOLD_V_M: float = float(os.getenv("HPM_MISSILE_E_THRESHOLD_V_M", "30"))
HPM_MISSILE_SIGMOID_STEEPNESS: float = float(os.getenv("HPM_MISSILE_SIGMOID_STEEPNESS", "0.15"))

# --- Blindaje heterogéneo del enjambre ---
# Fracción de drones "blindados" (umbral de susceptibilidad más alto) al
# generar una formación — un enjambre real no es homogéneo, algunas
# unidades llevan mejor protección/apantallado que otras.
DRONE_HARDENED_FRACTION: float = float(os.getenv("DRONE_HARDENED_FRACTION", "0.2"))
DRONE_HARDENED_THRESHOLD_MULT: float = float(os.getenv("DRONE_HARDENED_THRESHOLD_MULT", "2.5"))

# --- Enjambre inteligente (boids: Reynolds 1987) ---
BOIDS_ENABLED: bool = os.getenv("BOIDS_ENABLED", "true").lower() in ("true", "1", "yes")
BOIDS_NEIGHBOR_RADIUS: float = float(os.getenv("BOIDS_NEIGHBOR_RADIUS", "80"))
BOIDS_SEPARATION_WEIGHT: float = float(os.getenv("BOIDS_SEPARATION_WEIGHT", "1.5"))
BOIDS_ALIGNMENT_WEIGHT: float = float(os.getenv("BOIDS_ALIGNMENT_WEIGHT", "1.0"))
BOIDS_COHESION_WEIGHT: float = float(os.getenv("BOIDS_COHESION_WEIGHT", "1.0"))
BOIDS_MAX_TURN_RATE_DEG_S: float = float(os.getenv("BOIDS_MAX_TURN_RATE_DEG_S", "60"))
# Cuarta regla ("zona de patrulla"): sin esto, separación+alineación+cohesión
# puras dejan que el enjambre migre entero y se aleje sin límite del alcance
# de radar/armas (ver docs/FISICA_Y_MATEMATICA.md). Radio mayor al de la
# formación circular más ancha (200m) para no interferir con el spread
# normal de la formación; solo empuja de vuelta más allá de eso.
BOIDS_HOME_RADIUS: float = float(os.getenv("BOIDS_HOME_RADIUS", "280"))
BOIDS_HOME_WEIGHT: float = float(os.getenv("BOIDS_HOME_WEIGHT", "1.5"))

# --- Radar de detección ---
# Reutiliza HPM_FREQUENCY_GHZ (misma frecuencia de operación) y el origen
# del cañón (HPM_ORIGIN_X/Y/Z) como emplazamiento del radar.
# Calibrado (numéricamente, ver docs/FISICA_Y_MATEMATICA.md) para que la
# transición de detección caiga dentro del rango de combate real de este
# campo: con la formación circular por defecto (centrada en (500,500),
# radio 200) el enjambre queda a ~500-900m del origen del arma en (0,0) —
# los mismos rangos donde el cañón ya es débil. Con estos valores, SNR ≈
# 46dB a 100m y cruza el umbral de 10dB ≈ 850-900m, dando un enjambre
# parcialmente detectado por defecto (el lado cercano sí, el lejano no) en
# vez de "todo invisible" o "todo visible".
RADAR_TX_POWER_W: float = float(os.getenv("RADAR_TX_POWER_W", "40"))
RADAR_ANTENNA_GAIN_DBI: float = float(os.getenv("RADAR_ANTENNA_GAIN_DBI", "25"))
RADAR_RCS_M2: float = float(os.getenv("RADAR_RCS_M2", "0.02"))
RADAR_NOISE_FLOOR_W: float = float(os.getenv("RADAR_NOISE_FLOOR_W", "1e-13"))
# Umbral de SNR para 50% de probabilidad de detección — aproximación
# (~10-13dB es un valor de referencia común en ingeniería de radar para
# curvas Pd/Pfa reales; acá se usa como centro de una sigmoide simplificada,
# no la función Q de Marcum real). Ver docs/FISICA_Y_MATEMATICA.md.
RADAR_SNR_THRESHOLD_DB: float = float(os.getenv("RADAR_SNR_THRESHOLD_DB", "10"))
RADAR_SIGMOID_STEEPNESS: float = float(os.getenv("RADAR_SIGMOID_STEEPNESS", "0.35"))

# --- Jamming de comunicaciones ---
# Arma continua (no un pulso único como el cañón/misil): mientras está
# activa, se reevalúa cada tick qué drones quedan sin enlace de control.
# Umbral calibrado (numéricamente, ver docs/FISICA_Y_MATEMATICA.md) para que
# sea efectivo en el rango de combate real de este campo (~500-900m del
# origen del arma con la formación circular por defecto): a 80kW con el
# cono de 45° por defecto (G≈12.8, 11.1dBi), el campo E ronda 6-8 V/m en
# ese rango — un umbral de daño HPM (cientos de V/m) sería demasiado alto
# para negar solo el enlace de control, que requiere mucha menos energía
# que dañar hardware.
JAMMING_DEFAULT_POWER: float = float(os.getenv("JAMMING_DEFAULT_POWER", "80"))
JAMMING_CONE_APERTURE: float = float(os.getenv("JAMMING_CONE_APERTURE", "45"))
JAMMING_E_THRESHOLD_V_M: float = float(os.getenv("JAMMING_E_THRESHOLD_V_M", "4"))
JAMMING_SIGMOID_STEEPNESS: float = float(os.getenv("JAMMING_SIGMOID_STEEPNESS", "0.6"))

# --- Logging de validación en terminal ---
SIM_LOG_LEVEL: str = os.getenv("SIM_LOG_LEVEL", "INFO")
