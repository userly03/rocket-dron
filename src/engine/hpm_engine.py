"""
Motor HPM: dos modelos de probabilidad de neutralización.

- "legacy" (``calculate_neutralization_probability`` /
  ``calculate_area_neutralization_probability``): exponencial ad-hoc,
  P = 1 - exp(-k · potencia / distancia²), con atenuación angular en los
  bordes del cono. Nota de auditoría: una versión previa de este docstring
  atribuía esta fórmula a arXiv:2602.08477 — verificado (ver
  docs/FISICA_Y_MATEMATICA.md), esa atribución era incorrecta. El paper real
  usa un modelo sigmoide sobre densidad de potencia/campo E calibrado contra
  umbrales de latchup CMOS publicados, que es lo que sí implementa el modelo
  "friis" de abajo — no esta exponencial.

- "friis" (``calculate_neutralization_probability_friis`` /
  ``calculate_area_neutralization_probability_friis``): física real —
  densidad de potencia (ecuación de Friis) -> campo E (V/m) -> sigmoide
  sobre un umbral de susceptibilidad, calibrado contra los datos publicados
  en arXiv:2602.08477. Ver docs/FISICA_Y_MATEMATICA.md para el desarrollo
  completo y las fuentes.
"""

from __future__ import annotations

import numpy as np

from src.config import (
    HPM_APERTURE_EFFICIENCY,
    HPM_CONE_APERTURE,
    HPM_COUPLING_FIELD_EFFICIENCY,
    HPM_COUPLING_Q,
    HPM_DISH_DIAMETER_M,
    HPM_DUTY_CYCLE,
    HPM_E_THRESHOLD_V_M,
    HPM_FREQUENCY_GHZ,
    HPM_K_CONSTANT,
    HPM_LINK_FUNCTION,
    HPM_LOGLOGISTIC_B,
    HPM_LOGLOGISTIC_E50_V_M,
    HPM_MISSILE_E_THRESHOLD_V_M,
    HPM_MISSILE_LOGLOGISTIC_B,
    HPM_MISSILE_LOGLOGISTIC_E50_V_M,
    HPM_MISSILE_SIGMOID_STEEPNESS,
    HPM_PULSE_DURATION_NS,
    HPM_PULSE_TAU_ADIABATICO_NS,
    HPM_PULSE_TAU_ESTACIONARIO_NS,
    HPM_SIGMOID_STEEPNESS,
    HPM_SUBSISTEMAS,
    HPM_SUBSISTEMAS_LOGLOGISTIC_B,
    HPM_UPSET_DB_GAP_FIELD,
)
from src import config as config_mod
from src.engine.radar_engine import SPEED_OF_LIGHT_M_S
from src.utils.helpers import angle_difference, distance, distance3d

VACUUM_IMPEDANCE_OHM = 377.0


def probabilidad_desde_campo(
    campo_v_m: float,
    e_threshold: float,
    steepness: float,
    e50: float,
    b: float,
    link: str | None = None,
) -> float:
    """
    Convierte un campo E (V/m) en probabilidad de daño, según la función de
    enlace configurada (``HPM_LINK_FUNCTION``).

    **log_logistica** (default desde P1-F):

        P(E) = 1 / (1 + (E₅₀/E)^b)        P(0) = 0 exacto,  P(∞) = 1

    **logistica** (legacy, se conserva para comparar y para no romper tuning
    previo):

        P(E) = 1 / (1 + exp(-k·(E - E₀)))     P(0) = 1/(1+exp(k·E₀)) ≠ 0

    POR QUÉ CAMBIÓ EL DEFAULT. La logística tiene soporte en todo ℝ, pero el
    campo eléctrico es positivo. El resultado era un **piso** de 2.30 % (modelo
    agregado) o 3.30 % (OR-gate de cinco subsistemas) a campo CERO: un dron sin
    campo aplicado tenía 2-3 % de caer. Más allá de ~97 m más de la mitad de la
    probabilidad reportada era ese piso, y a 700 m —todo el rango de combate por
    defecto— el 90.7 % del número era artefacto. Ver
    docs/FISICA_Y_MATEMATICA.md §3.7.

    La log-logística (equivalentemente, una logística en ``ln E``) es el modelo
    estándar de dosis-respuesta para dosis positivas, justamente porque el
    soporte de la distribución de umbrales es ``(0, ∞)``. Ajusta los MISMOS dos
    puntos publicados con los MISMOS dos parámetros libres, y con residuo
    exacto (0.0000 pp) en vez de −1.92 pp.

    Conversión entre familias, cuando hace falta migrar parámetros: la que
    **preserva la pendiente en E₅₀** es ``b = E₅₀/σ``, porque
    ``dP/dE|E₅₀`` vale ``1/(4σ)`` en la logística y ``b/(4·E₅₀)`` en la
    log-logística.
    """
    modelo = HPM_LINK_FUNCTION if link is None else link

    if modelo == "log_logistica":
        if campo_v_m <= 0.0:
            return 0.0
        e50_seguro = max(float(e50), 1e-9)
        # P(E) = 1/(1+(E₅₀/E)^b) = sigmoide(b·ln(E/E₅₀)) — misma función,
        # reescrita para no desbordar cuando E es astronómicamente chico
        # frente a E₅₀ (ej. un desapunte extremo bajo el taper gaussiano de
        # apuntado, que nunca llega a cero exacto, a diferencia del taper de
        # cono — ver ``src.engine.experiments._factor_taper_haz``): con E
        # pequeño, ``(E₅₀/E)**b`` desborda ``float`` mucho antes de que la
        # probabilidad deje de ser, para cualquier propósito práctico, 0.
        x = b * float(np.log(campo_v_m / e50_seguro))
        if x >= 0:
            p = 1.0 / (1.0 + np.exp(-x))
        else:
            z = np.exp(x)
            p = z / (1.0 + z)
        return float(np.clip(p, 0.0, 1.0))

    if modelo == "logistica":
        exponent = -steepness * (campo_v_m - e_threshold)
        return float(np.clip(1.0 / (1.0 + np.exp(exponent)), 0.0, 1.0))

    raise ValueError(
        f"HPM_LINK_FUNCTION debe ser 'log_logistica' o 'logistica', no {modelo!r}"
    )



