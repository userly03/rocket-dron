"""Configuración del simulador desde variables de entorno."""

import math
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

# Velocidad de reposicionamiento del vehículo lanzador ("shoot and scoot":
# se mueve, se detiene, recién ahí puede disparar — ver HPMWeapon.
# iniciar_movimiento/en_movimiento). ~30 km/h es un crucero campo traviesa
# realista para un vehículo rastreado liviano (no de carretera, no a
# velocidad máxima) — más rápido que eso empieza a competir en velocidad
# con el propio enjambre (SWARM_AVANCE_VELOCIDAD_M_S=20) de forma que ya
# no se lee como "reposicionar la batería" sino como una persecución.
VEHICULO_VELOCIDAD_M_S: float = float(os.getenv("VEHICULO_VELOCIDAD_M_S", "8.3"))

MISSILE_SPEED: float = float(os.getenv("MISSILE_SPEED", "400"))
MISSILE_DEFAULT_POWER: float = float(os.getenv("MISSILE_DEFAULT_POWER", "50"))
MISSILE_DEFAULT_RADIUS: float = float(os.getenv("MISSILE_DEFAULT_RADIUS", "100"))
MISSILE_MUNITION_TOTAL: int = int(os.getenv("MISSILE_MUNITION_TOTAL", "10"))
MISSILE_DETONATION_DISTANCE: float = float(os.getenv("MISSILE_DETONATION_DISTANCE", "80"))

HPM_FREQUENCY_GHZ: float = float(os.getenv("HPM_FREQUENCY_GHZ", "2.45"))
HPM_COUPLING_K: float = float(os.getenv("HPM_COUPLING_K", "0.42"))
HPM_PULSE_DURATION_NS: float = float(os.getenv("HPM_PULSE_DURATION_NS", "100"))
HPM_BEAM_SIGMA: float = float(os.getenv("HPM_BEAM_SIGMA", "50"))

# --- Duty cycle (pico vs potencia promedio) ---
# Estas dos cosas vienen de fuentes DISTINTAS y no hay que confundirlas
# (auditoría: docs/AUDITORIA_CHECKLIST.md §1.5, §2 — el criterio de "done"
# viejo de este ítem era tautológico y se corrigió, ver P1-E en
# CHECKLIST_MEJORAS.md):
#
# 1. **El duty cycle SÍ viene del paper** (arXiv:2602.08477 §5): distingue
#    CW (25kW) de modo pulsado (500kW pico, 1% duty) porque los efectos
#    tipo latchup/breakdown dependen del campo INSTANTÁNEO durante el pulso,
#    no de la potencia promediada. El modelo trata ``potencia`` como
#    potencia PROMEDIO y calcula pico = promedio / duty_cycle. El paper NO
#    hace nada más que esto: escala el campo pico con el duty y ya
#    (docs/REFERENCIA_PAPER_2602.08477.md §6, "Lo que el paper NO hace").
#
# 2. **El crédito adicional por duración de pulso, g(τ), NO viene del
#    paper.** Es una extensión del proyecto, con cita propia: el modelo de
#    quemado de junturas semiconductoras de Wunsch-Bell (Wunsch, D.C. &
#    Bell, R.R., 1968, "Determination of Threshold Failure Levels of
#    Semiconductor Diodes and Transistors Due to Pulse Voltages", IEEE
#    Trans. Nucl. Sci. 15(6):244-259), que describe tres regímenes de la
#    potencia umbral de falla `P_fail(τ)` según cuánto tiempo tiene el calor
#    para difundir durante el pulso. `g(τ)` es el crédito de acoplamiento
#    (inverso al umbral: si `P_fail` baja, el daño efectivo sube) y se
#    aplica como `E_daño = E(pico) · g(τ)`. Desarrollo completo, incluida la
#    derivación de continuidad en los quiebres, en
#    docs/FISICA_Y_MATEMATICA.md §3.5. Antes de P1-E, `g(τ)` era
#    `min(√(τ/τ_ref), 3.0)` — el `√τ` coincidía con el régimen de difusión
#    térmica de Wunsch-Bell por accidente (sin cita) y el `3.0` era un
#    número mágico haciendo el trabajo de un cambio de régimen físico. Ya
#    no hay tope arbitrario: el régimen de estado estacionario ES el tope,
#    y es físico (ver ``HPM_PULSE_TAU_ESTACIONARIO_NS`` abajo).
#
# Con los defaults (duty=1.0, τ=τ_ref) g(τ)=1 y el modelo es idéntico al
# calibrado contra arXiv:2602.08477 — la compatibilidad es exacta por
# construcción (τ_ref cae exactamente en el borde del régimen de difusión,
# ver `HPM_PULSE_TAU_ADIABATICO_NS`), no por re-ajuste.
HPM_DUTY_CYCLE: float = float(os.getenv("HPM_DUTY_CYCLE", "1.0"))

# Quiebres de régimen de la ley Wunsch-Bell, en nanosegundos. **Advertencia
# de ventana de validez**: estos valores son órdenes de magnitud TÍPICOS
# para junturas de silicio (la literatura de hardening de semiconductores
# los ubica ahí de forma consistente desde Wunsch & Bell 1968), NO
# constantes universales — el punto de cruce real depende de la geometría
# de la juntura, el material y la masa térmica del dispositivo concreto.
# Se usan acá como aproximación de ingeniería razonable para electrónica de
# consumo (GPS/flight controller/ESC/cámara/BMS, los cinco subsistemas del
# paper), no como medición del hardware específico de ningún dron.
#   - τ ≲ 100 ns: régimen ADIABÁTICO — el calor no difunde durante el
#     pulso, la falla depende de la ENERGÍA total inyectada, P_fail ∝ τ⁻¹.
#   - 100 ns ≲ τ ≲ 10 µs: régimen de DIFUSIÓN TÉRMICA — el clásico
#     Wunsch-Bell, P_fail ∝ τ^(-1/2).
#   - τ ≳ 10 µs: régimen de ESTADO ESTACIONARIO — el calor difunde tan
#     rápido como entra, P_fail se vuelve independiente de τ (constante).
# HPM_PULSE_TAU_ADIABATICO_NS coincide con HPM_PULSE_DURATION_NS (100 ns)
# a propósito: el pulso de referencia del modelo cae exactamente en el
# borde entre adiabático y difusión térmica, que es donde se ancla g(τ_ref)=1.
HPM_PULSE_TAU_ADIABATICO_NS: float = float(os.getenv("HPM_PULSE_TAU_ADIABATICO_NS", "100"))
HPM_PULSE_TAU_ESTACIONARIO_NS: float = float(os.getenv("HPM_PULSE_TAU_ESTACIONARIO_NS", "10000"))
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

