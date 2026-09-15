"""Coevolución genética arma ↔ enjambre (P3-B).

Dos poblaciones evolucionan una CONTRA la otra: el arma busca maximizar
bajas, la defensa busca minimizarlas, y el fitness de cada una se mide
corriendo el runner Monte Carlo real (``src.engine.experiments.run_replica``)
— la simulación de verdad, no una aproximación analítica.

═══════════════════════════════════════════════════════════════════════════
POR QUÉ ESTE ÍTEM VA ÚLTIMO, Y NO POR "DEPENDER DE P1-A" EN ABSTRACTO
═══════════════════════════════════════════════════════════════════════════
La v1 del checklist declaraba ``deps: requiere P1-01`` — pero P1-01 (el
runner Monte Carlo) YA EXISTÍA cuando este ítem seguía bloqueado. La
dependencia real no era la EXISTENCIA del runner, sino que su ESTIMADOR
tuviera señal: antes de P1-A, la métrica primaria era
``P(aniquilación total del enjambre)``, que vale 0 en casi todo el espacio
de operación (medido: 1 baja en 240 exposiciones con la configuración por
defecto — ver docs/AUDITORIA_CHECKLIST.md §1.2). Un algoritmo genético con
fitness constante 0 no tiene GRADIENTE: no hay presión de selección, ningún
individuo es mejor que otro, y el GA no evoluciona nada, sea cual sea su
implementación. P1-A reemplazó eso por ``fraccion_media`` (fracción
neutralizada por réplica, con IC por bootstrap) — un estimador que SÍ varía
de forma continua con los parámetros del arma/defensa, y es lo que este
módulo usa como fitness.

═══════════════════════════════════════════════════════════════════════════
EL GENOMA
═══════════════════════════════════════════════════════════════════════════
Deliberadamente acotado a parámetros que YA se pasan como argumentos
explícitos por la pila existente (``SimulationEngine.fire``,
``ExperimentConfig``), para no depender de parchear constantes globales de
``src/config.py`` — un patrón que ya causó errores reales en esta sesión
(P1-D/P1-F: un valor importado como nombre al cargar un módulo no se puede
monkeypatchear sobre el módulo de origen, solo sobre el módulo que lo
importó). Genomas más ricos (pesos de boids, fracción de blindaje) exigirían
primero exponerlos como parámetros inyectables en ``Swarm``/``flocking.py``
— fuera del alcance de este ítem.

- **Arma** (atacante): ``potencia_kw``, ``apertura_cono``, ``duty_cycle`` —
  las tres ya viajan como argumentos de ``WeaponPolicy``/``sim.fire``.
- **Defensa** (enjambre): ``formacion`` (categórica) y ``cantidad`` — ambas
  ya son campos directos de ``ExperimentConfig``.

═══════════════════════════════════════════════════════════════════════════
LA FRONTERA DE PARETO
═══════════════════════════════════════════════════════════════════════════
No es "el mejor individuo final" de cada población — es el conjunto de
individuos NO DOMINADOS, evaluados a lo largo de TODA la corrida, en un
espacio (costo, efectividad):

- **Arma**: costo = ``potencia_kw`` (más potencia, más energía/complejidad
  del sistema); efectividad = ``fraccion_media`` lograda. Frontera:
  maximizar efectividad, minimizar costo.
- **Defensa**: costo = ``cantidad`` (más drones, más presupuesto);
  efectividad = ``1 - fraccion_media`` (supervivencia). Frontera: maximizar
  supervivencia, minimizar costo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from src import config as config_mod
from src.engine.experiments import ExperimentConfig, WeaponPolicy, run_replica
from src.utils.reproducibilidad import nuevo_generador

FORMACIONES = ("cuadrada", "circular", "aleatoria", "linea", "v")


DISTANCIA_COMBATE_M = 60.0
"""Distancia arma↔centroide del enjambre para la coevolución (P3-B).

Con el emplazamiento por defecto del proyecto (arma en el origen del campo,
enjambre en el centro) la distancia es ~707 m — un régimen donde, medido
directamente en el diseño de este módulo, la probabilidad de baja por
disparo es ~1e-4 incluso al tope de potencia que el presupuesto energético
del cañón permite entregar en una ráfaga (500 kJ / 0.5 s ≈ 1 MW). Con ~30
drones y un puñado de réplicas por generación, el fitness del arma queda
idénticamente 0.0 y el GA no tiene gradiente sobre el que evolucionar.

60 m cae dentro del alcance de 90% de baja que el propio paper de
referencia reporta para el modo PULSADO (~88 m, arXiv:2602.08477 §5, ver
docs/REFERENCIA_PAPER_2602.08477.md), y cerca de uno de sus dos puntos de
calibración exactos (40 m → 13.1% de baja en CW). Medido empíricamente
durante el diseño de este módulo, a esta distancia aparecen DOS gradientes
reales simultáneos, ninguno forzado a mano:

1. **``duty_cycle`` del arma**: a igual potencia PROMEDIO (y por lo tanto
   igual costo energético — ``_energia_por_disparo_kj`` solo depende de la
   potencia promedio, no del duty cycle), bajar el duty cycle de 1.0 (CW) a
   0.01 (1% pulsado) multiplica la fracción neutralizada varias veces (ej.
   60 kW: 0.000→0.050 a 60 m, 15 réplicas). Esto reproduce exactamente la
   comparación CW-vs-pulsado de la Tabla de la §5 del paper — el pulsado
   alcanza mucho más lejos a la misma energía media, porque el daño
   depende del campo PICO, no del promedio.
2. **``cantidad``/``formacion`` de la defensa**: formaciones compactas
   (cuadrada, v) concentran drones dentro del cono estrecho del arma;
   formaciones dispersas (circular, línea, aleatoria) y una cantidad mayor
   (que agranda la huella física de la formación) sacan una fracción
   creciente de drones FUERA del cono — medido: cuadrada n=10→4.8% de baja,
   cuadrada n=55→2.3%; circular ≈0.0-0.2% en todo el rango de cantidad. Es
   un resultado con sentido táctico real (dispersión como contramedida
   contra un arma direccional de haz angosto), no un artefacto del ajuste
   de parámetros.
