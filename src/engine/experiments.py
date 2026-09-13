"""Runner de experimentos Monte Carlo headless.

Ejecuta N réplicas de un escenario (misma configuración, misma política de
arma, distinta sub-semilla) y las agrega en estadística con señal.

LA UNIDAD DE MUESTREO ES LA RÉPLICA (P1-A). Esto no es un detalle de
implementación, es lo que hace que los intervalos sean válidos: los drones de
una misma réplica comparten geometría, semilla y configuración, así que sus
resultados individuales **no son Bernoulli independientes**. Agregar bajas por
dron y meterlas en un intervalo binomial (Wilson) daría un IC demasiado
estrecho por correlación intra-réplica. Cada réplica aporta UNA observación: su
fracción neutralizada.

MÉTRICA PRIMARIA — ``fraccion_media``: media de la fracción neutralizada por
réplica, con dos intervalos del 95%:

- ``ic95_bootstrap``: bootstrap de percentiles sobre las fracciones de réplica.
  Elección declarada: es simple, no supone normalidad (la distribución de la
  fracción está acotada en [0,1] y suele ser asimétrica cerca de los extremos,
  que es justo donde opera un arma HPM a media/larga distancia) y no necesita
  dependencias nuevas. No se usa bootstrap-t ni BCa: ganarían precisión en la
  cobertura para n chico, a costa de complejidad que no se puede verificar sin
  scipy (que está en el venv pero NO declarado en requirements.txt).
- ``ic95_t``: intervalo por t de Student sobre las mismas fracciones. Se
  reporta como contraste barato y verificable a mano: si los dos ICs difieren
  mucho, la distribución es muy asimétrica y eso **es información**, no ruido.

También: ``desviacion_estandar``, ``cv`` (coeficiente de variación σ/μ) y
percentiles p5/p25/p50/p75/p95. El CV es el que permite comparar contra el
paper de referencia, que reporta CV ≈ 39% a 30 m (ver
docs/REFERENCIA_PAPER_2602.08477.md §3) — criterio de aceptación del ítem P1-B.
Los percentiles importan porque con un enjambre parcialmente alcanzable la
distribución puede ser multimodal y la media sola lo esconde.

MÉTRICA SECUNDARIA — ``aniquilacion_total``: proporción de réplicas en las que
cayó el enjambre COMPLETO, con su IC de Wilson (ahí sí la réplica es un ensayo
Bernoulli legítimo, así que Wilson es correcto). Esto es lo que antes de P1-A
se reportaba como ``p_hat``/``ic95``, o sea como si fuera "la probabilidad de
baja". No lo era, y en casi todo el espacio de operación vale 0: medido con la
configuración por defecto (cañón 25 kW contra enjambre a ~700 m) daba 1 baja en
240 exposiciones y reportaba p̂=0 con IC=[0, 0.32] — un estimador ciego, que
además dejaba sin gradiente al ítem P3-B (coevolución genética: un fitness
constante 0 no evoluciona nada). Ver docs/AUDITORIA_CHECKLIST.md §1.2.

- ``convergencia``: serie de la fracción media acumulada y el semiancho de su
  IC cada réplica, para verificar que el estimador se estabiliza con N.

Cada réplica crea su propia ``SimulationEngine`` **sin hilo** y avanza con
``SimulationEngine._tick(dt)`` — el mismo paso que usa el bucle en tiempo
real, así que los números del experimento son los del modelo en producción.

RNG por réplica, aislado (P0-B): cada réplica construye su propio
``numpy.random.Generator`` con ``nuevo_generador(cfg.semilla + i)`` y se lo
inyecta a su ``SimulationEngine`` (que a su vez lo propaga a
``Swarm``/``HPMissileSystem``/``Drone``/``HPMissile``, ver
src/utils/reproducibilidad.py). No hay generador compartido con nadie: ni con
el hilo de la simulación interactiva, ni con otras réplicas, ni con otros
experimentos corriendo en paralelo. Antes de este cambio las réplicas
sembraban el generador GLOBAL de ``src/utils/reproducibilidad.py``
(``seed_simulacion(cfg.semilla + i)``), el mismo que consume
``SimulationEngine._run_loop`` de la simulación interactiva — un stopgap
documentado que hacía que dos consumidores concurrentes del generador se
corrompieran mutuamente (ver docs/AUDITORIA_CHECKLIST.md §3.1). Con la
inyección, esa limitación queda cerrada: ``tests/test_aislamiento_rng.py``
verifica que un experimento corrido en paralelo con la simulación
interactiva, y dos experimentos concurrentes con la misma semilla, dan
resultados bit a bit idénticos a correrlos aislados.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src import config as config_mod
from src.engine.parametros import EspecificacionMC
from src.engine.simulation import SimulationEngine
from src.utils.reproducibilidad import build_manifest, nuevo_generador

Z_95 = 1.959963984540054

# t de Student al 97.5% (bilateral 95%) por grados de libertad. Tabla en vez de
# scipy: scipy está en el venv pero NO en requirements.txt, así que el entorno
# no es reproducible desde requirements y no se puede depender de él (ver
# docs/AUDITORIA_CHECKLIST.md §4.6).
#
# Cuánto error introduce truncar la tabla: a df=30 la t (2.042) está un 4.0%
# por encima de la normal (1.960), NO menos del 1% — la convergencia t→normal
# es lenta. Recién alrededor de df≈120 (t=1.980) el error baja del 1%. Por eso
# la tabla llega a 120 en vez de a 30, y para df intermedios se toma el df
# tabulado INMEDIATAMENTE INFERIOR: da un t algo mayor, o sea un intervalo
# algo más ancho — conservador, que es el lado correcto para equivocarse en un
# intervalo de confianza.
_T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    40: 2.021, 50: 2.009, 60: 2.000, 80: 1.990, 100: 1.984, 120: 1.980,
}
_T_975_DF = sorted(_T_975)

# Semilla del remuestreo bootstrap. Fija a propósito: un IC que cambia de
# corrida en corrida sobre los mismos datos no es reportable. El bootstrap usa
# su propio Generator aislado (nuevo_generador), no el global ni el de la
# réplica.
BOOTSTRAP_SEED = 20260912
BOOTSTRAP_REMUESTREOS = 10_000


def t_critico_975(n: int) -> float:
    """Valor crítico t al 95% bilateral para ``n`` observaciones (df = n-1).

    Para un df no tabulado se usa el tabulado inmediatamente inferior (t algo
    mayor ⇒ intervalo algo más ancho: conservador). Por encima de df=120 se
    usa la normal, donde el error ya es < 1%.
    """
    df = n - 1
    if df <= 0:
        return float("nan")
    if df in _T_975:
        return float(_T_975[df])
    inferiores = [d for d in _T_975_DF if d < df]
    if not inferiores or df > _T_975_DF[-1]:
        return float(Z_95)
    return float(_T_975[inferiores[-1]])


def intervalo_t(valores: list[float] | np.ndarray) -> tuple[float, float]:
    """IC del 95% por t de Student sobre la media, recortado a [0, 1].

    Las observaciones son fracciones (acotadas en [0,1]), así que el intervalo
    se recorta: un límite fuera de [0,1] no es interpretable como fracción. El
    recorte se declara porque degrada la cobertura nominal cerca de los
    extremos — es precisamente el caso donde ``ic95_bootstrap`` es preferible.
    """
    x = np.asarray(valores, dtype=float)
    n = x.size
    if n == 0:
        return (0.0, 0.0)
    if n == 1:
        return (float(x[0]), float(x[0]))
    media = float(x.mean())
    # ddof=1: varianza muestral (estimador no sesgado), no poblacional.
    error_estandar = float(x.std(ddof=1)) / (n**0.5)
    semiancho = t_critico_975(n) * error_estandar
    return (max(0.0, media - semiancho), min(1.0, media + semiancho))


def intervalo_bootstrap(
    valores: list[float] | np.ndarray,
    remuestreos: int = BOOTSTRAP_REMUESTREOS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """IC del 95% por bootstrap de percentiles sobre la media.

    Remuestrea con reemplazo las observaciones POR RÉPLICA (no por dron: ver el
    docstring del módulo) y toma los percentiles 2.5 y 97.5 de la distribución
    de medias remuestreadas.

    Determinista por construcción: usa ``nuevo_generador(seed)``, un Generator
    aislado. Mismos datos ⇒ mismo intervalo, siempre.

    Caso degenerado: si todas las observaciones son idénticas (todas 0 o todas
    1, que ocurre de verdad — un arma inefectiva a larga distancia da todas 0),
    todas las medias remuestreadas coinciden y el intervalo colapsa a un punto.
    Eso es correcto y es lo que el bootstrap debe decir: con esos datos no hay
    variabilidad observada. No se ensancha artificialmente.
    """
    x = np.asarray(valores, dtype=float)
    n = x.size
    if n == 0:
        return (0.0, 0.0)
    if n == 1:
        return (float(x[0]), float(x[0]))

    gen = nuevo_generador(seed)
    idx = gen.integers(0, n, size=(remuestreos, n))
    medias = x[idx].mean(axis=1)
    lo, hi = np.percentile(medias, [2.5, 97.5])
    return (float(max(0.0, lo)), float(min(1.0, hi)))


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Intervalo de confianza de Wilson para una proporción (k éxitos en n).

    Mejor comportamiento que el IC normal en los extremos (p̂ cerca de 0 o 1),
    típicos de las probabilidades de baja HPM a media/larga distancia.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * (p * (1.0 - p) / n + z2 / (4.0 * n * n)) ** 0.5
    return (max(0.0, center - half), min(1.0, center + half))


@dataclass
class WeaponPolicy:
    """Política de arma mínima para una réplica.

    - "canion": un disparo del cañón HPM estático en ``delay_s`` (dirección
      fija; ``direccion=None`` conserva el azimut por defecto del arma).
    - "misil": un misil lanzado desde el origen del arma en ``delay_s``
      (``direccion=None`` = auto-apuntado al centroide detectado, igual que
      el lanzamiento manual por API).
    - "ninguna": grupo control (métrica base del escenario sin arma).
    """

    tipo: str = "ninguna"
    delay_s: float = 1.0
    potencia: float | None = None
    direccion: float | None = None
    misil_potencia: float | None = None
    misil_radio: float | None = None
    # Apertura del cono y duty cycle del CAÑÓN (P3-B: son parte del genoma
    # evolutivo del arma en la coevolución). None conserva los defaults del
    # arma, como el resto de los campos — no cambia el comportamiento de
    # ningún experimento existente que no los use.
    apertura_cono: float | None = None
    duty_cycle: float | None = None


@dataclass
class ExperimentConfig:
    formacion: str = "circular"
    cantidad: int = 30
    replicas: int = 50
    t_max_s: float = 60.0
    dt: float = 1.0 / 30.0
    semilla: int = 1234
    arma: WeaponPolicy = field(default_factory=WeaponPolicy)


def run_replica(cfg: ExperimentConfig, replica_idx: int) -> dict[str, Any]:
    """Ejecuta una réplica completa y devuelve su métrica primaria.

    Crea un generador NUEVO con ``nuevo_generador(cfg.semilla + replica_idx)``
    y se lo inyecta al motor: la réplica i es reproducible de forma aislada
    sin tocar (ni depender de) el generador global — así puede correr en
    paralelo con la simulación interactiva o con otras réplicas/experimentos.
    """
    gen = nuevo_generador(cfg.semilla + replica_idx)

    sim = SimulationEngine(swarm_size=cfg.cantidad, rng=gen)
    sim.configure_swarm(cfg.formacion, cfg.cantidad)

    disparado = False
    while sim.tiempo < cfg.t_max_s:
        if (
            not disparado
            and cfg.arma.tipo != "ninguna"
            and sim.tiempo >= cfg.arma.delay_s
        ):
            if cfg.arma.tipo == "canion":
                sim.fire(
                    potencia=cfg.arma.potencia,
                    direccion=cfg.arma.direccion,
                    apertura_cono=cfg.arma.apertura_cono,
                    duty_cycle=cfg.arma.duty_cycle,
                )
            else:
                sim.launch_missile(
                    x=sim.hpm.origen_x,
                    y=sim.hpm.origen_y,
                    angulo=cfg.arma.direccion,
                    potencia=cfg.arma.misil_potencia,
                    radio=cfg.arma.misil_radio,
                )
            disparado = True

        eventos_jamming, eventos_misil = sim._tick(cfg.dt)
        # Deuda técnica cerrada: antes se descartaba el retorno de ``_tick``,
        # así que una detonación de misil durante una réplica Monte Carlo
        # nunca llegaba a ``analytics.record_missile_detonation`` — las bajas
        # SÍ se contaban (HPMissile.detonar toca el estado del dron
        # directamente), pero el experimento quedaba sin diagnóstico por
        # disparo ni entrada en la curva de efectividad. Se procesan acá con
        # los mismos métodos que usa el bucle interactivo, para que un
        # experimento y una corrida en vivo dejen el mismo rastro en
        # ``analytics``.
        if eventos_misil:
            sim._process_missile_events(eventos_misil)
        if eventos_jamming:
            sim._process_jamming_events(eventos_jamming)

        conteo = sim.swarm.contar_por_estado()
        if conteo["neutralizado"] >= len(sim.swarm.drones):
            break

    conteo = sim.swarm.contar_por_estado()
    total = len(sim.swarm.drones)
    neutralizados = conteo["neutralizado"]
    return {
        "replica": replica_idx,
        "semilla": cfg.semilla + replica_idx,
        "neutralizados": neutralizados,
        "total": total,
        # MÉTRICA PRIMARIA de la réplica (P1-A): su fracción neutralizada. Es
        # la observación que entra a los intervalos del resumen.
        "fraccion": (neutralizados / total) if total > 0 else 0.0,
        "t_sim": round(sim.tiempo, 3),
        # MÉTRICA SECUNDARIA: ¿cayó el enjambre completo? Ensayo Bernoulli
        # legítimo a nivel réplica, pero vale 0 en casi todo el espacio de
        # operación — no confundir con "probabilidad de baja".
        "exito": neutralizados >= total and total > 0,
    }


@dataclass
class ExperimentRecord:
    id: str
    config: dict[str, Any]
    manifest: dict[str, Any]
    status: str = "corriendo"
    completadas: int = 0
    resultados: list[dict[str, Any]] = field(default_factory=list)
    resumen: dict[str, Any] | None = None
    error: str | None = None


class ExperimentManager:
    """Ejecuta experimentos en un hilo background y expone progreso/resultados."""

    def __init__(self) -> None:
        self._records: dict[str, ExperimentRecord] = {}
        self._lock = threading.Lock()

    def start(self, cfg: ExperimentConfig) -> str:
        exp_id = f"exp-{uuid.uuid4().hex[:8]}"
        record = ExperimentRecord(
            id=exp_id,
            config={
                "formacion": cfg.formacion,
                "cantidad": cfg.cantidad,
                "replicas": cfg.replicas,
                "t_max_s": cfg.t_max_s,
                "dt": cfg.dt,
                "semilla": cfg.semilla,
                "arma": {
                    "tipo": cfg.arma.tipo,
                    "delay_s": cfg.arma.delay_s,
                    "potencia": cfg.arma.potencia,
                    "direccion": cfg.arma.direccion,
                    "misil_potencia": cfg.arma.misil_potencia,
                    "misil_radio": cfg.arma.misil_radio,
                },
            },
            manifest=build_manifest({"experimento": {"id": exp_id}}),
        )
        with self._lock:
            self._records[exp_id] = record

        hilo = threading.Thread(
            target=self._run,
            args=(record, cfg),
            daemon=True,
            name=f"experiment-{exp_id}",
        )
        hilo.start()
        return exp_id

    def _run(self, record: ExperimentRecord, cfg: ExperimentConfig) -> None:
        try:
            for i in range(cfg.replicas):
                resultado = run_replica(cfg, i)
                with self._lock:
                    record.resultados.append(resultado)
                    record.completadas = i + 1

            with self._lock:
                record.resumen = self._summarize(record.resultados)
                record.status = "completado"
        except Exception as exc:  # noqa: BLE001 — reportar cualquier falla al cliente
            with self._lock:
                record.status = "error"
                record.error = f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _summarize(resultados: list[dict[str, Any]]) -> dict[str, Any]:
        """Agrega las réplicas en estadística con señal (P1-A).

        La unidad de muestreo es la réplica: cada una aporta UNA observación
        (su fracción neutralizada). Ver el docstring del módulo para por qué
        agregar por dron sería inválido.

        Todos los valores de salida son ``float``/``int`` nativos de Python, no
        escalares de numpy: el registro viaja por ``GET /api/experiments/{id}``
        y ``np.float64`` no serializa limpio a JSON en todos los caminos de
        FastAPI.
        """
        n = len(resultados)
        if n == 0:
            return {"replicas": 0}

        fracciones = [float(r["fraccion"]) for r in resultados]
        arr = np.asarray(fracciones, dtype=float)

        fraccion_media = float(arr.mean())
        # ddof=1: varianza muestral. Con n=1 numpy daría NaN, así que se acota.
        desv = float(arr.std(ddof=1)) if n > 1 else 0.0
        boot_lo, boot_hi = intervalo_bootstrap(arr)
        t_lo, t_hi = intervalo_t(arr)

        # Métrica secundaria: aniquilación total del enjambre. Acá la réplica
        # SÍ es un ensayo Bernoulli, así que Wilson es el intervalo correcto.
        exitos = sum(1 for r in resultados if r["exito"])
        aniq_lo, aniq_hi = wilson_interval(exitos, n)

        # Convergencia de la MÉTRICA PRIMARIA: media acumulada y semiancho de
        # su IC. El bootstrap se remuestrea en cada paso, así que se usa un
        # número reducido de remuestreos para que la serie no domine el coste
        # del experimento (la serie es diagnóstica, no reportable por sí sola).
        convergencia = []
        for i in range(1, n + 1):
            parcial = arr[:i]
            c_lo, c_hi = intervalo_bootstrap(parcial, remuestreos=1000)
            convergencia.append(
                {
                    "n": i,
                    "fraccion_media": round(float(parcial.mean()), 4),
                    "semiancho": round((c_hi - c_lo) / 2.0, 4),
                }
            )

        p5, p25, p50, p75, p95 = (
            float(v) for v in np.percentile(arr, [5, 25, 50, 75, 95])
        )

        return {
            "replicas": n,
            # ── MÉTRICA PRIMARIA ──
            "fraccion_media": round(fraccion_media, 4),
            "ic95_bootstrap": [round(boot_lo, 4), round(boot_hi, 4)],
            "ic95_t": [round(t_lo, 4), round(t_hi, 4)],
            "desviacion_estandar": round(desv, 4),
            # Coeficiente de variación σ/μ. Contraste contra el CV ≈ 39% que
            # reporta el paper a 30 m (docs/REFERENCIA_PAPER_2602.08477.md §3)
            # — criterio de aceptación de P1-B. None si la media es 0: el CV no
            # está definido ahí, y devolver 0 o inf sería mentir.
            "cv": round(desv / fraccion_media, 4) if fraccion_media > 0 else None,
            "percentiles": {
                "p5": round(p5, 4), "p25": round(p25, 4), "p50": round(p50, 4),
                "p75": round(p75, 4), "p95": round(p95, 4),
            },
            "convergencia": convergencia,
            "fracciones_por_replica": [round(f, 4) for f in fracciones],
            "neutralizados_por_replica": [int(r["neutralizados"]) for r in resultados],
            # ── MÉTRICA SECUNDARIA ──
            # Antes de P1-A esto se reportaba como "p_hat"/"ic95", o sea como
            # si fuera la probabilidad de baja. No lo es: es P(cae el enjambre
            # COMPLETO), que vale 0 en casi todo el espacio de operación.
            "aniquilacion_total": {
                "replicas_con_enjambre_aniquilado": exitos,
                "proporcion": round(exitos / n, 4),
                "ic95_wilson": [round(aniq_lo, 4), round(aniq_hi, 4)],
            },
        }

    def get(self, exp_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(exp_id)
            if record is None:
                return None
            return {
                "id": record.id,
                "status": record.status,
                "config": record.config,
                "completadas": record.completadas,
                "replicas": record.config["replicas"],
                "progress": record.completadas / max(1, record.config["replicas"]),
                "resumen": record.resumen,
                "resultados": record.resultados,
                "error": record.error,
                "manifest": record.manifest,
            }

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            ids = sorted(self._records.keys(), reverse=True)
        return [resumen for exp_id in ids if (resumen := self.get(exp_id)) is not None]


experiment_manager = ExperimentManager()


# ═══════════════════════════════════════════════════════════════════════════
# P1-B/P1-C · Monte Carlo de parámetros sobre un blanco único
# ═══════════════════════════════════════════════════════════════════════════
#
# Es el experimento del paper de referencia, y la prueba de aceptación de las
# dos fases: su salida se contrasta directamente contra 51.4% @ 20 m y
# 13.1% @ 40 m (Tabla de docs/REFERENCIA_PAPER_2602.08477.md §7) y contra el
# CV ≈ 39% @ 30 m que el paper reporta.
#
# Es deliberadamente SEPARADO del MC de enjambre (``run_replica``): el número
# publicado es la probabilidad de baja de UN blanco bajo incertidumbre de
# parámetros, no el resultado de una simulación de enjambre. Mezclar las dos
# cosas fue el defecto original — se reportaba una métrica de enjambre
# (aniquilación total) como si fuera la probabilidad de baja del paper.


def _factor_taper_haz(offset_deg: float, apertura_deg: float) -> float:
    """Atenuación en AMPLITUD por desapunte, coherente con ``friis_diagnostics``.

    El motor aplica ``cos²`` a la densidad de POTENCIA, así que en amplitud de
    campo el taper es ``cos¹`` (la raíz). Se replica exactamente eso acá para
    que el MC de blanco único y el motor de simulación no discrepen.
    (Que ese taper no sea un patrón de antena real es una limitación conocida
    y separada: es el ítem P2-C del checklist.)
    """
    semi = apertura_deg / 2.0
    if semi <= 0:
        return 1.0
    if abs(offset_deg) >= semi:
        return 0.0
    normalizado = abs(offset_deg) / semi
    return float(np.cos(normalizado * (np.pi / 2.0)))


def monte_carlo_blanco_unico(
    distancia_m: float,
    espec: "EspecificacionMC | None" = None,
    n: int = 10_000,
    seed: int = 8477,
    duty_cycle: float = 1.0,
    pulse_duration_ns: float | None = None,
    modelo_dano: str = "subsistemas",
) -> dict[str, Any]:
    """Monte Carlo de parámetros sobre un blanco a ``distancia_m``, en el eje.

    Reproduce el experimento del paper: por cada tirada se muestrean los ocho
    parámetros (potencia, diámetro de plato, eficiencia de apertura, error de
    apuntado, ángulo de polarización, longitud de cable y los umbrales de los
    cinco subsistemas), se propaga la cadena física completa y se evalúa la
    probabilidad de baja.

    Cadena por tirada:

        1. G = η·(πD/λ)²                       (plato real, P1-B)
        2. S = P_pico·G/(4πr²) · taper(θ_err)²  (Friis + desapunte)
        3. E_inc = √(S·377)
        4. E_inc ·= g(τ)                        (Wunsch-Bell, P1-E)
        5. E_acop = E_inc · k · f_pol           (acoplamiento, P1-C)
        6. P = OR-gate sobre los 5 subsistemas  (ecuación 7 del paper)

    SOBRE EL PASO 5 — ``√η_pol`` va CRUDO, sin normalizar. Historia, porque el
    error importa: una primera versión lo normalizaba (``√η_pol / E[√η_pol]``)
    para preservar la media del acoplamiento, y ``k`` se había ajustado contra
    los puntos publicados con un cálculo DETERMINISTA. Las dos decisiones
    juntas eran un error de método: ajustar un determinista a puntos que son
    salida de un Monte Carlo absorbe el sesgo del MC dentro del parámetro —
    exactamente el defecto §1.3 de la auditoría, cometido de nuevo. Se
    descartó. Ahora ``k`` se ajusta con el MC dentro del lazo y ``√η_pol`` se
    aplica crudo, que es lo coherente: el parámetro y su uso se calibran con el
    mismo procedimiento.

    ⚠ Ni así el modelo cierra: ver ``tests/test_parametros.py::
    TestModeloSubsistemasBloqueado`` y docs/FISICA_Y_MATEMATICA.md §3.6. El
    modelo de subsistemas está BLOQUEADO a falta de confirmar la cadena de
    acoplamiento contra el PDF del paper.

    Devuelve la probabilidad media de baja, su IC del 95% por bootstrap, el
    coeficiente de variación, percentiles y los diagnósticos de campo.
    """
    from src.engine.hpm_engine import (
        VACUUM_IMPEDANCE_OHM,
        antenna_gain_from_dish,
        calculate_neutralization_probability_friis,
        campo_acoplado_v_m,
        dish_beamwidth_deg,
        probabilidad_dano_sistema,
        pulse_coupling_factor,
    )
    from src.engine.parametros import EspecificacionMC as _Espec

    if espec is None:
        espec = _Espec.del_paper()

    gen = nuevo_generador(seed)
    muestras = [espec.muestrear(gen) for _ in range(n)]

    # √η_pol crudo: el acoplamiento y su parámetro k se calibran con el mismo
    # procedimiento (MC en el lazo), así que normalizar acá rompería esa
    # coherencia. Ver la nota del docstring sobre el error descartado.
    f_pol = np.array([m.eta_polarizacion**0.5 for m in muestras], dtype=float)

    g_tau = pulse_coupling_factor(pulse_duration_ns)
    duty = float(np.clip(duty_cycle, 1e-3, 1.0))
    r = max(float(distancia_m), 1e-6)

    probabilidades = np.empty(n, dtype=float)
    campos_incidentes = np.empty(n, dtype=float)

    for i, m in enumerate(muestras):
        ganancia = antenna_gain_from_dish(
            m.diametro_plato_m, m.eficiencia_apertura, config_mod.HPM_FREQUENCY_GHZ
        )
        apertura = dish_beamwidth_deg(m.diametro_plato_m, config_mod.HPM_FREQUENCY_GHZ)
        taper = _factor_taper_haz(m.error_apuntado_deg, apertura)

        potencia_pico_w = (m.potencia_kw / duty) * 1000.0
        densidad = (potencia_pico_w * ganancia) / (4.0 * np.pi * r**2) * taper**2
        e_inc = float(np.sqrt(max(densidad, 0.0) * VACUUM_IMPEDANCE_OHM)) * g_tau
        campos_incidentes[i] = e_inc

        if modelo_dano == "subsistemas":
            e_acop = campo_acoplado_v_m(e_inc) * float(f_pol[i])
            probabilidades[i] = probabilidad_dano_sistema(
                e_acop, m.umbrales_subsistemas
            )
        elif modelo_dano == "agregado":
            probabilidades[i] = calculate_neutralization_probability_friis(
                potencia_kw=m.potencia_kw,
                distancia=r,
                apertura_cono=apertura,
                angulo_offset=m.error_apuntado_deg,
                duty_cycle=duty,
                pulse_duration_ns=pulse_duration_ns,
            )
        else:
            raise ValueError(
                f"modelo_dano debe ser 'subsistemas' o 'agregado', no {modelo_dano!r}"
            )

    media = float(probabilidades.mean())
    desv = float(probabilidades.std(ddof=1)) if n > 1 else 0.0
    lo, hi = intervalo_bootstrap(probabilidades, remuestreos=2000, seed=seed + 1)
    p5, p50, p95 = (float(v) for v in np.percentile(probabilidades, [5, 50, 95]))

    return {
        "distancia_m": r,
        "tiradas": n,
        "modelo_dano": modelo_dano,
        "probabilidad_media": round(media, 6),
        "ic95_bootstrap": [round(lo, 6), round(hi, 6)],
        "desviacion_estandar": round(desv, 6),
        # CV de la probabilidad de baja entre tiradas. Contraste contra el
        # CV ≈ 39% @ 30 m que reporta el paper.
        "cv": round(desv / media, 6) if media > 0 else None,
        "percentiles": {"p5": round(p5, 6), "p50": round(p50, 6), "p95": round(p95, 6)},
        "campo_incidente_medio_v_m": round(float(campos_incidentes.mean()), 4),
        "campo_incidente_cv": (
            round(float(campos_incidentes.std(ddof=1) / campos_incidentes.mean()), 6)
            if n > 1 and campos_incidentes.mean() > 0 else None
        ),
        "espec": espec.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# P2-B · Curva dosis-respuesta recuperada de datos simulados (máxima
# verosimilitud), con IC por bootstrap y comparación contra la calibración
# ═══════════════════════════════════════════════════════════════════════════
#
# CIERRA EL LAZO: en vez de confiar en que el modelo hace lo que su
# configuración DICE que hace, se generan datos binarios (kill/no-kill) CON
# EL MOTOR REAL a varias distancias, se ajusta la curva dosis-respuesta que
# esos datos IMPLICAN, y se compara contra los parámetros configurados. Si un
# cambio futuro en la cadena física (acoplamiento, blindaje, duty cycle)
# desplaza silenciosamente la curva efectiva sin tocar
# HPM_LOGLOGISTIC_E50_V_M, esto lo detecta — a diferencia de
# tests/test_calibracion.py, que verifica el modelo TEÓRICO en dos puntos,
# no lo que el motor completo (con todos sus efectos encadenados) produce.
#
# ADAPTATIVO A HPM_LINK_FUNCTION: el ítem original (escrito antes de P1-F)
# pedía "E₅₀ y σ_E", el lenguaje de la logística. Con el default actual
# (log-logística), fijar la parametrización a logística estaría ajustando el
# modelo EQUIVOCADO. Se ajusta la familia que de verdad gobierna
# Drone.recibir_daño (HPM_LINK_FUNCTION), y se reporta además un "σ_E
# equivalente" (E₅₀/b, la misma conversión de P1-F) para no romper la letra
# del ítem.


def _campo_efectivo_v_m(
    distancia_m: float,
    potencia_kw: float,
    apertura_cono: float,
    cable_length_m: float,
    polarization: float,
) -> float:
    """Campo E que llega al blanco (post-acoplamiento), en el eje del haz."""
    from src.engine.hpm_engine import friis_diagnostics, susceptibility_coupling_factor

    diag = friis_diagnostics(potencia_kw, distancia_m, apertura_cono, 0.0)
    acoplamiento = susceptibility_coupling_factor(cable_length_m, polarization)
    return float(diag["campo_e_efectivo_v_m"] * acoplamiento)


def generar_datos_dosis_respuesta(
    distancias_m: list[float] | None = None,
    n_por_distancia: int = 300,
    seed: int = 2026,
    potencia_kw: float | None = None,
    apertura_cono: float | None = None,
    cable_length_m: float | None = None,
    polarization: float | None = None,
) -> tuple["np.ndarray", "np.ndarray"]:
    """
    Genera pares (campo E efectivo, kill) corriendo ``Drone.recibir_daño``
    —el motor real, no una fórmula reescrita— a varias distancias.

    Huella de susceptibilidad FIJADA (cable resonante a la frecuencia del
    arma, polarización óptima ⇒ acoplamiento = 1 por defecto): aísla la
    varianza de la SIGMOIDE (lo que se quiere recuperar) de la varianza de
    la huella de P2-04 (una segunda fuente de dispersión no controlada) —
    mismo criterio que el caso de verdad conocida de P1-A
    (``TestEstimadorTieneSenalEnElMotorReal``).

    Devuelve ``(campos, kills)`` como arrays de igual longitud
    (``len(distancias_m) · n_por_distancia``), listos para
    ``ajustar_dosis_respuesta``.
    """
    from src.config import HPM_CONE_APERTURE, HPM_DEFAULT_POWER, HPM_FREQUENCY_GHZ
    from src.models.drone import Drone

    if distancias_m is None:
        # Rango elegido para cubrir de ~86% a ~2% de probabilidad con la
        # calibración por defecto — ni saturado ni degenerado en ningún
        # extremo, lo que evita separación perfecta en el ajuste logístico.
        distancias_m = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0, 80.0]
    potencia = HPM_DEFAULT_POWER if potencia_kw is None else potencia_kw
    apertura = HPM_CONE_APERTURE if apertura_cono is None else apertura_cono
    cable = (
        (299_792_458.0 / (2.0 * HPM_FREQUENCY_GHZ * 1e9))
        if cable_length_m is None else cable_length_m
    )
    pol = 1.0 if polarization is None else polarization

    gen = nuevo_generador(seed)
    campos: list[float] = []
    kills: list[float] = []
    for distancia in distancias_m:
        campo = _campo_efectivo_v_m(distancia, potencia, apertura, cable, pol)
        for _ in range(n_por_distancia):
            drone = Drone(0, x=0.0, y=0.0, cable_length_m=cable, polarization=pol, rng=gen)
            kill = drone.recibir_daño(
                potencia=potencia, distancia=distancia,
                angulo_offset=0.0, apertura_cono=apertura,
            )
            campos.append(campo)
            kills.append(1.0 if kill else 0.0)

    return np.array(campos, dtype=float), np.array(kills, dtype=float)


def _logistic_irls(
    x: "np.ndarray", y: "np.ndarray", iteraciones: int = 100, tol: float = 1e-10,
    ridge: float = 1e-8,
) -> "np.ndarray":
    """
    Máxima verosimilitud de una regresión logística ``P = 1/(1+exp(-(β₀+β₁x)))``
    por **Newton-Raphson / IRLS** (Iteratively Reweighted Least Squares).

    Por qué esto ES el ajuste de la curva dosis-respuesta, no una aproximación:
    la log-verosimilitud de una logística en cualquier variable ``x`` es
    **cóncava**, así que Newton-Raphson converge al óptimo global en pocas
    iteraciones (verificado: 6 en un caso de prueba con 3000 puntos) — no
    hace falta ``scipy.optimize`` (no está en ``requirements.txt``, ver
    docs/AUDITORIA_CHECKLIST.md §4.6) ni un optimizador genérico.

    La reparametrización que conecta esto con las dos familias de enlace del
    proyecto:
    - **log-logística** (``P = 1/(1+(E₅₀/E)^b)``): es EXACTAMENTE una
      logística en ``x = ln(E)``, con ``β₁ = b`` y ``E₅₀ = exp(-β₀/β₁)``.
    - **logística** (``P = 1/(1+exp(-k(E-E₀)))``): es una logística en
      ``x = E`` directo, con ``β₁ = k`` y ``E₀ = -β₀/β₁``.

    ``ridge`` añade una regularización mínima a la Hessiana — sin ella, una
    muestra bootstrap con separación perfecta (posible con pocos puntos)
    puede dar una Hessiana casi singular; con ``ridge=1e-8`` el efecto sobre
    un ajuste bien condicionado es despreciable, y evita que
    ``np.linalg.solve`` lance ``LinAlgError`` en el caso raro.
    """
    X = np.column_stack([np.ones_like(x), x])
    beta = np.zeros(2)
    for _ in range(iteraciones):
        eta = np.clip(X @ beta, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1.0 - p), 1e-10, None)
        hessiana = X.T @ (X * w[:, None]) + ridge * np.eye(2)
        gradiente = X.T @ (y - p)
        delta = np.linalg.solve(hessiana, gradiente)
        beta = beta + delta
        if np.max(np.abs(delta)) < tol:
            break
    return beta


def _ajustar_una_vez(campos: "np.ndarray", kills: "np.ndarray", link: str) -> tuple[float, float, float]:
    """Un ajuste puntual. Devuelve ``(e50_o_e0, b_o_k, sigma_equivalente)``."""
    if link == "log_logistica":
        x = np.log(np.clip(campos, 1e-9, None))
        beta = _logistic_irls(x, kills)
        b = float(beta[1])
        e50 = float(np.exp(-beta[0] / beta[1])) if b != 0 else float("nan")
        sigma_equivalente = e50 / b if b != 0 else float("nan")
        return e50, b, sigma_equivalente

    beta = _logistic_irls(campos, kills)
    k = float(beta[1])
    e0 = float(-beta[0] / beta[1]) if k != 0 else float("nan")
    sigma = 1.0 / k if k != 0 else float("nan")
    return e0, k, sigma


def ajustar_dosis_respuesta(
    campos_v_m: "np.ndarray",
    kills: "np.ndarray",
    n_bootstrap: int = 1000,
    seed: int = 2026,
) -> dict[str, Any]:
    """
    Ajusta la curva dosis-respuesta ACTIVA (según ``HPM_LINK_FUNCTION``) por
    máxima verosimilitud, con IC del 95% por **bootstrap de percentiles**
    sobre las observaciones — mismo método y misma justificación que P1-A
    (``intervalo_bootstrap``): sin supuestos de normalidad, apropiado para un
    ajuste con pocos puntos de datos en los extremos.
    """
    link = config_mod.HPM_LINK_FUNCTION
    campos = np.asarray(campos_v_m, dtype=float)
    y = np.asarray(kills, dtype=float)
    n = len(campos)

    e50_hat, b_hat, sigma_hat = _ajustar_una_vez(campos, y, link)

    gen = nuevo_generador(seed)
    e50_boot: list[float] = []
    b_boot: list[float] = []
    sigma_boot: list[float] = []
    for _ in range(n_bootstrap):
        idx = gen.integers(0, n, size=n)
        try:
            e50_i, b_i, sigma_i = _ajustar_una_vez(campos[idx], y[idx], link)
        except np.linalg.LinAlgError:
            continue
        if np.isfinite(e50_i) and np.isfinite(b_i):
            e50_boot.append(e50_i)
            b_boot.append(b_i)
            sigma_boot.append(sigma_i)

    def _ic95(valores: list[float]) -> list[float]:
        if len(valores) < 10:
            return [float("nan"), float("nan")]
        lo, hi = np.percentile(valores, [2.5, 97.5])
        return [round(float(lo), 4), round(float(hi), 4)]

    return {
        "link_function": link,
        "n_observaciones": n,
        "n_bootstrap_exitosos": len(e50_boot),
        "e50_v_m": round(e50_hat, 4),
        "ic95_e50_v_m": _ic95(e50_boot),
        "parametro_forma": round(b_hat, 4),
        "ic95_parametro_forma": _ic95(b_boot),
        # "σ_E equivalente" (E₅₀/parámetro_forma): con link "logistica" ES
        # σ_E (1/k, la definición exacta). Con "log_logistica" es la
        # conversión de P1-F (b=E₅₀/σ), reportada para no romper la letra
        # del ítem original — NO es el σ_E de una logística real, que esta
        # familia no tiene.
        "sigma_e_equivalente_v_m": round(sigma_hat, 4) if np.isfinite(sigma_hat) else None,
        "ic95_sigma_e_equivalente": _ic95(sigma_boot),
    }


def comparar_contra_calibracion(ajuste: dict[str, Any]) -> dict[str, Any]:
    """
    ¿La curva que el simulador IMPLICA (recuperada de datos simulados con el
    motor real) coincide con la que se le CONFIGURÓ? Compara el ajuste
    contra los parámetros activos de ``src/config.py`` para la familia de
    enlace vigente.
    """
    link = ajuste["link_function"]
    if link == "log_logistica":
        e50_config = config_mod.HPM_LOGLOGISTIC_E50_V_M
        forma_config = config_mod.HPM_LOGLOGISTIC_B
    else:
        e50_config = config_mod.HPM_E_THRESHOLD_V_M
        forma_config = config_mod.HPM_SIGMOID_STEEPNESS

    lo_e, hi_e = ajuste["ic95_e50_v_m"]
    lo_b, hi_b = ajuste["ic95_parametro_forma"]
    e50_dentro = (
        np.isfinite(lo_e) and np.isfinite(hi_e) and lo_e <= e50_config <= hi_e
    )
    forma_dentro = (
        np.isfinite(lo_b) and np.isfinite(hi_b) and lo_b <= forma_config <= hi_b
    )

    return {
        "link_function": link,
        "e50_configurado": e50_config,
        "parametro_forma_configurado": forma_config,
        "e50_dentro_del_ic": bool(e50_dentro),
        "parametro_forma_dentro_del_ic": bool(forma_dentro),
        "recupera_la_calibracion": bool(e50_dentro and forma_dentro),
    }


def experimento_dosis_respuesta(
    distancias_m: list[float] | None = None,
    n_por_distancia: int = 300,
    n_bootstrap: int = 1000,
    seed: int = 2026,
) -> dict[str, Any]:
    """Genera datos, ajusta, y compara — en un solo paso, para el endpoint."""
    campos, kills = generar_datos_dosis_respuesta(
        distancias_m=distancias_m, n_por_distancia=n_por_distancia, seed=seed,
    )
    ajuste = ajustar_dosis_respuesta(campos, kills, n_bootstrap=n_bootstrap, seed=seed + 1)
    comparacion = comparar_contra_calibracion(ajuste)
    return {
        "distancias_m": distancias_m or [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0, 80.0],
        "n_por_distancia": n_por_distancia,
        "ajuste": ajuste,
        "comparacion": comparacion,
    }
