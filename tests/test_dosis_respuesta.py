"""Pruebas de la curva dosis-respuesta por máxima verosimilitud (P2-B).

Antes de aplicar el ajustador al motor real, se valida contra datos
SINTÉTICOS con parámetros conocidos — misma disciplina que P2-A validó su
estimador de Sobol contra la función de Ishigami antes de usarlo sobre el
modelo de daño: sin esa validación, los parámetros recuperados serían
números sin respaldo.
"""

from __future__ import annotations

import numpy as np
import pytest

from src import config as cfg
from src.engine.experiments import (
    _ajustar_una_vez,
    _logistic_irls,
    ajustar_dosis_respuesta,
    comparar_contra_calibracion,
    experimento_dosis_respuesta,
    generar_datos_dosis_respuesta,
)
from src.utils.reproducibilidad import nuevo_generador


class TestIRLSContraDatosSinteticos:
    """El optimizador, antes de confiar en él."""

    def test_recupera_parametros_logisticos_conocidos(self):
        rng = np.random.default_rng(42)
        beta0_real, beta1_real = -3.0, 0.05
        x = rng.uniform(-50, 150, 4000)
        p = 1.0 / (1.0 + np.exp(-(beta0_real + beta1_real * x)))
        y = (rng.random(4000) < p).astype(float)

        beta = _logistic_irls(x, y)
        assert beta[0] == pytest.approx(beta0_real, abs=0.15)
        assert beta[1] == pytest.approx(beta1_real, abs=0.01)

    def test_converge_en_pocas_iteraciones(self):
        """La log-verosimilitud logística es cóncava: Newton-Raphson debe
        converger rápido, no acercarse al límite de iteraciones.
        """
        rng = np.random.default_rng(7)
        x = rng.uniform(0, 100, 2000)
        p = 1.0 / (1.0 + np.exp(-(0.1 * (x - 50))))
        y = (rng.random(2000) < p).astype(float)

        # Con muy pocas iteraciones permitidas, ya debe estar cerca del
        # óptimo (si no convergiera rápido, este test fallaría).
        beta_pocas = _logistic_irls(x, y, iteraciones=8)
        beta_muchas = _logistic_irls(x, y, iteraciones=200)
        assert beta_pocas == pytest.approx(beta_muchas, abs=1e-6)

    def test_log_logistica_es_logistica_en_ln_e(self):
        """Confirma la reparametrización: ajustar log-logística sobre
        (E, kill) equivale a ajustar logística sobre (ln E, kill).
        """
        rng = np.random.default_rng(11)
        e50_real, b_real = 300.0, 4.0
        E = rng.uniform(50, 900, 5000)
        p = 1.0 / (1.0 + (e50_real / E) ** b_real)
        y = (rng.random(5000) < p).astype(float)

        e50_fit, b_fit, sigma_fit = _ajustar_una_vez(E, y, "log_logistica")
        assert e50_fit == pytest.approx(e50_real, rel=0.05)
        assert b_fit == pytest.approx(b_real, rel=0.08)
        assert sigma_fit == pytest.approx(e50_fit / b_fit)

    def test_familia_logistica_recupera_e0_y_k(self):
        rng = np.random.default_rng(13)
        e0_real, k_real = 20.0, 0.6
        E = rng.uniform(0, 60, 4000)
        p = 1.0 / (1.0 + np.exp(-k_real * (E - e0_real)))
        y = (rng.random(4000) < p).astype(float)

        e0_fit, k_fit, sigma_fit = _ajustar_una_vez(E, y, "logistica")
        assert e0_fit == pytest.approx(e0_real, abs=1.5)
        assert k_fit == pytest.approx(k_real, rel=0.1)
        assert sigma_fit == pytest.approx(1.0 / k_fit)


class TestBootstrapDeLaCurva:
    def test_ic_contiene_los_parametros_reales(self):
        rng = np.random.default_rng(99)
        e50_real, b_real = 400.0, 3.0
        E = rng.uniform(50, 900, 4000)
        p = 1.0 / (1.0 + (e50_real / E) ** b_real)
        y = (rng.random(4000) < p).astype(float)

        ajuste = ajustar_dosis_respuesta(E, y, n_bootstrap=500, seed=1)
        lo_e, hi_e = ajuste["ic95_e50_v_m"]
        lo_b, hi_b = ajuste["ic95_parametro_forma"]
        assert lo_e <= e50_real <= hi_e
        assert lo_b <= b_real <= hi_b

    def test_reproducible_con_la_misma_semilla(self):
        rng = np.random.default_rng(5)
        E = rng.uniform(50, 900, 1000)
        p = 1.0 / (1.0 + (400.0 / E) ** 3.0)
        y = (rng.random(1000) < p).astype(float)

        a = ajustar_dosis_respuesta(E, y, n_bootstrap=200, seed=42)
        b = ajustar_dosis_respuesta(E, y, n_bootstrap=200, seed=42)
        assert a == b

    def test_ic_se_estrecha_con_mas_observaciones(self):
        def ancho_ic(n: int) -> float:
            rng = np.random.default_rng(21)
            E = rng.uniform(50, 900, n)
            p = 1.0 / (1.0 + (400.0 / E) ** 3.0)
            y = (rng.random(n) < p).astype(float)
            ajuste = ajustar_dosis_respuesta(E, y, n_bootstrap=300, seed=1)
            lo, hi = ajuste["ic95_e50_v_m"]
            return hi - lo

        assert ancho_ic(500) > ancho_ic(5000)


