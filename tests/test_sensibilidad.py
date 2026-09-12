"""Pruebas del análisis de sensibilidad global (P2-A).

El test que decide si este módulo sirve para algo es
``TestEstimadorSobolContraAnalitico``: valida el estimador contra la función de
Ishigami, que tiene índices de Sobol **analíticos**. Sin esa validación, los
índices que produzca el módulo sobre el modelo de daño serían números sin
respaldo — y el punto entero de P2-A es dejar de producir números sin respaldo.
"""

import math

import numpy as np
import pytest

from src import config as cfg
from src.engine.sensitivity import (
    ParametroSensibilidad,
    espacio_parametros_dano,
    indices_sobol,
    informe_sensibilidad,
    probabilidad_baja_desde_vector,
    screening_morris,
)


# ═══════════════════════════════════════════════════════════════════════════
# Función de Ishigami: el banco de pruebas estándar, con índices analíticos
# ═══════════════════════════════════════════════════════════════════════════

_A, _B = 7.0, 0.1


def _ishigami(U: np.ndarray) -> np.ndarray:
    """f = sin(x₁) + a·sin²(x₂) + b·x₃⁴·sin(x₁), con xᵢ ~ U[-π, π]."""
    X = -math.pi + 2 * math.pi * np.atleast_2d(U)
    x1, x2, x3 = X[:, 0], X[:, 1], X[:, 2]
    return np.sin(x1) + _A * np.sin(x2) ** 2 + _B * x3**4 * np.sin(x1)


def _indices_analiticos_ishigami() -> dict[str, tuple[float, float]]:
    """(S₁, S_T) exactos de Ishigami. Derivación estándar de la literatura."""
    v1 = 0.5 * (1 + _B * math.pi**4 / 5) ** 2
    v2 = _A**2 / 8
    vt3 = 8 * _B**2 * math.pi**8 / 225
    v = _A**2 / 8 + _B * math.pi**4 / 5 + _B**2 * math.pi**8 / 18 + 0.5
    return {
        "x1": (v1 / v, (v1 + vt3) / v),
        "x2": (v2 / v, v2 / v),
        # x3 es el caso DURO: efecto principal exactamente 0, efecto total no.
        # Solo actúa por interacción con x1. Un estimador mal implementado
        # suele darle S₁ apreciable o S_T ≈ 0.
        "x3": (0.0, vt3 / v),
    }


class TestEstimadorSobolContraAnalitico:
    """Validación del estimador de Saltelli contra índices exactos."""

    def test_recupera_los_indices_de_ishigami(self):
        analitico = _indices_analiticos_ishigami()
        res = indices_sobol(0.0, n_base=32768, modelo=_ishigami, k_dim=3, seed=7)
        por_nombre = {d["nombre"]: d for d in res["parametros"]}

        for nombre, (s1_a, st_a) in analitico.items():
            d = por_nombre[nombre]
            assert d["s1"] == pytest.approx(s1_a, abs=0.025), (
                f"S₁ de {nombre}: {d['s1']} vs analítico {s1_a}"
            )
            assert d["st"] == pytest.approx(st_a, abs=0.025), (
                f"S_T de {nombre}: {d['st']} vs analítico {st_a}"
            )

    def test_captura_el_caso_duro_de_x3(self):
        """x₃ tiene S₁ = 0 exacto pero S_T ≈ 0.244: puro efecto por interacción.

        Es el test que distingue un estimador correcto de uno que confunde
        efecto principal con total.
        """
        res = indices_sobol(0.0, n_base=32768, modelo=_ishigami, k_dim=3, seed=7)
        x3 = next(d for d in res["parametros"] if d["nombre"] == "x3")
        assert abs(x3["s1"]) < 0.02
        assert x3["st"] > 0.2
        assert x3["interaccion"] > 0.2

    def test_estima_bien_la_varianza_de_la_salida(self):
        v_analitica = _A**2 / 8 + _B * math.pi**4 / 5 + _B**2 * math.pi**8 / 18 + 0.5
        res = indices_sobol(0.0, n_base=16384, modelo=_ishigami, k_dim=3, seed=7)
        assert res["varianza_salida"] == pytest.approx(v_analitica, rel=0.03)

    def test_converge_al_aumentar_n(self):
        """El error debe bajar con N. Es la propiedad que justifica pagar más cómputo."""
        analitico = _indices_analiticos_ishigami()

        def error_total(n: int) -> float:
            res = indices_sobol(0.0, n_base=n, modelo=_ishigami, k_dim=3, seed=7)
            por_nombre = {d["nombre"]: d for d in res["parametros"]}
            return sum(
                abs(por_nombre[k]["s1"] - v[0]) + abs(por_nombre[k]["st"] - v[1])
                for k, v in analitico.items()
            )

        assert error_total(32768) < error_total(1024)

    def test_st_nunca_menor_que_s1_en_parametros_relevantes(self):
        """S_T ≥ S₁ es una propiedad del método, no del modelo."""
        res = indices_sobol(0.0, n_base=8192, modelo=_ishigami, k_dim=3, seed=7)
        for d in res["parametros"]:
            if d["st"] > 0.05:  # fuera del ruido
                assert d["st"] >= d["s1"] - 0.02

    def test_modelo_sin_varianza_no_rompe(self):
        """Un modelo constante ⇒ varianza 0 ⇒ índices 0, sin división por cero."""
        res = indices_sobol(
            0.0, n_base=64, modelo=lambda U: np.zeros(np.atleast_2d(U).shape[0]), k_dim=3
        )
        assert all(d["s1"] == 0.0 and d["st"] == 0.0 for d in res["parametros"])

    def test_requiere_k_dim_al_inyectar_modelo(self):
        with pytest.raises(ValueError, match="k_dim"):
            indices_sobol(0.0, modelo=_ishigami)