# --- Función de enlace del modelo de daño (P1-F) ---
# "log_logistica" (default): P(E) = 1/(1+(E₅₀/E)^b)
# "logistica"     (legacy) : P(E) = 1/(1+exp(-k·(E-E₀)))
#
# POR QUÉ SE CAMBIÓ EL DEFAULT. La logística opera sobre ``E`` y tiene soporte
# en **todo ℝ**, pero el campo eléctrico es una magnitud **positiva**.
# Consecuencia estructural, no un detalle numérico:
#
#     P(E=0) = 1/(1+exp(k·E₀)) = 1/(1+exp(0.0075·500)) = 2.30 %
#
# Un dron sin ningún campo aplicado tenía 2.30 % de probabilidad de caer (3.30 %
# con el OR-gate de cinco subsistemas, que compone cinco colas). Dicho en
# términos del modelo de umbrales que la sigmoide representa: una logística en
# ``E`` afirma que una fracción de la población de componentes falla a campo
# **negativo**, que no significa nada.
#
# Cuánto contaminaba (medido, docs/FISICA_Y_MATEMATICA.md §3.7): más allá de
# ~97 m MÁS DE LA MITAD de la probabilidad reportada era ese piso, y a 700 m
# —con el enjambre circular por defecto a 500-900 m, o sea TODO el rango de
# combate— el **90.7 %** del número era artefacto.
#
# La log-logística (equivalentemente: una logística en ``ln E``) da
# ``P(0) = 0`` exacto y ``P(∞) = 1``, y es el modelo estándar de
# dosis-respuesta para dosis positivas, precisamente porque el soporte de la
# distribución de umbrales es ``(0, ∞)``. Encontrado por el análisis de
# sensibilidad (§3.8), no buscado.
HPM_LINK_FUNCTION: str = os.getenv("HPM_LINK_FUNCTION", "log_logistica")

# Parámetros de la log-logística del CAÑÓN, ajustados a los MISMOS dos puntos
# publicados que calibraban la logística (arXiv:2602.08477: 51.4 % @ 20 m con
# E = 497.2 V/m, 13.1 % @ 40 m con E = 248.6 V/m). El ajuste es **exacto**:
# residuo 0.0000 pp en AMBOS puntos, contra −1.92 pp que daba la logística. Dos
# parámetros libres igual que antes — no se compró el arreglo con más grados de
# libertad.
#
# DECISIÓN METODOLÓGICA DECLARADA: se ajusta contra el campo que calcula **el
# paper** (497.2 / 248.6 V/m), no contra el que calcula el simulador
# (465.48 / 232.74 V/m, un −6.4 % por usar G ≈ 26000/θ² en vez de la fórmula de
# plato). El motivo: ``E₅₀`` es una propiedad de la **electrónica del blanco**,
# no de la antena del arma. Ajustarlo contra el campo del simulador metería el
# déficit de ganancia del EMISOR dentro del umbral del BLANCO — exactamente el
# error de categoría del hallazgo 2/§1.3 de la auditoría, que fue lo que dejó
# el umbral viejo en 500 V/m, por encima de los cinco umbrales reales.
#
# Consecuencia aceptada: con ``HPM_ANTENNA_MODEL = "apertura"`` el simulador
# queda −4.63 pp por debajo del paper a 20 m. Ese residuo es **enteramente
# atribuible** al déficit de ganancia ya medido, y se cierra poniendo
# ``HPM_ANTENNA_MODEL = "plato"`` (G = η(πD/λ)² → 21.16 dBi contra los 21.2
# publicados). Se deja como dos decisiones separadas a propósito.
HPM_LOGLOGISTIC_E50_V_M: float = float(os.getenv("HPM_LOGLOGISTIC_E50_V_M", "487.389"))
HPM_LOGLOGISTIC_B: float = float(os.getenv("HPM_LOGLOGISTIC_B", "2.8106"))

# Ídem para el MISIL. Convertidos desde los parámetros logísticos previos
# (E₀ = 30 V/m, steepness = 0.15) con la transformación que **preserva la
# pendiente en E₅₀**:
#     logística:     dP/dE|E₅₀ = 1/(4σ)
#     log-logística: dP/dE|E₅₀ = b/(4·E₅₀)
#     igualando  ⇒   b = E₅₀/σ = 30·0.15 = 4.5
# Es una conversión, no una recalibración: el misil nunca tuvo puntos de datos
# propios (su umbral es una concesión de jugabilidad, ver §4 del doc de física).
HPM_MISSILE_LOGLOGISTIC_E50_V_M: float = float(
    os.getenv("HPM_MISSILE_LOGLOGISTIC_E50_V_M", "30.0")
)
HPM_MISSILE_LOGLOGISTIC_B: float = float(os.getenv("HPM_MISSILE_LOGLOGISTIC_B", "4.5"))

# Exponente de forma de la log-logística de los SUBSISTEMAS. La misma
# conversión b = E₅₀/σ aplicada a la Tabla 1 del paper da **exactamente 5.0
# para los cinco subsistemas** (150/30, 200/40, 250/50, 300/60, 350/70).
# HALLAZGO PROPIO: eso significa que la columna σ_E de la Tabla 1 es
# literalmente E₅₀/5 y **no aporta información independiente** de la columna
# E₅₀ — el paper describe los cinco subsistemas con un único parámetro de forma
# y cinco umbrales, aunque presente diez números.
HPM_SUBSISTEMAS_LOGLOGISTIC_B: float = float(
    os.getenv("HPM_SUBSISTEMAS_LOGLOGISTIC_B", "5.0")
)

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

# --- Antena de plato real (P1-B) ---
# La aproximación G ≈ 26000/apertura² (ver hpm_engine.antenna_gain_from_aperture)
# es una fórmula de ingeniería de radar legítima, pero no describe un plato
# parabólico concreto: a 15° da 20.63 dBi contra los 21.2 dBi del plato de
# 60 cm del paper, un sesgo sistemático de −6.4% en campo E que
# tests/test_calibracion.py midió idéntico en los dos puntos de calibración
# (prueba de que es un offset de ganancia y no un error de modelo).
#
# Con el diámetro y la eficiencia de apertura se puede usar la fórmula real de
# plato, G = η·(πD/λ)², que da 21.16 dBi — el sesgo baja a −0.5%. Ver
# hpm_engine.antenna_gain_from_dish. Se deja como modelo SELECCIONABLE
# (HPM_ANTENNA_MODEL) y no como reemplazo, porque cambiar la ganancia por
# defecto movería la calibración de §3.4 y esa es una decisión aparte de
# añadir la capacidad.
#   "apertura": G ≈ 26000/θ² a partir de HPM_CONE_APERTURE (default, calibrado)
#   "plato":    G = η·(πD/λ)² a partir de HPM_DISH_DIAMETER_M / HPM_APERTURE_EFFICIENCY
HPM_ANTENNA_MODEL: str = os.getenv("HPM_ANTENNA_MODEL", "apertura")
HPM_DISH_DIAMETER_M: float = float(os.getenv("HPM_DISH_DIAMETER_M", "0.60"))
HPM_APERTURE_EFFICIENCY: float = float(os.getenv("HPM_APERTURE_EFFICIENCY", "0.55"))