def resonance_frequency_ghz(cable_length_m: float) -> float:
    """Frecuencia de resonancia de un cableado tipo dipolo de media onda: f = c/(2L)."""
    if cable_length_m <= 0:
        return float("inf")
    return SPEED_OF_LIGHT_M_S / (2.0 * cable_length_m) / 1e9


def frequency_coupling(
    cable_length_m: float,
    frequency_ghz: float = HPM_FREQUENCY_GHZ,
    q: float = HPM_COUPLING_Q,
) -> float:
    """
    Eficiencia de acoplamiento η(f): lorentziana centrada en la resonancia
    del cableado con ancho f_res/Q. η = 1 en f = f_res; cae a ambos lados —
    un blanco con cableado desintonizado respecto a la frecuencia del arma
    acopla mucha menos energía (misma fuente de incertidumbre que el Monte
    Carlo del paper de referencia, acá determinística por dron).
    """
    f_res = resonance_frequency_ghz(cable_length_m)
    ancho = max(f_res / max(q, 1e-6), 1e-9)
    return float(1.0 / (1.0 + ((frequency_ghz - f_res) / ancho) ** 2))


def susceptibility_coupling_factor(
    cable_length_m: float | None = None,
    polarization: float | None = None,
    frequency_ghz: float = HPM_FREQUENCY_GHZ,
    q: float = HPM_COUPLING_Q,
) -> float:
    """
    Factor de AMPLITUD de campo que acopla el blanco: √(η(f) · pol).

    η(f) es la eficiencia de acoplamiento por resonancia (en potencia); pol
    es el factor de mismatch de polarización [0,1] (1 = acoplamiento óptimo,
    como el parámetro de "polarization mismatch" del paper). La amplitud del
    campo inducido escala con la raíz de la eficiencia en potencia. Sin
    cable ni polarización (None, None) el factor es 1 — el modelo queda
    idéntico al anterior (compatibilidad con el calibrado).
    """
    if cable_length_m is None and polarization is None:
        return 1.0
    eta = frequency_coupling(cable_length_m, frequency_ghz, q) if cable_length_m is not None else 1.0
    pol = float(np.clip(polarization, 0.0, 1.0)) if polarization is not None else 1.0
    return float(np.sqrt(eta * pol))


def _credito_wunsch_bell_crudo(
    tau_ns: float,
    tau_adiabatico_ns: float,
    tau_estacionario_ns: float,
) -> float:
    """Ley Wunsch-Bell por tramos, anclada en el quiebre adiabático/difusión.

    Devuelve el crédito en AMPLITUD de campo, sin normalizar todavía (vale 1
    exactamente en ``tau_adiabatico_ns``). ``pulse_coupling_factor`` lo
    normaliza contra el pulso de referencia.
    """
    t1 = max(tau_adiabatico_ns, 1e-9)
    t2 = max(tau_estacionario_ns, t1)

    if tau_ns <= t1:
        # Adiabático: E_fail ∝ τ^(-1/2)  →  crédito ∝ τ^(1/2)
        return float((tau_ns / t1) ** 0.5)
    if tau_ns <= t2:
        # Difusión térmica: E_fail ∝ τ^(-1/4)  →  crédito ∝ τ^(1/4)
        return float((tau_ns / t1) ** 0.25)
    # Estado estacionario: el umbral deja de depender de τ. El techo NO es un
    # tope arbitrario: es el valor que la rama de difusión alcanza en t2.
    return float((t2 / t1) ** 0.25)