class TestEspacioDeParametros:
    def test_escalado_al_rango(self):
        p = ParametroSensibilidad("x", 10.0, 20.0)
        assert p.escalar(0.0) == 10.0
        assert p.escalar(1.0) == 20.0
        assert p.escalar(0.5) == 15.0

    def test_incluye_los_cinco_umbrales_y_los_del_paper(self):
        nombres = {p.nombre for p in espacio_parametros_dano()}
        for nombre in cfg.HPM_SUBSISTEMAS:
            assert f"e50_{nombre}" in nombres
        for esperado in ("potencia_kw", "diametro_plato_m", "eficiencia_apertura",
                         "error_apuntado_deg", "angulo_polarizacion_rad"):
            assert esperado in nombres

    def test_marca_los_no_calibrados(self):
        """La columna ``calibrado`` es lo que hace útil el informe."""
        params = {p.nombre: p for p in espacio_parametros_dano()}
        assert params["coupling_field_efficiency"].calibrado is False
        assert params["pulse_duration_ns"].calibrado is False
        assert params["potencia_kw"].calibrado is True


class TestFuncionDeModelo:
    def test_decrece_con_la_distancia(self):
        base = {p.nombre: p.escalar(0.5) for p in espacio_parametros_dano()}
        base["angulo_polarizacion_rad"] = 0.0  # acoplamiento óptimo
        p20 = probabilidad_baja_desde_vector(base, 20.0)
        p60 = probabilidad_baja_desde_vector(base, 60.0)
        assert p20 > p60

    def test_en_rango_0_1(self):
        for u in (0.0, 0.25, 0.5, 0.75, 1.0):
            valores = {p.nombre: p.escalar(u) for p in espacio_parametros_dano()}
            assert 0.0 <= probabilidad_baja_desde_vector(valores, 30.0) <= 1.0

    def test_desapunte_extremo_deja_el_PISO_de_la_sigmoide(self):
        """⚠ DEFECTO DOCUMENTADO: a campo CERO la probabilidad NO es cero.

        Fuera del haz el taper va a 0, así que el campo incidente es
        exactamente 0 — y sin embargo el OR-gate devuelve **3.30 %**.

        CAUSA RAÍZ: la sigmoide logística opera sobre ``E`` y tiene soporte en
        todo ℝ, pero el campo eléctrico es una magnitud POSITIVA. ``P(0) ≠ 0``
        es una consecuencia estructural de haber elegido una logística en ``E``
        en vez de en ``ln E``.

        Magnitud del artefacto (medido, ver docs/FISICA_Y_MATEMATICA.md §3.7):
          · modelo agregado:     P(0) = 2.30 %
          · OR-gate 5 subsistemas: P(0) = 3.30 %
          · más allá de ~97 m, MÁS DE LA MITAD de la probabilidad reportada es
            piso, no física
          · a 700 m (el rango de combate por defecto) el **90.7 %** del número
            reportado es artefacto

        Este test fija el defecto para que no se pierda. **Si falla, alguien lo
        corrigió** (ítem P1-F del checklist) y hay que actualizar el test, la
        calibración y re-correr la sensibilidad.
        """
        valores = {p.nombre: p.escalar(0.5) for p in espacio_parametros_dano()}
        valores["error_apuntado_deg"] = 90.0
        p_fuera_del_haz = probabilidad_baja_desde_vector(valores, 30.0)
        assert p_fuera_del_haz > 0.0, "si es 0, el piso se corrigió: ver P1-F"
        assert p_fuera_del_haz == pytest.approx(0.033, abs=0.002)

    def test_el_piso_es_independiente_de_la_distancia(self):
        """Confirma que es un piso y no un decaimiento: a 30 m y a 30 km, igual.

        Es la firma de un artefacto: una cantidad física que no depende de la
        distancia cuando no hay campo.
        """
        valores = {p.nombre: p.escalar(0.5) for p in espacio_parametros_dano()}
        valores["error_apuntado_deg"] = 90.0
        cerca = probabilidad_baja_desde_vector(valores, 30.0)
        lejos = probabilidad_baja_desde_vector(valores, 30_000.0)
        assert cerca == pytest.approx(lejos, abs=1e-12)