# --- Modelo de daño: agregado vs 5 subsistemas (P1-C) ---
# "agregado":    una sola sigmoide con HPM_E_THRESHOLD_V_M / HPM_SIGMOID_STEEPNESS.
#                Es el default, para no mover la calibración existente.
# "subsistemas": los cinco subsistemas de la Tabla 1 de arXiv:2602.08477,
#                combinados con lógica OR-gate (ecuación 7 del paper):
#                    P_sistema(E) = 1 − Π_i [1 − P_i(E)]
#                El dron cae si cae CUALQUIER subsistema.
#
# POR QUÉ EL MODELO DE SUBSISTEMAS ES MEJOR CIENCIA, no solo "más detalle":
# el modelo agregado tiene DOS parámetros libres (E₀ y la pendiente) ajustados
# a DOS puntos publicados → cero grados de libertad → **no es falsable**:
# cualquier par de puntos se puede reproducir. El modelo de subsistemas toma
# los cinco pares (E₅₀, σ_E) COMO PUBLICADOS y deja un único parámetro libre
# (la eficiencia de acoplamiento de abajo) → un grado de libertad → **sí es
# falsable**. Y pasa la prueba: con k = 0.2568 reproduce ambos puntos con
# residuos de −0.11 pp (20 m) y +0.62 pp (40 m), DENTRO de los márgenes que
# el propio paper declara (±1.0 y ±0.7 pp). El modelo agregado, con el doble
# de parámetros libres, se queda en −1.92 pp a 20 m: FUERA del margen.
# ⚠ ESTADO REAL: el argumento de falsabilidad se sostiene (1 gl vs 0 gl), pero
# el modelo de subsistemas **no pasa la prueba todavía**. Con el ajuste
# metodológicamente correcto (Monte Carlo dentro del lazo) los residuos son
# −1.48 pp a 20 m y +4.19 pp a 40 m, fuera de los márgenes ±1.0 / ±0.7 del
# paper. Tres señales independientes apuntan a que la varianza del acoplamiento
# está sobreestimada, y la atribución de varianza señala a la polarización
# (55% del CV total). Bloqueado a falta de confirmar la cadena de acoplamiento
# contra el PDF. Ver docs/FISICA_Y_MATEMATICA.md §3.6 y CHECKLIST_MEJORAS.md P1-C.
# Por eso el default sigue siendo "agregado".
HPM_DAMAGE_MODEL: str = os.getenv("HPM_DAMAGE_MODEL", "agregado")

# Umbrales de daño por subsistema: {nombre: (E₅₀ V/m, σ_E V/m)}. Tabla 1 de
# arXiv:2602.08477, tomados como publicados y NO ajustados.
#
# CONFIRMADO CONTRA EL PDF (2026-09-13, antes solo extraídos del HTML de
# arXiv con dos fetches independientes concordantes — ahora leídos
# directamente de la Tabla 1 del PDF, coinciden exactamente): 150/30
# (GPS/GNSS LNA), 200/40 (cámara CMOS), 250/50 (flight controller), 300/60
# (ESC gate oxide), 350/70 (BMS MOSFET) V/m.
HPM_SUBSISTEMAS: dict[str, tuple[float, float]] = {
    "gps_gnss_lna": (150.0, 30.0),
    "camara_cmos": (200.0, 40.0),
    "flight_controller": (250.0, 50.0),
    "esc_gate_oxide": (300.0, 60.0),
    "bms_mosfet": (350.0, 70.0),
}

# Eficiencia de acoplamiento en CAMPO entre el campo incidente y el campo que
# ve el subsistema susceptible.
#
# ACTUALIZADO 2026-09-13, tras leer el PDF real del paper (antes solo se
# tenía el HTML de arXiv, sin el código fuente). El Listado 1 (modelo
# determinista) y el Listado 2 (núcleo del Monte Carlo, "abreviado" según
# el propio paper) muestran el pipeline que produce 51.4%/13.1%: parten del
# campo incidente de Friis, aplican pérdida por apuntado (potencia,
# gaussiana — ver ``DRONE_POLARIZATION_ANGLE_MIN_RAD`` y
# ``src.engine.experiments._factor_taper_haz``) y pérdida de polarización
# (potencia, cos²φ acotado a 0.1) — y comparan ESE campo contra los umbrales
# E₅₀ de la Tabla 1 (ambos en V/m), SIN ningún paso de acoplamiento a
# voltios inducidos en cable (Ec. 4-5 del paper, que en el texto aparece
# como motivación teórica, no como parte del código mostrado).
#
# PROBADO Y DESCARTADO: k=1.0 (sin atenuación extra, tomando el pipeline de
# arriba literalmente) SOBRESTIMA fuerte — a 20m da 91.6% contra 51.4%
# publicado, +40pp. La hipótesis "no hay ningún paso de acoplamiento
# adicional" no sostiene los números publicados: o el Listado 2 abreviado
# omite un paso real (el más probable candidato sigue siendo la cadena de
# voltios de la Ec. 4-5), o falta algo más en la cadena.
#
# Reajustado con el MC en el lazo (método correcto, ver docstring de
# ``campo_acoplado_v_m``) bajo el modelo YA corregido (polarización +
# apuntado): k=0.44 minimiza el error cuadrático a los dos puntos
# publicados, pero SIGUE sin cerrar — y con una firma distinta a antes:
# residuo +2.25pp a 20m (2.25× el margen ±1.0pp) y −4.44pp a 40m (6.3× el
# margen ±0.7pp), de SIGNOS OPUESTOS (antes, con el modelo viejo, ambos
# residuos eran negativos) — ningún k único cierra los dos. El CV a 30m con
# este k es ≈1.03, PEOR que el 0.63 de antes y muy por encima del ≈0.39 del
# paper — descarta que "falta variabilidad" (ej. F(θ_wire) sin implementar)
# sea el problema: el modelo YA tiene demasiada varianza, agregar más la
# empeoraría. Ver CHECKLIST_MEJORAS.md P1-C y docs/FISICA_Y_MATEMATICA.md
# §3.6 para el detalle completo.
HPM_COUPLING_FIELD_EFFICIENCY: float = float(
    os.getenv("HPM_COUPLING_FIELD_EFFICIENCY", "0.44")
)

# --- Presupuesto energético y térmico del arma (P2-F) ---
# En sistemas HPM reales (Epirus Leonidas, THOR de la USAF) el límite
# operativo NO es el haz — la propagación electromagnética no "se cansa" —
# sino la potencia primaria disponible y la refrigeración del amplificador:
# la cadencia sostenida queda acotada por cuánto calor se puede sacar del
# amplificador, no por la física de la propagación. Sin este presupuesto,
# ``HPMWeapon.disparar()`` dispara infinitas veces gratis a coste cero, lo
# que vacía de contenido a P3-A (asignación arma-blanco, WTA): sin
# restricción de energía la solución óptima trivial es "disparale a todo".
# Ver CHECKLIST_MEJORAS.md P2-F y docs/ROADMAP_CIENTIFICO.md.
#
# PROBLEMA DE ESCALA (decisión de MODELADO de este proyecto, NO un dato de
# arXiv:2602.08477): la energía de UN pulso aislado,
# potencia_promedio · HPM_PULSE_DURATION_NS, es irrelevante para cualquier
# presupuesto — a 25 kW y 100 ns son 2.5 mJ, nada. Lo que agota un banco de
# energía real y calienta un amplificador real no es un pulso suelto sino
# la RÁFAGA completa de pulsos que constituye lo que el operador (y esta
# API, con ``HPMWeapon.disparar()``/``POST /api/fire``) llama "un disparo":
# el arma emite a una PRF (frecuencia de repetición de pulso) alta durante
# una ventana de tiempo, no un único pulso. ``HPM_DISPARO_DURACION_S`` es
# esa ventana: el presupuesto de energía de un disparo se calcula como
# ``potencia_promedio · HPM_DISPARO_DURACION_S`` (kW·s = kJ) — NO con
# ``HPM_PULSE_DURATION_NS``, que sigue gobernando EXCLUSIVAMENTE el
# acoplamiento g(τ) de Wunsch-Bell (ver arriba) y no interviene en absoluto
# en el balance de energía/calor. El paper de referencia no publica
# duración de ráfaga ni PRF; 0.5 s se eligió para que la energía por
# disparo (decenas de kJ) tenga el orden de magnitud de un banco de
# capacitores de un arma de energía dirigida real, no el de un pulso de
# radar.
HPM_DISPARO_DURACION_S: float = float(os.getenv("HPM_DISPARO_DURACION_S", "0.5"))