def pulse_coupling_factor(
    pulse_duration_ns: float | None = None,
    reference_ns: float = HPM_PULSE_DURATION_NS,
    tau_adiabatico_ns: float = HPM_PULSE_TAU_ADIABATICO_NS,
    tau_estacionario_ns: float = HPM_PULSE_TAU_ESTACIONARIO_NS,
) -> float:
    """
    Crédito de acoplamiento por duración de pulso g(τ), según el modelo de
    quemado de junturas de **Wunsch-Bell** (Wunsch & Bell 1968, IEEE Trans.
    Nucl. Sci. 15(6):244-259). NO viene del paper de referencia del proyecto:
    arXiv:2602.08477 escala el campo pico con el duty cycle y no incorpora
    ningún escalado por duración de pulso (ver
    docs/REFERENCIA_PAPER_2602.08477.md §6). Es una extensión propia, con su
    propia cita y su propia ventana de validez.

    DERIVACIÓN (la cadena de unidades es lo que hace falta cuidar):

    Wunsch-Bell da un umbral de **potencia absorbida** ``P_fail(τ)``, con tres
    regímenes según cuánto alcanza a difundir el calor durante el pulso:

        adiabático        (τ ≲ τ₁)        P_fail ∝ τ⁻¹     (falla por ENERGÍA)
        difusión térmica  (τ₁ ≲ τ ≲ τ₂)   P_fail ∝ τ^(-1/2)  (el Wunsch-Bell clásico)
        estado estacionario (τ ≳ τ₂)      P_fail ∝ τ⁰      (independiente de τ)

    Pero la sigmoide de daño de este motor opera sobre el **campo E**, no sobre
    potencia. La conversión no es opcional: la potencia acoplada al blanco va
    como el cuadrado de la tensión inducida, y ésta es proporcional al campo
    incidente (``V_ind ∝ E``, ``P ∝ V²/R``), así que ``P_absorbida ∝ E²`` y el
    umbral en campo es la raíz del umbral en potencia:

        E_fail(τ) ∝ √(P_fail(τ))

    Aplicando eso a los tres regímenes:

        adiabático           E_fail ∝ τ^(-1/2)   →   g(τ) ∝ τ^(1/2)
        difusión térmica     E_fail ∝ τ^(-1/4)   →   g(τ) ∝ τ^(1/4)
        estado estacionario  E_fail = const      →   g(τ) = const

    ``g`` es el inverso del umbral (en vez de BAJAR ``E₀`` dentro de la
    sigmoide, se SUBE el campo efectivo por el factor recíproco — es
    numéricamente equivalente y evita exactamente el error del hallazgo 7 de
    docs/FISICA_Y_MATEMATICA.md, donde desplazar el umbral dentro de una
    sigmoide no lineal producía reducciones de 14× a 821× en vez de las
    pedidas).

    CONTINUIDAD: ambos quiebres empalman en valor por construcción, porque los
    tres tramos están anclados al mismo τ₁ y evaluados en el punto de quiebre
    dan lo mismo por ambos lados —
    en τ₁:  (τ₁/τ₁)^(1/2) = 1 = (τ₁/τ₁)^(1/4);
    en τ₂:  la rama de difusión vale (τ₂/τ₁)^(1/4), que es literalmente la
    constante del tramo estacionario. g es continua (no derivable en los
    quiebres, que es lo físicamente esperado en un cambio de régimen).

    NORMALIZACIÓN: el resultado se divide por el crudo en ``reference_ns``, de
    modo que ``g(τ_ref) = 1`` **exactamente** para cualquier configuración.
    Eso es un requisito duro, no una conveniencia: la calibración del modelo
    (43.56% @ 20 m, 11.87% @ 40 m, ver tests/test_calibracion.py) se hizo con
    τ = τ_ref, y cualquier valor distinto de 1 la movería. Con los defaults
    τ_ref = τ₁ = 100 ns, el pulso de referencia cae justo en el quiebre
    adiabático/difusión y la normalización es la identidad.

    CORRECCIÓN QUE INTRODUJO ESTE MODELO (P1-E): la versión anterior usaba
    ``g(τ) = min(√(τ/τ_ref), 3.0)``. Dos defectos que se cancelaban
    parcialmente entre sí:

      1. El exponente 1/2 en el régimen de difusión era **una raíz de más**:
         saltaba la conversión potencia→campo y aplicaba al campo el exponente
         que corresponde a la potencia. El correcto es 1/4.
      2. El tope ``3.0`` era un número mágico — pero resulta ser casi exacto
         como techo del régimen estacionario: (τ₂/τ₁)^(1/4) = 100^(1/4) ≈
         3.162. O sea que el valor del techo estaba bien por casualidad,
         mientras el exponente estaba mal. El efecto neto era que la
         saturación ocurría a τ ≈ 900 ns (donde √(τ/τ_ref) alcanza 3) en vez
         de a los 10 µs físicos, y entre 100 ns y 900 ns el crédito crecía al
         doble de velocidad de lo que corresponde.

    Ver docs/FISICA_Y_MATEMATICA.md §3.5 para el desarrollo completo y la
    clasificación de esta ley en el sistema de tres categorías del documento.
    """
    tau = reference_ns if pulse_duration_ns is None else pulse_duration_ns
    if tau <= 0:
        return 1.0

    crudo = _credito_wunsch_bell_crudo(tau, tau_adiabatico_ns, tau_estacionario_ns)
    crudo_ref = _credito_wunsch_bell_crudo(
        max(reference_ns, 1e-9), tau_adiabatico_ns, tau_estacionario_ns
    )
    if crudo_ref <= 0:
        return 1.0
    return float(crudo / crudo_ref)


def calculate_area_neutralization_probability(
    potencia: float,
    distancia: float,
    k: float = HPM_K_CONSTANT,
) -> float:
    """
    Probabilidad de neutralización por efecto HPM de área (misil CHAMP).

    P = 1 - exp(-k * potencia / distancia²)

    Sin atenuación angular — todos los blancos dentro del radio son evaluados.
    """
    if distancia <= 0:
        return 1.0
    intensidad = potencia / (distancia**2)
    return float(np.clip(1.0 - np.exp(-k * intensidad), 0.0, 1.0))


def calculate_neutralization_probability(
    potencia: float,
    distancia: float,
    angulo_offset: float,
    apertura_cono: float,
    k: float = HPM_K_CONSTANT,
) -> float:
    """
    Calcula la probabilidad de neutralización de un blanco.

    Args:
        potencia: Potencia del HPM en kW.
        distancia: Distancia al blanco en metros.
        angulo_offset: Desviación angular respecto al eje del cono (grados).
        apertura_cono: Apertura total del cono en grados.
        k: Constante del modelo exponencial.
    """
    if distancia <= 0:
        return 1.0

    half_cone = apertura_cono / 2.0
    if abs(angulo_offset) > half_cone:
        return 0.0

    intensidad = potencia / (distancia**2)
    probabilidad_base = 1.0 - np.exp(-k * intensidad)

    if half_cone > 0:
        normalized_offset = abs(angulo_offset) / half_cone
        factor_angular = np.cos(normalized_offset * (np.pi / 2.0)) ** 2
    else:
        factor_angular = 1.0

    return float(np.clip(probabilidad_base * factor_angular, 0.0, 1.0))