class TestScreeningMorris:
    def test_produce_un_efecto_por_parametro(self):
        res = screening_morris(30.0, r=8)
        assert len(res["parametros"]) == len(espacio_parametros_dano())
        assert all(d["mu_estrella"] >= 0 for d in res["parametros"])

    def test_ordenado_por_importancia(self):
        res = screening_morris(30.0, r=8)
        mus = [d["mu_estrella"] for d in res["parametros"]]
        assert mus == sorted(mus, reverse=True)

    def test_coste_es_r_por_k_mas_1(self):
        r, k = 8, len(espacio_parametros_dano())
        res = screening_morris(30.0, r=r)
        assert res["evaluaciones"] == r * (k + 1)

    def test_reproducible(self):
        a = screening_morris(30.0, r=6, seed=42)
        b = screening_morris(30.0, r=6, seed=42)
        assert a["parametros"] == b["parametros"]

    def test_trayectorias_dentro_del_cubo_unitario(self):
        """Salirse del cubo daría parámetros fuera de su rango declarado."""
        from src.engine.sensitivity import _trayectorias_morris
        from src.utils.reproducibilidad import nuevo_generador

        U = _trayectorias_morris(13, 20, 8, nuevo_generador(1))
        assert U.min() >= 0.0 and U.max() <= 1.0