# Energía almacenada en el banco (capacitores/baterías) que alimenta la
# ráfaga; se descarga con cada disparo y se recarga entre disparos desde la
# potencia primaria (``HPM_RECARGA_KW``). Dimensionado para que, con los
# defaults de este bloque, el presupuesto TÉRMICO (no el energético) sea el
# que primero corta la cadencia sostenida — igual que en Leonidas/THOR,
# donde el cuello de botella declarado es la refrigeración, no la energía
# disponible: a 25 kW · 0.5 s = 12.5 kJ/disparo, 500 kJ alcanzarían para
# ~40 disparos por energía sola, pero el límite térmico corta la ráfaga
# bastante antes (23 disparos con los defaults de este archivo, verificado
# en ``tests/test_presupuesto_arma.py``) — el comportamiento que este ítem
# existe para introducir. También holgado a propósito para que un disparo
# suelto (o unos pocos) de la suite existente nunca se vea afectado por
# este cambio.
HPM_ENERGIA_ALMACENADA_KJ: float = float(os.getenv("HPM_ENERGIA_ALMACENADA_KJ", "500.0"))

# Potencia primaria de recarga del banco (generador/vehículo), en kW.
# Deliberadamente MENOR que la potencia de disparo por defecto (25 kW): esa
# es la razón de ser de un banco de energía intermedio entre la fuente
# primaria y la ráfaga — la fuente primaria no puede sostener por sí sola
# la potencia de ráfaga, así que el banco actúa de buffer que se recarga
# mucho más lento de lo que se descarga (a 10 kW, recargar el banco vacío
# entero toma 50 s).
HPM_RECARGA_KW: float = float(os.getenv("HPM_RECARGA_KW", "10.0"))

# Fracción de la energía de la ráfaga que sale como haz electromagnético;
# el resto, ``1 - eficiencia``, se disipa como calor en el amplificador.
# 0.3 es un valor de ingeniería típico de fuentes de microondas de alta
# potencia (magnetrones/viracadores/klystrons rondan 20-50% de eficiencia
# de conversión DC→RF); no es un dato de arXiv:2602.08477, que no publica
# presupuesto térmico del transmisor.
HPM_EFICIENCIA_AMPLIFICADOR: float = float(os.getenv("HPM_EFICIENCIA_AMPLIFICADOR", "0.3"))

# Límite térmico operativo y temperatura ambiente, en °C. 125°C deja margen
# de seguridad razonable por debajo del límite de juntura típico de
# amplificadores de RF de estado sólido de alta potencia (GaN HEMT: 150-
# 225°C según el fabricante y el punto de referencia) — se opera con
# margen, no al límite absoluto del semiconductor. 25°C es la temperatura
# ambiente estándar de referencia (la misma que usa la ley de enfriamiento
# de Newton de abajo).
HPM_TEMP_MAX_C: float = float(os.getenv("HPM_TEMP_MAX_C", "125.0"))
HPM_TEMP_AMBIENTE_C: float = float(os.getenv("HPM_TEMP_AMBIENTE_C", "25.0"))

# Capacidad térmica del conjunto amplificador + disipador, en kJ/°C.
# Estimación de ingeniería, no una medición: ~5 kg de cobre/aluminio
# (calor específico c≈0.4-0.9 kJ/kg·°C) da un orden de magnitud de 2-4
# kJ/°C; se toma el extremo inferior (menor masa térmica → calienta más
# rápido por disparo → presupuesto más restrictivo), consistente con el
# espíritu conservador de este ítem.
HPM_CAPACIDAD_TERMICA_KJ_C: float = float(os.getenv("HPM_CAPACIDAD_TERMICA_KJ_C", "2.0"))

# Coeficiente de disipación (ley de enfriamiento de Newton), en kW por °C
# de diferencia con el ambiente: potencia_disipada = k·(T - T_ambiente).
# Junto con ``HPM_CAPACIDAD_TERMICA_KJ_C``, la constante de tiempo del
# enfriamiento es τ = C/k = 2.0/0.02 = 100 s — un amplificador con
# disipación pasiva/convección moderada (sin refrigeración líquida activa)
# se enfría en el orden de minutos, no de segundos: "hay que esperar" es
# una decisión táctica real (P3-A/WTA la explota), no un detalle cosmético.
HPM_DISIPACION_KW_C: float = float(os.getenv("HPM_DISIPACION_KW_C", "0.02"))

# --- Propagación sobre tierra y patrón de antena (P2-C) ---
# Sustituyen al ítem cortado P3-08 (FDTD de campo cercano), que corregía el
# régimen r < 2D²/λ ≈ 5.9 m en un campo de 1000×1000 m. Estos dos efectos sí
# operan en el rango donde el simulador vive. Ver src/engine/propagation.py.
#
# AMBOS SON OPT-IN, y el motivo es el mismo que con HPM_ANTENNA_MODEL: los dos
# MUEVEN LA CALIBRACIÓN de docs/FISICA_Y_MATEMATICA.md §3.4, que está hecha
# contra el paper — y el paper modela espacio libre, sin tierra. Activarlos por
# defecto sería recalibrar de refilón.
#
# ⚠ HALLAZGO que cambió el diseño de este ítem: la justificación original decía
# que la reflexión en tierra "convierte la altitud en variable táctica, un
# enjambre puede volar en un nulo". **Es falso a 2.45 GHz.** La separación entre
# franjas en altitud es λ·r/(2·h_tx): 0.76 m a 100 m, 2.29 m a 300 m y 5.35 m a
# 700 m, con 22 a 157 ciclos completos dentro de la banda de vuelo (40-160 m).
# Un dron oscila ±4 m (DRONE_BOB_AMPLITUDE_M) y el espaciado del enjambre es de
# 30 m: cruza varias franjas por oscilación. El patrón existe pero no es
# explotable ni controlable a esta frecuencia.
#
# Por eso el uso correcto del efecto es ESTADÍSTICO: promediado sobre las
# franjas, ⟨|F|²⟩ = 2 exactamente, o sea **+3.01 dB** — el modelo de espacio
# libre SUBESTIMA la potencia media recibida sobre tierra en 3 dB (verificado
# numéricamente a 0.1/0.5/2.45 GHz y a 100/300/700 m: da 3.0 dB en los nueve
# casos). Y la dispersión que introduce (p5-p95: −16 a +6 dB) es varianza real,
# que P2-A demostró que domina las conclusiones de este modelo.
#
# La altitud SÍ sería variable táctica por debajo de ~0.5 GHz (franja de 26 m a
# 700 m). Como HPM_FREQUENCY_GHZ es barrible, el modelo determinista se
# conserva y es el correcto en ese régimen — consultar
# propagation.franja_resoluble() antes de interpretar un valor puntual.
PROPAGATION_GROUND_REFLECTION: bool = os.getenv(
    "PROPAGATION_GROUND_REFLECTION", "false"
).lower() in ("true", "1", "yes")

# Coeficiente de reflexión del suelo. −1 = incidencia rasante sobre suelo
# conductor: la reflexión invierte la fase. Es el caso límite estándar y el más
# desfavorable (nulos profundos). Un suelo real con pérdidas da |Γ| < 1, que
# atenúa tanto los máximos como los nulos.
GROUND_REFLECTION_COEFF: float = float(os.getenv("GROUND_REFLECTION_COEFF", "-1.0"))