def antenna_gain_from_aperture(apertura_deg: float) -> float:
    """
    Ganancia aproximada de una antena direccional a partir de su apertura de
    haz (grados) — aproximación estándar de ingeniería de RF:

        G ≈ 26000 / (θ_az · θ_el)

    Se asume haz simétrico (θ_az = θ_el = apertura_cono), ya que el modelo
    solo tiene un ángulo de apertura configurado.
    """
    apertura = max(float(apertura_deg), 1.0)
    return 26000.0 / (apertura**2)


def power_density(potencia_w: float, ganancia: float, distancia_m: float) -> float:
    """
    Densidad de potencia en espacio libre (ecuación de Friis):

        S = (P · G) / (4π r²)   [W/m²]
    """
    r = max(float(distancia_m), 1e-6)
    return (potencia_w * ganancia) / (4.0 * np.pi * r**2)


def efield_from_power_density(densidad_w_m2: float) -> float:
    """
    Campo eléctrico E (V/m) a partir de la densidad de potencia, usando la
    impedancia del espacio libre (377 Ω):

        E = sqrt(S · 377)
    """
    return float(np.sqrt(max(float(densidad_w_m2), 0.0) * VACUUM_IMPEDANCE_OHM))


def friis_diagnostics(
    potencia_kw: float,
    distancia: float,
    apertura_cono: float = 360.0,
    angulo_offset: float = 0.0,
    duty_cycle: float = 1.0,
    pulse_duration_ns: float | None = None,
    rango_horizontal_m: float | None = None,
    altura_rx_m: float | None = None,
) -> dict:
    """Calcula ganancia, densidad de potencia y campo E para reporte/validación.

    ``potencia_kw`` es la potencia PROMEDIO; el campo se calcula con el PICO
    (promedio / duty_cycle), porque el daño tipo latchup depende del campo
    instantáneo durante el pulso. ``campo_e_efectivo_v_m`` aplica además el
    crédito por duración de pulso (ver ``pulse_coupling_factor``) — es el
    valor que entra a la sigmoide de daño.
    """
    duty = float(np.clip(duty_cycle, 1e-3, 1.0))
    potencia_pico_kw = potencia_kw / duty
    ganancia = antenna_gain_from_aperture(apertura_cono) if apertura_cono < 360 else 1.0
    potencia_w = potencia_pico_kw * 1000.0
    densidad = power_density(potencia_w, ganancia, distancia)

    half_cone = apertura_cono / 2.0
    if 0 < apertura_cono < 360 and half_cone > 0:
        # Patrón de antena (P2-C). Por defecto el taper cos² histórico; con
        # PROPAGATION_ANTENNA_PATTERN="airy" el patrón real de apertura
        # circular, que tiene lóbulos laterales. El factor de propagation es
        # de AMPLITUD, así que se eleva al cuadrado para la densidad de
        # potencia. Import local para no crear un ciclo de módulos.
        from src.engine.propagation import factor_patron_antena

        densidad *= factor_patron_antena(angulo_offset, apertura_cono) ** 2

    # Reflexión en tierra (P2-C, opt-in). Requiere la geometría vertical, que
    # friis_diagnostics no recibe: sin ella el efecto no se puede calcular, así
    # que se omite en silencio. Los llamadores que sí tienen la geometría
    # (HPMWeapon.disparar, que conoce origen_z y drone.z) la pasan explícita.
    if (
        config_mod.PROPAGATION_GROUND_REFLECTION
        and rango_horizontal_m is not None
        and altura_rx_m is not None
    ):
        from src.engine.propagation import factor_dos_rayos

        densidad *= factor_dos_rayos(rango_horizontal_m, altura_rx_m) ** 2

    campo_e = efield_from_power_density(densidad)
    acoplamiento = pulse_coupling_factor(pulse_duration_ns)
    return {
        "ganancia_antena": round(ganancia, 4),
        "potencia_promedio_kw": round(potencia_kw, 4),
        "potencia_pico_kw": round(potencia_pico_kw, 4),
        "duty_cycle": round(duty, 4),
        "acoplamiento_pulso": round(acoplamiento, 4),
        "densidad_potencia_w_m2": round(densidad, 6),
        "campo_e_v_m": round(campo_e, 4),
        "campo_e_efectivo_v_m": round(campo_e * acoplamiento, 4),
    }


