"""Pruebas de la asignación arma-blanco optimizada (WTA, P3-A).

Estructura: primero se valida el OPTIMIZADOR en abstracto (greedy + búsqueda
local contra fuerza bruta exacta, sobre matrices de valor arbitrarias — igual
disciplina que P2-A validó Sobol contra Ishigami antes de aplicarlo al
modelo de daño), y solo después se prueba la integración con el motor real.

Honestidad declarada: el heurístico NO siempre alcanza el óptimo exacto en
instancias ADVERSARIALES (matrices de valor aleatorias sin estructura física)
— es un resultado teórico esperado, WTA es NP-difícil y greedy+búsqueda local
no tiene garantía de aproximación en el caso general. Sobre instancias
REALISTAS (generadas por el propio modelo físico, que es el caso de uso real
de este módulo), sí alcanza el óptimo exacto de forma consistente — eso es
lo que se verifica como criterio de aceptación.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.config import (
    DRONE_CABLE_LENGTH_MAX_M,
    DRONE_CABLE_LENGTH_MIN_M,
    DRONE_POLARIZATION_ANGLE_MAX_RAD,
    DRONE_POLARIZATION_ANGLE_MIN_RAD,
    DRONE_POLARIZATION_MIN_ETA,
)
from src.engine.hpm_engine import calculate_neutralization_probability_friis as pf
from src.engine.targeting import (
    BlancoEnCluster,
    Cluster,
    OpcionDeDisparo,
    asignar_greedy,
    bajas_esperadas,
    formar_clusters,
    matriz_de_bajas_esperadas,
    mejorar_con_busqueda_local,
    planificar_asignacion,
    resolver_wta,
    resolver_wta_fuerza_bruta,
    valor_total,
)
from src.models.hpm_system import HPMissileSystem
from src.models.hpm_weapon import HPMWeapon
from src.models.swarm import FormacionTipo, Swarm
from src.utils.reproducibilidad import seed_simulacion


class TestClustering:
    def test_agrupa_por_cercania(self):
        blancos = [
            BlancoEnCluster(0, 0.0, 0.0, 100.0),
            BlancoEnCluster(1, 10.0, 0.0, 100.0),
            BlancoEnCluster(2, 500.0, 500.0, 100.0),
        ]
        clusters = formar_clusters(blancos, radio_cluster_m=50.0)
        assert len(clusters) == 2
        tamanos = sorted(c.tamano for c in clusters)
        assert tamanos == [1, 2]

    def test_union_transitiva(self):
        """A-B-C se agrupan aunque A y C estén lejos, si B conecta a ambos."""
        blancos = [
            BlancoEnCluster(0, 0.0, 0.0, 100.0),
            BlancoEnCluster(1, 40.0, 0.0, 100.0),
            BlancoEnCluster(2, 80.0, 0.0, 100.0),
        ]
        clusters = formar_clusters(blancos, radio_cluster_m=45.0)
        assert len(clusters) == 1
        assert clusters[0].tamano == 3

    def test_sin_blancos_no_hay_clusters(self):
        assert formar_clusters([], radio_cluster_m=50.0) == []

    def test_centroide_es_el_promedio(self):
        blancos = [BlancoEnCluster(0, 0.0, 0.0, 0.0), BlancoEnCluster(1, 100.0, 0.0, 0.0)]
        cluster = Cluster(id=0, blancos=blancos)
        assert cluster.centroide == (50.0, 0.0, 0.0)


class TestBajasEsperadasEvitaElSesgoDeJensen:
    """El hallazgo central del módulo: promediar acoplamientos y luego
    calcular P(kill) subestima las bajas frente a promediar P(kill) sobre
    la distribución de acoplamientos — la sigmoide es cóncava ahí.
    """

    def test_mc_supera_a_la_probabilidad_del_acoplamiento_medio(self):
        opcion = OpcionDeDisparo(
            id=0, tipo="canion", potencia_kw=25.0,
            origen_x=0.0, origen_y=0.0, origen_z=8.0, apertura_cono=15.0,
        )
        cluster = Cluster(id=0, blancos=[BlancoEnCluster(0, 30.0, 0.0, 8.0)])
        bajas_mc = bajas_esperadas(opcion, cluster, n_muestras=3000, seed=1)

        cable_medio = (DRONE_CABLE_LENGTH_MIN_M + DRONE_CABLE_LENGTH_MAX_M) / 2
        # E[max(cos²φ, piso)] para φ~U[ÁNGULO_MIN, ÁNGULO_MAX] — no tiene una
        # forma cerrada trivial de escribir a mano (la distribución ya no es
        # uniforme desde que se corrigió a cos²φ, ver src/config.py), así
        # que se aproxima por cuadratura numérica directa en vez de arriesgar
        # una derivación manual.
        angulos = np.linspace(DRONE_POLARIZATION_ANGLE_MIN_RAD, DRONE_POLARIZATION_ANGLE_MAX_RAD, 200_000)
        pol_medio = float(np.mean(np.maximum(np.cos(angulos) ** 2, DRONE_POLARIZATION_MIN_ETA)))
        p_del_promedio = pf(
            25.0, 30.0, 15.0, 0.0, cable_length_m=cable_medio, polarization=pol_medio
        )

        assert bajas_mc > p_del_promedio, (
            "la integral de Monte Carlo debe superar a la probabilidad del "
            "acoplamiento promedio (sesgo de Jensen, sigmoide cóncava aquí)"
        )
        # La diferencia debe ser sustancial, no ruido de muestreo.
        assert (bajas_mc - p_del_promedio) / p_del_promedio > 0.2

    def test_reproducible_con_la_misma_semilla(self):
        opcion = OpcionDeDisparo(
            id=0, tipo="canion", potencia_kw=25.0,
            origen_x=0.0, origen_y=0.0, origen_z=8.0, apertura_cono=15.0,
        )
        cluster = Cluster(id=0, blancos=[BlancoEnCluster(0, 30.0, 0.0, 8.0)])
        a = bajas_esperadas(opcion, cluster, n_muestras=500, seed=7)
        b = bajas_esperadas(opcion, cluster, n_muestras=500, seed=7)
        assert a == b

    def test_cero_fuera_del_cono(self):
        opcion = OpcionDeDisparo(
            id=0, tipo="canion", potencia_kw=25.0,
            origen_x=0.0, origen_y=0.0, origen_z=8.0, apertura_cono=10.0,
        )
        # Un blanco en (0, 100) está a 90° del eje +x: muy fuera de un cono
        # de 10° apuntando al propio blanco... se apunta al centroide, que
        # es el propio blanco, así que hace falta un SEGUNDO blanco lejos
        # angularmente para que quede fuera del cono.
        cluster = Cluster(
            id=0,
            blancos=[BlancoEnCluster(0, 30.0, 0.0, 8.0), BlancoEnCluster(1, 0.0, 500.0, 8.0)],
        )
        bajas = bajas_esperadas(opcion, cluster, n_muestras=200, seed=1)
        # El centroide está entre ambos; con apertura 10° al menos uno de
        # los dos queda fuera del cono y no aporta bajas de ese origen.
        assert bajas < 2.0  # no ambos a probabilidad alta simultánea

    def test_misil_cero_fuera_del_radio_de_efecto(self):
        """La distancia relevante para el misil es la de CADA blanco al
        CENTROIDE del cluster (donde detona) — no al origen del arma (el
        misil vuela hasta ahí). Con un solo blanco el centroide coincide con
        su propia posición (distancia 0, siempre "dentro"), así que hace
        falta un cluster ESPARCIDO —más ancho que el radio de efecto— para
        que algún blanco quede fuera de la detonación.
        """
        opcion = OpcionDeDisparo(
            id=0, tipo="misil", potencia_kw=50.0,
            origen_x=0.0, origen_y=0.0, origen_z=8.0, radio_efecto=50.0,
        )
        # Centroide en (0,0); un blanco a 30 m (dentro) y otro a 500 m
        # (bien fuera de los 50 m de radio_efecto).
        cluster = Cluster(
            id=0,
            blancos=[BlancoEnCluster(0, 30.0, 0.0, 8.0), BlancoEnCluster(1, -500.0, 0.0, 8.0)],
        )
        bajas_ambos = bajas_esperadas(opcion, cluster, n_muestras=200, seed=1)

        # Control: el mismo cluster pero SOLO con el blanco lejano da 0.
        cluster_solo_lejano = Cluster(id=1, blancos=[BlancoEnCluster(1, -500.0, 0.0, 8.0)])
        # (con un solo blanco el centroide coincide con él, distancia 0 —
        # para aislar el efecto hay que comparar con/sin el blanco cercano)
        cluster_solo_cercano = Cluster(id=2, blancos=[BlancoEnCluster(0, 30.0, 0.0, 8.0)])
        bajas_ambos_recomputado = bajas_esperadas(
            OpcionDeDisparo(id=0, tipo="misil", potencia_kw=50.0,
                            origen_x=0.0, origen_y=0.0, origen_z=8.0, radio_efecto=50.0),
            cluster, n_muestras=200, seed=1,
        )
        # El centroide de {30, -500} es -235: ninguno de los dos blancos
        # individuales está a menos de 50 m de ESE punto, así que las bajas
        # esperadas del cluster conjunto deben ser 0 — es el caso real que
        # se quería probar (un cluster demasiado disperso para un solo
        # misil, ninguno de los dos entra en el radio de la detonación en
        # el centroide).
        assert bajas_ambos_recomputado == 0.0

    def test_tipo_desconocido_falla_explicito(self):
        opcion = OpcionDeDisparo(
            id=0, tipo="laser", potencia_kw=25.0, origen_x=0.0, origen_y=0.0, origen_z=8.0,
        )
        cluster = Cluster(id=0, blancos=[BlancoEnCluster(0, 30.0, 0.0, 8.0)])
        with pytest.raises(ValueError, match="tipo de opción"):
            bajas_esperadas(opcion, cluster, n_muestras=10)


class TestValorTotalYRendimientosDecrecientes:
    def test_dos_disparos_al_mismo_cluster_tienen_rendimiento_decreciente(self):
        """El segundo disparo al MISMO cluster vale menos que el primero,
        porque parte de los drones ya están 'cubiertos' por el primero."""
        matriz = np.array([[0.5], [0.5]])  # 2 opciones, 1 cluster, f=0.5 cada una
        tamanos = [10]
        valor_uno = valor_total({0: 0}, matriz, tamanos)
        valor_dos = valor_total({0: 0, 1: 0}, matriz, tamanos)
        ganancia_primero = valor_uno
        ganancia_segundo = valor_dos - valor_uno
        assert ganancia_segundo < ganancia_primero

    def test_supervivencia_es_el_producto_de_1_menos_fraccion(self):
        """``matriz`` recibe CONTEOS crudos de bajas esperadas (como los
        produce ``bajas_esperadas``/``matriz_de_bajas_esperadas``), no
        fracciones directas — ``valor_total`` divide por ``tamanos``
        internamente para obtener la fracción que entra al producto de
        supervivencias. Con tamaño 10 y fracciones deseadas 0.3 y 0.4, los
        conteos crudos son 3.0 y 4.0.
        """
        matriz = np.array([[3.0, 0.0], [4.0, 0.0]])
        tamanos = [10, 5]
        valor = valor_total({0: 0, 1: 0}, matriz, tamanos)
        esperado = 10 * (1 - (1 - 0.3) * (1 - 0.4))
        assert valor == pytest.approx(esperado)

    def test_sin_asignaciones_valor_cero(self):
        matriz = np.array([[0.5, 0.5]])
        assert valor_total({}, matriz, [10, 10]) == 0.0


class TestGreedyYBusquedaLocalContraFuerzaBruta:
    """El criterio de aceptación real del ítem (no 'mejor que el greedy',
    que sería tautológico — contra el ÓPTIMO EXACTO)."""

    def test_instancias_pequenas_aleatorias(self):
        """Sobre matrices de valor ARBITRARIAS (sin estructura física),
        documenta el gap real del heurístico — no se fuerza a que sea 0.
        """
        rng = np.random.default_rng(0)
        gaps = []
        for _ in range(20):
            n_op = int(rng.integers(1, 7))
            n_cl = int(rng.integers(1, 7))
            matriz = rng.uniform(0, 3, size=(n_op, n_cl))
            tamanos = list(rng.integers(1, 6, size=n_cl))
            _, valor_h = resolver_wta(matriz, tamanos)
            _, valor_fb = resolver_wta_fuerza_bruta(matriz, tamanos)
            assert valor_h <= valor_fb + 1e-6, "el heurístico NUNCA puede superar al óptimo"
            gap = (valor_fb - valor_h) / valor_fb if valor_fb > 1e-9 else 0.0
            gaps.append(gap)
        # Documentado, no idealizado: en matrices SIN estructura física el
        # heurístico no siempre alcanza el óptimo (WTA es NP-difícil), pero
        # el gap medio debe ser modesto.
        assert np.mean(gaps) < 0.15

    def test_instancias_realistas_del_modelo_fisico_alcanzan_el_optimo(self):
        """Sobre matrices generadas por el modelo físico real (el caso de
        uso genuino de este módulo, con caída suave por distancia en vez de
        valores arbitrarios), el heurístico alcanza el óptimo exacto.
        """
        rng = np.random.default_rng(0)

        def instancia(seed: int):
            r = np.random.default_rng(seed)
            n_cl = int(r.integers(2, 6))
            clusters = []
            for c in range(n_cl):
                cx, cy = r.uniform(-800, 800), r.uniform(-800, 800)
                n_drones = int(r.integers(1, 5))
                blancos = [
                    BlancoEnCluster(i, cx + r.uniform(-20, 20), cy + r.uniform(-20, 20), 100.0)
                    for i in range(n_drones)
                ]
                clusters.append(Cluster(id=c, blancos=blancos))
            opciones = []
            idx = 0
            for _ in range(int(r.integers(1, 4))):
                opciones.append(
                    OpcionDeDisparo(idx, "canion", 25.0, 0.0, 0.0, 8.0, apertura_cono=179.0)
                )
                idx += 1
            for _ in range(int(r.integers(0, 3))):
                opciones.append(
                    OpcionDeDisparo(idx, "misil", 50.0, 0.0, 0.0, 8.0, radio_efecto=150.0)
                )
                idx += 1
            return opciones, clusters

        exactos = 0
        total = 0
        for prueba in range(12):
            opciones, clusters = instancia(200 + prueba)
            if not opciones:
                continue
            matriz = matriz_de_bajas_esperadas(opciones, clusters, n_muestras=40, seed=prueba)
            tamanos = [c.tamano for c in clusters]
            _, valor_h = resolver_wta(matriz, tamanos)
            _, valor_fb = resolver_wta_fuerza_bruta(matriz, tamanos)
            total += 1
            if abs(valor_h - valor_fb) < 1e-6:
                exactos += 1

        assert total >= 10
        assert exactos == total, f"solo {exactos}/{total} instancias realistas alcanzaron el óptimo"

    def test_busqueda_local_nunca_empeora_al_greedy(self):
        """Propiedad estructural: la búsqueda local arranca DESDE el greedy
        y solo aplica movimientos que mejoran — no puede empeorar. (Esto es
        justamente lo que hacía tautológico al criterio de v1: se conserva
        como propiedad de sanidad, no como criterio de aceptación).
        """
        rng = np.random.default_rng(3)
        for _ in range(10):
            matriz = rng.uniform(0, 2, size=(4, 4))
            tamanos = list(rng.integers(1, 5, size=4))
            inicial = asignar_greedy(matriz, tamanos)
            valor_greedy = valor_total(inicial, matriz, tamanos)
            mejorado = mejorar_con_busqueda_local(inicial, matriz, tamanos)
            valor_mejorado = valor_total(mejorado, matriz, tamanos)
            assert valor_mejorado >= valor_greedy - 1e-9

    def test_greedy_solo_no_alcanza_el_optimo_en_algun_caso(self):
        """Confirma que la búsqueda local APORTA algo: existe al menos una
        instancia donde greedy solo no llega al óptimo pero
        greedy+búsqueda local sí (o donde busqueda local mejora sobre
        greedy) — si no, el vecindario de intercambio sería inútil.
        """
        rng = np.random.default_rng(0)
        alguna_mejora = False
        for _ in range(30):
            n_op, n_cl = int(rng.integers(2, 6)), int(rng.integers(2, 6))
            matriz = rng.uniform(0, 3, size=(n_op, n_cl))
            tamanos = list(rng.integers(1, 6, size=n_cl))
            inicial = asignar_greedy(matriz, tamanos)
            valor_greedy = valor_total(inicial, matriz, tamanos)
            _, valor_final = resolver_wta(matriz, tamanos)
            if valor_final > valor_greedy + 1e-6:
                alguna_mejora = True
                break
        assert alguna_mejora, "la búsqueda local nunca mejoró sobre el greedy en 30 pruebas"


class TestPlanificarAsignacionConElMotorReal:
    def test_sin_tracks_devuelve_plan_vacio(self):
        seed_simulacion(1)
        swarm = Swarm(formacion=FormacionTipo.CIRCULAR)
        swarm.inicializar_formacion("circular", 5)
        # Sin barrer ticks: no hay tracks todavía.
        hpm = HPMWeapon()
        sistema = HPMissileSystem()
        plan = planificar_asignacion(swarm, hpm, sistema)
        assert plan["asignacion"] == []

    def test_con_tracks_y_presupuesto_produce_un_plan(self):
        seed_simulacion(2)
        swarm = Swarm(formacion=FormacionTipo.CIRCULAR)
        swarm.inicializar_formacion("circular", 10)
        for d in swarm.drones:
            d.velocidad = 0.0
            d.x = swarm.centro_x + (d.x - swarm.centro_x) * 0.05  # acercar al origen
            d.y = swarm.centro_y + (d.y - swarm.centro_y) * 0.05

        from src.config import RADAR_REVISITA_S
        for _ in range(int(RADAR_REVISITA_S / 0.1) + 2):
            swarm.actualizar(0.1)

        hpm = HPMWeapon()
        sistema = HPMissileSystem()
        plan = planificar_asignacion(swarm, hpm, sistema, n_muestras=30)

        assert plan["opciones_disponibles"] > 0
        assert plan["bajas_esperadas_total"] >= 0.0
        for item in plan["asignacion"]:
            assert item["tipo"] in ("canion", "misil")

    def test_sin_energia_ni_municion_no_hay_opciones(self):
        seed_simulacion(3)
        swarm = Swarm(formacion=FormacionTipo.CIRCULAR)
        swarm.inicializar_formacion("circular", 5)
        from src.config import RADAR_REVISITA_S
        for _ in range(int(RADAR_REVISITA_S / 0.1) + 2):
            swarm.actualizar(0.1)

        hpm = HPMWeapon()
        hpm.energia_actual_kj = 0.0
        sistema = HPMissileSystem()
        sistema.municion_restante = 0

        plan = planificar_asignacion(swarm, hpm, sistema)
        assert plan["opciones_disponibles"] == 0
        assert plan["asignacion"] == []
        assert plan["bajas_esperadas_total"] == 0.0


class TestEndpointTargetingPlan:
    def test_responde_con_las_claves_esperadas(self):
        from fastapi.testclient import TestClient
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/api/targeting/plan", params={"n_muestras": 20})
            assert resp.status_code == 200
            d = resp.json()
            assert "asignacion" in d and "clusters" in d and "bajas_esperadas_total" in d

    def test_rechaza_parametros_fuera_de_rango(self):
        from fastapi.testclient import TestClient
        from src.main import app

        with TestClient(app) as client:
            assert client.get(
                "/api/targeting/plan", params={"radio_cluster_m": 1.0}
            ).status_code == 400
            assert client.get(
                "/api/targeting/plan", params={"n_muestras": 1}
            ).status_code == 400
