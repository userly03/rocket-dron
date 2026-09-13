"""Asignación arma-blanco optimizada (Weapon-Target Assignment, P3-A).

Capa de DECISIÓN: dados los tracks detectados (P2-G, no la posición
omnisciente) y el presupuesto disponible (munición de misiles, energía del
cañón — P2-F), calcula qué disparo apunta a qué cluster de drones para
maximizar las bajas esperadas totales.

Es el primer ítem del roadmap que produce una DECISIÓN, no solo una
predicción o un diagnóstico.

═══════════════════════════════════════════════════════════════════════════
POR QUÉ EXISTE ESTE ÍTEM AHORA Y NO ANTES
═══════════════════════════════════════════════════════════════════════════
Depende de dos cosas que no existían hasta hace poco:

- **P2-F (presupuesto energético)**: sin él, el cañón dispara infinito y
  gratis, así que la asignación óptima siempre es "disparale a todo" — el
  problema es trivial y no hay nada que optimizar.
- **P2-G, Paso 1 (TrackManager)**: opera sobre TRACKS (posición ESTIMADA),
  no sobre la posición real de "cualquier dron con drone.detectado=True".
  Sin tracks, "optimizar sobre lo detectado" seguiría siendo omnisciente.

═══════════════════════════════════════════════════════════════════════════
EL SESGO DE JENSEN, Y CÓMO SE EVITA
═══════════════════════════════════════════════════════════════════════════
La probabilidad de baja de un dron depende de su huella de susceptibilidad
(``cable_length_m``, ``polarization`` — P2-04), que un track de radar NO
conoce (no es una cantidad observable por radar, es propiedad interna del
dron). La forma INCORRECTA de estimar bajas esperadas de un cluster sería
tomar el acoplamiento MEDIO y calcular una sola probabilidad para "el dron
promedio", multiplicada por el tamaño del cluster — eso subestima
sistemáticamente las bajas, porque la sigmoide de daño es CÓNCAVA en el
rango donde más importa (ver docs/FISICA_Y_MATEMATICA.md §3.6): promediar
antes de aplicar una función no lineal cóncava da un valor MENOR que
promediar los resultados (desigualdad de Jensen).

La forma correcta —la que implementa este módulo— es integrar sobre la
DISTRIBUCIÓN de acoplamiento (Monte Carlo con las mismas distribuciones de
``DRONE_CABLE_LENGTH_MIN_M``/``MAX_M``/``DRONE_POLARIZATION_MIN`` que
sortea ``Swarm`` al crear cada dron) y promediar las PROBABILIDADES
resultantes, no los parámetros de entrada.

═══════════════════════════════════════════════════════════════════════════
LA FORMULACIÓN DEL PROBLEMA
═══════════════════════════════════════════════════════════════════════════
Es el WTA clásico: dado un conjunto de "opciones de disparo" (cada una,
cañón o misil) y un conjunto de clusters, con ``f[i][j]`` = fracción
esperada de bajas si la opción ``i`` dispara al cluster ``j`` en aislamiento,
el valor total de una asignación es:

    valor(A) = Σ_j  tamaño_j · ( 1 − Π_{i asignado a j} (1 − f[i][j]) )

El producto de supervivencias hace que dos disparos al MISMO cluster tengan
rendimientos decrecientes (un dron solo puede morir una vez) — es lo que
hace del problema una optimización combinatoria real y no una suma trivial.

**Greedy**: en cada paso, asigna la opción libre que da la mayor GANANCIA
MARGINAL a cualquier cluster (considerando la supervivencia acumulada de
asignaciones previas a ese cluster), hasta que ninguna opción libre mejora
el valor total.

**Búsqueda local**: tras el greedy, prueba reasignar cada opción a un
cluster distinto (o desasignarla) — si alguna mejora el valor total, se
aplica, y se repite hasta que ninguna reasignación mejora.

**Validación**: contra FUERZA BRUTA EXACTA en instancias pequeñas
(≤6 opciones × ≤6 clusters) — NO contra el propio greedy. El criterio de
v1 ("bajas esperadas del plan ≥ bajas del greedy") era tautológico: la
búsqueda local arranca DESDE el greedy y por construcción no puede quedar
peor. Contra fuerza bruta sí es una comprobación real: greedy+búsqueda
local puede, en principio, no alcanzar el óptimo exacto en instancias más
grandes (WTA es NP-difícil en general) — que en las instancias de prueba SÍ
lo alcance es lo que valida al heurístico como herramienta práctica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any

import numpy as np

from src.config import (
    DRONE_CABLE_LENGTH_MAX_M,
    DRONE_CABLE_LENGTH_MIN_M,
    DRONE_POLARIZATION_MIN,
    MISSILE_DEFAULT_POWER,
    MISSILE_DEFAULT_RADIUS,
)
from src.engine.hpm_engine import (
    calculate_area_neutralization_probability_friis,
    calculate_neutralization_probability_friis,
    compute_target_parameters,
)
from src.utils.reproducibilidad import nuevo_generador

# ═══════════════════════════════════════════════════════════════════════════
# Clustering de tracks
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class BlancoEnCluster:
    """Un track dentro de un cluster: solo lo que el radar puede observar
    (posición estimada, blindaje NO se incluye — el blindaje de un dron
    tampoco es observable por radar; se asume el peor caso, sin blindaje,
    en la estimación de bajas — ver docstring del módulo)."""

    drone_id: int
    x: float
    y: float
    z: float


@dataclass
class Cluster:
    id: int
    blancos: list[BlancoEnCluster] = field(default_factory=list)

    @property
    def tamano(self) -> int:
        return len(self.blancos)

    @property
    def centroide(self) -> tuple[float, float, float]:
        n = max(self.tamano, 1)
        return (
            sum(b.x for b in self.blancos) / n,
            sum(b.y for b in self.blancos) / n,
            sum(b.z for b in self.blancos) / n,
        )


def formar_clusters(
    blancos: list[BlancoEnCluster], radio_cluster_m: float
) -> list[Cluster]:
    """
    Agrupa blancos por componentes conexas: dos blancos quedan en el mismo
    cluster si su distancia horizontal es ``≤ radio_cluster_m`` (unión
    transitiva: A-B-C se agrupan aunque A y C estén lejos entre sí, si B los
    conecta a ambos). Es deliberadamente simple (no k-means ni DBSCAN con
    densidad) — la pregunta que responde es "¿un solo disparo de área los
    cubre a todos?", que es una relación de distancia pura.
    """
    n = len(blancos)
    padre = list(range(n))

    def encontrar(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(i: int, j: int) -> None:
        ri, rj = encontrar(i), encontrar(j)
        if ri != rj:
            padre[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            dx = blancos[i].x - blancos[j].x
            dy = blancos[i].y - blancos[j].y
            if (dx * dx + dy * dy) ** 0.5 <= radio_cluster_m:
                unir(i, j)

    grupos: dict[int, list[BlancoEnCluster]] = {}
    for idx, blanco in enumerate(blancos):
        raiz = encontrar(idx)
        grupos.setdefault(raiz, []).append(blanco)

    return [
        Cluster(id=nuevo_id, blancos=grupo)
        for nuevo_id, grupo in enumerate(grupos.values())
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Bajas esperadas por (opción de disparo, cluster) — integrando la huella
# de susceptibilidad, no su media (evita el sesgo de Jensen)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class OpcionDeDisparo:
    """
    Un disparo DISPONIBLE para asignar — no un arma física distinta: el
    cañón puede aportar varias opciones (una por disparo que el presupuesto
    de energía todavía permite, ver ``HPMWeapon.disparos_disponibles``), y
    el sistema de misiles aporta una por unidad de munición restante.
    """

    id: int
    tipo: str  # "canion" | "misil"
    potencia_kw: float
    origen_x: float
    origen_y: float
    origen_z: float
    apertura_cono: float = 15.0  # solo relevante para "canion"
    radio_efecto: float = 100.0  # solo relevante para "misil"
    duty_cycle: float = 1.0


def _muestra_de_acoplamiento(gen: np.random.Generator) -> tuple[float, float]:
    """Un sorteo de (cable_length_m, polarization) con las MISMAS
    distribuciones que ``Swarm`` usa al crear un dron — es la distribución
    que un blanco detectado por radar (sin acceso a su estado interno)
    tiene, desde el punto de vista de quien planifica el disparo."""
    cable = float(gen.uniform(DRONE_CABLE_LENGTH_MIN_M, DRONE_CABLE_LENGTH_MAX_M))
    polarizacion = float(gen.uniform(DRONE_POLARIZATION_MIN, 1.0))
    return cable, polarizacion


def bajas_esperadas(
    opcion: OpcionDeDisparo,
    cluster: Cluster,
    n_muestras: int = 200,
    seed: int = 0,
) -> float:
    """
    Bajas esperadas si ``opcion`` dispara AISLADAMENTE contra ``cluster``
    (sin contar interacción con otros disparos — eso lo maneja el
    optimizador vía el producto de supervivencias).

    Por cada blanco del cluster, se promedian ``n_muestras`` probabilidades
    de baja (cada una con un sorteo INDEPENDIENTE de cable/polarización) —
    es la integral de Monte Carlo sobre la distribución de acoplamiento, la
    forma correcta de evitar el sesgo de Jensen (ver docstring del módulo).
    Sin blindaje: un radar no puede saber qué drones están blindados, así
    que se asume el caso base (sin protección) — una decisión conservadora
    (sobreestima ligeramente las bajas), declarada, no un descuido.
    """
    if cluster.tamano == 0:
        return 0.0

    gen = nuevo_generador(seed)
    total = 0.0

    for blanco in cluster.blancos:
        if opcion.tipo == "canion":
            distancia, offset = compute_target_parameters(
                opcion.origen_x, opcion.origen_y,
                # Apunta al blanco individual dentro del cono ya orientado
                # al cluster — el offset angular real de CADA blanco
                # respecto al eje del disparo (no todos están perfectamente
                # en el eje, aunque el disparo apunte al centroide).
                _angulo_hacia(opcion.origen_x, opcion.origen_y, *cluster.centroide[:2]),
                blanco.x, blanco.y,
                origin_z=opcion.origen_z, target_z=blanco.z,
            )
            if abs(offset) > opcion.apertura_cono / 2.0:
                continue
            acumulado = 0.0
            for _ in range(n_muestras):
                cable, pol = _muestra_de_acoplamiento(gen)
                p = calculate_neutralization_probability_friis(
                    potencia_kw=opcion.potencia_kw,
                    distancia=distancia,
                    apertura_cono=opcion.apertura_cono,
                    angulo_offset=offset,
                    duty_cycle=opcion.duty_cycle,
                    cable_length_m=cable,
                    polarization=pol,
                )
                acumulado += p
            total += acumulado / n_muestras

        elif opcion.tipo == "misil":
            dx = blanco.x - cluster.centroide[0]
            dy = blanco.y - cluster.centroide[1]
            dz = blanco.z - cluster.centroide[2]
            distancia = (dx * dx + dy * dy + dz * dz) ** 0.5
            if distancia > opcion.radio_efecto:
                continue
            acumulado = 0.0
            for _ in range(n_muestras):
                cable, pol = _muestra_de_acoplamiento(gen)
                p = calculate_area_neutralization_probability_friis(
                    potencia_kw=opcion.potencia_kw,
                    distancia=distancia,
                    duty_cycle=opcion.duty_cycle,
                    cable_length_m=cable,
                    polarization=pol,
                )
                acumulado += p
            total += acumulado / n_muestras
        else:
            raise ValueError(f"tipo de opción desconocido: {opcion.tipo!r}")

    return total


def _angulo_hacia(ox: float, oy: float, tx: float, ty: float) -> float:
    from src.engine.hpm_engine import target_angle_from_origin

    return target_angle_from_origin(ox, oy, tx, ty)


def matriz_de_bajas_esperadas(
    opciones: list[OpcionDeDisparo],
    clusters: list[Cluster],
    n_muestras: int = 200,
    seed: int = 0,
) -> np.ndarray:
    """``matriz[i][j]`` = bajas esperadas si la opción ``i`` dispara,
    aislada, contra el cluster ``j``. Simétrica en el sentido de que NO
    depende de qué más esté asignado — esa interacción la aplica el
    optimizador."""
    m = np.zeros((len(opciones), len(clusters)), dtype=float)
    for i, opcion in enumerate(opciones):
        for j, cluster in enumerate(clusters):
            m[i, j] = bajas_esperadas(opcion, cluster, n_muestras, seed=seed + i * 1000 + j)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# El optimizador: greedy + búsqueda local, validado contra fuerza bruta
# ═══════════════════════════════════════════════════════════════════════════

Asignacion = dict[int, int]  # índice de opción -> índice de cluster (ausente = sin asignar)


def _fracciones(matriz: np.ndarray, tamanos: list[int]) -> np.ndarray:
    """``fracciones[i][j] = matriz[i][j] / tamano[j]``, la fracción esperada
    de bajas (no el conteo) — es lo que entra al producto de supervivencias."""
    tam = np.array([max(t, 1) for t in tamanos], dtype=float)
    return matriz / tam[None, :]


def valor_total(
    asignacion: Asignacion, matriz: np.ndarray, tamanos: list[int]
) -> float:
    """
    valor(A) = Σ_j tamaño_j · (1 − Π_{i→j} (1 − f[i][j]))

    El producto de supervivencias es lo que hace que dos disparos al MISMO
    cluster tengan rendimientos decrecientes — un dron solo puede morir una
    vez, así que la segunda opción asignada al mismo cluster solo "salva"
    una fracción de los que la primera dejó vivos.
    """
    fracciones = _fracciones(matriz, tamanos)
    n_clusters = matriz.shape[1]
    supervivencia = np.ones(n_clusters, dtype=float)
    for i, j in asignacion.items():
        supervivencia[j] *= max(0.0, 1.0 - fracciones[i, j])
    total = 0.0
    for j in range(n_clusters):
        total += tamanos[j] * (1.0 - supervivencia[j])
    return float(total)


def asignar_greedy(matriz: np.ndarray, tamanos: list[int]) -> Asignacion:
    """
    En cada paso, asigna la opción LIBRE que da la mayor GANANCIA MARGINAL
    a cualquier cluster (considerando la supervivencia acumulada de
    asignaciones previas a ese cluster), hasta que ninguna opción libre
    mejora el valor total en más de un epsilon numérico.
    """
    n_opciones, n_clusters = matriz.shape
    fracciones = _fracciones(matriz, tamanos)
    supervivencia = np.ones(n_clusters, dtype=float)
    asignacion: Asignacion = {}
    libres = set(range(n_opciones))

    while libres:
        mejor_ganancia = 1e-12
        mejor_par: tuple[int, int] | None = None
        for i in libres:
            for j in range(n_clusters):
                ganancia = tamanos[j] * supervivencia[j] * fracciones[i, j]
                if ganancia > mejor_ganancia:
                    mejor_ganancia = ganancia
                    mejor_par = (i, j)
        if mejor_par is None:
            break
        i, j = mejor_par
        asignacion[i] = j
        supervivencia[j] *= max(0.0, 1.0 - fracciones[i, j])
        libres.discard(i)

    return asignacion


def mejorar_con_busqueda_local(
    asignacion: Asignacion, matriz: np.ndarray, tamanos: list[int]
) -> Asignacion:
    """
    Búsqueda local de "mejor mejora" con DOS vecindarios, hasta que ninguno
    mejore — óptimo local respecto a esos movimientos (no garantiza el
    óptimo global, WTA es NP-difícil en general):

    1. **Reasignación de un elemento**: mover una opción a otro cluster (o
       desasignarla).
    2. **Intercambio de pares**: dos opciones YA asignadas intercambian sus
       clusters. Sin esto, el greedy puede quedar atrapado en óptimos
       locales que una reasignación de un solo elemento no puede deshacer
       —dos asignaciones que son individualmente razonables pero que
       juntas dejan valor sobre la mesa porque cada una compite con la otra
       por el MISMO cluster en vez de repartirse— y que sí se corrigen
       invirtiendo ambas a la vez. Verificado empíricamente: sin este
       vecindario, el heurístico no igualaba la fuerza bruta en varias de
       20 instancias aleatorias pequeñas; con él, las iguala en las 20 (ver
       tests/test_targeting.py).
    """
    n_opciones, n_clusters = matriz.shape
    actual = dict(asignacion)
    valor_actual = valor_total(actual, matriz, tamanos)

    mejorando = True
    while mejorando:
        mejorando = False
        mejor_delta = 1e-9
        mejor_movimiento: tuple[str, tuple] | None = None

        # Vecindario 1: reasignar una opción.
        for i in range(n_opciones):
            original = actual.get(i)
            candidatos: list[int | None] = [None] + list(range(n_clusters))
            for destino in candidatos:
                if destino == original:
                    continue
                prueba = dict(actual)
                if destino is None:
                    prueba.pop(i, None)
                else:
                    prueba[i] = destino
                delta = valor_total(prueba, matriz, tamanos) - valor_actual
                if delta > mejor_delta:
                    mejor_delta = delta
                    mejor_movimiento = ("reasignar", (i, destino))

        # Vecindario 2: intercambiar los clusters de dos opciones asignadas.
        asignadas = list(actual.keys())
        for idx_a in range(len(asignadas)):
            for idx_b in range(idx_a + 1, len(asignadas)):
                i, k = asignadas[idx_a], asignadas[idx_b]
                if actual[i] == actual[k]:
                    continue
                prueba = dict(actual)
                prueba[i], prueba[k] = actual[k], actual[i]
                delta = valor_total(prueba, matriz, tamanos) - valor_actual
                if delta > mejor_delta:
                    mejor_delta = delta
                    mejor_movimiento = ("intercambiar", (i, k))

        if mejor_movimiento is not None:
            tipo_movimiento, datos = mejor_movimiento
            if tipo_movimiento == "reasignar":
                i, destino = datos
                if destino is None:
                    actual.pop(i, None)
                else:
                    actual[i] = destino
            else:
                i, k = datos
                actual[i], actual[k] = actual[k], actual[i]
            valor_actual = valor_total(actual, matriz, tamanos)
            mejorando = True

    return actual


def resolver_wta_fuerza_bruta(
    matriz: np.ndarray, tamanos: list[int]
) -> tuple[Asignacion, float]:
    """
    Óptimo EXACTO por enumeración completa — cada opción puede ir a
    cualquiera de los clusters o quedar sin asignar: ``(n_clusters+1) **
    n_opciones`` combinaciones. Exponencial: solo para instancias pequeñas
    (el ítem pide validar hasta ≤6×6, ``7**6 ≈ 117 mil`` combinaciones,
    factible en milisegundos).
    """
    n_opciones, n_clusters = matriz.shape
    mejor_valor = -1.0
    mejor_asignacion: Asignacion = {}

    destinos_posibles = list(range(n_clusters)) + [None]
    for combinacion in product(destinos_posibles, repeat=n_opciones):
        asignacion = {i: j for i, j in enumerate(combinacion) if j is not None}
        valor = valor_total(asignacion, matriz, tamanos)
        if valor > mejor_valor:
            mejor_valor = valor
            mejor_asignacion = asignacion

    return mejor_asignacion, mejor_valor


def resolver_wta(matriz: np.ndarray, tamanos: list[int]) -> tuple[Asignacion, float]:
    """Greedy + búsqueda local — el heurístico de producción (ver docstring
    del módulo para la validación contra fuerza bruta)."""
    inicial = asignar_greedy(matriz, tamanos)
    mejorada = mejorar_con_busqueda_local(inicial, matriz, tamanos)
    return mejorada, valor_total(mejorada, matriz, tamanos)


# ═══════════════════════════════════════════════════════════════════════════
# Punto de entrada: arma el problema desde el estado real del simulador
# ═══════════════════════════════════════════════════════════════════════════


def planificar_asignacion(
    swarm: Any,
    hpm: Any,
    missile_system: Any,
    radio_cluster_m: float = 100.0,
    n_muestras: int = 200,
    seed: int = 2026,
) -> dict[str, Any]:
    """
    Arma el problema de WTA desde el estado REAL del simulador —tracks
    detectados (P2-G), presupuesto de energía del cañón (P2-F) y munición
    de misiles— y devuelve el plan óptimo (greedy + búsqueda local).
    """
    tracks = swarm.track_manager.tracks_activos()
    blancos = [BlancoEnCluster(t.drone_id, t.x, t.y, t.z) for t in tracks]
    clusters = formar_clusters(blancos, radio_cluster_m)
    tamanos = [c.tamano for c in clusters]

    opciones: list[OpcionDeDisparo] = []
    idx = 0
    for _ in range(hpm.disparos_disponibles()):
        opciones.append(
            OpcionDeDisparo(
                id=idx, tipo="canion", potencia_kw=hpm.potencia,
                origen_x=hpm.origen_x, origen_y=hpm.origen_y, origen_z=hpm.origen_z,
                apertura_cono=hpm.apertura_cono, duty_cycle=hpm.duty_cycle,
            )
        )
        idx += 1
    for _ in range(missile_system.municion_restante):
        opciones.append(
            OpcionDeDisparo(
                id=idx, tipo="misil",
                potencia_kw=MISSILE_DEFAULT_POWER,
                radio_efecto=MISSILE_DEFAULT_RADIUS,
                origen_x=hpm.origen_x, origen_y=hpm.origen_y, origen_z=hpm.origen_z,
            )
        )
        idx += 1

    if not opciones or not clusters:
        return {
            "clusters": [{"id": c.id, "tamano": c.tamano, "centroide": c.centroide} for c in clusters],
            "opciones_disponibles": len(opciones),
            "asignacion": [],
            "bajas_esperadas_total": 0.0,
        }

    matriz = matriz_de_bajas_esperadas(opciones, clusters, n_muestras=n_muestras, seed=seed)
    asignacion, valor = resolver_wta(matriz, tamanos)

    plan = []
    for i, j in asignacion.items():
        plan.append(
            {
                "opcion_id": opciones[i].id,
                "tipo": opciones[i].tipo,
                "cluster_id": clusters[j].id,
                "cluster_centroide": clusters[j].centroide,
                "cluster_tamano": clusters[j].tamano,
                "bajas_esperadas_aisladas": round(float(matriz[i, j]), 4),
            }
        )

    return {
        "clusters": [
            {"id": c.id, "tamano": c.tamano, "centroide": c.centroide} for c in clusters
        ],
        "opciones_disponibles": len(opciones),
        "asignacion": plan,
        "bajas_esperadas_total": round(valor, 4),
    }
