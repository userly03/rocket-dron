"""
Test de regresión de la calibración física (P1-D, CHECKLIST_MEJORAS.md).

Toda la credibilidad física del proyecto descansa en dos puntos de datos
publicados en arXiv:2602.08477 (cañón HPM de 25kW CW, plato parabólico de
60cm — 21.2 dBi — a 2.45GHz). De ahí salieron ``HPM_E_THRESHOLD_V_M=500`` y
``HPM_SIGMOID_STEEPNESS=0.0075`` (ver docs/FISICA_Y_MATEMATICA.md §3.4).
Antes de este archivo, esa calibración vivía solo en un comentario y en una
tabla del documento: nada impedía que un cambio futuro de un default
(umbral, pendiente, apertura del cono, duty cycle) la invalidara en
silencio. Este archivo la convierte en algo que puede fallar un build.

Hay DOS comparaciones con propósitos distintos, y este archivo las trata
distinto a propósito (ver ``src.engine.validation.verificar_calibracion``
para la justificación completa):

- Contra la fotografía DOCUMENTADA del propio simulador (43.6%/11.9% a
  20/40m): tolerancia estrecha, porque esos números salen matemáticamente
  del modelo — si se mueven, alguien tocó un default sin querer.
- Contra el PAPER (51.4%/13.1%): la brecha ya está explicada en §3.4 (la
  aproximación de ganancia G≈26000/apertura² no reproduce un plato
  parabólico real de 60cm) y no se trata como fallo — se verifica que el
  orden de magnitud y la forma de la curva se mantengan, no el valor exacto.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.config as config
from src.engine.hpm_engine import calculate_neutralization_probability_friis
from src.engine.validation import (
    CALIBRACION_DISTANCIA_M,
    CALIBRACION_PAPER_CAMPO_E_V_M,
    CALIBRACION_PAPER_PROBABILIDAD,
    TOLERANCIA_REGRESION_SIMULADOR_PP,
    verificar_calibracion,
)


class TestPuntosDeReferencia:
    """Los dos puntos de datos del paper, contra la fotografía del simulador."""

    def test_probabilidad_20m_dentro_de_tolerancia_estrecha(self):
        resultado = verificar_calibracion()
        punto = resultado["puntos"]["20m"]
        assert abs(punto["desviacion_vs_simulador_documentado_pp"]) <= TOLERANCIA_REGRESION_SIMULADOR_PP, (
            f"la calibración a 20m se movió: {punto['probabilidad_calculada']:.4f} "
            f"calculado vs {punto['probabilidad_simulador_documentada']:.4f} "
            "documentado en docs/FISICA_Y_MATEMATICA.md §3.4 — revisar si cambió "
            "HPM_E_THRESHOLD_V_M, HPM_SIGMOID_STEEPNESS, HPM_CONE_APERTURE o "
            "HPM_DUTY_CYCLE"
        )

    def test_probabilidad_40m_dentro_de_tolerancia_estrecha(self):
        resultado = verificar_calibracion()
        punto = resultado["puntos"]["40m"]
        assert abs(punto["desviacion_vs_simulador_documentado_pp"]) <= TOLERANCIA_REGRESION_SIMULADOR_PP, (
            f"la calibración a 40m se movió: {punto['probabilidad_calculada']:.4f} "
            f"calculado vs {punto['probabilidad_simulador_documentada']:.4f} "
            "documentado en docs/FISICA_Y_MATEMATICA.md §3.4 — revisar si cambió "
            "HPM_E_THRESHOLD_V_M, HPM_SIGMOID_STEEPNESS, HPM_CONE_APERTURE o "
            "HPM_DUTY_CYCLE"
        )

    def test_brecha_contra_el_paper_es_informativa_no_bloqueante(self):
        """
        La diferencia contra el paper (51.4%/13.1%) es esperada y está
        documentada en §3.4: el simulador usa una aproximación de ganancia
        (G≈26000/apertura²) que da ~20.6 dBi para un cono de 15°, no los
        21.2 dBi de un plato parabólico real de 60cm. No debe tratarse como
        regresión — solo se exige que la brecha se mantenga acotada (orden
        de magnitud), no que desaparezca.
        """
        resultado = verificar_calibracion()
        for punto in resultado["puntos"].values():
            assert abs(punto["desviacion_vs_paper_pp"]) < 10.0, (
                "la brecha contra el paper creció mucho más allá de lo "
                "documentado en §3.4 — esto ya no es la diferencia esperable "
                "de la aproximación de ganancia, es una regresión real"
            )


class TestFormaDeLaCurva:
    def test_probabilidad_decrece_con_la_distancia(self):
        resultado = verificar_calibracion()
        p20 = resultado["puntos"]["20m"]["probabilidad_calculada"]
        p40 = resultado["puntos"]["40m"]["probabilidad_calculada"]
        assert p20 > p40

    def test_razon_20m_40m_del_orden_de_la_del_paper(self):
        """
        El paper da una razón p(20m)/p(40m) ≈ 51.4/13.1 ≈ 3.92: la curva cae
        rápido con la distancia (ley del inverso del cuadrado dentro de una
        sigmoide). El simulador no reproduce el valor exacto (ver arriba),
        pero la FORMA de la caída —qué tan rápido decrece— debería quedar en
        el mismo orden. Tolerancia amplia (±30%): esto es una verificación
        de forma, no de calibración fina.
        """
        resultado = verificar_calibracion()
        p20 = resultado["puntos"]["20m"]["probabilidad_calculada"]
        p40 = resultado["puntos"]["40m"]["probabilidad_calculada"]
        razon_simulador = p20 / p40
        razon_paper = (
            CALIBRACION_PAPER_PROBABILIDAD["20m"] / CALIBRACION_PAPER_PROBABILIDAD["40m"]
        )
        assert razon_paper * 0.7 <= razon_simulador <= razon_paper * 1.3, (
            f"razón simulador={razon_simulador:.2f} vs razón paper={razon_paper:.2f} "
            "— la forma de la curva se alejó demasiado de la del paper"
        )


class TestCampoElectrico:
    """
    Campo E calculado en los dos puntos, contra los 497.2/248.6 V/m del
    paper. Esos valores del paper son para un plato de 21.2 dBi; el
    simulador usa la aproximación G≈26000/apertura², que con el cono
    default de 15° da ~20.6 dBi — una diferencia sistemática pequeña y
    esperada (medida hoy: ~465.5 V/m y ~232.7 V/m, unos 30-16 V/m por
    debajo del paper). No se fuerza a coincidir exactamente: se verifica
    que la diferencia se mantenga en ese orden, no que desaparezca.
    """

    def test_campo_e_cerca_del_paper_dentro_de_diferencia_esperada_por_ganancia(self):
        resultado = verificar_calibracion()
        for clave, punto in resultado["puntos"].items():
            campo_paper = CALIBRACION_PAPER_CAMPO_E_V_M[clave]
            diferencia_relativa = abs(punto["campo_e_v_m"] - campo_paper) / campo_paper
            # ~20.6 dBi vs ~21.2 dBi de ganancia real es una diferencia de
            # potencia lineal de ~13%, y el campo E escala con la raíz de la
            # potencia, así que la diferencia esperada en E es de ~6-7%.
            # Se deja margen hasta 10% para no ser frágil a redondeos.
            assert diferencia_relativa < 0.10, (
                f"campo E en {clave} se alejó del paper más de lo esperable "
                f"por la diferencia de ganancia de antena: {punto['campo_e_v_m']:.1f} "
                f"V/m calculado vs {campo_paper} V/m del paper "
                f"({diferencia_relativa:.1%} de diferencia)"
            )


class TestDeteccionDeRegresiones:
    """
    Un test de regresión que no puede fallar no sirve de nada. Esta clase
    demuestra que ``verificar_calibracion()`` efectivamente detecta cuando
    alguien toca, uno por uno, cada uno de los cuatro defaults que
    CHECKLIST_MEJORAS.md (P1-D) identifica como capaces de invalidar la
    calibración en silencio.

    Se parchea el ATRIBUTO del módulo ``src.config`` (``monkeypatch.
    setattr(config, "...", valor)``), no una constante importada por nombre:
    ``verificar_calibracion`` lee ``config.HPM_E_THRESHOLD_V_M`` etc. en el
    momento de la llamada y se los pasa explícitamente a
    ``calculate_neutralization_probability_friis`` — precisamente para que
    este parcheo tenga efecto. Si en cambio se parcheara el default de
    parámetro de ``calculate_neutralization_probability_friis`` (``e_threshold:
    float = HPM_E_THRESHOLD_V_M``), no serviría: ese default se captura una
    sola vez al importar ``src.engine.hpm_engine``, antes de que cualquier
    test corra.
    """

    def test_detecta_cambio_de_umbral_de_campo(self, monkeypatch):
        monkeypatch.setattr(config, "HPM_E_THRESHOLD_V_M", config.HPM_E_THRESHOLD_V_M + 50)
        resultado = verificar_calibracion()
        desviacion_maxima = max(
            abs(p["desviacion_vs_simulador_documentado_pp"]) for p in resultado["puntos"].values()
        )
        assert desviacion_maxima > TOLERANCIA_REGRESION_SIMULADOR_PP

    def test_detecta_cambio_de_pendiente_de_sigmoide(self, monkeypatch):
        monkeypatch.setattr(config, "HPM_SIGMOID_STEEPNESS", config.HPM_SIGMOID_STEEPNESS * 1.5)
        resultado = verificar_calibracion()
        desviacion_maxima = max(
            abs(p["desviacion_vs_simulador_documentado_pp"]) for p in resultado["puntos"].values()
        )
        assert desviacion_maxima > TOLERANCIA_REGRESION_SIMULADOR_PP

    def test_detecta_cambio_de_apertura_del_cono(self, monkeypatch):
        monkeypatch.setattr(config, "HPM_CONE_APERTURE", config.HPM_CONE_APERTURE + 5)
        resultado = verificar_calibracion()
        desviacion_maxima = max(
            abs(p["desviacion_vs_simulador_documentado_pp"]) for p in resultado["puntos"].values()
        )
        assert desviacion_maxima > TOLERANCIA_REGRESION_SIMULADOR_PP

    def test_detecta_cambio_de_duty_cycle(self, monkeypatch):
        monkeypatch.setattr(config, "HPM_DUTY_CYCLE", 0.9)
        resultado = verificar_calibracion()
        desviacion_maxima = max(
            abs(p["desviacion_vs_simulador_documentado_pp"]) for p in resultado["puntos"].values()
        )
        assert desviacion_maxima > TOLERANCIA_REGRESION_SIMULADOR_PP


class TestCalculoDirectoSinPasarPorElHelper:
    """
    Verificación independiente: llama directamente a
    ``calculate_neutralization_probability_friis`` (sin pasar por
    ``verificar_calibracion``) para confirmar que el helper no está
    introduciendo un error de cableado (parámetro mal pasado, distancia
    invertida, etc.) que hiciera que el test de arriba pasara por las
    razones equivocadas.
    """

    def test_valores_calculados_directamente_coinciden_con_el_helper(self):
        resultado = verificar_calibracion()
        for clave, distancia in CALIBRACION_DISTANCIA_M.items():
            directo = calculate_neutralization_probability_friis(
                potencia_kw=config.HPM_DEFAULT_POWER,
                distancia=distancia,
                apertura_cono=config.HPM_CONE_APERTURE,
                angulo_offset=0.0,
                e_threshold=config.HPM_E_THRESHOLD_V_M,
                steepness=config.HPM_SIGMOID_STEEPNESS,
                duty_cycle=config.HPM_DUTY_CYCLE,
                cable_length_m=None,
                polarization=None,
            )
            assert directo == pytest.approx(resultado["puntos"][clave]["probabilidad_calculada"])


class TestEndpointCalibracion:
    """GET /api/calibracion — permite verificar en caliente una instancia corriendo."""

    def test_endpoint_responde_200_con_las_claves_esperadas(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/api/calibracion")
            assert resp.status_code == 200
            cuerpo = resp.json()
            assert "puntos" in cuerpo
            assert set(cuerpo["puntos"].keys()) == {"20m", "40m"}
            for punto in cuerpo["puntos"].values():
                assert {
                    "probabilidad_calculada",
                    "probabilidad_simulador_documentada",
                    "probabilidad_paper",
                    "campo_e_v_m",
                    "campo_e_paper_v_m",
                    "desviacion_vs_simulador_documentado_pp",
                    "desviacion_vs_paper_pp",
                } <= set(punto.keys())
