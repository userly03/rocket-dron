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

logger = logging.getLogger("simulador.validacion")

_EPS = 1e-6


def check_shot_invariants(
    eventos: list[dict[str, Any]],
    radio_o_apertura_ctx: dict[str, Any] | None = None,
) -> list[str]:
    """
    Verifica invariantes físicas conocidas sobre una lista de eventos de
    impacto (del cañón o de una detonación de misil).

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

    def _mismo_offset(a: dict[str, Any], b: dict[str, Any]) -> bool:
        oa, ob = a.get("angulo_offset"), b.get("angulo_offset")
        if oa is None and ob is None:
            return True
        if oa is None or ob is None:
            return False
        return abs(oa - ob) <= ANGULO_TOLERANCIA_DEG

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