# Patrón de antena: "cos2" (el taper actual, default) o "airy" (apertura
# circular uniformemente iluminada, F = |2J₁(u)/u|).
#   - "cos2" NO es el patrón de ninguna antena real: no tiene lóbulos
#     laterales, y su forma no depende ni de D ni de λ. Dice que fuera del cono
#     nominal no llega NADA.
#   - "airy" es física establecida (transformada de Fourier de una apertura
#     circular) y tiene lóbulos laterales reales: el primero a −17.6 dB en
#     potencia. Un enjambre justo fuera del haz nominal recibe del orden del 2%
#     de la potencia del eje, no cero.
PROPAGATION_ANTENNA_PATTERN: str = os.getenv("PROPAGATION_ANTENNA_PATTERN", "cos2")

# --- Blindaje heterogéneo del enjambre ---
# Fracción de drones "blindados" (umbral de susceptibilidad más alto) al
# generar una formación — un enjambre real no es homogéneo, algunas
# unidades llevan mejor protección/apantallado que otras.
DRONE_HARDENED_FRACTION: float = float(os.getenv("DRONE_HARDENED_FRACTION", "0.2"))
DRONE_HARDENED_THRESHOLD_MULT: float = float(os.getenv("DRONE_HARDENED_THRESHOLD_MULT", "2.5"))

# --- Huella de susceptibilidad (acoplamiento por frecuencia + polarización) ---
# Cada dron sortea una longitud de cableado interno; su resonancia (dipolo de
# media onda, f = c/2L) hace que la eficiencia de acoplamiento η(f) sea una
# lorentziana alrededor de f_res con ancho f_res/Q (config: HPM_COUPLING_Q).
# El factor de amplitud que llega a la sigmoide de daño es √(η·pol): el
# blanco con cableado resonante con la frecuencia del arma acopla todo; el
# desintonizado, mucho menos. Con estos defaults la resonancia típica cae en
# 1.0–7.5 GHz, bracketando la frecuencia por defecto del arma (2.45 GHz).
DRONE_CABLE_LENGTH_MIN_M: float = float(os.getenv("DRONE_CABLE_LENGTH_MIN_M", "0.02"))
DRONE_CABLE_LENGTH_MAX_M: float = float(os.getenv("DRONE_CABLE_LENGTH_MAX_M", "0.15"))
# η_pol = cos²φ, φ ~ Uniforme[ÁNGULO_MIN, ÁNGULO_MAX] rad (default [0, π]),
# acotado por abajo a DRONE_POLARIZATION_MIN_ETA.
#
# CONFIRMADO contra el código fuente real del paper (arXiv:2602.08477,
# Listado 2, leído en PDF el 2026-09-13 — antes solo se tenía el HTML de
# arXiv, sin el código): `pol_loss = max(cos(pol)**2, 0.1)`, multiplicado
# directamente sobre la potencia (EIRP) antes de la raíz cuadrada para el
# campo — exactamente este modelo, piso incluido, y el piso va sobre
# cos²φ (dominio de potencia), NO sobre √(cos²φ). Ya estaba implementado así
# en `src/engine/parametros.py` (P1-B, deducido sin el PDF, ahora confirmado
# correcto) pero el motor principal (`Drone`, del que dependen P2-D/P3-A/P3-B)
# seguía usando un modelo viejo y físicamente incorrecto: `Uniforme[0.3, 1.0]`
# plano — mismo error que P1-B ya había señalado en `parametros.py` sin
# haberlo corregido en el motor principal. Corregido acá (2026-09-13).
#
# Antes: `DRONE_POLARIZATION_MIN = 0.3` acotaba un sorteo uniforme directo
# del factor de potencia — plano, subestimaba la varianza justo en la
# variable que el paper reporta como dominante del CV (§3.6 de
# docs/FISICA_Y_MATEMATICA.md).
DRONE_POLARIZATION_ANGLE_MIN_RAD: float = float(
    os.getenv("DRONE_POLARIZATION_ANGLE_MIN_RAD", "0.0")
)
DRONE_POLARIZATION_ANGLE_MAX_RAD: float = float(
    os.getenv("DRONE_POLARIZATION_ANGLE_MAX_RAD", str(math.pi))
)
# Piso de η_pol = cos²φ. Sin piso, con φ ~ U[0,π] (densidad de cos²φ diverge
# en 0), una fracción no despreciable de blancos quedaría con acoplamiento
# numéricamente nulo — y un blanco perfectamente cruzado en polarización
# igual acopla algo, por despolarización del entorno y geometría 3D real.
DRONE_POLARIZATION_MIN_ETA: float = float(os.getenv("DRONE_POLARIZATION_MIN_ETA", "0.1"))
HPM_COUPLING_Q: float = float(os.getenv("HPM_COUPLING_Q", "5.0"))

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
# Comparte el origen del cañón (HPM_ORIGIN_X/Y/Z) como emplazamiento del
# radar, pero NO su frecuencia. Antes reutilizaba HPM_FREQUENCY_GHZ; se
# separó porque la ecuación de radar lleva λ² (ver radar_engine.py):
#   Pr = (Pt · G² · λ² · σ) / ((4π)³ · r⁴)
# así que barrer la frecuencia del ARMA para estudiar resonancia de
# acoplamiento (ver DRONE_CABLE_LENGTH_*/HPM_COUPLING_Q más abajo) cambiaba
# a la vez el alcance de detección del radar, confundiendo ese experimento
# con un efecto puramente instrumental (a cuántos drones se les dispara,
# no cuánto daño hace cada disparo). Default = 2.45, igual al de
# HPM_FREQUENCY_GHZ, para no mover la calibración de detección ya ajustada
# (ver el comentario siguiente); las dos constantes solo divergen si se
# barre una de las dos explícitamente. Auditoría §3.2.
RADAR_FREQUENCY_GHZ: float = float(os.getenv("RADAR_FREQUENCY_GHZ", "2.45"))
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

# --- Radar dinámico: barrido + filtro α-β-γ (P2-G) ---
# El radar de arriba decide instantáneamente, cada tick, si un blanco "se
# conoce" — omnisciente por construcción: la decisión usa la posición VERDADERA
# del dron, y drone.detectado es un booleano sin memoria ni incertidumbre. Un
# radar real de barrido revisita el campo periódicamente y mantiene un TRACK
# (posición y velocidad ESTIMADAS, no la real) entre revisitas — ver
# ``radar_engine.TrackManager``. Auditoría §3.3: sin esto, un filtro α-β-γ
# sobre un booleano sería decorativo, porque HPMissile._resolver_objetivo y
# HPMissileSystem.lanzar apuntaban usando la posición REAL de cualquier dron
# "detectado", no una estimación con error.
#
# ⚠ ESTO MUEVE NÚMEROS CALIBRADOS (documentado, no un descuido): con barrido
# periódico, la detección de un dron recién aparecido ya no es instantánea
# (espera hasta la próxima revisita, como máximo RADAR_REVISITA_S segundos de
# retraso) y el punto de auto-apuntado del misil usa la posición ESTIMADA del
# centroide, no la real — puede diferir en algunos metros. El rango de
# detección en estado ESTACIONARIO (una vez adquirido el track y revisitado
# con regularidad) no cambia: sigue gobernado por evaluar_deteccion(), la
# misma ecuación de radar de arriba.
#
# Periodo de revisita: 1 s. Del orden de un radar de vigilancia de corto
# alcance/contra-UAS de barrido rápido (rotación de 1-4 s es común en esa
# clase de sistemas) — no una medición de ningún radar real, decisión de
# ingeniería declarada como tal.
RADAR_REVISITA_S: float = float(os.getenv("RADAR_REVISITA_S", "1.0"))

