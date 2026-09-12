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
# arXiv:2602.08477, tomados como publicados y NO ajustados. Procedencia
# declarada en docs/REFERENCIA_PAPER_2602.08477.md §1 (extraídos del HTML de
# arXiv con dos fetches independientes concordantes; pendiente de confirmar
# contra el PDF).
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
# ⚠ VALOR PROVISIONAL — NO VALIDADO. El modelo de subsistemas está BLOQUEADO
# (ver CHECKLIST_MEJORAS.md P1-C y docs/FISICA_Y_MATEMATICA.md §3.6): con
# ninguna de las dos calibraciones intentadas reproduce los dos puntos
# publicados dentro de los márgenes del paper.
#
#   ajuste contra el DETERMINISTA : k = 0.2568  → residuos −0.11 / +0.62 pp
#       (parecía cerrar, pero es un error de método: ajustar un cálculo
#        determinista a puntos que son SALIDA de un Monte Carlo es exactamente
#        el defecto §1.3 de la auditoría, absorber el sesgo del MC dentro de un
#        parámetro. Se descartó.)
#   ajuste con el MC EN EL LAZO   : k = 0.3693  → residuos −1.48 / +4.19 pp
#       (método correcto, pero NO cierra: el residuo a 40 m es 6× el margen)
#
# Se deja el valor del ajuste correcto (0.3693) porque es el metodológicamente
# defendible, aunque no valide. Nada del comportamiento por defecto depende de
# él: HPM_DAMAGE_MODEL = "agregado".
HPM_COUPLING_FIELD_EFFICIENCY: float = float(
    os.getenv("HPM_COUPLING_FIELD_EFFICIENCY", "0.3693")
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
DRONE_POLARIZATION_MIN: float = float(os.getenv("DRONE_POLARIZATION_MIN", "0.3"))
# Piso de η_pol = cos²φ en el modelo del paper (P1-B). Distinto de
# DRONE_POLARIZATION_MIN, que acota un sorteo UNIFORME del factor de potencia:
# éste acota cos²φ con φ ~ U[0,π], cuya densidad diverge en 0. Sin piso, una
# fracción no despreciable de blancos quedaría con acoplamiento numéricamente
# nulo — y un blanco perfectamente cruzado en polarización igual acopla algo,
# por despolarización del entorno y por la geometría 3D real del cableado.
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

# --- Reproducibilidad ---
# Semilla del generador aleatorio global (PCG64). None (default) = corrida
# no determinista. Con un entero, cualquier corrida/esperimento es bit a bit
# reproducible (ver src/utils/reproducibilidad.py).
_SIM_SEED_RAW = os.getenv("SIM_SEED")
SIM_SEED: int | None = int(_SIM_SEED_RAW) if _SIM_SEED_RAW else None
