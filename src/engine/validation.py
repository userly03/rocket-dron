"""
Validación de invariantes físicas y formato de reportes numéricos para la
terminal.

El objetivo es que cada disparo/detonación imprima en la terminal donde
corre el servidor los números que la simulación usó (distancia, campo E,
probabilidad...) junto con cualquier inconsistencia detectada, para poder
comparar contra la física esperada e ir puliendo el modelo con evidencia
concreta en vez de conjeturas.
"""

from __future__ import annotations

import logging
from typing import Any

import src.config as config
from src.engine.hpm_engine import (
    calculate_neutralization_probability_friis,
    friis_diagnostics,
)

logger = logging.getLogger("simulador.validacion")

_EPS = 1e-6


def check_shot_invariants(
    eventos: list[dict[str, Any]],
    radio_o_apertura_ctx: dict[str, Any] | None = None,
) -> list[str]:
    """
    Verifica invariantes físicas conocidas sobre una lista de eventos de
    impacto (del cañón o de una detonación de misil).

    La monotonicidad probabilidad-vs-distancia solo se exige entre pares de
    eventos con offset angular Y factor de acoplamiento (``√(η·pol)``,
    P2-04) comparables — ver ``_mismo_offset``/``_acoplamiento_comparable``
    abajo. Si algún evento no trae ``factor_acoplamiento`` (eventos legacy,
    o el modelo "legacy" que no usa huella de susceptibilidad), ese par se
    excluye del chequeo en vez de arriesgar un falso positivo.

    Devuelve una lista de mensajes de advertencia; vacía si todo es consistente.
    """
    avisos: list[str] = []
    ctx = radio_o_apertura_ctx or {}
    radio_efecto = ctx.get("radio_efecto")

    # Para el cañón direccional, la probabilidad depende también del offset
    # angular respecto al eje del cono (atenuación fuera del centro del haz):
    # un dron más lejano pero más centrado puede tener mayor probabilidad que
    # uno más cercano cerca del borde del cono. La monotonicidad respecto a
    # la distancia solo es un invariante válido entre blancos con offset
    # angular similar (o sin offset, como en el misil de área).
    ANGULO_TOLERANCIA_DEG = 2.0

    # Desde P2-04 (huella de susceptibilidad), la probabilidad de un dron ya
    # no depende solo de distancia y offset angular: cada dron sortea una
    # longitud de cableado y una polarización propias, que entran a la
    # sigmoide de daño como el factor de amplitud √(η·pol)
    # (``Drone.factor_acoplamiento()``). Dos drones a la misma distancia y
    # mismo offset pueden tener acoplamientos muy distintos — uno resonante
    # (η≈1) y otro desintonizado (η≈0.1) — y ENTONCES la monotonía
    # probabilidad-vs-distancia deja de ser un invariante entre ellos: el
    # dron más lejano pero mejor acoplado puede, legítimamente, tener mayor
    # probabilidad. Observado en corridas reales (deuda técnica menor,
    # CHECKLIST_MEJORAS.md): ``d=898.67m→p=0.0097 vs d=899.1m→p=0.0244`` —
    # un falso positivo, no un bug del modelo de daño.
    #
    # Tolerancia RELATIVA (no absoluta): el factor de acoplamiento vive en
    # [0,1] pero no es una magnitud con una escala natural fija de "cuánto
    # es distinto" en términos absolutos — 15% de diferencia relativa es un
    # criterio conservador (bastante más estricto que la dispersión típica
    # sorteada, ver DRONE_CABLE_LENGTH_*/DRONE_POLARIZATION_MIN en
    # config.py) para considerar "el mismo acoplamiento, dentro de ruido".
    ACOPLAMIENTO_TOLERANCIA_REL = 0.15

    def _mismo_offset(a: dict[str, Any], b: dict[str, Any]) -> bool:
        oa, ob = a.get("angulo_offset"), b.get("angulo_offset")
        if oa is None and ob is None:
            return True
        if oa is None or ob is None:
            return False
        return abs(oa - ob) <= ANGULO_TOLERANCIA_DEG

    def _acoplamiento_comparable(a: dict[str, Any], b: dict[str, Any]) -> bool:
        """
        True solo si AMBOS eventos declaran su factor de acoplamiento y son
        relativamente comparables. Degradación deliberada: si el dato falta
        (eventos generados antes de esta corrección, o el modelo "legacy",
        que no usa huella de susceptibilidad y no lo publica) se devuelve
        False — el chequeo de monotonía simplemente no se aplica a ese par.
        Es preferible NO reportar a reportar un falso positivo (ver
        docstring de la función).
        """
        fa, fb = a.get("factor_acoplamiento"), b.get("factor_acoplamiento")
        if fa is None or fb is None:
            return False
        referencia = max(abs(fa), abs(fb), _EPS)
        return abs(fa - fb) <= ACOPLAMIENTO_TOLERANCIA_REL * referencia

    ordenados = sorted(
        (e for e in eventos if e.get("distancia") is not None and e.get("probabilidad") is not None),
        key=lambda e: e["distancia"],
    )

    for evento in eventos:
        distancia = evento.get("distancia")
        probabilidad = evento.get("probabilidad")
        neutralizado = evento.get("neutralizado")
        drone_id = evento.get("drone_id")

        if distancia is not None and distancia < 0:
            avisos.append(f"dron {drone_id}: distancia negativa ({distancia} m)")

        if probabilidad is not None and not (-_EPS <= probabilidad <= 1.0 + _EPS):
            avisos.append(f"dron {drone_id}: probabilidad fuera de [0,1] ({probabilidad})")

        if (
            radio_efecto is not None
            and distancia is not None
            and probabilidad is not None
            and distancia > radio_efecto + _EPS
            and probabilidad > _EPS
        ):
            avisos.append(
                f"dron {drone_id}: probabilidad {probabilidad} > 0 fuera del radio de "
                f"efecto (distancia={distancia} m > radio={radio_efecto} m)"
            )

        if neutralizado and probabilidad is not None and probabilidad <= _EPS:
            avisos.append(
                f"dron {drone_id}: neutralizado con probabilidad calculada ~0 "
                f"({probabilidad}) — resultado inconsistente con el modelo"
            )

    # Monotonicidad: a mayor distancia (y mismo offset angular), la
    # probabilidad no debería aumentar.
    for anterior, actual in zip(ordenados, ordenados[1:]):
        if (
            _mismo_offset(anterior, actual)
            and _acoplamiento_comparable(anterior, actual)
            and actual["distancia"] > anterior["distancia"] + _EPS
            and actual["probabilidad"] > anterior["probabilidad"] + 1e-3
        ):
            avisos.append(
                f"la probabilidad no decrece con la distancia: "
                f"d={anterior['distancia']}m→p={anterior['probabilidad']} vs "
                f"d={actual['distancia']}m→p={actual['probabilidad']}"
            )

    return avisos