# Ganancias del filtro α-β-γ (posición, velocidad, aceleración). Valores de
# amortiguamiento moderado, tomados de la práctica estándar de filtros de
# seguimiento de ganancia fija (no ajustados contra ningún radar real,
# decisión de ingeniería) — verificados EMPÍRICAMENTE en
# tests/test_radar_dinamico.py: convergen sin oscilar sobre una trayectoria
# de velocidad constante y sobre una de aceleración constante, y no divergen
# ante una revisita de dato faltante.
RADAR_FILTRO_ALPHA: float = float(os.getenv("RADAR_FILTRO_ALPHA", "0.6"))
RADAR_FILTRO_BETA: float = float(os.getenv("RADAR_FILTRO_BETA", "0.3"))
RADAR_FILTRO_GAMMA: float = float(os.getenv("RADAR_FILTRO_GAMMA", "0.05"))

# Umbral de residual (m) entre la posición PREDICHA por el filtro y la
# posición MEDIDA en la revisita, más allá del cual el track se declara
# perdido (maniobra demasiado abrupta para que el modelo de aceleración
# constante la explique) — en vez de "corregir" el filtro hacia un salto que
# no es ruido de medición sino un cambio real de comportamiento. Un dron en
# vuelo recto a velocidad típica (10-30 m/s, ver VELOCIDAD_MIN/MAX) se
# desplaza 10-30 m por revisita de 1 s, bien explicado por el término de
# velocidad del filtro; el umbral se fija muy por encima de eso para no
# perder tracks en vuelo normal, y por debajo del desplazamiento que produce
# un giro boids al máximo (BOIDS_MAX_TURN_RATE_DEG_S) combinado con la
# velocidad máxima. Verificado empíricamente en
# tests/test_radar_dinamico.py: vuelo recto NO pierde el track, una maniobra
# evasiva fuerte SÍ.
RADAR_PERDIDA_TRACK_RESIDUAL_M: float = float(
    os.getenv("RADAR_PERDIDA_TRACK_RESIDUAL_M", "120.0")
)

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

# --- OPFOR reactivo: memoria de amenaza + repulsor con decaimiento (P2-E) ---
# Un enjambre con control reactivo real no vuelve a formación inmediatamente
# tras un impacto: cada dron recuerda dónde fue el último golpe (detonación
# de misil o exposición al cañón que le "pegó cerca") y durante un rato se
# aleja de ese punto, encima del flocking normal — dispersión post-ataque.
# Ver Drone.registrar_impacto/actualizar_amenaza y el 5to término de
# src/engine/flocking.py::compute_headings.
#
# Constante de tiempo del decaimiento exponencial de la intensidad de la
# memoria (intensidad *= exp(-dt/tau)). 5s da un "susto" que domina el
# comportamiento durante unos pocos segundos tras el golpe (varias veces la
# constante de tiempo del giro acotado de boids) y se disuelve en el orden
# de 15-20s (3-4·tau) — lo bastante para ver dispersión real en cualquier
# corrida de longitud típica de este simulador, sin dejar al enjambre
# huyendo indefinidamente de un punto que ya no es una amenaza.
THREAT_MEMORY_DECAY_TAU_S: float = float(os.getenv("THREAT_MEMORY_DECAY_TAU_S", "5.0"))
# Peso del término de amenaza en compute_headings, mismo orden de magnitud
# que los pesos de boids existentes (separación 1.5, alineación/cohesión
# 1.0, home 1.5) pero algo mayor: una reacción de pánico post-impacto real
# debería, al menos brevemente, dominar sobre la cohesión/alineación local
# (que es exactamente lo que hace que un enjambre atacado se disperse en
# vez de seguir volando en formación ordenada).
BOIDS_THREAT_WEIGHT: float = float(os.getenv("BOIDS_THREAT_WEIGHT", "2.5"))

# Propagación de alarma entre vecinos (P2-E, Parte 4 — biomimesis).
# Hallazgo real de literatura, antes NO implementado (ver
# docs/ESTADO_DEL_ARTE_BIOMIMESIS.md §2): Attanasi et al. (Nature Physics /
# arXiv:1303.7097) miden que en bandadas reales la alarma se propaga de
# vecino a vecino MÁS RÁPIDO que el reposicionamiento físico del grupo —
# un estornino ve a su vecino asustarse y reacciona él mismo, sin haber
# visto al depredador. Hasta este ítem, `_threat_vector` solo sembraba
# memoria de amenaza en el dron IMPACTADO DIRECTAMENTE (P2-E, Parte 2) —
# un enjambre bajo ataque real, salvo el dron golpeado, volaba exactamente
# igual que uno en patrulla tranquila.
#
# Ganancia de atenuación por salto: un dron SIN amenaza propia adopta la
# intensidad del vecino más alarmado, multiplicada por esta ganancia (< 1).
# < 1 es la condición que hace de esto una ONDA que se apaga, no una
# reacción en cadena que satura el enjambre entero a intensidad 1.0 en
# cualquier ataque puntual: con ganancia g y N saltos, la intensidad en el
# salto N es como mucho g^N — con g=0.7, al 5to salto ya está por debajo
# de 0.17, y un dron nunca puede tener MÁS intensidad que el que se la
# contagió (ver `flocking.propagate_alarm`: siempre `max(propia,
# vecino*ganancia)`, nunca al revés). 0.7 es deliberadamente alto (no
# 0.3-0.4): con una ganancia baja la propagación se apaga en 1-2 saltos y
# el efecto sería indistinguible de "solo el dron impactado reacciona" —
# el punto del ítem es que la onda alcance a varios vecinos más allá del
# punto de impacto, no solo al primero.
BOIDS_ALARM_PROPAGATION_GAIN: float = float(os.getenv("BOIDS_ALARM_PROPAGATION_GAIN", "0.7"))

# --- Misión ofensiva del enjambre ---
# Hasta acá el enjambre era prey puro: patrullaba alrededor de su propio
# centro de formación y solo reaccionaba si lo atacaban — nunca tuvo un
# objetivo propio. Sin un objetivo, "¿lo pararon a tiempo?" no es una
# pregunta que el modelo pueda responder, solo "¿cuántos neutralizaste?"
# — una métrica de laboratorio, no una operacional. Esto le da al
# enjambre una MISIÓN: avanzar hacia un punto (por defecto, el propio
# origen del arma — el enjambre ataca la batería que lo defiende, el
# motivo más simple de que esté ahí) y llegar cuenta como una brecha de
# la defensa. Ver ``Swarm.objetivo_x/y``/``_avanzar_formacion_hacia_
# objetivo`` y ``Drone.objetivo_alcanzado``.
#
# Condicional y apagado por defecto, mismo criterio que amenaza/home: con
# ``Swarm.objetivo_x = None`` (el default) esto no aporta nada — el
# enjambre patrulla exactamente igual que antes de este ítem. Se activa
# explícitamente por quien construye el ``Swarm``/``SimulationEngine``
# (``SimulationEngine.mision_activa``), NO globalmente acá, para no
# invalidar en silencio la calibración de distancia/potencia ya hecha en
# Monte Carlo y coevolución (``DISTANCIA_COMBATE_M`` en
# ``src/engine/coevolution.py``, `research/BARRIDO_DEPREDADOR_PRESA.md`) —
# esos experimentos siguen con la misión apagada salvo que se pida lo
# contrario a propósito.
#
# Velocidad de avance de la FORMACIÓN (no de cada dron — cada dron sigue
# gobernado por su propia velocidad individual, VELOCIDAD_MIN/MAX en
# swarm.py; esto es la velocidad a la que se mueve el ANCLA de cohesión
# que el enjambre persigue). 20 m/s cae en el medio del rango individual
# (10-30 m/s) — la formación avanza a un ritmo que un dron individual
# puede sostener, ni más rápido de lo físicamente plausible ni tan lento
# que nunca cierre la distancia dentro de una corrida típica de este
# proyecto (15-60s, ver ExperimentConfig.t_max_s).
SWARM_AVANCE_VELOCIDAD_M_S: float = float(os.getenv("SWARM_AVANCE_VELOCIDAD_M_S", "20.0"))

