"""
Barrido depredador-presa (§2.2 de docs/ESTADO_DEL_ARTE_BIOMIMESIS.md).

Chen & Kolokolnikov (2014), arXiv:1403.3250, predicen que el resultado de
un enjambre frente a un depredador NO es monótono en la fuerza del
atacante: débil → escape, moderada → "anillo de confusión", fuerte →
persecución caótica, extrema → captura. Esto barre la potencia del cañón
(proxy de "fuerza del atacante") contra dos formaciones — cuadrada
(compacta) y circular (dispersa) — usando el runner Monte Carlo real
(``src.engine.experiments.run_replica``) y el estimador corregido (P1-A,
``fraccion_media``), buscando si aparece alguna transición no monótona
parecida, o si la relación es simplemente monótona creciente en este
sistema (que también sería un resultado real, no un fallo del barrido).

Geometría: reusa DISTANCIA_COMBATE_M/_origen_combate/_rumbo_al_centro_del_
campo de src.engine.coevolution — la MISMA distancia arma↔enjambre (60m)
que P3-B ya validó como el único régimen de este proyecto donde existe
señal real (a la distancia por defecto del proyecto, ~707m, la
probabilidad de baja es ~1e-4 incluso al tope de potencia — ver el
docstring de DISTANCIA_COMBATE_M). duty_cycle=0.01 (pulsado) por el mismo
motivo: a duty_cycle=1.0 (CW, el default) esta distancia y este rango de
potencia dan fracción neutralizada ~0 en casi todo el barrido, medido
durante el diseño de P3-B.

Corre standalone: python -m research.barrido_depredador_presa
"""

from __future__ import annotations

import json
import time

import numpy as np

from src.engine.coevolution import DISTANCIA_COMBATE_M, _origen_combate
from src.engine.experiments import ExperimentConfig, WeaponPolicy, run_replica

POTENCIAS_KW = [10, 15, 20, 30, 40, 50, 65, 80, 100]
FORMACIONES = ["cuadrada", "circular"]
CANTIDAD = 30
REPLICAS = 30
T_MAX_S = 6.0
DELAY_S = 1.0
DUTY_CYCLE = 0.01
SEMILLA_BASE = 90210


def punto(formacion: str, potencia_kw: float, semilla: int) -> dict:
    origen_x, origen_y = _origen_combate()
    cfg = ExperimentConfig(
        formacion=formacion,
        cantidad=CANTIDAD,
        replicas=REPLICAS,
        t_max_s=T_MAX_S,
        semilla=semilla,
        arma=WeaponPolicy(
            tipo="canion",
            delay_s=DELAY_S,
            potencia=potencia_kw,
            duty_cycle=DUTY_CYCLE,
            origen_x=origen_x,
            origen_y=origen_y,
        ),
    )
    fracciones = [run_replica(cfg, i)["fraccion"] for i in range(cfg.replicas)]
    arr = np.asarray(fracciones, dtype=float)
    return {
        "formacion": formacion,
        "potencia_kw": potencia_kw,
        "fraccion_media": float(arr.mean()),
        "desviacion_estandar": float(arr.std(ddof=1)),
        "cv": float(arr.std(ddof=1) / arr.mean()) if arr.mean() > 0 else None,
    }


def main() -> None:
    t0 = time.monotonic()
    resultados = []
    for formacion in FORMACIONES:
        for i, potencia in enumerate(POTENCIAS_KW):
            r = punto(formacion, potencia, SEMILLA_BASE + 1000 * i)
            resultados.append(r)
            print(
                f"{formacion:10s} potencia={potencia:5.1f}kW  "
                f"fraccion_media={r['fraccion_media']:.4f}  "
                f"cv={r['cv']}"
            )
    print(f"\n{len(resultados)} puntos en {time.monotonic() - t0:.1f}s")
    print(f"origen del arma: {_origen_combate()}  (DISTANCIA_COMBATE_M={DISTANCIA_COMBATE_M})")

    with open("research/barrido_depredador_presa_resultados.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