def format_shot_report(
    tipo: str,
    contexto: dict[str, Any],
    eventos: list[dict[str, Any]],
) -> str:
    """Construye un bloque de texto legible con los números clave del disparo."""
    neutralizados = sum(1 for e in eventos if e.get("neutralizado"))
    distancias = [e["distancia"] for e in eventos if e.get("distancia") is not None]
    probabilidades = [e["probabilidad"] for e in eventos if e.get("probabilidad") is not None]

    lineas = [f"--- {tipo} — t={contexto.get('tiempo', 0):.2f}s ---"]
    for clave in ("potencia_kw", "direccion", "radio_efecto", "apertura_cono", "campo_e_v_m"):
        if clave in contexto and contexto[clave] is not None:
            lineas.append(f"  {clave}: {contexto[clave]}")

    lineas.append(f"  afectados={len(eventos)} neutralizados={neutralizados}")
    if distancias:
        lineas.append(
            f"  distancia (3D, slant range): min={min(distancias):.1f}m max={max(distancias):.1f}m"
        )
    horizontales = [e["distancia_horizontal"] for e in eventos if e.get("distancia_horizontal") is not None]
    deltas_z = [e["delta_altitud"] for e in eventos if e.get("delta_altitud") is not None]
    if horizontales and deltas_z:
        lineas.append(
            f"  desglose: horizontal min={min(horizontales):.1f}m max={max(horizontales):.1f}m "
            f"| Δaltitud min={min(deltas_z):.1f}m max={max(deltas_z):.1f}m "
            "(confirma que la distancia 3D no es solo x,y)"
        )
    if probabilidades:
        lineas.append(
            f"  probabilidad: min={min(probabilidades):.4f} max={max(probabilidades):.4f}"
        )

    return "\n".join(lineas)


def log_shot(tipo: str, contexto: dict[str, Any], eventos: list[dict[str, Any]]) -> None:
    """Imprime el reporte del disparo y cualquier advertencia de validación."""
    logger.info(format_shot_report(tipo, contexto, eventos))

    avisos = check_shot_invariants(eventos, contexto)
    for aviso in avisos:
        logger.warning("[VALIDACIÓN] ⚠ %s", aviso)