class TestComparacionContraCalibracion:
    """El campo que hay que leer primero — y debe poder fallar."""

    def test_detecta_cuando_no_coincide(self):
        """Control negativo: datos generados con parámetros MUY distintos
        a los configurados deben marcar la discrepancia.
        """
        rng = np.random.default_rng(1)
        E = rng.uniform(50, 900, 3000)
        p = 1.0 / (1.0 + (700.0 / E) ** 3.5)  # muy distinto a HPM_LOGLOGISTIC_E50_V_M
        y = (rng.random(3000) < p).astype(float)

        ajuste = ajustar_dosis_respuesta(E, y, n_bootstrap=500, seed=1)
        comparacion = comparar_contra_calibracion(ajuste)
        assert comparacion["recupera_la_calibracion"] is False
        assert comparacion["e50_dentro_del_ic"] is False

    def test_reporta_los_parametros_configurados_actuales(self):
        rng = np.random.default_rng(1)
        E = rng.uniform(50, 900, 500)
        y = (rng.random(500) < 0.5).astype(float)
        ajuste = ajustar_dosis_respuesta(E, y, n_bootstrap=100, seed=1)
        comparacion = comparar_contra_calibracion(ajuste)
        assert comparacion["e50_configurado"] == cfg.HPM_LOGLOGISTIC_E50_V_M
        assert comparacion["parametro_forma_configurado"] == cfg.HPM_LOGLOGISTIC_B


class TestGeneracionDeDatosConElMotorReal:
    def test_campo_decrece_con_la_distancia(self):
        campos, _ = generar_datos_dosis_respuesta(
            distancias_m=[20.0, 40.0, 80.0], n_por_distancia=5, seed=1
        )
        # 5 observaciones por distancia, en orden.
        assert campos[0] > campos[5] > campos[10]

    def test_kills_son_binarios(self):
        _, kills = generar_datos_dosis_respuesta(
            distancias_m=[15.0, 60.0], n_por_distancia=20, seed=2
        )
        assert set(np.unique(kills)).issubset({0.0, 1.0})

    def test_huella_de_susceptibilidad_fijada_no_sorteada(self):
        """Todos los drones generados usan el MISMO cable resonante y la
        MISMA polarización óptima — sin esto, el ajuste mezclaría la
        varianza de la sigmoide con la del acoplamiento (P2-04).
        """
        campos, _ = generar_datos_dosis_respuesta(
            distancias_m=[30.0], n_por_distancia=50, seed=3
        )
        # A la MISMA distancia, con huella fijada, el campo debe ser
        # idéntico en las 50 observaciones (varía solo el sorteo de kill).
        assert len(set(np.round(campos, 6))) == 1

    def test_reproducible(self):
        a = generar_datos_dosis_respuesta(distancias_m=[20.0, 40.0], n_por_distancia=30, seed=7)
        b = generar_datos_dosis_respuesta(distancias_m=[20.0, 40.0], n_por_distancia=30, seed=7)
        assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


class TestExperimentoEndToEnd:
    """El criterio de aceptación del ítem: corriendo contra el propio
    modelo, el ajuste recupera los valores de entrada dentro del IC.
    """

    def test_recupera_la_calibracion_del_motor_real(self):
        resultado = experimento_dosis_respuesta(n_por_distancia=400, n_bootstrap=600, seed=2026)
        assert resultado["comparacion"]["recupera_la_calibracion"] is True
        assert resultado["ajuste"]["e50_v_m"] == pytest.approx(
            cfg.HPM_LOGLOGISTIC_E50_V_M, rel=0.1
        )
        assert resultado["ajuste"]["parametro_forma"] == pytest.approx(
            cfg.HPM_LOGLOGISTIC_B, rel=0.15
        )

    def test_serializable(self):
        import json
        r = experimento_dosis_respuesta(n_por_distancia=50, n_bootstrap=100, seed=1)
        json.dumps(r)


class TestEndpointDosisRespuesta:
    def test_responde_con_las_claves_esperadas(self):
        from fastapi.testclient import TestClient
        from src.main import app

        with TestClient(app) as client:
            resp = client.get(
                "/api/dosis-respuesta",
                params={"n_por_distancia": 50, "n_bootstrap": 100},
            )
            assert resp.status_code == 200
            d = resp.json()
            assert "ajuste" in d and "comparacion" in d
            assert "recupera_la_calibracion" in d["comparacion"]

    def test_rechaza_parametros_fuera_de_rango(self):
        from fastapi.testclient import TestClient
        from src.main import app

        with TestClient(app) as client:
            assert client.get(
                "/api/dosis-respuesta", params={"n_por_distancia": 1}
            ).status_code == 400
            assert client.get(
                "/api/dosis-respuesta", params={"n_bootstrap": 10}
            ).status_code == 400