"""


def _origen_combate() -> tuple[float, float]:
    """Emplazamiento del arma a ``DISTANCIA_COMBATE_M`` del centro del
    campo, sobre la misma recta que ``_rumbo_al_centro_del_campo()`` — así
    el azimut de disparo no cambia, solo el alcance."""
    rumbo_rad = math.radians(_rumbo_al_centro_del_campo())
    cx, cy = config_mod.FIELD_WIDTH / 2, config_mod.FIELD_HEIGHT / 2
    return (
        cx - DISTANCIA_COMBATE_M * math.cos(rumbo_rad),
        cy - DISTANCIA_COMBATE_M * math.sin(rumbo_rad),
    )


def _rumbo_al_centro_del_campo() -> float:
    """Acimut (grados) desde el origen del cañón (``HPM_ORIGIN_X/Y``) hacia
    el centro del campo (``FIELD_WIDTH/HEIGHT`` / 2) — donde ``Swarm``
    coloca el centroide de CUALQUIER formación (ver
    ``Swarm.__init__``/``inicializar_formacion``: ninguna formación mueve
    ``centro_x``/``centro_y``, solo cambia cómo se reparten los drones
    alrededor de ese punto).

    Sin esto, ``WeaponPolicy(direccion=None)`` deja el cañón apuntando a su
    azimut por defecto (``HPM_DEFAULT_ANGLE``), que con la geometría por
    defecto del proyecto (arma en (0,0), campo 1000×1000) NO coincide con el
    enjambre — medido: con ``direccion=None`` el cañón dispara a 0 drones en
    4 generaciones completas (fitness del arma idénticamente 0.0, sin
    gradiente alguno, ver commit de este ítem). Todos los tests existentes
    que disparan el cañón contra el enjambre por defecto usan
    ``direccion=45`` a mano (``tests/test_experiments.py``); este helper
    calcula ese mismo valor a partir de la config en vez de repetirlo como
    número mágico, para que siga siendo correcto si alguien cambia el
    tamaño del campo o el origen del arma.
    """
    dx = config_mod.FIELD_WIDTH / 2 - config_mod.HPM_ORIGIN_X
    dy = config_mod.FIELD_HEIGHT / 2 - config_mod.HPM_ORIGIN_Y
    return math.degrees(math.atan2(dy, dx)) % 360


# ═══════════════════════════════════════════════════════════════════════════
# Genomas
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class GenomaArma:
    potencia_kw: float
    apertura_cono: float
    duty_cycle: float

    LIMITES = {
        "potencia_kw": (10.0, 100.0),
        "apertura_cono": (5.0, 60.0),
        "duty_cycle": (0.01, 1.0),
    }

    def clonar_acotado(self) -> "GenomaArma":
        return GenomaArma(
            potencia_kw=float(np.clip(self.potencia_kw, *self.LIMITES["potencia_kw"])),
            apertura_cono=float(np.clip(self.apertura_cono, *self.LIMITES["apertura_cono"])),
            duty_cycle=float(np.clip(self.duty_cycle, *self.LIMITES["duty_cycle"])),
        )

    def a_weapon_policy(self, delay_s: float = 1.0) -> WeaponPolicy:
        origen_x, origen_y = _origen_combate()
        return WeaponPolicy(
            tipo="canion", delay_s=delay_s,
            potencia=self.potencia_kw, direccion=_rumbo_al_centro_del_campo(),
            apertura_cono=self.apertura_cono, duty_cycle=self.duty_cycle,
            origen_x=origen_x, origen_y=origen_y,
        )

    @classmethod
    def aleatorio(cls, gen: np.random.Generator) -> "GenomaArma":
        lo, hi = cls.LIMITES["duty_cycle"]
        return cls(
            potencia_kw=float(gen.uniform(*cls.LIMITES["potencia_kw"])),
            apertura_cono=float(gen.uniform(*cls.LIMITES["apertura_cono"])),
            # log-uniforme, no uniforme (ver nota en el módulo, sección
            # "sesgo de muestreo de duty_cycle"): el rango [0.01, 1.0]
            # cubre DOS ÓRDENES DE MAGNITUD, y el efecto sobre el campo pico
            # es multiplicativo en 1/duty_cycle — un muestreo uniforme deja
            # el 99% de las muestras por encima de 0.02, subrepresentando
            # brutalmente la región (duty bajo) donde el arma es letal.
            duty_cycle=float(10 ** gen.uniform(math.log10(lo), math.log10(hi))),
        )


@dataclass
class GenomaDefensa:
    formacion_idx: int  # índice en FORMACIONES
    cantidad: float  # continuo internamente, se redondea al evaluar

    LIMITE_CANTIDAD = (10.0, 60.0)

    @property
    def formacion(self) -> str:
        return FORMACIONES[int(np.clip(self.formacion_idx, 0, len(FORMACIONES) - 1))]

    def clonar_acotado(self) -> "GenomaDefensa":
        return GenomaDefensa(
            formacion_idx=int(np.clip(round(self.formacion_idx), 0, len(FORMACIONES) - 1)),
            cantidad=float(np.clip(self.cantidad, *self.LIMITE_CANTIDAD)),
        )

    @classmethod
    def aleatorio(cls, gen: np.random.Generator) -> "GenomaDefensa":
        return cls(
            formacion_idx=int(gen.integers(0, len(FORMACIONES))),
            cantidad=float(gen.uniform(*cls.LIMITE_CANTIDAD)),
        )


# ═══════════════════════════════════════════════════════════════════════════
# Fitness — el runner Monte Carlo real
# ═══════════════════════════════════════════════════════════════════════════


def _fraccion_media(cfg: ExperimentConfig) -> float:
    """Media de la fracción neutralizada sobre ``cfg.replicas`` réplicas
    reales — la métrica primaria de P1-A, sin la maquinaria de bootstrap
    (innecesaria para un punto de fitness dentro del bucle evolutivo; el
    IC se calcula aparte si hace falta reportarlo)."""
    resultados = [run_replica(cfg, i) for i in range(cfg.replicas)]
    return float(np.mean([r["fraccion"] for r in resultados]))


def evaluar_enfrentamiento(
    arma: GenomaArma,
    defensa: GenomaDefensa,
    replicas: int,
    t_max_s: float,
    semilla: int,
) -> float:
    """
    Fracción media neutralizada si ``arma`` dispara contra un enjambre
    configurado según ``defensa`` — el número que gobierna el fitness de
    AMBAS poblaciones (``fitness_arma = esto``, ``fitness_defensa = 1 - esto``)
    cuando la misión ofensiva está apagada (el caso de siempre hasta este
    punto). Firma sin tocar a propósito — la usan ``evolucionar_arma_contra_
    defensa_fija``/``evolucionar_defensa_contra_arma_fija`` (controles
    experimentales que aíslan el mecanismo del GA) y ~10 tests existentes;
    ver ``_evaluar_enfrentamiento_con_mision`` para la versión que también
    mide si el enjambre llegó al objetivo, usada solo dentro de
    ``coevolucionar``.
    """
    cfg = ExperimentConfig(
        formacion=defensa.formacion,
        cantidad=int(round(defensa.cantidad)),
        replicas=replicas,
        t_max_s=t_max_s,
        semilla=semilla,
        arma=arma.a_weapon_policy(),
    )
    return _fraccion_media(cfg)


def _evaluar_enfrentamiento_con_mision(
    arma: GenomaArma,
    defensa: GenomaDefensa,
    replicas: int,
    t_max_s: float,
    semilla: int,
    con_mision: bool,
) -> tuple[float, float]:
    """
    Como ``evaluar_enfrentamiento``, pero devuelve ``(fraccion_media,
    fraccion_alcanzo_objetivo)`` — ambas del MISMO conjunto de réplicas,
    sin costo extra de simulación. ``fraccion_alcanzo_objetivo`` es 0.0
    si ``con_mision=False`` (sin objetivo, ningún dron puede tener
    ``objetivo_alcanzado`` — ver ``run_replica``).
    """
    cfg = ExperimentConfig(
        formacion=defensa.formacion,
        cantidad=int(round(defensa.cantidad)),
        replicas=replicas,
        t_max_s=t_max_s,
        semilla=semilla,
        arma=arma.a_weapon_policy(),
        con_mision=con_mision,
    )
    resultados = [run_replica(cfg, i) for i in range(cfg.replicas)]
    fraccion_media = float(np.mean([r["fraccion"] for r in resultados]))
    fraccion_alcanzo = float(np.mean([r["fraccion_alcanzo_objetivo"] for r in resultados]))
    return fraccion_media, fraccion_alcanzo


def _fitness_arma(fraccion_media: float, fraccion_alcanzo: float, con_mision: bool) -> float:
    """
    Cuánto le conviene este genoma al ARMA. Sin misión (el default):
    ``fraccion_media`` sola, byte a byte igual que antes de este ítem —
    ver ``con_mision=False`` en ``coevolucionar``. Con misión: promedio
    simple con "impidió la brecha" (``1 - fraccion_alcanzo``).

    Por qué promedio simple y no un peso distinto para cada término: no
    hay evidencia para preferir uno sobre el otro — neutralizar más no es
    lo mismo que impedir que lleguen (un arma lenta puede neutralizar
    bastante y aun así dejar pasar al resto), y esta característica
    existe precisamente porque esas dos cosas pueden divergir. Pesarlas
    distinto sin una razón medida sería inventar un número, lo mismo que
    este proyecto evita en el resto de sus constantes.
    """
    if not con_mision:
        return fraccion_media
    return 0.5 * fraccion_media + 0.5 * (1.0 - fraccion_alcanzo)


def _fitness_defensa(fraccion_media: float, fraccion_alcanzo: float, con_mision: bool) -> float:
    """
    Cuánto le conviene este genoma a la DEFENSA/enjambre. Sin misión:
    supervivencia sola (``1 - fraccion_media``), igual que antes. Con
    misión: promedio simple con "llegó al objetivo" — sobrevivir y
    cumplir la misión son dos formas distintas de que el ataque
    "funcione"; ninguna alcanza sola (ver ``_fitness_arma`` para el
    mismo razonamiento del lado del arma).
    """
    supervivencia = 1.0 - fraccion_media
    if not con_mision:
        return supervivencia
    return 0.5 * supervivencia + 0.5 * fraccion_alcanzo


# ═══════════════════════════════════════════════════════════════════════════
# Operadores genéticos (genéricos sobre un vector de genes en [0,1]
# normalizado internamente por límites, para reutilizar el mismo código
# entre el genoma de arma y el de defensa)
# ═══════════════════════════════════════════════════════════════════════════


def _torneo(fitness: list[float], gen: np.random.Generator, k: int = 3) -> int:
    """Selección por torneo: elige el mejor entre ``k`` candidatos al azar."""
    candidatos = gen.integers(0, len(fitness), size=k)
    return int(max(candidatos, key=lambda i: fitness[i]))


def _cruzar_arma(a: GenomaArma, b: GenomaArma, gen: np.random.Generator) -> GenomaArma:
    alpha = float(gen.uniform(0.0, 1.0))
    # duty_cycle se cruza en ESCALA LOGARÍTMICA (ver aleatorio()): un blend
    # lineal entre 0.9 y 0.02 da ~0.5 (todavía casi inerte); un blend en
    # log10 da 10^(0.5·log10(0.9)+0.5·log10(0.02)) ≈ 0.13 — preserva el
    # orden de magnitud de cada padre en vez de que el más alto domine.
    log_duty = alpha * math.log10(a.duty_cycle) + (1 - alpha) * math.log10(b.duty_cycle)
    return GenomaArma(
        potencia_kw=alpha * a.potencia_kw + (1 - alpha) * b.potencia_kw,
        apertura_cono=alpha * a.apertura_cono + (1 - alpha) * b.apertura_cono,
        duty_cycle=10 ** log_duty,
    ).clonar_acotado()


def _mutar_arma(g: GenomaArma, gen: np.random.Generator, tasa: float = 0.3) -> GenomaArma:
    nuevo = GenomaArma(g.potencia_kw, g.apertura_cono, g.duty_cycle)
    for campo, (lo, hi) in GenomaArma.LIMITES.items():
        if gen.random() < tasa:
            if campo == "duty_cycle":
                # Paso multiplicativo (aditivo en log10): con σ=0.15
                # décadas, un salto de 2σ mueve el duty cycle en un factor
                # ~4.7× hacia arriba o abajo — suficiente para cruzar de
                # "inerte" a "letal" en pocas generaciones, algo que un
                # paso aditivo en escala lineal (σ≈0.15) casi nunca logra
                # partiendo de valores altos (ver hallazgo de diseño de
                # este ítem: sin esto, el GA queda con el 99% del rango de
                # duty_cycle inalcanzable en una corrida corta).
                sigma_log = 0.5
                log_valor = math.log10(nuevo.duty_cycle) + float(gen.normal(0.0, sigma_log))
                nuevo.duty_cycle = 10 ** log_valor
            else:
                sigma = (hi - lo) * 0.15
                valor = getattr(nuevo, campo) + float(gen.normal(0.0, sigma))
                setattr(nuevo, campo, valor)
    return nuevo.clonar_acotado()


def _cruzar_defensa(a: GenomaDefensa, b: GenomaDefensa, gen: np.random.Generator) -> GenomaDefensa:
    alpha = float(gen.uniform(0.0, 1.0))
    formacion_idx = a.formacion_idx if gen.random() < 0.5 else b.formacion_idx
    return GenomaDefensa(
        formacion_idx=formacion_idx,
        cantidad=alpha * a.cantidad + (1 - alpha) * b.cantidad,
    ).clonar_acotado()


def _mutar_defensa(g: GenomaDefensa, gen: np.random.Generator, tasa: float = 0.3) -> GenomaDefensa:
    formacion_idx = g.formacion_idx
    cantidad = g.cantidad
    if gen.random() < tasa:
        formacion_idx = int(gen.integers(0, len(FORMACIONES)))
    if gen.random() < tasa:
        sigma = (GenomaDefensa.LIMITE_CANTIDAD[1] - GenomaDefensa.LIMITE_CANTIDAD[0]) * 0.15
        cantidad = cantidad + float(gen.normal(0.0, sigma))
    return GenomaDefensa(formacion_idx, cantidad).clonar_acotado()


def _evolucionar_poblacion(
    poblacion: list,
    fitness: list[float],
    gen: np.random.Generator,
    cruzar,
    mutar,
    aleatorio_fn,
    elitismo: int = 1,
) -> list:
    """Un paso generacional genérico: elitismo + torneo + cruce + mutación."""
    n = len(poblacion)
    orden = sorted(range(n), key=lambda i: -fitness[i])
    nueva = [poblacion[i] for i in orden[:elitismo]]

    while len(nueva) < n:
        i = _torneo(fitness, gen)
        j = _torneo(fitness, gen)
        hijo = cruzar(poblacion[i], poblacion[j], gen)
        hijo = mutar(hijo, gen)
        nueva.append(hijo)

    return nueva


# ═══════════════════════════════════════════════════════════════════════════
# Frontera de Pareto
# ═══════════════════════════════════════════════════════════════════════════


def frontera_pareto(puntos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """
    Subconjunto NO DOMINADO de ``puntos = [(costo, valor), ...]``, definiendo
    la frontera como "minimizar costo, maximizar valor": un punto está
    DOMINADO si existe otro punto con costo ``≤`` Y valor ``≥``, con al
    menos una desigualdad estricta.
    """
    frontera = []
    for i, (costo_i, valor_i) in enumerate(puntos):
        dominado = False
        for j, (costo_j, valor_j) in enumerate(puntos):
            if i == j:
                continue
            mejor_o_igual = costo_j <= costo_i and valor_j >= valor_i
            estrictamente_mejor = costo_j < costo_i or valor_j > valor_i
            if mejor_o_igual and estrictamente_mejor:
                dominado = True
                break
        if not dominado:
            frontera.append((costo_i, valor_i))
    # Deduplicar y ordenar por costo, para un resultado presentable.
    frontera = sorted(set(frontera))
    return frontera


# ═══════════════════════════════════════════════════════════════════════════
# Evolución de UNA población contra un oponente FIJO
#
# Útil como control experimental: en la coevolución completa (más abajo) el
# oponente de cada generación es el CAMPEÓN de la generación anterior de la
# otra población — un blanco móvil, así que "el fitness de la generación 5
# fue mayor que el de la generación 1" no es una comparación limpia (el
# oponente también cambió). Estas dos funciones evolucionan una sola
# población contra un rival que NO cambia, para poder afirmar sin ambigüedad
# "esta población mejoró" — es lo que ``tests/test_coevolution.py`` usa para
# verificar el criterio de aceptación del ítem sin el ruido de un blanco
# móvil.
# ═══════════════════════════════════════════════════════════════════════════


def evolucionar_arma_contra_defensa_fija(
    defensa_fija: GenomaDefensa,
    n_generaciones: int,
    tam_poblacion: int,
    replicas_por_evaluacion: int,
    t_max_s: float,
    seed: int,
) -> tuple[list[float], GenomaArma]:
    """Evoluciona SOLO la población de armas contra ``defensa_fija`` (que no
    cambia). Devuelve el fitness MEDIO de la población por generación (no el
    del mejor individuo) y el mejor genoma final.

    Por qué la MEDIA y no el máximo: con el nivel de letalidad realista de
    esta escala de combate (fracciones de un pequeño % por réplica, ver
    docstring de ``DISTANCIA_COMBATE_M``), no es raro que un individuo
    cualquiera saque 0 bajas en sus ``replicas_por_evaluacion`` réplicas por
    pura casualidad — su fitness (o el de la defensa, 1 - fracción) toca el
    techo exacto (0.0 o 1.0) sin que eso refleje mérito real del genoma.
    Medido en el diseño de este módulo: con población de 6-8 y pocas
    réplicas, el MÁXIMO de la población queda pegado al techo la mayoría de
    las generaciones (ceiling effect), enmascarando por completo la mejora
    real que sí ocurre en el resto de la población. La MEDIA, al promediar
    sobre ``tam_poblacion × replicas_por_evaluacion`` muestras en vez de
    ``replicas_por_evaluacion``, es un estimador mucho menos ruidoso de si
    la población en conjunto está mejorando.
    """
    gen = nuevo_generador(seed)
    poblacion = [GenomaArma.aleatorio(gen) for _ in range(tam_poblacion)]
    fitness_medio_por_gen: list[float] = []
    mejor_genoma = poblacion[0]

    for generacion in range(n_generaciones):
        semilla_gen = seed + 1000 * (generacion + 1)
        fitness = [
            evaluar_enfrentamiento(
                ind, defensa_fija, replicas_por_evaluacion, t_max_s,
                semilla_gen + i * replicas_por_evaluacion,
            )
            for i, ind in enumerate(poblacion)
        ]
        mejor_idx = int(np.argmax(fitness))
        mejor_genoma = poblacion[mejor_idx]
        fitness_medio_por_gen.append(float(np.mean(fitness)))
        poblacion = _evolucionar_poblacion(poblacion, fitness, gen, _cruzar_arma, _mutar_arma, GenomaArma.aleatorio)

    return fitness_medio_por_gen, mejor_genoma


def evolucionar_defensa_contra_arma_fija(
    arma_fija: GenomaArma,
    n_generaciones: int,
    tam_poblacion: int,
    replicas_por_evaluacion: int,
    t_max_s: float,
    seed: int,
) -> tuple[list[float], GenomaDefensa]:
    """Evoluciona SOLO la población de defensa (fitness = supervivencia)
    contra ``arma_fija`` (que no cambia). Devuelve el fitness MEDIO de la
    población por generación (ver el porqué en el docstring de
    ``evolucionar_arma_contra_defensa_fija`` — mismo ceiling effect, acá con
    el techo en 1.0 en vez de 0.0) y el mejor genoma final."""
    gen = nuevo_generador(seed)
    poblacion = [GenomaDefensa.aleatorio(gen) for _ in range(tam_poblacion)]
    fitness_medio_por_gen: list[float] = []
    mejor_genoma = poblacion[0]

    for generacion in range(n_generaciones):
        semilla_gen = seed + 1000 * (generacion + 1)
        fitness = [
            1.0 - evaluar_enfrentamiento(
                arma_fija, ind, replicas_por_evaluacion, t_max_s,
                semilla_gen + i * replicas_por_evaluacion,
            )
            for i, ind in enumerate(poblacion)
        ]
        mejor_idx = int(np.argmax(fitness))
        mejor_genoma = poblacion[mejor_idx]
        fitness_medio_por_gen.append(float(np.mean(fitness)))
        poblacion = _evolucionar_poblacion(
            poblacion, fitness, gen, _cruzar_defensa, _mutar_defensa, GenomaDefensa.aleatorio
        )

    return fitness_medio_por_gen, mejor_genoma


# ═══════════════════════════════════════════════════════════════════════════
# El bucle coevolutivo
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ResultadoCoevolucion:
    generaciones: int
    mejor_arma_por_generacion: list[GenomaArma] = field(default_factory=list)
    mejor_defensa_por_generacion: list[GenomaDefensa] = field(default_factory=list)
    fitness_arma_por_generacion: list[float] = field(default_factory=list)
    fitness_defensa_por_generacion: list[float] = field(default_factory=list)
    # Fitness MEDIO de la población (no el del campeón) por generación — ver
    # el porqué (ceiling effect) en el docstring de
    # ``evolucionar_arma_contra_defensa_fija``. Es la serie que hay que
    # mirar para juzgar si la población MEJORÓ; ``fitness_*_por_generacion``
    # de arriba (el campeón) satura en el techo casi todas las generaciones
    # a esta escala de letalidad y no es un buen indicador de tendencia.
    fitness_arma_media_por_generacion: list[float] = field(default_factory=list)
    fitness_defensa_media_por_generacion: list[float] = field(default_factory=list)
    puntos_arma: list[tuple[float, float]] = field(default_factory=list)  # (potencia, fraccion) — SIEMPRE fraccion_media cruda, no el fitness combinado (ver coevolucionar)
    puntos_defensa: list[tuple[float, float]] = field(default_factory=list)  # (cantidad, supervivencia) — ídem
    # Misión ofensiva (P3-B + P2-E/misión, ver ExperimentConfig.con_mision):
    # False (default) deja fitness_arma/fitness_defensa EXACTAMENTE como
    # antes de este ítem — fraccion_media/supervivencia sin mezclar con
    # nada. Con con_mision=True, esas dos series pasan a ser el promedio
    # con la señal de brecha (ver _fitness_arma/_fitness_defensa); estas
    # dos series nuevas guardan la fraccion_alcanzo_objetivo CRUDA del
    # enfrentamiento del campeón, para poder reportarla sin ambigüedad
    # (0.0 en todas las generaciones si con_mision=False).
    con_mision: bool = False
    fraccion_alcanzo_arma_por_generacion: list[float] = field(default_factory=list)
    fraccion_alcanzo_defensa_por_generacion: list[float] = field(default_factory=list)

    def frontera_arma(self) -> list[tuple[float, float]]:
        return frontera_pareto(self.puntos_arma)

    def frontera_defensa(self) -> list[tuple[float, float]]:
        return frontera_pareto(self.puntos_defensa)


def coevolucionar(
    n_generaciones: int = 5,
    tam_poblacion: int = 8,
    replicas_por_evaluacion: int = 3,
    t_max_s: float = 8.0,
    cantidad_defensa_base: int = 20,
    seed: int = 2026,
    on_generacion: Callable[[int, ResultadoCoevolucion], None] | None = None,
    con_mision: bool = False,
) -> ResultadoCoevolucion:
    """
    Corre ``n_generaciones`` de coevolución. Cada generación evalúa TODOS
    los individuos de AMBAS poblaciones contra el MEJOR individuo de la
    generación anterior de la población contraria ("hall of fame" de un solo
    campeón — más barato que round-robin completo y suficiente para una
    corrida corta, ver el ``done`` del ítem: "corrida corta, réplicas
    reducidas").

    Determinista: un único generador (``nuevo_generador(seed)``) gobierna
    la inicialización, selección, cruce y mutación de ambas poblaciones —
    misma semilla, mismo resultado byte a byte.

    ``on_generacion(generacion_idx, resultado_parcial)``, si se pasa, se
    llama al final de CADA generación con el ``resultado`` acumulado hasta
    ahí (mismo objeto que se devuelve al final, ya con esa generación
    agregada) — pensado para reportar progreso desde un job en background
    (P3-B no tiene forma de correr "rápido": una corrida de varios minutos
    necesita poder mostrar avance, no solo el resultado final). No cambia
    nada de la lógica determinista del algoritmo.

    ``con_mision`` (False por defecto): además de neutralizar, el arma
    también evoluciona contra impedir que el enjambre llegue al objetivo,
    y el enjambre también evoluciona contra llegar — ver ``_fitness_arma``/
    ``_fitness_defensa`` para el porqué del promedio simple entre las dos
    señales. Apagado, esto es byte a byte lo mismo que antes de que
    existiera esta opción.
    """
    gen = nuevo_generador(seed)

    poblacion_arma = [GenomaArma.aleatorio(gen) for _ in range(tam_poblacion)]
    poblacion_defensa = [GenomaDefensa.aleatorio(gen) for _ in range(tam_poblacion)]

    # Campeón inicial (generación "0"): un enjambre/arma de referencia, para
    # que la generación 1 tenga contra qué medirse sin depender de un
    # individuo aleatorio de la propia primera generación.
    #
    # NO son los defaults "neutros" del proyecto (CW 25kW / formación
    # circular): medido durante el diseño de este módulo, esa pareja da
    # fracción neutralizada ~0.0-0.002 en ``DISTANCIA_COMBATE_M`` = 60 m —
    # un "empate en cero" que deja a AMBAS poblaciones sin gradiente en la
    # generación 1 (arma: cualquier genoma es indistinguible de otro contra
    # un enjambre disperso que ya sobrevive casi todo; defensa: cualquier
    # formación empata en supervivencia ≈100% contra un arma casi inerte).
    # El campeón inicial de cada lado es, en cambio, el ADVERSARIO del otro:
    # un arma pulsada de potencia media (vulnerable a que la defensa evolue
    # DISTANCIA, no CONTRA nada) y una defensa compacta (vulnerable a que el
    # arma evolucione potencia/duty cycle, no una formación ya inmune).
    campeon_arma = GenomaArma(potencia_kw=60.0, apertura_cono=15.0, duty_cycle=0.05)
    campeon_defensa = GenomaDefensa(formacion_idx=FORMACIONES.index("cuadrada"), cantidad=cantidad_defensa_base)

    resultado = ResultadoCoevolucion(generaciones=n_generaciones, con_mision=con_mision)

    for generacion in range(n_generaciones):
        semilla_generacion = seed + 1000 * (generacion + 1)

        # (fraccion_media, fraccion_alcanzo) crudas por individuo — la
        # fuente de verdad. fitness_* es lo que gobierna selección/
        # reproducción (_fitness_arma/_fitness_defensa combinan ambas
        # señales solo si con_mision=True).
        crudos_arma = [
            _evaluar_enfrentamiento_con_mision(
                individuo, campeon_defensa, replicas_por_evaluacion, t_max_s,
                semilla_generacion + i * replicas_por_evaluacion, con_mision,
            )
            for i, individuo in enumerate(poblacion_arma)
        ]
        crudos_defensa = [
            _evaluar_enfrentamiento_con_mision(
                campeon_arma, individuo, replicas_por_evaluacion, t_max_s,
                semilla_generacion + 500 + i * replicas_por_evaluacion, con_mision,
            )
            for i, individuo in enumerate(poblacion_defensa)
        ]
        fitness_arma = [_fitness_arma(fm, fa, con_mision) for fm, fa in crudos_arma]
        fitness_defensa = [_fitness_defensa(fm, fa, con_mision) for fm, fa in crudos_defensa]

        # puntos_arma/puntos_defensa (la frontera de Pareto) siguen siendo
        # SIEMPRE fraccion_media/supervivencia crudas, no el fitness
        # combinado — para que "fraccion_neutralizada"/"supervivencia" en
        # el JSON de salida sigan significando lo que dicen que significan,
        # con o sin misión.
        for individuo, (fm, _fa) in zip(poblacion_arma, crudos_arma):
            resultado.puntos_arma.append((individuo.potencia_kw, fm))
        for individuo, (fm, _fa) in zip(poblacion_defensa, crudos_defensa):
            resultado.puntos_defensa.append((individuo.cantidad, 1.0 - fm))

        mejor_idx_arma = int(np.argmax(fitness_arma))
        mejor_idx_defensa = int(np.argmax(fitness_defensa))
        campeon_arma = poblacion_arma[mejor_idx_arma]
        campeon_defensa = poblacion_defensa[mejor_idx_defensa]

        resultado.mejor_arma_por_generacion.append(campeon_arma)
        resultado.mejor_defensa_por_generacion.append(campeon_defensa)
        resultado.fitness_arma_media_por_generacion.append(float(np.mean(fitness_arma)))
        resultado.fitness_defensa_media_por_generacion.append(float(np.mean(fitness_defensa)))
        resultado.fitness_arma_por_generacion.append(fitness_arma[mejor_idx_arma])
        resultado.fitness_defensa_por_generacion.append(fitness_defensa[mejor_idx_defensa])
        resultado.fraccion_alcanzo_arma_por_generacion.append(crudos_arma[mejor_idx_arma][1])
        resultado.fraccion_alcanzo_defensa_por_generacion.append(crudos_defensa[mejor_idx_defensa][1])

        poblacion_arma = _evolucionar_poblacion(
            poblacion_arma, fitness_arma, gen, _cruzar_arma, _mutar_arma, GenomaArma.aleatorio
        )
        poblacion_defensa = _evolucionar_poblacion(
            poblacion_defensa, fitness_defensa, gen, _cruzar_defensa, _mutar_defensa,
            GenomaDefensa.aleatorio,
        )

        if on_generacion is not None:
            on_generacion(generacion, resultado)

    return resultado


def resumen_json(resultado: ResultadoCoevolucion) -> dict[str, Any]:
    """Serializa el resultado para el endpoint/API — sin objetos dataclass."""
    return {
        "generaciones": resultado.generaciones,
        "fitness_arma_por_generacion": [round(f, 4) for f in resultado.fitness_arma_por_generacion],
        "fitness_defensa_por_generacion": [round(f, 4) for f in resultado.fitness_defensa_por_generacion],
        "fitness_arma_media_por_generacion": [round(f, 4) for f in resultado.fitness_arma_media_por_generacion],
        "fitness_defensa_media_por_generacion": [
            round(f, 4) for f in resultado.fitness_defensa_media_por_generacion
        ],
        "mejor_arma_final": {
            "potencia_kw": round(resultado.mejor_arma_por_generacion[-1].potencia_kw, 2),
            "apertura_cono": round(resultado.mejor_arma_por_generacion[-1].apertura_cono, 2),
            "duty_cycle": round(resultado.mejor_arma_por_generacion[-1].duty_cycle, 4),
            "fraccion_alcanzo_objetivo": (
                round(resultado.fraccion_alcanzo_arma_por_generacion[-1], 4)
                if resultado.con_mision and resultado.fraccion_alcanzo_arma_por_generacion else None
            ),
        } if resultado.mejor_arma_por_generacion else None,
        "mejor_defensa_final": {
            "formacion": resultado.mejor_defensa_por_generacion[-1].formacion,
            "cantidad": int(round(resultado.mejor_defensa_por_generacion[-1].cantidad)),
            "fraccion_alcanzo_objetivo": (
                round(resultado.fraccion_alcanzo_defensa_por_generacion[-1], 4)
                if resultado.con_mision and resultado.fraccion_alcanzo_defensa_por_generacion else None
            ),
        } if resultado.mejor_defensa_por_generacion else None,
        "frontera_pareto_arma": [
            {"potencia_kw": round(c, 2), "fraccion_neutralizada": round(v, 4)}
            for c, v in resultado.frontera_arma()
        ],
        "frontera_pareto_defensa": [
            {"cantidad": round(c, 2), "supervivencia": round(v, 4)}
            for c, v in resultado.frontera_defensa()
        ],
        # Misión ofensiva (ExperimentConfig.con_mision, ver el commit que la
        # introdujo): None/ausente si estaba apagada durante esta corrida —
        # a diferencia del resto de los campos de acá, que siempre están
        # presentes con 0, acá se prefiere None a un 0 engañoso: un 0
        # podría leerse como "el mejor arma encontrada NO impidió ninguna
        # brecha" en vez de "esta corrida ni siquiera midió eso".
        "con_mision": resultado.con_mision,
        "fraccion_alcanzo_arma_por_generacion": (
            [round(f, 4) for f in resultado.fraccion_alcanzo_arma_por_generacion]
            if resultado.con_mision else None
        ),
        "fraccion_alcanzo_defensa_por_generacion": (
            [round(f, 4) for f in resultado.fraccion_alcanzo_defensa_por_generacion]
            if resultado.con_mision else None
        ),
    }