def calculate_neutralization_probability_friis(
    potencia_kw: float,
    distancia: float,
    apertura_cono: float,
    angulo_offset: float = 0.0,
    e_threshold: float = HPM_E_THRESHOLD_V_M,
    steepness: float = HPM_SIGMOID_STEEPNESS,
    e50: float = HPM_LOGLOGISTIC_E50_V_M,
    b: float = HPM_LOGLOGISTIC_B,
    link: str | None = None,
    duty_cycle: float = 1.0,
    pulse_duration_ns: float | None = None,
    cable_length_m: float | None = None,
    polarization: float | None = None,
    frequency_ghz: float = HPM_FREQUENCY_GHZ,
) -> float:
    """
    Probabilidad de neutralización basada en física real (modelo Friis):

        S = P_pico·G / (4πr²)  →  E = √(S·377)  →  E_eff = E·g(τ)
        →  E_blanco = E_eff · √(η(f_res)·pol)
        →  P_neutralizacion = sigmoide(E_blanco, E_umbral)

    ``potencia_kw`` es la potencia promedio; el daño latchup depende del pico
    (duty cycle) y de la duración del pulso (``pulse_coupling_factor``). La
    huella de susceptibilidad (resonancia del cableado + polarización) reduce
    la amplitud acoplada por blanco; con duty=1.0, τ=referencia y sin huella
    es exactamente el modelo calibrado contra arXiv:2602.08477.
    """
    if distancia <= 0:
        return 1.0

    half_cone = apertura_cono / 2.0
    if half_cone > 0 and abs(angulo_offset) > half_cone:
        return 0.0

    diag = friis_diagnostics(
        potencia_kw, distancia, apertura_cono, angulo_offset,
        duty_cycle=duty_cycle, pulse_duration_ns=pulse_duration_ns,
    )
    acoplamiento = susceptibility_coupling_factor(
        cable_length_m, polarization, frequency_ghz
    )
    campo_blanco = diag["campo_e_efectivo_v_m"] * acoplamiento
    return probabilidad_desde_campo(
        campo_blanco, e_threshold, steepness, e50, b, link
    )


def calculate_area_neutralization_probability_friis(
    potencia_kw: float,
    distancia: float,
    e_threshold: float = HPM_MISSILE_E_THRESHOLD_V_M,
    steepness: float = HPM_MISSILE_SIGMOID_STEEPNESS,
    e50: float = HPM_MISSILE_LOGLOGISTIC_E50_V_M,
    b: float = HPM_MISSILE_LOGLOGISTIC_B,
    link: str | None = None,
    duty_cycle: float = 1.0,
    pulse_duration_ns: float | None = None,
    cable_length_m: float | None = None,
    polarization: float | None = None,
    frequency_ghz: float = HPM_FREQUENCY_GHZ,
) -> float:
    """
    Variante omnidireccional (ganancia isotrópica G=1) del modelo Friis para
    el misil de área (detonación soft-kill circular, sin cono direccional).

    Usa un umbral/pendiente propios (``HPM_MISSILE_E_THRESHOLD_V_M``), NO los
    del cañón: un radiador isotrópico esparce la potencia sobre 4π
    estereorradianes en vez de concentrarla en un haz, así que reutilizar el
    umbral calibrado contra un plato de alta ganancia (ver
    ``calculate_neutralization_probability_friis``) haría al misil casi
    inefectivo salvo con potencias de MW. Ver docs/FISICA_Y_MATEMATICA.md.
    Igual que el cañón: ``potencia_kw`` es promedio, el daño usa el pico, y
    la huella de susceptibilidad reduce la amplitud acoplada por blanco.
    """
    if distancia <= 0:
        return 1.0

    diag = friis_diagnostics(
        potencia_kw, distancia, apertura_cono=360.0,
        duty_cycle=duty_cycle, pulse_duration_ns=pulse_duration_ns,
    )
    acoplamiento = susceptibility_coupling_factor(
        cable_length_m, polarization, frequency_ghz
    )
    campo_blanco = diag["campo_e_efectivo_v_m"] * acoplamiento
    return probabilidad_desde_campo(
        campo_blanco, e_threshold, steepness, e50, b, link
    )


def apply_hardening_odds(probabilidad: float, factor: float) -> float:
    """
    Reduce una probabilidad de neutralización según un factor de blindaje,
    operando en espacio de "momios" (odds = p/(1-p)), no multiplicando el
    umbral de campo E.

    Nota de auditoría — bug encontrado y corregido: multiplicar el umbral
    E₀ por un factor (p. ej. 2.5×) para simular blindaje daba una reducción
    real de probabilidad de 14× a 821× según la distancia (no 2.5×),
    porque el umbral vive dentro de una sigmoide no lineal — desplazarlo
    saca el punto de operación fuera del rango donde la sigmoide es
    sensible, y la probabilidad colapsa a ~0 en casi todo el rango de
    combate útil. En espacio de momios, dividir por ``factor`` sí da una
    reducción proporcional y predecible en cualquier punto de la curva:

        odds = p / (1 - p)
        odds_blindado = odds / factor
        p_blindado = odds_blindado / (1 + odds_blindado)

    Ver docs/FISICA_Y_MATEMATICA.md.
    """
    if factor <= 1.0 or probabilidad <= 0.0:
        return float(np.clip(probabilidad, 0.0, 1.0))
    if probabilidad >= 1.0:
        probabilidad = 1.0 - 1e-9

    odds = probabilidad / (1.0 - probabilidad)
    odds_reducidos = odds / factor
    return float(np.clip(odds_reducidos / (1.0 + odds_reducidos), 0.0, 1.0))


def target_angle_from_origin(
    origin_x: float,
    origin_y: float,
    target_x: float,
    target_y: float,
) -> float:
    """Ángulo hacia el blanco desde el origen del HPM (grados)."""
    dx = target_x - origin_x
    dy = target_y - origin_y
    return float(np.degrees(np.arctan2(dy, dx)) % 360)


def compute_target_parameters(
    origin_x: float,
    origin_y: float,
    weapon_direction: float,
    target_x: float,
    target_y: float,
    origin_z: float = 0.0,
    target_z: float = 0.0,
) -> tuple[float, float]:
    """
    Calcula distancia y offset angular de un blanco respecto al HPM.

    La distancia es 3D (slant range): el cañón HPM apunta su cono en azimut
    (rotación horizontal), pero un dron a otra altitud está físicamente más
    lejos que la distancia proyectada en el plano X-Y.

    Returns:
        Tupla (distancia, angulo_offset).
    """
    dist = distance3d(origin_x, origin_y, origin_z, target_x, target_y, target_z)
    bearing = target_angle_from_origin(origin_x, origin_y, target_x, target_y)
    offset = angle_difference(weapon_direction, bearing)
    return dist, offset


