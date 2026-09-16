"""
Sensor RF pasivo (ESM — Electronic Support Measures): detecta al dron por
su PROPIA emisión (enlace de control/telemetría), no por reflexión de una
señal propia transmitida por este sistema, que es lo que hace el radar
(``radar_engine.py``).

La diferencia física central es que el radar es monoestático: la misma
antena transmite Y recibe la reflexión, así que la señal recorre el
camino ida-y-vuelta y se atenúa dos veces (de ahí ``r⁴`` y ``G²`` en
``radar_received_power_w``). Este sensor solo ESCUCHA — el dron transmite,
este receptor recibe — un enlace unidireccional (ecuación de Friis, ``r²``,
``Gt·Gr`` en vez de ``G²``). Esa asimetría (r² vs r⁴) es la razón de fondo
por la que, en la práctica, un receptor pasivo detecta emisores activos a
mucha más distancia que un radar detecta blancos pasivos de igual
potencia — es doctrina real de guerra electrónica (ESM/RWR bien conocido
por superar en alcance al radar que los ilumina), no una particularidad
de este modelo.

Verificado numéricamente antes de integrar esto a ningún arma/radar (ver
docs/SEGUIMIENTO_SESION.md): con los valores por defecto de
``src/config.py`` (dron a 25mW / 2dBi, receptor a 6dBi/2.4GHz, mismo
umbral SNR y piso de ruido que el radar), el alcance de detección sale en
~3948m — casi 3x la diagonal del mapa (1000×1000m, diagonal ≈1414m). Esto
significa que, DENTRO del mapa, este sensor detecta virtualmente siempre
que haya línea de vista — no hay "punto ciego por distancia" como sí lo
hay con el radar (que sí tiene techo de alcance dentro del mapa por el
r⁴). Deliberadamente NO se bajó la potencia del dron para forzar un
alcance "más chico" — sería inventar un dato falso para que el resultado
se vea más interesante. El resultado real es el hallazgo: la única
defensa real contra este sensor es bloquear la línea de vista (relieve,
estructuras), no la distancia — motivo por el cual ambos, línea de vista
por obstáculos y por relieve (``considerar_relieve``, ver
``hpm_engine.linea_de_vista_bloqueada``), siguen aplicando idénticos acá.
"""

from __future__ import annotations

from src.config import RF_SENSOR_SIGMOID_STEEPNESS, RF_SENSOR_SNR_THRESHOLD_DB
from src.engine.radar_engine import detection_probability, wavelength_m


def rf_received_power_w(
    pt_w: float,
    gt_linear: float,
    gr_linear: float,
    wavelength_m_: float,
    distancia_m: float,
) -> float:
    """
    Ecuación de Friis (enlace unidireccional):

        Pr = (Pt · Gt · Gr · λ²) / ((4π · r)²)

    A diferencia de ``radar_received_power_w``, ``Gt`` (antena del dron
    emisor) y ``Gr`` (antena de este receptor) son ganancias DISTINTAS —
    no hay G² porque no es la misma antena la que transmite y recibe.
    """
    r = max(distancia_m, 1e-6)
    return (pt_w * gt_linear * gr_linear * wavelength_m_**2) / ((4.0 * 3.141592653589793 * r) ** 2)


def evaluar_deteccion_rf(
    distancia_m: float,
    pt_w: float,
    gt_dbi: float,
    gr_dbi: float,
    frequency_ghz: float,
    noise_floor_w: float,
    snr_threshold_db: float = RF_SENSOR_SNR_THRESHOLD_DB,
    steepness: float = RF_SENSOR_SIGMOID_STEEPNESS,
) -> tuple[bool, float]:
    """
    Evalúa si la emisión de un dron a ``distancia_m`` queda detectada por
    este sensor. Misma convención que ``radar_engine.evaluar_deteccion``:
    decisión determinística sobre la probabilidad (>=50%), no un sorteo
    por tick.

    ``snr_threshold_db``/``steepness`` tienen el mismo valor por defecto
    que el radar (ver el comentario de ``RF_SENSOR_SNR_THRESHOLD_DB`` en
    ``src/config.py``), pero son una constante propia — no el mismo
    parámetro reutilizado — para poder diferenciar la electrónica de
    ambos receptores en el futuro sin tocar esta firma.

    Returns:
        Tupla ``(detectado, probabilidad)``.
    """
    gt_linear = 10.0 ** (gt_dbi / 10.0)
    gr_linear = 10.0 ** (gr_dbi / 10.0)
    wl = wavelength_m(frequency_ghz)
    pr = rf_received_power_w(pt_w, gt_linear, gr_linear, wl, distancia_m)
    probabilidad = detection_probability(pr, noise_floor_w, snr_threshold_db, steepness)
    return probabilidad >= 0.5, probabilidad