# Radio (m) dentro del cual un dron activo se considera que "alcanzó" el
# objetivo — una brecha de la defensa. Más chico que el radio de efecto
# típico de un misil HPM propio (50-200 m, ver el rango válido de
# ``misil_radio`` en ``ExperimentRequest``/``MissileRequest`` de
# ``src/api/routes.py``): llegar y estar sobre el objetivo es una
# tolerancia más ajustada que el área que nuestra propia arma logra cubrir
# de un pulso.
SWARM_OBJETIVO_RADIO_IMPACTO_M: float = float(os.getenv("SWARM_OBJETIVO_RADIO_IMPACTO_M", "30.0"))

# --- Estructuras atacables (edificios) — ver src/models/structure.py ---
# A diferencia del vehículo (un solo impacto kamikaze lo inutiliza), un
# edificio tiene "salud" propia porque son varios drones chicos contra
# una construcción real, no contra electrónica expuesta — un solo FPV no
# tira una pared. 100/25 = 4 drones en promedio para destruir uno,
# número redondo elegido para que sea un objetivo con cuerpo (no un
# solo-hit como el vehículo) pero alcanzable por una fracción razonable
# de un enjambre de 30-50, no todo el enjambre entero.
ESTRUCTURA_SALUD_MAXIMA: float = float(os.getenv("ESTRUCTURA_SALUD_MAXIMA", "100.0"))
ESTRUCTURA_DANO_POR_DRON: float = float(os.getenv("ESTRUCTURA_DANO_POR_DRON", "25.0"))
# Mismo radio que SWARM_OBJETIVO_RADIO_IMPACTO_M por defecto (constante
# aparte, ajustable independiente — un edificio real tiene más "cuerpo"
# físico que el vehículo, podría justificar un radio distinto más
# adelante, pero no hay medición todavía que lo respalde).
ESTRUCTURA_RADIO_IMPACTO_M: float = float(os.getenv("ESTRUCTURA_RADIO_IMPACTO_M", "30.0"))
# Radio (m) del footprint que bloquea línea de vista (ver
# hpm_engine.linea_de_vista_bloqueada) — más chico que el radio de
# impacto de arriba a propósito: "llegaste y contás como que llegaste"
# (impacto) es un área más generosa que "esto bloquea físicamente un haz"
# (bloqueo), que debería aproximar el tamaño real de una construcción
# chica, no todo el radio de tolerancia de la misión.
ESTRUCTURA_RADIO_BLOQUEO_M: float = float(os.getenv("ESTRUCTURA_RADIO_BLOQUEO_M", "12.0"))

# Peso del término de "acercamiento final" en compute_headings (ver
# flocking._final_approach_vector). Medido durante el diseño de este
# ítem, en dos pasos:
#
# 1. Sin este término, avanzar SOLO el ancla de cohesión (formacion_x/y
#    hacia objetivo_x/y) no alcanza — _home_vector da fuerza CERO dentro
#    de BOIDS_HOME_RADIUS (es un límite de "no te alejes", no una meta de
#    "andá hacia acá"), así que el enjambre queda orbitando indefinidamente
#    a ~BOIDS_HOME_RADIUS del objetivo (verificado: 120s simulados, ningún
#    dron se acercó a menos de ~195m).
# 2. Con este término pero en el mismo orden de magnitud que los otros
#    pesos de boids (se probó 2.0, comparable a home=1.5/amenaza=2.5), el
#    enjambre queda en un SEGUNDO equilibrio estable, más cerca pero
#    tampoco llega: la fuerza de separación entre drones comprimidos
#    hacia el mismo punto (que también crece a medida que se acercan)
#    empata a la atracción antes de entrar al radio de impacto —
#    verificado: 10 drones, 300s simulados, congelado en ~211m desde el
#    segundo 60, sin una sola brecha. La atracción es CONSTANTE
#    (vector unitario) pero la separación local crece con la densidad del
#    grupo comprimiéndose — a peso parejo, separación gana.
#
# 8.0 (empírico, ~3-5× el resto de los pesos) es lo que hizo falta para
# que la atracción realmente domine a la separación en el tramo final:
# verificado con 10 y con 50 drones (el tamaño por defecto de la demo en
# vivo, SWARM_SIZE) — en ambos casos el enjambre converge completo dentro
# de ~60-80s simulados, sin oscilación, asentándose justo dentro de
# SWARM_OBJETIVO_RADIO_IMPACTO_M (27-29m). No es un valor "elegante" — es
# el que se necesitó para vencer una fuerza que compite de verdad, medido
# corriendo el motor real, no estimado a mano.
BOIDS_MISSION_WEIGHT: float = float(os.getenv("BOIDS_MISSION_WEIGHT", "8.0"))

# --- OPFOR reactivo: perfiles de pérdida de enlace (P2-E) ---
# Antes, perder el enlace (jammer) "congelaba" al dron (Drone.mover
# retornaba temprano) — no es lo que hace un dron real: ejecuta un
# comportamiento de contingencia PROGRAMADO. Se sortea un perfil por dron
# al crearlo (como el blindaje), con el generador inyectado, no el global.
#
# Reparto por defecto, basado en la doctrina pública de failsafe de
# radio-control de flight controllers reales (Ardupilot/PX4/DJI, que
# documentan explícitamente estos cuatro comportamientos como opciones de
# failsafe configurables):
#   - RTH (0.40): el failsafe primario recomendado y más comúnmente
#     configurado por defecto en la práctica — la mayoría del enjambre
#     "hace lo correcto".
#   - HOVER (0.30): mantener posición ("Loiter"/"Brake") es el
#     comportamiento INMEDIATO casi universal antes de que se cumpla el
#     timeout que dispara RTH/Land — con timeouts cortos, una fracción
#     grande del enjambre queda efectivamente en este estado la mayor
#     parte del tiempo que dura la pérdida de enlace.
#   - ATERRIZAR (0.20): "Land now" es el otro failsafe primario soportado
#     por (casi) todo flight controller moderno, preferido en operación
#     urbana/restringida donde alejarse no es aceptable.
#   - FLYAWAY (0.10): la falla residual real y documentada del propio
#     ecosistema (GPS/compás caído, firmware sin failsafe configurado,
#     etc.) — deliberadamente NO cero: es precisamente el caso que hace de
#     un enjambre sin enlace una amenaza que sigue existiendo, no un
#     problema resuelto por completo. Las cuatro fracciones suman 1.0.
DRONE_LOST_LINK_RTH_FRACTION: float = float(os.getenv("DRONE_LOST_LINK_RTH_FRACTION", "0.40"))
DRONE_LOST_LINK_HOVER_FRACTION: float = float(os.getenv("DRONE_LOST_LINK_HOVER_FRACTION", "0.30"))
DRONE_LOST_LINK_ATERRIZAR_FRACTION: float = float(
    os.getenv("DRONE_LOST_LINK_ATERRIZAR_FRACTION", "0.20")
)
DRONE_LOST_LINK_FLYAWAY_FRACTION: float = float(
    os.getenv("DRONE_LOST_LINK_FLYAWAY_FRACTION", "0.10")
)
# Tasa de descenso del perfil ATERRIZAR, en m/s. Del orden de un descenso
# controlado tipo "land now" de un multirotor real (1-3 m/s), no una caída
# libre ni un descenso instantáneo.
DRONE_LOST_LINK_DESCENT_RATE_M_S: float = float(
    os.getenv("DRONE_LOST_LINK_DESCENT_RATE_M_S", "2.0")
)