class TestSensibilidadDelModeloDeDano:
    """Los resultados sustantivos. Fijados para detectar deriva del modelo."""

    def test_la_polarizacion_domina(self):
        """S₁ ≈ 0.43-0.57 y S_T ≈ 0.58-0.66 según la distancia.

        Confirma por descomposición de varianza lo que el paper concluye
        cualitativamente y lo que la atribución manual de §3.6 había estimado
        (55 % del CV). La diferencia es que ahora es una FRACCIÓN DE VARIANZA,
        que suma, en vez de una diferencia de varianzas, que no.
        """
        res = indices_sobol(30.0, n_base=1024, seed=2026)
        top = res["parametros"][0]
        assert top["nombre"] == "angulo_polarizacion_rad"
        assert top["st"] > 0.5

    def test_dos_parametros_no_calibrados_dominan_tras_la_polarizacion(self):
        """AMENAZA A LA VALIDEZ, cuantificada.

        ``coupling_field_efficiency`` (el parámetro PROVISIONAL de P1-C, que
        está bloqueado) y ``pulse_duration_ns`` (la extensión Wunsch-Bell, que
        no viene del paper) son el 2.º y 3.º en efecto total. Juntos aportan
        entre el 43 % y el 59 % de la varianza según la distancia.

        Es el hallazgo central de P2-A: cualquier conclusión del modelo de
        subsistemas lleva dentro una contribución de varianza grande de dos
        parámetros que no están validados contra datos.
        """
        res = indices_sobol(30.0, n_base=1024, seed=2026)
        no_calibrados = [d for d in res["parametros"] if not d["calibrado"]]
        assert len(no_calibrados) == 2
        suma_st = sum(d["st"] for d in no_calibrados)
        assert suma_st > 0.30, f"S_T de los no calibrados: {suma_st}"

    def test_los_umbrales_publicados_aportan_poco(self):
        """Los cinco E₅₀ tienen S_T pequeño — su rango ±15 % es estrecho.

        Consecuencia práctica: afinar los umbrales importa mucho menos que
        clavar el acoplamiento. Orienta dónde poner el esfuerzo de calibración.
        """
        res = indices_sobol(30.0, n_base=1024, seed=2026)
        for d in res["parametros"]:
            if d["nombre"].startswith("e50_"):
                assert d["st"] < 0.10

    def test_longitud_de_cable_tiene_efecto_exactamente_nulo(self):
        """DETECTOR: S₁ = S_T = 0 EXACTO porque el parámetro no entra al modelo.

        El realce por resonancia está omitido a propósito mientras P1-C esté
        bloqueado (docs/FISICA_Y_MATEMATICA.md §3.6), así que
        ``longitud_cable_m`` no tiene camino hacia la salida. Se deja en el
        espacio de parámetros para que el cero exacto lo delate.

        **Si este test falla, alguien conectó la resonancia** — y entonces hay
        que re-correr el análisis de sensibilidad completo, porque el
        acoplamiento gana una segunda fuente de variabilidad.
        """
        res = indices_sobol(30.0, n_base=512, seed=2026)
        cable = next(d for d in res["parametros"] if d["nombre"] == "longitud_cable_m")
        assert cable["s1"] == 0.0
        assert cable["st"] == 0.0

    def test_hay_interacciones_relevantes(self):
        """ΣS₁ < 0.9 ⇒ el modelo no es aditivo: las interacciones importan.

        Justifica haber calculado S_T y no solo S₁: quedarse en los efectos
        principales perdería entre el 13 % y el 31 % de la varianza.
        """
        res = indices_sobol(30.0, n_base=1024, seed=2026)
        assert res["suma_s1"] < 0.95
        assert res["fraccion_interaccion"] > 0.05

    def test_morris_y_sobol_coinciden_en_los_dominantes(self):
        """Chequeo de sanidad interno: si los dos métodos discrepan en QUIÉN
        domina, uno está mal muestreado y el informe no es de fiar."""
        inf = informe_sensibilidad(distancia_m=30.0, n_base=512, r_morris=30)
        assert inf["coherencia_morris_sobol"]["coherente"], (
            inf["coherencia_morris_sobol"]
        )

    def test_el_informe_reporta_las_amenazas(self):
        inf = informe_sensibilidad(distancia_m=30.0, n_base=512, r_morris=20)
        nombres = {a["nombre"] for a in inf["amenazas_a_la_validez"]}
        assert "coupling_field_efficiency" in nombres

    def test_informe_serializable(self):
        import json
        json.dumps(informe_sensibilidad(distancia_m=30.0, n_base=128, r_morris=8))


class TestEndpointSensibilidad:
    def test_responde_con_las_claves_esperadas(self):
        from fastapi.testclient import TestClient
        from src.main import app

        with TestClient(app) as client:
            resp = client.get(
                "/api/sensibilidad",
                params={"distancia_m": 30.0, "n_base": 64, "r_morris": 6},
            )
            assert resp.status_code == 200
            d = resp.json()
            for clave in ("morris", "sobol", "dominantes",
                          "amenazas_a_la_validez", "coherencia_morris_sobol"):
                assert clave in d
            assert len(d["sobol"]["parametros"]) == 13

    def test_rechaza_parametros_fuera_de_rango(self):
        from fastapi.testclient import TestClient
        from src.main import app

        with TestClient(app) as client:
            assert client.get("/api/sensibilidad", params={"n_base": 1}).status_code == 400
            assert client.get("/api/sensibilidad", params={"r_morris": 999}).status_code == 400
            assert client.get(
                "/api/sensibilidad", params={"distancia_m": -5}
            ).status_code == 400
