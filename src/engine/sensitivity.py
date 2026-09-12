"""Análisis de sensibilidad global del modelo de daño (P2-A).

POR QUÉ ESTE MÓDULO ES EL SALTO CIENTÍFICO DEL ROADMAP
======================================================
El simulador tiene ~20 parámetros libres y **dos** calibrados contra datos
publicados. Sin descomposición de varianza no se puede responder la pregunta
que decide si un resultado es publicable o no:

    ¿esta conclusión depende de un parámetro calibrado, o de uno inventado?

Con índices de Sobol la respuesta es cuantitativa: *"el alcance efectivo está
dominado por E₅₀ (S₁ = 0.4) y la polarización (0.3); el quiebre de régimen de
pulso aporta < 0.02"*. Eso convierte cada objeción sobre un número mágico en un
dato, y es la defensa contra la crítica obvia al proyecto entero: *"ajustaste
veinte parámetros a dos puntos de datos"*.

El framework de referencia hace exactamente esto (arXiv:2602.08477 corre 10.000
tiradas sobre ocho parámetros y reporta el coeficiente de variación), y hay un
paper hermano dedicado al tema (arXiv:2510.16495, *"…A Probabilistic Antenna
Propagation Framework with Sensitivity Analysis"*).

PRECEDENTE EN ESTE PROYECTO
===========================
La atribución de varianza que diagnosticó el bloqueo de P1-C (apagar una
distribución a la vez y medir el CV, ver docs/FISICA_Y_MATEMATICA.md §3.6) es un
prototipo manual de esto. Funcionó —localizó la polarización como el 55 % del
CV— pero tiene dos límites que este módulo resuelve: (a) "apagar una a la vez"
mide una diferencia de varianza, no una contribución a la varianza, y no suma 1;
(b) no distingue efecto principal de interacción.

DOS MÉTODOS, EN ORDEN DE COSTE
==============================
1. **Screening de Morris** (efectos elementales). Coste ``r·(k+1)``
   evaluaciones. Da ``μ*`` (magnitud media del efecto) y ``σ`` (dispersión del
   efecto, que delata interacciones o no-linealidad). Barato: sirve para
   descartar los parámetros irrelevantes antes de pagar Sobol.
2. **Índices de Sobol** (descomposición de varianza). Coste ``N·(k+2)`` con el
   estimador de Saltelli. Da ``S₁`` (efecto principal: qué fracción de la
   varianza explica ese parámetro solo) y ``S_T`` (efecto total: incluye todas
   sus interacciones). ``S_T − S₁`` es la interacción.

SIN DEPENDENCIAS NUEVAS
=======================
Todo en numpy. En particular **no** se usa ``scipy.stats.qmc`` para secuencias
de Sobol: ``scipy`` está en el venv pero no en ``requirements.txt``, así que el
entorno no es reproducible desde él (ver docs/AUDITORIA_CHECKLIST.md §4.6). Se
usa muestreo pseudoaleatorio simple. **Consecuencia declarada**: el estimador
converge como ``1/√N`` en vez de casi ``1/N``, o sea que hace falta un ``N``
mayor para el mismo error. Es un coste de cómputo, no un sesgo — los
estimadores de Saltelli son consistentes con muestreo aleatorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from src import config as config_mod
from src.engine.hpm_engine import (
    VACUUM_IMPEDANCE_OHM,
    antenna_gain_from_dish,
    campo_acoplado_v_m,
    dish_beamwidth_deg,
    probabilidad_dano_sistema,
    pulse_coupling_factor,
)
from src.utils.reproducibilidad import nuevo_generador


# ═══════════════════════════════════════════════════════════════════════════
# Espacio de parámetros
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ParametroSensibilidad:
    """Un parámetro del análisis, con su hiper-rectángulo de exploración.

    Morris y Sobol trabajan sobre un hiper-rectángulo, no sobre distribuciones
    arbitrarias. Para los parámetros que el paper especifica como normales se
    usa ``μ ± 3σ`` (cubre el 99.7 %); para los uniformes, su rango literal. Esa
    conversión es una decisión de modelado y está declarada acá: los índices
    resultantes describen la sensibilidad **sobre el rango explorado**, y
    cambiar el rango cambia los índices. No es un defecto del método — es lo
    que significa "sensibilidad global": global respecto a un dominio, que hay
    que declarar.
    """

    nombre: str
    lo: float
    hi: float
    # Qué representa, para el informe legible.
    descripcion: str = ""
    # True si el valor está calibrado contra datos publicados. Es la columna
    # que hace útil el informe: un parámetro dominante y NO calibrado es una
    # amenaza a la validez; uno dominante y calibrado es una fortaleza.
    calibrado: bool = False

    def escalar(self, u: float) -> float:
        """Mapea u ∈ [0,1] al rango del parámetro."""
        return self.lo + (self.hi - self.lo) * u


def espacio_parametros_dano() -> list[ParametroSensibilidad]:
    """Los parámetros que gobiernan la probabilidad de baja de un blanco.

    Rangos derivados de la Tabla 2 de arXiv:2602.08477 (ver
    docs/REFERENCIA_PAPER_2602.08477.md §3) más los parámetros propios del
    proyecto que no vienen del paper — que son justamente los que interesa
    vigilar.
    """
    subs = config_mod.HPM_SUBSISTEMAS
    params = [
        ParametroSensibilidad(
            "potencia_kw", 25.0 - 3 * 1.25, 25.0 + 3 * 1.25,
            "Potencia promedio del arma (kW). Paper: Normal(25, 1.25).",
            calibrado=True,
        ),
        ParametroSensibilidad(
            "diametro_plato_m", 0.60 - 3 * 0.005, 0.60 + 3 * 0.005,
            "Diámetro del plato (m). Paper: Normal(0.60, 0.005).",
            calibrado=True,
        ),
        ParametroSensibilidad(
            "eficiencia_apertura", 0.50, 0.60,
            "Eficiencia de apertura del plato. Paper: Uniforme[0.50, 0.60].",
            calibrado=True,
        ),
        ParametroSensibilidad(
            "error_apuntado_deg", 0.0, 3.0,
            "Desapunte (grados). Paper: Rayleigh(1°); se explora hasta 3σ.",
            calibrado=True,
        ),
        ParametroSensibilidad(
            "angulo_polarizacion_rad", 0.0, np.pi,
            "Ángulo de polarización (rad) → η_pol = cos²φ. Paper: Uniforme[0, π].",
            calibrado=True,
        ),
        ParametroSensibilidad(
            "longitud_cable_m", 0.05, 0.25,
            "Longitud del cableado interno (m). Paper: Uniforme[5, 25] cm. "
            "⚠ ACTUALMENTE NO TIENE CAMINO AL MODELO: el realce por resonancia "
            "(1+(Q-1)exp(-(L-λ₀/2)²/2σ_L²)) se omitió a propósito mientras P1-C "
            "está bloqueado (docs/FISICA_Y_MATEMATICA.md §3.6). Se deja en el "
            "espacio a propósito: su S₁ = S_T = 0 EXACTO es la detección "
            "automática de esa omisión, y el test que lo fija falla el día que "
            "alguien conecte la resonancia — recordando que hay que reanalizar.",
            calibrado=True,
        ),
        # ── Parámetros propios del proyecto, NO del paper ──
        ParametroSensibilidad(
            "coupling_field_efficiency",
            0.5 * config_mod.HPM_COUPLING_FIELD_EFFICIENCY,
            1.5 * config_mod.HPM_COUPLING_FIELD_EFFICIENCY,
            "Eficiencia de acoplamiento en campo. PROVISIONAL y no validada "
            "(P1-C bloqueado): se explora ±50 % del valor ajustado.",
            calibrado=False,
        ),
        ParametroSensibilidad(
            "pulse_duration_ns", 20.0, 5000.0,
            "Duración del pulso (ns) → g(τ) de Wunsch-Bell. Rango que cruza el "
            "quiebre adiabático/difusión (100 ns) sin llegar al estacionario.",
            calibrado=False,
        ),
    ]
    # Los cinco umbrales, ±15 % del nominal (como los muestrea el paper).
    for nombre, (e50, _sigma) in subs.items():
        params.append(
            ParametroSensibilidad(
                f"e50_{nombre}", 0.85 * e50, 1.15 * e50,
                f"Umbral de daño E₅₀ del subsistema {nombre} (V/m). "
                f"Nominal {e50}, paper: Normal(±15 %).",
                calibrado=True,
            )
        )
    return params


# ═══════════════════════════════════════════════════════════════════════════
# Función de modelo
# ═══════════════════════════════════════════════════════════════════════════


def probabilidad_baja_desde_vector(
    valores: dict[str, float],
    distancia_m: float,
    duty_cycle: float = 1.0,
) -> float:
    """Probabilidad de baja de un blanco, como función escalar de los parámetros.

    Es la misma cadena física que ``experiments.monte_carlo_blanco_unico``,
    reexpresada como función pura de un vector de parámetros — que es lo que
    Morris y Sobol necesitan. Mantenerlas coherentes importa: si divergen, los
    índices describirían un modelo que no es el que produce los resultados.

        G = η(πD/λ)²  →  S = P_pico·G/(4πr²)·taper²  →  E = √(377·S)·g(τ)
        →  E_acop = E·k·√η_pol  →  P = OR-gate(5 subsistemas)
    """
    f_ghz = config_mod.HPM_FREQUENCY_GHZ
    d = valores["diametro_plato_m"]
    ganancia = antenna_gain_from_dish(d, valores["eficiencia_apertura"], f_ghz)
    apertura = dish_beamwidth_deg(d, f_ghz)

    # Taper por desapunte: cos² sobre densidad de potencia ⇒ cos¹ en amplitud.
    semi = apertura / 2.0
    offset = abs(valores["error_apuntado_deg"])
    taper = 0.0 if (semi <= 0 or offset >= semi) else float(
        np.cos((offset / semi) * (np.pi / 2.0))
    )

    duty = float(np.clip(duty_cycle, 1e-3, 1.0))
    r = max(float(distancia_m), 1e-6)
    potencia_pico_w = (valores["potencia_kw"] / duty) * 1000.0
    densidad = (potencia_pico_w * ganancia) / (4.0 * np.pi * r**2) * taper**2

    g_tau = pulse_coupling_factor(valores["pulse_duration_ns"])
    e_inc = float(np.sqrt(max(densidad, 0.0) * VACUUM_IMPEDANCE_OHM)) * g_tau

    eta_pol = max(
        config_mod.DRONE_POLARIZATION_MIN_ETA,
        float(np.cos(valores["angulo_polarizacion_rad"]) ** 2),
    )
    e_acop = campo_acoplado_v_m(
        e_inc, valores["coupling_field_efficiency"]
    ) * eta_pol**0.5

    umbrales = {
        nombre: (valores[f"e50_{nombre}"], sigma)
        for nombre, (_e50, sigma) in config_mod.HPM_SUBSISTEMAS.items()
    }
    return probabilidad_dano_sistema(e_acop, umbrales)


def _constructor_modelo(
    distancia_m: float,
    params: Sequence[ParametroSensibilidad],
    duty_cycle: float = 1.0,
) -> Callable[[np.ndarray], np.ndarray]:
    """Envuelve el modelo como ``f(U) -> y`` con ``U`` en el cubo unitario."""
    nombres = [p.nombre for p in params]

    def f(U: np.ndarray) -> np.ndarray:
        U = np.atleast_2d(U)
        y = np.empty(U.shape[0], dtype=float)
        for i, fila in enumerate(U):
            valores = {
                nombre: params[j].escalar(float(fila[j]))
                for j, nombre in enumerate(nombres)
            }
            y[i] = probabilidad_baja_desde_vector(valores, distancia_m, duty_cycle)
        return y

    return f


# ═══════════════════════════════════════════════════════════════════════════
# Screening de Morris (efectos elementales)
# ═══════════════════════════════════════════════════════════════════════════


def _trayectorias_morris(
    k: int, r: int, niveles: int, gen: np.random.Generator
) -> np.ndarray:
    """Construye ``r`` trayectorias de Morris en el cubo unitario de dimensión ``k``.

    Método de trayectorias de Morris (1991) con la mejora de Campolongo: cada
    trayectoria tiene ``k+1`` puntos y entre puntos consecutivos **cambia un
    solo parámetro**, en un salto fijo ``Δ = niveles / (2·(niveles−1))``. Ese
    salto es el que garantiza que los efectos elementales sean comparables
    entre parámetros.

    Devuelve un array ``(r·(k+1), k)``.
    """
    delta = niveles / (2.0 * (niveles - 1))
    # Rejilla de partida: sólo la mitad inferior de los niveles, para que
    # sumar delta nunca salga del cubo.
    posibles = np.arange(0, niveles // 2) / (niveles - 1)

    puntos = []
    for _ in range(r):
        base = gen.choice(posibles, size=k)
        orden = gen.permutation(k)
        # Signo aleatorio: el salto puede ser hacia arriba o hacia abajo.
        signos = gen.choice([1.0, -1.0], size=k)
        actual = base.astype(float).copy()
        # Si el signo es negativo hay que arrancar desde arriba para no salir.
        for j in range(k):
            if signos[j] < 0:
                actual[j] = min(1.0, actual[j] + delta)
        puntos.append(actual.copy())
        for idx in orden:
            actual[idx] = float(np.clip(actual[idx] + signos[idx] * delta, 0.0, 1.0))
            puntos.append(actual.copy())
    return np.array(puntos, dtype=float)


def screening_morris(
    distancia_m: float,
    params: Sequence[ParametroSensibilidad] | None = None,
    r: int = 40,
    niveles: int = 8,
    seed: int = 2026,
    duty_cycle: float = 1.0,
) -> dict[str, Any]:
    """Screening de Morris: ``μ*`` y ``σ`` de los efectos elementales.

    - ``mu_estrella``: media de los VALORES ABSOLUTOS de los efectos
      elementales. Se usa el valor absoluto (Campolongo et al. 2007) porque la
      media con signo se cancela cuando el efecto cambia de dirección en
      distintas zonas del espacio — un parámetro importante pero no monótono
      parecería irrelevante.
    - ``sigma``: desviación estándar de los efectos. Un ``σ`` grande respecto a
      ``μ*`` **delata interacciones o fuerte no-linealidad**: el efecto de ese
      parámetro depende de dónde estén los demás.

    Coste: ``r·(k+1)`` evaluaciones. Es el método barato: sirve para descartar
    parámetros irrelevantes antes de pagar Sobol.
    """
    params = list(params if params is not None else espacio_parametros_dano())
    k = len(params)
    gen = nuevo_generador(seed)
    f = _constructor_modelo(distancia_m, params, duty_cycle)

    U = _trayectorias_morris(k, r, niveles, gen)
    y = f(U)

    delta = niveles / (2.0 * (niveles - 1))
    efectos: list[list[float]] = [[] for _ in range(k)]
    por_trayectoria = k + 1
    for t in range(r):
        base = t * por_trayectoria
        for paso in range(k):
            i0, i1 = base + paso, base + paso + 1
            cambio = U[i1] - U[i0]
            idx = int(np.argmax(np.abs(cambio)))
            salto = float(cambio[idx])
            if abs(salto) < 1e-12:
                continue
            efectos[idx].append(float((y[i1] - y[i0]) / salto * delta))

    resultados = []
    for j, p in enumerate(params):
        e = np.array(efectos[j], dtype=float)
        if e.size == 0:
            mu_est, sigma = 0.0, 0.0
        else:
            mu_est = float(np.abs(e).mean())
            sigma = float(e.std(ddof=1)) if e.size > 1 else 0.0
        resultados.append(
            {
                "nombre": p.nombre,
                "mu_estrella": round(mu_est, 6),
                "sigma": round(sigma, 6),
                "calibrado": p.calibrado,
                "muestras": int(e.size),
            }
        )
    resultados.sort(key=lambda d: -d["mu_estrella"])

    return {
        "metodo": "morris",
        "distancia_m": float(distancia_m),
        "evaluaciones": int(U.shape[0]),
        "trayectorias": r,
        "niveles": niveles,
        "salida_media": round(float(y.mean()), 6),
        "parametros": resultados,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Índices de Sobol (descomposición de varianza)
# ═══════════════════════════════════════════════════════════════════════════


def indices_sobol(
    distancia_m: float,
    params: Sequence[ParametroSensibilidad] | None = None,
    n_base: int = 1024,
    seed: int = 2026,
    duty_cycle: float = 1.0,
    modelo: Callable[[np.ndarray], np.ndarray] | None = None,
    k_dim: int | None = None,
) -> dict[str, Any]:
    """Índices de Sobol de primer orden (``S₁``) y total (``S_T``).

    Estimadores de **Saltelli et al. (2010)**, que son los de menor varianza
    entre los de coste ``N(k+2)``:

        S₁ᵢ = (1/N) Σ  f_B · (f_ABᵢ − f_A)  /  V
        S_Tᵢ = (1/2N) Σ (f_A − f_ABᵢ)²      /  V

    donde ``A`` y ``B`` son dos matrices independientes ``N×k`` en el cubo
    unitario, ``ABᵢ`` es ``A`` con su columna ``i`` reemplazada por la de ``B``,
    y ``V`` es la varianza de la salida estimada sobre ``A`` y ``B`` juntas.

    Interpretación:
    - ``S₁ᵢ``: fracción de la varianza que explica el parámetro ``i`` **solo**.
    - ``S_Tᵢ``: incluye todas sus interacciones. Siempre ``S_Tᵢ ≥ S₁ᵢ``.
    - ``S_Tᵢ − S₁ᵢ``: cuánto del efecto de ``i`` pasa por interacción con otros.
    - ``Σ S₁ᵢ`` cercano a 1 ⇒ modelo casi aditivo; muy por debajo de 1 ⇒ las
      interacciones importan.

    Nota sobre los estimadores: ``S₁`` puede salir **ligeramente negativo** para
    un parámetro genuinamente irrelevante. No es un error: es ruido de muestreo
    alrededor de cero, y recortarlo a 0 sesgaría el resultado hacia arriba. Se
    devuelve el valor crudo y se declara acá.

    ``modelo`` y ``k_dim`` permiten inyectar una función arbitraria (se usan
    para validar el estimador contra funciones de test con índices analíticos
    conocidos, ver ``tests/test_sensibilidad.py``).
    """
    if modelo is None:
        params = list(params if params is not None else espacio_parametros_dano())
        k = len(params)
        f = _constructor_modelo(distancia_m, params, duty_cycle)
        nombres = [p.nombre for p in params]
        calibrados = [p.calibrado for p in params]
    else:
        if k_dim is None:
            raise ValueError("al inyectar `modelo` hay que dar `k_dim`")
        k = int(k_dim)
        f = modelo
        params = None
        nombres = [f"x{j + 1}" for j in range(k)]
        calibrados = [False] * k

    gen = nuevo_generador(seed)
    A = gen.random((n_base, k))
    B = gen.random((n_base, k))

    y_A = f(A)
    y_B = f(B)

    # Varianza estimada sobre las dos muestras juntas (2N puntos).
    combinada = np.concatenate([y_A, y_B])
    V = float(combinada.var(ddof=1))

    resultados = []
    for j in range(k):
        AB = A.copy()
        AB[:, j] = B[:, j]
        y_AB = f(AB)

        if V <= 1e-15:
            s1 = st = 0.0
        else:
            s1 = float(np.mean(y_B * (y_AB - y_A)) / V)
            st = float(np.mean((y_A - y_AB) ** 2) / (2.0 * V))

        resultados.append(
            {
                "nombre": nombres[j],
                "s1": round(s1, 6),
                "st": round(st, 6),
                "interaccion": round(st - s1, 6),
                "calibrado": calibrados[j],
            }
        )

    resultados.sort(key=lambda d: -d["st"])
    suma_s1 = float(sum(d["s1"] for d in resultados))

    return {
        "metodo": "sobol_saltelli",
        "distancia_m": float(distancia_m),
        "n_base": int(n_base),
        # Coste real del estimador: A, B y las k matrices AB_i.
        "evaluaciones": int(n_base * (k + 2)),
        "varianza_salida": round(V, 9),
        "salida_media": round(float(combinada.mean()), 6),
        "suma_s1": round(suma_s1, 6),
        # Σ S₁ ≈ 1 ⇒ modelo aditivo. Bastante menor ⇒ interacciones relevantes.
        "fraccion_interaccion": round(max(0.0, 1.0 - suma_s1), 6),
        "parametros": resultados,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Informe legible
# ═══════════════════════════════════════════════════════════════════════════


def informe_sensibilidad(
    distancia_m: float = 30.0,
    n_base: int = 512,
    r_morris: int = 40,
    seed: int = 2026,
) -> dict[str, Any]:
    """Corre Morris y Sobol y arma el informe con la lectura que importa.

    La clave del informe es ``amenazas_a_la_validez``: los parámetros que
    dominan la varianza **y no están calibrados** contra datos publicados. Un
    parámetro dominante y calibrado es una fortaleza del modelo; uno dominante y
    no calibrado es una conclusión que en realidad depende de una elección
    arbitraria, y hay que decirlo antes de publicar cualquier resultado que se
    apoye en ella.
    """
    morris = screening_morris(distancia_m, r=r_morris, seed=seed)
    sobol = indices_sobol(distancia_m, n_base=n_base, seed=seed)

    por_nombre = {d["nombre"]: d for d in sobol["parametros"]}
    amenazas = [
        {
            "nombre": d["nombre"],
            "st": d["st"],
            "s1": d["s1"],
        }
        for d in sobol["parametros"]
        if not d["calibrado"] and d["st"] >= 0.05
    ]

    dominantes = [d["nombre"] for d in sobol["parametros"][:3]]

    return {
        "distancia_m": float(distancia_m),
        "morris": morris,
        "sobol": sobol,
        "dominantes": dominantes,
        "amenazas_a_la_validez": amenazas,
        "modelo_casi_aditivo": bool(sobol["suma_s1"] > 0.9),
        "coherencia_morris_sobol": _coherencia(morris, por_nombre),
    }


def _coherencia(morris: dict[str, Any], sobol_por_nombre: dict[str, Any]) -> dict[str, Any]:
    """¿Coinciden los dos métodos en el ranking de los tres dominantes?

    Morris y Sobol miden cosas distintas (magnitud media del efecto vs fracción
    de varianza explicada), así que no tienen por qué dar el mismo orden — pero
    si discrepan en QUIÉN domina, uno de los dos está mal muestreado y el
    informe no es de fiar. Es un chequeo de sanidad interno, no un resultado.
    """
    top_morris = [d["nombre"] for d in morris["parametros"][:3]]
    orden_sobol = sorted(sobol_por_nombre.values(), key=lambda d: -d["st"])
    top_sobol = [d["nombre"] for d in orden_sobol[:3]]
    comunes = len(set(top_morris) & set(top_sobol))
    return {
        "top3_morris": top_morris,
        "top3_sobol": top_sobol,
        "coincidencias_en_top3": comunes,
        "coherente": comunes >= 2,
    }