# ─────────────────────────────────────────────────────────────────────────
# Regresión de la calibración (P1-D, CHECKLIST_MEJORAS.md)
# ─────────────────────────────────────────────────────────────────────────
#
# Todo lo que sigue existe por una sola razón: la credibilidad física del
# proyecto descansa en DOS puntos de datos publicados (arXiv:2602.08477,
# cañón de 25kW CW con plato parabólico de 60cm — 21.2 dBi — a 2.45GHz), de
# los que se derivaron por ajuste numérico `HPM_E_THRESHOLD_V_M=500` y
# `HPM_SIGMOID_STEEPNESS=0.0075` (ver docs/FISICA_Y_MATEMATICA.md §3.4). Esa
# derivación hasta ahora vivía solo en un comentario y en una tabla de un
# .md: nada impedía que un cambio futuro de `HPM_CONE_APERTURE`,
# `HPM_DUTY_CYCLE` o de los propios umbrales moviera la calibración sin que
# nadie se enterara. `verificar_calibracion()` convierte esa tabla en algo
# que un test puede ejecutar y hacer fallar el build.
#
# Los valores de referencia del paper son la verdad física publicada. Los
# valores "documentados del simulador" son OTRA cosa: son lo que el propio
# modelo da HOY, congelado como fotografía — sirven para detectar que
# alguien movió un default, no para juzgar si el modelo es fiel al paper
# (eso ya está discutido y aceptado en §3.4: la aproximación de ganancia
# G≈26000/apertura² da ~20.6 dBi para un cono de 15°, no los 21.2 dBi de un
# plato parabólico real de 60cm, así que una brecha de unos pocos puntos
# porcentuales contra el paper es esperada y no es una regresión).

# Fuente: arXiv:2602.08477, Tabla de resultados para el cañón de 25kW CW /
# plato de 60cm (21.2 dBi) a 2.45GHz. Ver docs/FISICA_Y_MATEMATICA.md §3.4.
CALIBRACION_PAPER_CAMPO_E_V_M: dict[str, float] = {"20m": 497.2, "40m": 248.6}
CALIBRACION_PAPER_PROBABILIDAD: dict[str, float] = {"20m": 0.514, "40m": 0.131}
CALIBRACION_DISTANCIA_M: dict[str, float] = {"20m": 20.0, "40m": 40.0}

# Lo que el simulador (con su propia aproximación de ganancia, NO un plato
# parabólico real) da HOY con la configuración default documentada en §3.4:
# cono de 15° (~20.6 dBi), 25kW, duty_cycle=1.0, HPM_E_THRESHOLD_V_M=500,
# HPM_SIGMOID_STEEPNESS=0.0075. Medido el 2026-09-12 con
# `calculate_neutralization_probability_friis` directamente (mismo camino
# que usa esta función) y verificado contra §3.4, que documenta 43.6% y
# 11.9% — coincide. Esta es la fotografía que protege el test de regresión:
# si se mueve, algo cambió en el modelo o en un default, no en el paper.
# ACTUALIZADO en P1-F (2026-09-12): la función de enlace pasó de logística en
# ``E`` a **log-logística**, porque la logística tiene soporte en todo ℝ y daba
# ``P(E=0) = 2.30 %`` — un piso que a 700 m era el 90.7 % del número reportado
# (ver docs/FISICA_Y_MATEMATICA.md §3.7). Valores anteriores: 0.436 / 0.119.
# Los nuevos quedan MÁS CERCA del paper a 20 m (−4.63 pp contra −7.84 pp antes),
# porque los parámetros log-logísticos se ajustaron a los dos puntos publicados
# de forma exacta.
CALIBRACION_SIMULADOR_DOCUMENTADA: dict[str, float] = {"20m": 0.4677, "40m": 0.1113}

# Tolerancia contra la fotografía del simulador (arriba): estos números
# salen matemáticamente de la configuración actual, así que si se mueven más
# de esto es porque alguien tocó un default (umbral, pendiente, apertura del
# cono, duty cycle...) y no actualizó la calibración. Deliberadamente
# estrecha.
TOLERANCIA_REGRESION_SIMULADOR_PP: float = 0.5  # puntos porcentuales absolutos