def alcance_para_probabilidad(
    probabilidad_objetivo: float,
    potencia_kw: float,
    apertura_cono: float = HPM_CONE_APERTURE,
    duty_cycle: float = 1.0,
    pulse_duration_ns: float | None = None,
    e_threshold: float = HPM_E_THRESHOLD_V_M,
    steepness: float = HPM_SIGMOID_STEEPNESS,
    e50: float = HPM_LOGLOGISTIC_E50_V_M,
    b: float = HPM_LOGLOGISTIC_B,
    link: str | None = None,
    dist_min_m: float = 0.1,
    dist_max_m: float = 100_000.0,
    tolerancia_m: float = 1e-3,
) -> float | None:
    """
    Distancia a la que el modelo ``friis`` da ``probabilidad_objetivo`` de
    neutralización, en el eje del haz y sin huella de susceptibilidad.

    Es la métrica con la que la literatura reporta el rendimiento de un arma
    HPM ("alcance de 90% de baja"), y la que permite comparar contra los dos
    números publicados en arXiv:2602.08477 §5 — CW ≈18 m, pulsado ≈88 m — que
    son el criterio de aceptación del ítem P1-E. Reemplaza el criterio
    tautológico anterior ("pulsado neutraliza a más distancia que CW"), que no
    podía fallar: el modelo define pico = promedio/duty, así que duty↓ ⇒ E↑ ⇒
    P↑ por álgebra, no por física (ver docs/AUDITORIA_CHECKLIST.md §2).

    Búsqueda por bisección: la probabilidad es estrictamente decreciente en la
    distancia a offset angular fijo (mismo invariante que verifica
    ``validation.check_shot_invariants``), así que la bisección es válida y
    converge. Devuelve ``None`` si la probabilidad objetivo no se alcanza en
    ningún punto del intervalo — el caso real de un arma que nunca llega al
    90% de baja a ninguna distancia.
    """
    def p(r: float) -> float:
        return calculate_neutralization_probability_friis(
            potencia_kw=potencia_kw,
            distancia=r,
            apertura_cono=apertura_cono,
            angulo_offset=0.0,
            e_threshold=e_threshold,
            steepness=steepness,
            e50=e50,
            b=b,
            link=link,
            duty_cycle=duty_cycle,
            pulse_duration_ns=pulse_duration_ns,
        )

    # Si ni a quemarropa se alcanza el objetivo, el arma no lo alcanza nunca.
    if p(dist_min_m) < probabilidad_objetivo:
        return None
    # Si incluso en el extremo lejano se supera, el intervalo es insuficiente
    # para acotar la respuesta: mejor declararlo que devolver dist_max.
    if p(dist_max_m) >= probabilidad_objetivo:
        return None

    lo, hi = dist_min_m, dist_max_m
    while hi - lo > tolerancia_m:
        mid = 0.5 * (lo + hi)
        if p(mid) >= probabilidad_objetivo:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


# ═══════════════════════════════════════════════════════════════════════════
# P1-B · Ganancia de plato parabólico real
# ═══════════════════════════════════════════════════════════════════════════


def antenna_gain_from_dish(
    diametro_m: float = HPM_DISH_DIAMETER_M,
    eficiencia_apertura: float = HPM_APERTURE_EFFICIENCY,
    frequency_ghz: float = HPM_FREQUENCY_GHZ,
) -> float:
    """
    Ganancia de un reflector parabólico: **física establecida**, no aproximación.

        G = η · (π·D / λ)²

    donde ``η`` es la eficiencia de apertura (fracción del área geométrica que
    se comporta como apertura efectiva: típicamente 0.50–0.70 en un plato real,
    limitada por iluminación del alimentador, bloqueo y errores de superficie).

    POR QUÉ SE AÑADIÓ (P1-B): ``antenna_gain_from_aperture`` usa
    ``G ≈ 26000/θ²``, que es una fórmula de ingeniería de radar legítima pero
    no describe un plato concreto. A 15° da 20.63 dBi contra los 21.2 dBi del
    plato de 60 cm del paper — un sesgo sistemático que
    ``tests/test_calibracion.py`` midió como **−6.4 % en campo E, idéntico en
    los dos puntos de calibración** (prueba de que es un offset de ganancia y
    no un error de modelo).

    Con esta fórmula y los valores del paper (D = 0.60 m, η = 0.55, 2.45 GHz)
    el resultado es **21.16 dBi**, y el sesgo en campo baja de −6.4 % a
    **−0.5 %**. Los dos modelos coexisten bajo ``HPM_ANTENNA_MODEL`` en vez de
    reemplazarse: cambiar la ganancia por defecto movería la calibración de
    docs/FISICA_Y_MATEMATICA.md §3.4, y eso es una decisión separada de añadir
    la capacidad.

    Relación con la apertura del haz: para un plato, θ ≈ 70·λ/D grados. Con los
    valores del paper da ≈ 14.3°, muy cerca del ``HPM_CONE_APERTURE`` = 15° que
    el proyecto ya usaba — o sea que las dos rutas describen la misma antena y
    difieren solo en la constante de la fórmula de ganancia.
    """
    d = max(float(diametro_m), 1e-6)
    eta = float(np.clip(eficiencia_apertura, 1e-6, 1.0))
    lam = SPEED_OF_LIGHT_M_S / (max(float(frequency_ghz), 1e-9) * 1e9)
    return float(eta * (np.pi * d / lam) ** 2)