# --- Upset vs damage + fallo latente (P2-D) ---
# Reemplaza la premisa cortada de P3-09 (thermal runaway de batería, que
# fallaba el presupuesto energético por ~10⁹: 10-20 kJ para llevar una celda
# 18650 a runaway contra microjulios acoplados por un pulso de 100 ns — ver
# docs/AUDITORIA_CHECKLIST.md §3.6). Se conserva la maquinaria valiosa de ese
# ítem (decaimiento por tick + atribución diferida de bajas al disparo
# original) con el mecanismo físico correcto: la literatura de vulnerabilidad
# EMI separa UPSET (perturbación RECUPERABLE — reset de brownout,
# desincronización de ESC, deriva de IMU, pérdida momentánea de fix GPS) de
# DAMAGE (falla PERMANENTE — ruptura de óxido de puerta, latchup destructivo).
# Una sola sigmoide a "neutralizado" no puede expresar el caso operativamente
# decisivo: un enjambre que se desordena y SE RECUPERA.
#
# DECISIÓN DE MODELADO (categoría 3, NO dato de ningún paper — a diferencia
# de HPM_SUBSISTEMAS, que sí son los umbrales publicados de daño permanente):
# el umbral de UPSET se deriva del umbral de DAÑO ya calibrado
# (HPM_LOGLOGISTIC_E50_V_M / HPM_MISSILE_LOGLOGISTIC_E50_V_M) escalado por una
# brecha en dB de campo. Se evita depender de P1-C (bloqueado, ver
# docs/FISICA_Y_MATEMATICA.md §3.6): usar los umbrales absolutos de la Tabla 1
# del paper mezclaría un modelo NO validado con la contabilidad de upset. La
# convención general en literatura de vulnerabilidad EMI/IEMI para
# electrónica digital sitúa los umbrales de upset recuperable entre 10 y
# 20 dB por debajo del umbral de daño permanente, en campo. Se toma el
# extremo CONSERVADOR de ese rango (10 dB — el upset "cuesta" relativamente
# poco campo), que en amplitud de campo es un factor 10^(10/20) ≈ 3.162:
#     E50_upset = E50_damage / 3.162
# Mismo exponente de forma ``b`` que el umbral de daño: no se inventa una
# segunda curva, se desplaza la ya calibrada.
HPM_UPSET_DB_GAP_FIELD: float = float(os.getenv("HPM_UPSET_DB_GAP_FIELD", "10.0"))

# Duración de exposición para CONTABILIDAD DE ENERGÍA ABSORBIDA (Parte 2 —
# NO la probabilidad de daño, que ya usa el campo INSTANTÁNEO vía duty
# cycle/Wunsch-Bell). Mismo razonamiento que motivó HPM_DISPARO_DURACION_S en
# P2-F para el presupuesto del ARMA: la energía de un pulso aislado
# (potencia · HPM_PULSE_DURATION_NS) da microjulios, irrelevante para
# cualquier contabilidad acumulativa — lo que importa es la ráfaga completa.
# El cañón reutiliza HPM_DISPARO_DURACION_S (mismo evento físico, la ráfaga
# de tierra). El misil tiene su propia duración, mucho más corta: una
# detonación es un evento único, no una ráfaga sostenida — el tren de pulsos
# de un misil tipo CHAMP dura del orden de decenas de milisegundos, no medio
# segundo.
MISSILE_DETONACION_DURACION_S: float = float(
    os.getenv("MISSILE_DETONACION_DURACION_S", "0.05")
)

# Hazard rate MÁXIMO inicial (1/s) al entrar en "riesgo latente" — el caso de
# una exposición en la zona de upset, más cerca del umbral de daño que del de
# upset (severidad→1 en la escala [0,1] de esa zona, ver
# Drone.recibir_daño).
#
# DERIVACIÓN (no un número elegido a ojo): con un hazard rate que decae
# exponencialmente con constante de tiempo τ (``DRONE_RIESGO_LATENTE_
# DECAY_TAU_S`` abajo), la probabilidad de que el riesgo madure en una
# neutralización ALGUNA VEZ (integrando la exposición completa, no un solo
# tick) es:
#     P(falla eventual) = 1 - exp(-h₀·τ)
# donde h₀ es el hazard inicial. Se fija el peor caso posible (severidad=1,
# la exposición justo por debajo del umbral de daño) en un lanzamiento de
# moneda: P(falla eventual) = 0.5 ⟹ h₀·τ = ln(2) ⟹ h₀ = ln(2)/τ.
# Con τ=4s: h₀ ≈ 0.1733/s. Consecuencia: en el PEOR caso de upset, la mitad
# de los drones se recupera y la mitad no — y para el resto de la zona
# (severidad<1) las chances de recuperarse son mayores. Verificado por
# simulación (no solo por la fórmula cerrada): a severidad=0.6 sobre 2000
# repeticiones, ~19-20% de fallo eventual, consistente con
# 1-exp(-0.6·0.1733·4).
DRONE_RIESGO_LATENTE_MAX_POR_S: float = float(
    os.getenv("DRONE_RIESGO_LATENTE_MAX_POR_S", "0.1733")
)

# Constante de tiempo de decaimiento del riesgo latente (s). Deliberadamente
# CORTA frente a THREAT_MEMORY_DECAY_TAU_S (memoria táctica del enjambre,
# P2-E): un upset electrónico real (brownout, desincronización) se resuelve
# en segundos si el subsistema no llegó a fallar del todo, no en la escala de
# tiempo de una maniobra de enjambre.
DRONE_RIESGO_LATENTE_DECAY_TAU_S: float = float(
    os.getenv("DRONE_RIESGO_LATENTE_DECAY_TAU_S", "4.0")
)

# --- Logging de validación en terminal ---
SIM_LOG_LEVEL: str = os.getenv("SIM_LOG_LEVEL", "INFO")

# --- Reproducibilidad ---
# Semilla del generador aleatorio global (PCG64). None (default) = corrida
# no determinista. Con un entero, cualquier corrida/esperimento es bit a bit
# reproducible (ver src/utils/reproducibilidad.py).
_SIM_SEED_RAW = os.getenv("SIM_SEED")
SIM_SEED: int | None = int(_SIM_SEED_RAW) if _SIM_SEED_RAW else None