def verificar_calibracion() -> dict[str, Any]:
    """
    Convierte la calibración de docs/FISICA_Y_MATEMATICA.md §3.4 — hasta
    ahora solo un comentario y una tabla en un documento — en una garantía
    ejecutable: recalcula, con la configuración ACTUAL de ``src.config`` y
    el modelo físico real (``calculate_neutralization_probability_friis``),
    la probabilidad de neutralización en los dos únicos puntos de datos
    publicados contra los que el proyecto fue calibrado (arXiv:2602.08477).

    Deliberadamente lee ``src.config`` por atributo del módulo (``config.
    HPM_E_THRESHOLD_V_M``, no ``from src.config import HPM_E_THRESHOLD_V_M``)
    y pasa cada valor explícitamente a
    ``calculate_neutralization_probability_friis`` en vez de confiar en sus
    defaults de parámetro: esos defaults se capturan una sola vez, al
    importarse ``src.engine.hpm_engine`` (ej. ``e_threshold: float =
    HPM_E_THRESHOLD_V_M``), así que un ``monkeypatch.setattr`` sobre
    ``src.config`` en un test NO los movería si dependiéramos de ellos. Leer
    el atributo del módulo en el momento de la llamada es lo que permite que
    tests/test_calibracion.py pueda demostrar que este detector de
    regresión realmente detecta algo.

    Se evalúa en el eje del haz (``angulo_offset=0``, sin atenuación de
    borde de cono) y sin huella de susceptibilidad (``cable_length_m=None,
    polarization=None``): es el camino "modelo calibrado puro" contra el que
    se ajustó el paper — con footprint de susceptibilidad activo la
    probabilidad depende además del cableado del blanco, algo que el paper
    no modela y que introduciría una variable ajena a esta calibración.

    Devuelve un dict ``{"puntos": {"20m": {...}, "40m": {...}}}`` donde cada
    punto trae la probabilidad calculada, la probabilidad documentada del
    simulador (fotografía congelada, ver ``CALIBRACION_SIMULADOR_
    DOCUMENTADA``), la probabilidad del paper, el campo E calculado y el
    del paper, y las desviaciones (en puntos porcentuales) contra cada
    referencia. La desviación contra el simulador documentado es la que
    importa para regresión; la desviación contra el paper es información de
    contexto, no un criterio de aprobado/reprobado (ver nota de brecha
    esperada más arriba).
    """
    puntos: dict[str, Any] = {}
    for clave, distancia in CALIBRACION_DISTANCIA_M.items():
        probabilidad = calculate_neutralization_probability_friis(
            potencia_kw=config.HPM_DEFAULT_POWER,
            distancia=distancia,
            apertura_cono=config.HPM_CONE_APERTURE,
            angulo_offset=0.0,
            # Los cinco parámetros del modelo de daño se leen de ``config``
            # POR ATRIBUTO en el momento de la llamada y se pasan EXPLÍCITOS.
            # No es estilo: ``calculate_neutralization_probability_friis``
            # captura sus defaults al importar ``hpm_engine``, así que si se
            # confiara en ellos un ``monkeypatch.setattr(config, ...)`` no
            # tendría ningún efecto y los tests de regresión de
            # ``TestDeteccionDeRegresiones`` pasarían sin poder fallar —
            # decorativos. Se verificó que ocurre.
            # AMPLIADO en P1-F: al añadir la función de enlace log-logística
            # hubo que sumar ``e50``, ``b`` y ``link`` a esta lista. Dos tests
            # de regresión lo detectaron al dejar de detectar: hasta que se
            # pasaron explícitos, parchear los parámetros nuevos no movía nada.
            e_threshold=config.HPM_E_THRESHOLD_V_M,
            steepness=config.HPM_SIGMOID_STEEPNESS,
            e50=config.HPM_LOGLOGISTIC_E50_V_M,
            b=config.HPM_LOGLOGISTIC_B,
            link=config.HPM_LINK_FUNCTION,
            duty_cycle=config.HPM_DUTY_CYCLE,
            cable_length_m=None,
            polarization=None,
        )
        diagnostico = friis_diagnostics(
            config.HPM_DEFAULT_POWER,
            distancia,
            config.HPM_CONE_APERTURE,
            angulo_offset=0.0,
            duty_cycle=config.HPM_DUTY_CYCLE,
        )
        campo_e = diagnostico["campo_e_v_m"]
        prob_doc_sim = CALIBRACION_SIMULADOR_DOCUMENTADA[clave]
        prob_paper = CALIBRACION_PAPER_PROBABILIDAD[clave]
        campo_paper = CALIBRACION_PAPER_CAMPO_E_V_M[clave]

        puntos[clave] = {
            "distancia_m": distancia,
            "probabilidad_calculada": probabilidad,
            "probabilidad_simulador_documentada": prob_doc_sim,
            "probabilidad_paper": prob_paper,
            "campo_e_v_m": campo_e,
            "campo_e_paper_v_m": campo_paper,
            "desviacion_vs_simulador_documentado_pp": (probabilidad - prob_doc_sim) * 100.0,
            "desviacion_vs_paper_pp": (probabilidad - prob_paper) * 100.0,
        }

    return {"puntos": puntos}