def dish_beamwidth_deg(
    diametro_m: float = HPM_DISH_DIAMETER_M,
    frequency_ghz: float = HPM_FREQUENCY_GHZ,
) -> float:
    """Ancho de haz a −3 dB de un plato: θ ≈ 70·λ/D grados (aproximación estándar)."""
    d = max(float(diametro_m), 1e-6)
    lam = SPEED_OF_LIGHT_M_S / (max(float(frequency_ghz), 1e-9) * 1e9)
    return float(70.0 * lam / d)


# ═══════════════════════════════════════════════════════════════════════════
# P1-C · Modelo de daño por subsistemas (OR-gate)
# ═══════════════════════════════════════════════════════════════════════════


def probabilidad_dano_subsistema(
    campo_v_m: float, e50: float, sigma_e: float, link: str | None = None
) -> float:
    """Sigmoide de daño de UN subsistema: P = 1/(1+exp(-(E-E₅₀)/σ_E)).

    Nótese la parametrización: el paper usa ``σ_E`` (ancho, en V/m), mientras
    el modelo agregado del proyecto usa ``steepness`` (pendiente, en m/V). Son
    recíprocos: ``steepness = 1/σ_E``. Se conserva la del paper acá para poder
    tomar la Tabla 1 literalmente, sin conversiones que inviten a errores.
    """
    return probabilidad_desde_campo(
        campo_v_m,
        e_threshold=e50,
        steepness=1.0 / max(float(sigma_e), 1e-9),
        e50=e50,
        # b = E₅₀/σ preserva la pendiente en E₅₀. Para la Tabla 1 del paper da
        # exactamente 5.0 en los cinco subsistemas, de ahí el default de
        # config (HPM_SUBSISTEMAS_LOGLOGISTIC_B).
        b=HPM_SUBSISTEMAS_LOGLOGISTIC_B,
        link=link,
    )


def probabilidad_dano_sistema(
    campo_v_m: float,
    subsistemas: dict[str, tuple[float, float]] | None = None,
    link: str | None = None,
) -> float:
    """
    Probabilidad de baja del dron por lógica **OR-gate** sobre sus subsistemas
    — ecuación (7) de arXiv:2602.08477:

        P_sistema(E) = 1 − Π_i [ 1 − P_i(E) ]

    Es decir: la supervivencia del sistema es el producto de las supervivencias
    individuales. El dron cae si cae **cualquier** subsistema.

    Consecuencia de modelado que importa: el subsistema dominante a campo bajo
    es el más débil (el LNA de GPS/GNSS, E₅₀ = 150 V/m), no el promedio. Una
    sola sigmoide agregada **no puede** reproducir la forma de la curva de un
    OR-gate de cinco sigmoides con umbrales y anchos distintos — por eso
    ajustar una sola a dos puntos absorbe el sesgo en vez de reproducir el
    modelo (ver docs/AUDITORIA_CHECKLIST.md §1.3).
    """
    tabla = HPM_SUBSISTEMAS if subsistemas is None else subsistemas
    supervivencia = 1.0
    for e50, sigma_e in tabla.values():
        supervivencia *= 1.0 - probabilidad_dano_subsistema(
            campo_v_m, e50, sigma_e, link
        )
    return float(np.clip(1.0 - supervivencia, 0.0, 1.0))


def desglose_por_subsistema(
    campo_v_m: float,
    subsistemas: dict[str, tuple[float, float]] | None = None,
    link: str | None = None,
) -> list[dict[str, Any]]:
    """
    Probabilidad de daño de CADA subsistema por separado a un campo dado,
    más su probabilidad de sistema (OR-gate, ecuación 7) — para mostrar en
    el frontend (panel "Laboratorio") cuál subsistema domina a qué campo,
    en vez de solo el número agregado de ``probabilidad_dano_sistema``.

    Ordenado de más a menos vulnerable (E₅₀ ascendente) — el orden en que
    fallarían si el campo subiera gradualmente.
    """
    tabla = HPM_SUBSISTEMAS if subsistemas is None else subsistemas
    filas = [
        {
            "nombre": nombre,
            "e50_v_m": e50,
            "sigma_e_v_m": sigma_e,
            "probabilidad": probabilidad_dano_subsistema(campo_v_m, e50, sigma_e, link),
        }
        for nombre, (e50, sigma_e) in tabla.items()
    ]
    filas.sort(key=lambda f: f["e50_v_m"])
    return filas


