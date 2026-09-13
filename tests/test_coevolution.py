"""Pruebas de la coevolución genética arma↔enjambre (P3-B).

Estructura, misma disciplina que el resto del proyecto (Sobol/Ishigami en
P2-A, WTA/fuerza bruta en P3-A): primero se valida el MOTOR GENÉTICO en
abstracto —selección/cruce/mutación/elitismo— contra una función de fitness
SINTÉTICA y conocida (maximizar potencia_kw sin más), y solo después se
prueba la integración con el runner Monte Carlo real, que es mucho más
lento y mucho más ruidoso.

Honestidad declarada sobre el ruido físico: a la distancia de combate de
esta coevolución (``DISTANCIA_COMBATE_M`` = 60 m), la probabilidad de baja
por disparo sigue siendo baja (pocos % por drone — ver el docstring de
``DISTANCIA_COMBATE_M`` en ``src/engine/coevolution.py``) porque el factor
de acoplamiento cable/polarización de cada drone se sortea al azar y solo
una fracción minoritaria cae cerca de la resonancia. Por eso las pruebas de
integración comparan el MEJOR individuo de la ÚLTIMA generación contra el
MEJOR de la PRIMERA (no exigen mejora estrictamente monótona generación a
generación, que con esta varianza sería una expectativa poco realista) y
usan un oponente FIJO (no el campeón móvil de la coevolución completa) para
que la comparación entre generaciones no esté contaminada por un rival que
también está cambiando.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.engine.coevolution import (
    DISTANCIA_COMBATE_M,
    FORMACIONES,
    GenomaArma,
    GenomaDefensa,
    ResultadoCoevolucion,
    _cruzar_arma,
    _evolucionar_poblacion,
    _mutar_arma,
    _origen_combate,
    _rumbo_al_centro_del_campo,
    _torneo,
    coevolucionar,
    evaluar_enfrentamiento,
    evolucionar_arma_contra_defensa_fija,
    evolucionar_defensa_contra_arma_fija,
    frontera_pareto,
    resumen_json,
)
from src.utils.reproducibilidad import nuevo_generador


class TestGenomas:
    def test_genoma_arma_se_acota_a_sus_limites(self):
        g = GenomaArma(potencia_kw=1e9, apertura_cono=-10, duty_cycle=5.0)
        acotado = g.clonar_acotado()
        lo, hi = GenomaArma.LIMITES["potencia_kw"]
        assert lo <= acotado.potencia_kw <= hi
        lo, hi = GenomaArma.LIMITES["apertura_cono"]
        assert lo <= acotado.apertura_cono <= hi
        lo, hi = GenomaArma.LIMITES["duty_cycle"]
        assert lo <= acotado.duty_cycle <= hi

    def test_genoma_defensa_se_acota_y_redondea_formacion(self):
        g = GenomaDefensa(formacion_idx=99, cantidad=-5)
        acotado = g.clonar_acotado()
        assert 0 <= acotado.formacion_idx < len(FORMACIONES)
        lo, hi = GenomaDefensa.LIMITE_CANTIDAD
        assert lo <= acotado.cantidad <= hi

    def test_genoma_defensa_formacion_es_un_nombre_valido(self):
        gen = nuevo_generador(1)
        for _ in range(20):
            g = GenomaDefensa.aleatorio(gen)
            assert g.formacion in FORMACIONES

    def test_a_weapon_policy_usa_el_origen_de_combate(self):
        arma = GenomaArma(potencia_kw=50.0, apertura_cono=15.0, duty_cycle=1.0)
        policy = arma.a_weapon_policy()
        ox, oy = _origen_combate()
        assert policy.origen_x == pytest.approx(ox)
        assert policy.origen_y == pytest.approx(oy)
        assert policy.direccion == pytest.approx(_rumbo_al_centro_del_campo())
        assert policy.potencia == 50.0
        assert policy.apertura_cono == 15.0
        assert policy.duty_cycle == 1.0


class TestOrigenDeCombate:
    def test_distancia_al_centro_del_campo_es_la_configurada(self):
        import math

        from src import config as config_mod

        ox, oy = _origen_combate()
        cx, cy = config_mod.FIELD_WIDTH / 2, config_mod.FIELD_HEIGHT / 2
        assert math.hypot(cx - ox, cy - oy) == pytest.approx(DISTANCIA_COMBATE_M, abs=1e-6)


class TestFronteraPareto:
    def test_domina_estrictamente_en_ambos_ejes(self):
        # (costo, valor): minimizar costo, maximizar valor.
        # (1, 5) domina a (2, 3): menor costo Y mayor valor.
        puntos = [(1.0, 5.0), (2.0, 3.0)]
        assert frontera_pareto(puntos) == [(1.0, 5.0)]

    def test_no_dominados_quedan_ambos(self):
        # (1,3) tiene menor costo pero también menor valor que (2,5): no se
        # dominan entre sí, ambos deben sobrevivir.
        puntos = [(1.0, 3.0), (2.0, 5.0)]
        resultado = frontera_pareto(puntos)
        assert set(resultado) == {(1.0, 3.0), (2.0, 5.0)}

    def test_punto_dominado_por_dos_lados_desaparece(self):
        puntos = [(1.0, 5.0), (2.0, 3.0), (0.5, 5.0), (3.0, 1.0)]
        resultado = frontera_pareto(puntos)
        # (0.5, 5.0) domina a (1.0, 5.0) [igual valor, menor costo] y a
        # (2.0, 3.0) y a (3.0, 1.0). Solo (0.5, 5.0) debería sobrevivir.
        assert resultado == [(0.5, 5.0)]

    def test_frontera_vacia_para_lista_vacia(self):
        assert frontera_pareto([]) == []

    def test_puntos_duplicados_no_se_repiten(self):
        puntos = [(1.0, 2.0), (1.0, 2.0), (2.0, 1.0)]
        resultado = frontera_pareto(puntos)
        assert resultado.count((1.0, 2.0)) == 1


class TestMotorGeneticoSintetico:
    """Valida selección + cruce + mutación + elitismo contra un fitness
    SINTÉTICO y conocido (maximizar potencia_kw), sin tocar el motor de
    simulación — la misma disciplina de "sintético antes que real" que ya
    usó este proyecto para Sobol (P2-A) y WTA (P3-A)."""

    def test_torneo_favorece_estadisticamente_al_mejor(self):
        gen = nuevo_generador(7)
        fitness = [0.0, 0.0, 0.0, 1.0]  # el índice 3 es estrictamente el mejor
        ganadores = [_torneo(fitness, gen, k=3) for _ in range(2000)]
        # ``_torneo`` sortea CON reemplazo (``gen.integers``): el mejor gana
        # si y solo si aparece al menos una vez entre los k=3 sorteos sobre
        # n=4 individuos. P(aparece) = 1 - ((n-1)/n)^k = 1 - (3/4)^3 =
        # 0.578125 — no "casi siempre", como decía una versión anterior de
        # este test (afirmación matemáticamente incorrecta, corregida antes
        # de cerrar el ítem). Con 2000 repeticiones el error estándar es
        # ~0.011, así que una banda de ±0.06 alrededor del valor teórico es
        # generosa y no debería fallar por casualidad.
        frac_gana_el_mejor = np.mean([g == 3 for g in ganadores])
        assert abs(frac_gana_el_mejor - 0.578125) < 0.06

    def test_poblacion_converge_hacia_mayor_potencia_con_fitness_directo(self):
        """Sin tocar la física: fitness = potencia_kw directamente. Si el
        motor genético (selección + cruce + mutación + elitismo) funciona,
        la potencia media de la población debe subir generación a
        generación hacia el límite superior."""
        gen = nuevo_generador(123)
        poblacion = [GenomaArma.aleatorio(gen) for _ in range(20)]
        medias = []
        for _ in range(15):
            fitness = [ind.potencia_kw for ind in poblacion]
            medias.append(float(np.mean(fitness)))
            poblacion = _evolucionar_poblacion(
                poblacion, fitness, gen, _cruzar_arma, _mutar_arma, GenomaArma.aleatorio
            )
        # última generación
        fitness_final = [ind.potencia_kw for ind in poblacion]
        medias.append(float(np.mean(fitness_final)))

        assert medias[-1] > medias[0]
        # Converge cerca del límite superior del gen (100.0).
        hi = GenomaArma.LIMITES["potencia_kw"][1]
        assert medias[-1] > hi * 0.7

    def test_elitismo_nunca_pierde_al_mejor_individuo(self):
        gen = nuevo_generador(55)
        poblacion = [GenomaArma.aleatorio(gen) for _ in range(10)]
        fitness = [ind.potencia_kw for ind in poblacion]
        mejor_antes = max(fitness)
        nueva = _evolucionar_poblacion(poblacion, fitness, gen, _cruzar_arma, _mutar_arma, GenomaArma.aleatorio)
        # El elite (elitismo=1 por defecto) es una copia exacta del mejor.
        assert any(ind.potencia_kw == pytest.approx(mejor_antes) for ind in nueva)


class TestReproducibilidad:
    """Misma semilla, mismo resultado byte a byte — criterio de aceptación
    explícito del ítem ('la frontera de Pareto es reproducible con la misma
    semilla')."""

    def test_misma_semilla_misma_frontera_y_mismo_fitness(self):
        r1 = coevolucionar(
            n_generaciones=3, tam_poblacion=5, replicas_por_evaluacion=2, t_max_s=4.0, seed=2026
        )
        r2 = coevolucionar(
            n_generaciones=3, tam_poblacion=5, replicas_por_evaluacion=2, t_max_s=4.0, seed=2026
        )
        assert r1.fitness_arma_por_generacion == r2.fitness_arma_por_generacion
        assert r1.fitness_defensa_por_generacion == r2.fitness_defensa_por_generacion
        assert r1.frontera_arma() == r2.frontera_arma()
        assert r1.frontera_defensa() == r2.frontera_defensa()
        assert resumen_json(r1) == resumen_json(r2)

    def test_semillas_distintas_dan_resultados_distintos(self):
        r1 = coevolucionar(
            n_generaciones=3, tam_poblacion=5, replicas_por_evaluacion=2, t_max_s=4.0, seed=1
        )
        r2 = coevolucionar(
            n_generaciones=3, tam_poblacion=5, replicas_por_evaluacion=2, t_max_s=4.0, seed=2
        )
        # No exige que TODO difiera (podría coincidir por casualidad en
        # algún valor), pero la frontera completa idéntica sería una señal
        # de que la semilla no está gobernando nada.
        assert r1.frontera_arma() != r2.frontera_arma() or r1.frontera_defensa() != r2.frontera_defensa()


class TestCallbackDeProgreso:
    """on_generacion: el gancho que el job en background (frontend,
    "Laboratorio") usa para reportar avance sin esperar a que termine toda
    la corrida — no debe cambiar el resultado determinista del algoritmo."""

    def test_se_llama_una_vez_por_generacion_con_el_indice_correcto(self):
        llamadas = []
        coevolucionar(
            n_generaciones=3, tam_poblacion=4, replicas_por_evaluacion=2, t_max_s=4.0,
            seed=7, on_generacion=lambda i, r: llamadas.append(i),
        )
        assert llamadas == [0, 1, 2]

    def test_el_resultado_parcial_ya_tiene_la_generacion_actual_agregada(self):
        longitudes = []
        coevolucionar(
            n_generaciones=3, tam_poblacion=4, replicas_por_evaluacion=2, t_max_s=4.0,
            seed=7, on_generacion=lambda i, r: longitudes.append(len(r.fitness_arma_por_generacion)),
        )
        assert longitudes == [1, 2, 3]

    def test_no_cambia_el_resultado_final_ni_la_reproducibilidad(self):
        r_sin_callback = coevolucionar(
            n_generaciones=3, tam_poblacion=4, replicas_por_evaluacion=2, t_max_s=4.0, seed=11,
        )
        r_con_callback = coevolucionar(
            n_generaciones=3, tam_poblacion=4, replicas_por_evaluacion=2, t_max_s=4.0, seed=11,
            on_generacion=lambda i, r: None,
        )
        assert resumen_json(r_sin_callback) == resumen_json(r_con_callback)


class TestEvaluarEnfrentamiento:
    def test_devuelve_una_fraccion_valida(self):
        arma = GenomaArma(potencia_kw=60.0, apertura_cono=15.0, duty_cycle=0.01)
        defensa = GenomaDefensa(formacion_idx=FORMACIONES.index("cuadrada"), cantidad=20)
        frac = evaluar_enfrentamiento(arma, defensa, replicas=3, t_max_s=6.0, semilla=10)
        assert 0.0 <= frac <= 1.0

    def test_mas_potencia_da_fraccion_media_mayor_o_igual(self):
        """No determinista dron a dron (factor de acoplamiento aleatorio),
        pero con réplicas suficientes la MEDIA debe respetar la monotonía
        del modelo Friis (P≥0 creciente en potencia) — mismo criterio que
        ``test_ic_contiene_probabilidad_teorica`` en test_experiments.py."""
        defensa = GenomaDefensa(formacion_idx=FORMACIONES.index("cuadrada"), cantidad=20)
        debil = GenomaArma(potencia_kw=10.0, apertura_cono=15.0, duty_cycle=0.01)
        fuerte = GenomaArma(potencia_kw=100.0, apertura_cono=15.0, duty_cycle=0.01)

        frac_debil = np.mean(
            [evaluar_enfrentamiento(debil, defensa, replicas=1, t_max_s=6.0, semilla=100 + i) for i in range(25)]
        )
        frac_fuerte = np.mean(
            [evaluar_enfrentamiento(fuerte, defensa, replicas=1, t_max_s=6.0, semilla=100 + i) for i in range(25)]
        )
        assert frac_fuerte >= frac_debil

    def test_duty_cycle_bajo_da_fraccion_mayor_a_igual_potencia(self):
        """La comparación CW-vs-pulsado de la §5 del paper de referencia: a
        igual potencia PROMEDIO (mismo costo energético), bajar el duty
        cycle sube el campo pico y por lo tanto la probabilidad de baja."""
        defensa = GenomaDefensa(formacion_idx=FORMACIONES.index("cuadrada"), cantidad=20)
        cw = GenomaArma(potencia_kw=60.0, apertura_cono=15.0, duty_cycle=1.0)
        pulsado = GenomaArma(potencia_kw=60.0, apertura_cono=15.0, duty_cycle=0.01)

        frac_cw = np.mean(
            [evaluar_enfrentamiento(cw, defensa, replicas=1, t_max_s=6.0, semilla=200 + i) for i in range(25)]
        )
        frac_pulsado = np.mean(
            [evaluar_enfrentamiento(pulsado, defensa, replicas=1, t_max_s=6.0, semilla=200 + i) for i in range(25)]
        )
        assert frac_pulsado >= frac_cw

    def test_formacion_dispersa_sobrevive_mejor_que_compacta(self):
        """Circular (donut disperso, radio fijo ~200m) debe perder menos
        que cuadrada (formación compacta) frente al mismo arma de haz
        angosto — dispersión como contramedida real contra un arma
        direccional, ver docstring de DISTANCIA_COMBATE_M."""
        arma = GenomaArma(potencia_kw=60.0, apertura_cono=15.0, duty_cycle=0.01)
        compacta = GenomaDefensa(formacion_idx=FORMACIONES.index("cuadrada"), cantidad=20)
        dispersa = GenomaDefensa(formacion_idx=FORMACIONES.index("circular"), cantidad=20)

        frac_compacta = np.mean(
            [evaluar_enfrentamiento(arma, compacta, replicas=1, t_max_s=6.0, semilla=300 + i) for i in range(25)]
        )
        frac_dispersa = np.mean(
            [evaluar_enfrentamiento(arma, dispersa, replicas=1, t_max_s=6.0, semilla=300 + i) for i in range(25)]
        )
        assert frac_dispersa <= frac_compacta


@pytest.mark.slow
class TestMejoraFrenteAOponenteFijo:
    """Criterio de aceptación del ítem ('una corrida corta mejora el
    fitness de cada población y degrada el del adversario'), medido con un
    oponente FIJO para que la comparación entre generaciones no esté
    contaminada por un rival que también evoluciona (ver docstring del
    módulo)."""

    def test_arma_mejora_contra_defensa_fija(self):
        defensa_fija = GenomaDefensa(formacion_idx=FORMACIONES.index("cuadrada"), cantidad=20)
        fitness_por_gen, _ = evolucionar_arma_contra_defensa_fija(
            defensa_fija, n_generaciones=6, tam_poblacion=10, replicas_por_evaluacion=6,
            t_max_s=6.0, seed=42,
        )
        assert fitness_por_gen[-1] >= fitness_por_gen[0]

    def test_defensa_mejora_contra_arma_fija(self):
        # Arma con haz angosto y pulsado: castiga fuerte a la formación
        # compacta con la que arrancan los genomas de defensa al azar, así
        # que hay margen real de mejora huyendo hacia formaciones dispersas.
        arma_fija = GenomaArma(potencia_kw=80.0, apertura_cono=15.0, duty_cycle=0.01)
        fitness_por_gen, mejor = evolucionar_defensa_contra_arma_fija(
            arma_fija, n_generaciones=6, tam_poblacion=10, replicas_por_evaluacion=6,
            t_max_s=6.0, seed=42,
        )
        assert fitness_por_gen[-1] >= fitness_por_gen[0]


class TestCoevolucionCompleta:
    def test_produce_resultado_bien_formado(self):
        r = coevolucionar(n_generaciones=3, tam_poblacion=5, replicas_por_evaluacion=2, t_max_s=4.0, seed=7)
        assert isinstance(r, ResultadoCoevolucion)
        assert len(r.fitness_arma_por_generacion) == 3
        assert len(r.fitness_defensa_por_generacion) == 3
        assert len(r.mejor_arma_por_generacion) == 3
        assert len(r.mejor_defensa_por_generacion) == 3
        for f in r.fitness_arma_por_generacion + r.fitness_defensa_por_generacion:
            assert 0.0 <= f <= 1.0

    def test_resumen_json_es_serializable(self):
        import json

        r = coevolucionar(n_generaciones=2, tam_poblacion=4, replicas_por_evaluacion=2, t_max_s=4.0, seed=7)
        resumen = resumen_json(r)
        json.dumps(resumen)  # no debe lanzar
        assert "frontera_pareto_arma" in resumen
        assert "frontera_pareto_defensa" in resumen
        assert resumen["mejor_arma_final"] is not None
        assert resumen["mejor_defensa_final"] is not None


class TestJobDeCoevolucionEnBackground:
    """El panel "Laboratorio" del frontend corre esto como un job async
    (POST arranca, GET pollea) porque una corrida real tarda demasiado
    para un endpoint síncrono — ver src/api/coevolucion_jobs.py."""

    PARAMS_RAPIDOS = {
        "n_generaciones": 2, "tam_poblacion": 3, "replicas_por_evaluacion": 1,
        "t_max_s": 2.0, "seed": 99,
    }

    def _esperar_job(self, client, job_id, timeout_s=60):
        import time

        limite = time.monotonic() + timeout_s
        while time.monotonic() < limite:
            d = client.get(f"/api/coevolucion/status/{job_id}").json()
            if d["estado"] != "ejecutando":
                return d
            time.sleep(0.5)
        pytest.fail(f"el job {job_id} no terminó dentro de {timeout_s}s")

    def test_arranca_y_termina_completado_con_progreso_y_resultado(self):
        from fastapi.testclient import TestClient

        from src.main import app

        with TestClient(app) as client:
            r = client.post("/api/coevolucion/start", json=self.PARAMS_RAPIDOS)
            assert r.status_code == 200
            job_id = r.json()["job_id"]

            d = self._esperar_job(client, job_id)
            assert d["estado"] == "completado"
            assert d["error"] is None
            assert len(d["progreso"]) == self.PARAMS_RAPIDOS["n_generaciones"]
            assert [p["generacion"] for p in d["progreso"]] == [0, 1]
            assert "frontera_pareto_arma" in d["resultado"]
            assert "frontera_pareto_defensa" in d["resultado"]

    def test_job_id_inexistente_da_404(self):
        from fastapi.testclient import TestClient

        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/api/coevolucion/status/no-existe-este-id")
            assert resp.status_code == 404

    def test_rechaza_parametros_fuera_de_rango(self):
        from fastapi.testclient import TestClient

        from src.main import app

        with TestClient(app) as client:
            assert client.post("/api/coevolucion/start", json={"n_generaciones": 999}).status_code == 422
            assert client.post("/api/coevolucion/start", json={"tam_poblacion": 1}).status_code == 422
            assert client.post("/api/coevolucion/start", json={"t_max_s": 1000}).status_code == 422