def campo_acoplado_v_m(
    campo_incidente_v_m: float,
    eficiencia_campo: float = HPM_COUPLING_FIELD_EFFICIENCY,
) -> float:
    """Campo que ve el subsistema susceptible, a partir del campo incidente.

    ``eficiencia_campo`` es el único parámetro libre del modelo de
    subsistemas. CONFIRMADO contra el código fuente real del paper (PDF de
    arXiv:2602.08477, Listados 1-2, leído el 2026-09-13) que el pipeline que
    produce 51.4%/13.1% compara el campo incidente (con pérdidas de apuntado
    y polarización ya aplicadas, ambas en potencia) DIRECTAMENTE contra los
    umbrales E₅₀ de la Tabla 1 — sin ningún paso de acoplamiento a voltios
    inducidos en cable visible en el código. La cadena
    ``V_ind = E·L_eff·F(θ)·√η_pol`` (Ec. 4-5 del paper) aparece en el texto
    como motivación teórica, pero no en el listado (explícitamente
    "abreviado"), así que este parámetro sigue siendo un gancho de
    atenuación en campo, sin unidades de voltios — no hay inconsistencia
    dimensional V/m-vs-voltios que resolver, porque nunca se introducen
    voltios en ningún camino de este proyecto.

    PROBADO Y DESCARTADO: ``eficiencia_campo=1.0`` (tomar el pipeline de
    arriba literalmente, sin atenuación) sobrestima fuerte (+40pp a 20m) —
    ver ``HPM_COUPLING_FIELD_EFFICIENCY`` en ``src/config.py`` para el
    detalle. El default actual (0.44) es un reajuste por mínimos cuadrados
    contra los dos puntos publicados, CON EL MC EN EL LAZO (método correcto:
    ver la nota histórica sobre 0.2568/0.3693 más abajo) bajo el modelo YA
    corregido de polarización y apuntado — pero tampoco cierra: los
    residuos a 20m y 40m salen de signos OPUESTOS (antes, con el modelo
    viejo, ambos eran del mismo signo), y el CV a 30m con este ajuste es
    ≈1.03, peor que antes. Ningún valor de este parámetro puede arreglar
    eso: es un problema de FORMA de la curva (cómo cae con la distancia y
    con qué varianza), no de escala. Historia de valores intentados:
    0.2568 (ajustado contra el determinista — error de método, absorbía el
    sesgo del MC en el parámetro, descartado); 0.3693 (MC en el lazo bajo el
    modelo VIEJO de polarización, correcto pero sin validar); 0.44 (MC en el
    lazo bajo el modelo corregido, correcto pero sin validar — el actual).
    """
    return float(max(0.0, campo_incidente_v_m) * np.clip(eficiencia_campo, 0.0, 1.0))


# ═══════════════════════════════════════════════════════════════════════════
# P2-D · Umbral de upset (derivado del umbral de daño) y energía absorbida
# ═══════════════════════════════════════════════════════════════════════════


def e50_upset_desde_damage(
    e50_damage: float, gap_db_campo: float = HPM_UPSET_DB_GAP_FIELD
) -> float:
    """
    Umbral de UPSET (recuperable), derivado del umbral de DAÑO (permanente)
    ya calibrado, escalado por una brecha en dB de CAMPO (ver
    ``HPM_UPSET_DB_GAP_FIELD`` en ``src/config.py`` para la justificación de
    la brecha de 10 dB):

        E50_upset = E50_damage / 10^(gap_db/20)

    Es una decisión de modelado (categoría 3), no un dato de arXiv:2602.08477
    — ese paper no distingue upset de daño. Se deriva del umbral CALIBRADO
    (no de la Tabla 1 sin validar de P1-C) para no acoplar la contabilidad de
    upset a un modelo bloqueado.
    """
    factor = 10.0 ** (gap_db_campo / 20.0)
    return float(e50_damage) / max(factor, 1e-9)


def energia_absorbida_j(
    potencia_kw: float,
    distancia: float,
    apertura_cono: float,
    angulo_offset: float,
    duty_cycle: float,
    cable_length_m: float,
    duracion_exposicion_s: float,
    pulse_duration_ns: float | None = None,
) -> float:
    """
    Energía absorbida por el arnés de cableado durante UNA exposición
    (P2-D, Parte 2). Reemplaza ``dano = probabilidad·potencia·0.5``, aritmética
    dimensionalmente vacía señalada en docs/AUDITORIA_CHECKLIST.md §4.5 como
    el último resto de los "puntos de daño arbitrarios" que
    docs/FISICA_Y_MATEMATICA.md §5.4 declara haber eliminado.

    Cadena física:

        S_promedio = S_pico · duty_cycle
        A_efectiva = cable_length_m²
        E_absorbida = S_promedio · A_efectiva · duracion_exposicion_s      [J]

    ``S_promedio`` recupera la densidad de potencia PROMEDIO a partir de la
    que calcula ``friis_diagnostics`` (basada en el PICO — correcto para el
    campo instantáneo que gobierna la sigmoide de daño, pero no para energía
    total: la energía es potencia promedio por tiempo, por definición).

    ``A_efectiva`` NO introduce un parámetro libre nuevo: se deriva de la
    longitud de cable YA sorteada por dron (``cable_length_m``, huella de
    susceptibilidad de P2-04) como el orden de magnitud de la sección que
    subtiende un lazo de esa longitud. Un cable más largo (y más cerca de la
    resonancia) también capta más energía — el mismo parámetro aleatorio
    gobierna dos efectos físicos relacionados, en vez de sumar una constante
    inventada.

    ``duracion_exposicion_s`` NO es ``HPM_PULSE_DURATION_NS`` (un pulso
    aislado da microjulios, irrelevante) sino la duración de la RÁFAGA
    completa — mismo razonamiento que ``HPM_DISPARO_DURACION_S`` en P2-F.
    Se pasa explícita porque cañón (ráfaga sostenida) y misil (detonación
    única) tienen duraciones muy distintas.
    """
    diag = friis_diagnostics(
        potencia_kw, distancia, apertura_cono, angulo_offset,
        duty_cycle=duty_cycle, pulse_duration_ns=pulse_duration_ns,
    )
    duty = float(np.clip(duty_cycle, 1e-3, 1.0))
    densidad_promedio = diag["densidad_potencia_w_m2"] * duty
    area_efectiva_m2 = max(float(cable_length_m), 1e-6) ** 2
    return float(densidad_promedio * area_efectiva_m2 * max(float(duracion_exposicion_s), 0.0))
