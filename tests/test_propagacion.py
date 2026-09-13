"""Pruebas de propagación sobre tierra y patrón de antena (P2-C).

Sustituyen al ítem cortado P3-08 (FDTD de campo cercano, que corregía un
régimen de 5.9 m en un campo de 1000 m).

Estructura: primero se valida cada pieza contra valores **analíticos**
conocidos (J₁ tabulada, posiciones de los nulos de Airy, el promedio exacto
del factor de dos rayos), y solo después se mide la consecuencia sobre el
modelo. Sin la validación analítica los números serían afirmaciones sin
respaldo.
"""

import math

import numpy as np
import pytest

from src import config as cfg
from src.engine.propagation import (
    FACTOR_DOS_RAYOS_MEDIO_POTENCIA,
    _bessel_j1,
    diferencia_de_camino_m,
    factor_dos_rayos,
    factor_patron_antena,
    franja_resoluble,
    informe_propagacion,
    patron_apertura_circular,
    patron_cos2,
    separacion_franjas_m,
)

LAMBDA_2G45_M = 299792458.0 / 2.45e9
DIAMETRO_M = 0.60


def _theta_de_u(u: float, d: float = DIAMETRO_M, lam: float = LAMBDA_2G45_M) -> float:
    """Ángulo (grados) al que el patrón de Airy alcanza el argumento ``u``."""
    return math.degrees(math.asin(min(1.0, u * lam / (math.pi * d))))


class TestBesselJ1:
    """La aproximación de Abramowitz-Stegun, contra valores tabulados."""

    @pytest.mark.parametrize(
        "x,esperado",
        [
            (0.0, 0.0),
            (1.0, 0.4400505857),
            (2.0, 0.5767248078),
            (5.0, -0.3275791376),
            (10.0, 0.0434727462),
        ],
    )
    def test_valores_tabulados(self, x, esperado):
        assert _bessel_j1(x) == pytest.approx(esperado, abs=1e-7)

    def test_cero_en_el_primer_nulo(self):
        """J₁(3.8317) = 0 — el primer cero, que fija el nulo del patrón."""
        assert abs(_bessel_j1(3.8317)) < 1e-5

    def test_es_impar(self):
        for x in (0.5, 2.0, 7.0, 12.0):
            assert _bessel_j1(-x) == pytest.approx(-_bessel_j1(x), abs=1e-9)


class TestPatronApertura:
    """Patrón de Airy contra sus posiciones y niveles analíticos."""

    def test_unidad_en_el_eje(self):
        assert patron_apertura_circular(0.0) == pytest.approx(1.0)

    def test_ancho_de_haz_a_media_potencia(self):
        """HPBW = 12.05° para D=0.60 m a 2.45 GHz (aproximación 58.4λ/D: 11.91°).

        Nótese que es MÁS ESTRECHO que los 14.28° de la aproximación 70λ/D que
        usa el proyecto (`dish_beamwidth_deg`): 70λ/D describe un plato con
        taper de alimentador, y Airy es el caso de iluminación uniforme. Las
        dos son correctas para su arquetipo.
        """
        theta_3db = _theta_de_u(1.6163)
        assert 2 * theta_3db == pytest.approx(12.05, abs=0.1)
        assert patron_apertura_circular(theta_3db) ** 2 == pytest.approx(0.5, abs=0.01)
        assert 2 * theta_3db == pytest.approx(58.4 * LAMBDA_2G45_M / DIAMETRO_M, rel=0.02)

    def test_primer_nulo_en_la_posicion_analitica(self):
        """Primer nulo en u = 3.8317 ⇒ θ = 14.40°, con profundidad real."""
        theta_nulo = _theta_de_u(3.8317)
        assert theta_nulo == pytest.approx(14.40, abs=0.05)
        nivel_db = 20 * math.log10(max(patron_apertura_circular(theta_nulo), 1e-15))
        assert nivel_db < -80, f"el nulo debe ser profundo, dio {nivel_db} dB"

    def test_primer_lobulo_lateral_a_menos_17_6_db(self):
        """u = 5.136 ⇒ −17.57 dB en potencia. El número canónico de Airy.

        Es la propiedad que el taper `cos²` no tiene en absoluto: el `cos²`
        vale exactamente cero fuera del cono nominal.
        """
        theta_lobulo = _theta_de_u(5.136)
        nivel_db = 20 * math.log10(patron_apertura_circular(theta_lobulo))
        assert nivel_db == pytest.approx(-17.57, abs=0.1)

    def test_depende_del_diametro_y_de_la_frecuencia(self):
        """El ancho sale de la física de la apertura, no de un parámetro libre.

        Duplicar D o duplicar f debe estrechar el haz por igual (ambos entran
        como D/λ).
        """
        base = patron_apertura_circular(5.0, diametro_m=0.6, frequency_ghz=2.45)
        doble_d = patron_apertura_circular(5.0, diametro_m=1.2, frequency_ghz=2.45)
        doble_f = patron_apertura_circular(5.0, diametro_m=0.6, frequency_ghz=4.90)
        assert doble_d < base
        assert doble_d == pytest.approx(doble_f, abs=1e-9)


class TestCos2NoEsUnPatronDeAntena:
    """Cuantifica la discrepancia del taper histórico. Es el hallazgo de P2-C."""

    def test_cos2_trunca_a_cero_donde_airy_no(self):
        """Fuera del cono nominal `cos²` dice cero; Airy dice −5 dB.

        Consecuencia operativa: con `cos²` un enjambre justo fuera del haz
        nominal es perfectamente seguro. Con un patrón real recibe del orden
        del 30 % del campo del eje, y el primer nulo no llega hasta 14.4°.
        """
        semi = cfg.HPM_CONE_APERTURE / 2.0  # 7.5°
        justo_fuera = semi + 0.1
        assert patron_cos2(justo_fuera, cfg.HPM_CONE_APERTURE) == 0.0
        airy = patron_apertura_circular(justo_fuera)
        assert airy > 0.5, f"Airy a {justo_fuera}° debe seguir siendo apreciable: {airy}"

    def test_discrepancia_en_el_borde_del_haz(self):
        """A 7.4° (justo dentro del semicono) la discrepancia es ~29 dB."""
        c2 = patron_cos2(7.4, 15.0)
        ai = patron_apertura_circular(7.4)
        db_c2 = 20 * math.log10(c2)
        db_ai = 20 * math.log10(ai)
        assert (db_ai - db_c2) == pytest.approx(28.9, abs=1.5)

    def test_airy_integra_mas_potencia_que_cos2(self):
        """Integrado sobre el ángulo sólido, Airy ve ~3.2× más potencia.

        O sea: el modelo actual **subestima** la letalidad fuera de eje.
        """
        angs = np.linspace(0.0, 60.0, 20001)
        peso = np.sin(np.radians(angs))
        int_c2 = float(np.trapezoid(
            np.array([patron_cos2(a, 15.0) ** 2 for a in angs]) * peso, angs))
        int_airy = float(np.trapezoid(
            np.array([patron_apertura_circular(a) ** 2 for a in angs]) * peso, angs))
        assert int_airy / int_c2 == pytest.approx(3.2, abs=0.3)

    def test_el_selector_respeta_el_default(self):
        assert cfg.PROPAGATION_ANTENNA_PATTERN == "cos2"
        assert factor_patron_antena(5.0, 15.0) == pytest.approx(patron_cos2(5.0, 15.0))

    def test_modelo_desconocido_falla_explicito(self):
        with pytest.raises(ValueError, match="PROPAGATION_ANTENNA_PATTERN"):
            factor_patron_antena(5.0, 15.0, modelo="inventado")


class TestDosRayos:
    def test_diferencia_de_camino_exacta(self):
        """Geometría exacta, no la aproximación 2·h_tx·h_rx/r."""
        r, h_tx, h_rx = 100.0, 8.0, 40.0
        esperado = math.hypot(r, h_rx + h_tx) - math.hypot(r, h_rx - h_tx)
        assert diferencia_de_camino_m(r, h_tx, h_rx) == pytest.approx(esperado)
        # A rango corto la aproximación de campo lejano falla apreciablemente.
        aprox = 2 * h_tx * h_rx / r
        assert abs(esperado - aprox) / esperado > 0.05

    def test_factor_acotado_en_0_2(self):
        """Con Γ=−1 el factor de amplitud vive en [0, 2] (potencia: −∞ a +6 dB)."""
        for r in (50.0, 200.0, 700.0):
            for h in np.linspace(40.0, 160.0, 200):
                f = factor_dos_rayos(r, float(h))
                assert 0.0 <= f <= 2.0 + 1e-9

    def test_media_en_potencia_es_exactamente_2(self):
        """⟨|F|²⟩ = 2 (+3.01 dB): el resultado analítico clave de P2-C.

        El término en coseno promedia a cero cuando la fase barre muchos
        ciclos. Consecuencia: **el modelo de espacio libre subestima la
        potencia media recibida sobre tierra en 3 dB**, y eso es independiente
        de la frecuencia y del rango.
        """
        alturas = np.linspace(40.0, 160.0, 8001)
        for f_ghz in (0.5, 2.45):
            for r in (100.0, 300.0, 700.0):
                pot = np.array(
                    [factor_dos_rayos(r, float(h), frequency_ghz=f_ghz) ** 2
                     for h in alturas]
                )
                assert pot.mean() == pytest.approx(
                    FACTOR_DOS_RAYOS_MEDIO_POTENCIA, rel=0.05
                ), f"f={f_ghz} GHz, r={r} m: media {pot.mean()}"
        assert 10 * math.log10(FACTOR_DOS_RAYOS_MEDIO_POTENCIA) == pytest.approx(3.01, abs=0.01)

    def test_coeficiente_de_reflexion_nulo_recupera_espacio_libre(self):
        """Γ=0 (sin suelo) ⇒ factor 1: control de que el efecto es el suelo."""
        assert factor_dos_rayos(300.0, 100.0, coeficiente_reflexion=0.0) == pytest.approx(1.0)

    def test_suelo_con_perdidas_atenua_los_extremos(self):
        """|Γ|<1 comprime el rango: máximos menores y nulos menos profundos."""
        alturas = np.linspace(40.0, 160.0, 2001)
        ideal = np.array([factor_dos_rayos(300.0, float(h), coeficiente_reflexion=-1.0) for h in alturas])
        con_perdidas = np.array([factor_dos_rayos(300.0, float(h), coeficiente_reflexion=-0.5) for h in alturas])
        assert con_perdidas.max() < ideal.max()
        assert con_perdidas.min() > ideal.min()


class TestFranjasNoSonResolubles:
    """El hallazgo que cambió el diseño de P2-C. Fijado para que no se pierda."""

    def test_separacion_de_franjas_medida(self):
        """λ·r/(2·h_tx): 0.76 m a 100 m, 2.29 m a 300 m, 5.35 m a 700 m."""
        for r, esperado in ((100.0, 0.76), (300.0, 2.29), (700.0, 5.35)):
            assert separacion_franjas_m(r) == pytest.approx(esperado, abs=0.02)

    def test_no_resoluble_a_2_45_ghz_en_todo_el_campo(self):
        """A 2.45 GHz la franja es menor que la oscilación del dron (±4 m).

        Por eso "volar en un nulo" NO es una táctica disponible a esta
        frecuencia: el dron cruza varias franjas por oscilación. Si este test
        empieza a fallar, alguien cambió la frecuencia, la altura del emisor o
        la amplitud de oscilación, y hay que revisar la conclusión de §3.9.
        """
        for r in (100.0, 300.0, 500.0):
            assert not franja_resoluble(r), f"a {r} m la franja no debería ser resoluble"

    def test_caben_muchos_ciclos_en_la_banda_de_vuelo(self):
        """22 a 157 ciclos completos en 40-160 m según el rango."""
        banda = cfg.DRONE_ALTITUD_MAX - cfg.DRONE_ALTITUD_MIN
        for r, ciclos_min in ((100.0, 100), (700.0, 20)):
            ciclos = banda / separacion_franjas_m(r)
            assert ciclos > ciclos_min

    def test_si_es_resoluble_a_frecuencia_baja(self):
        """Por debajo de ~0.5 GHz la altitud SÍ pasa a ser variable táctica.

        Como `HPM_FREQUENCY_GHZ` es barrible, el modelo determinista se
        conserva y es el correcto en ese régimen.
        """
        assert franja_resoluble(700.0, frequency_ghz=0.5)
        assert franja_resoluble(700.0, frequency_ghz=0.1)
        assert separacion_franjas_m(700.0, frequency_ghz=0.1) == pytest.approx(131.2, abs=1.0)


class TestIntegracionConElMotor:
    """Ambos efectos son opt-in y no mueven nada por defecto."""

    def test_defaults_no_alteran_el_motor(self):
        """Requisito duro: la calibración de §3.4 no se mueve."""
        from src.engine.hpm_engine import friis_diagnostics

        assert cfg.PROPAGATION_GROUND_REFLECTION is False
        assert cfg.PROPAGATION_ANTENNA_PATTERN == "cos2"
        assert friis_diagnostics(25.0, 20.0, 15.0, 0.0)["campo_e_v_m"] == pytest.approx(
            465.4802, abs=0.01
        )

    def test_airy_aumenta_el_campo_fuera_de_eje(self, monkeypatch):
        from src.engine import hpm_engine

        monkeypatch.setattr(cfg, "PROPAGATION_ANTENNA_PATTERN", "airy")
        e_airy = hpm_engine.friis_diagnostics(25.0, 100.0, 15.0, 7.4)["campo_e_v_m"]
        monkeypatch.setattr(cfg, "PROPAGATION_ANTENNA_PATTERN", "cos2")
        e_cos2 = hpm_engine.friis_diagnostics(25.0, 100.0, 15.0, 7.4)["campo_e_v_m"]
        # Factor ~28 en campo a 7.4° (los 28.9 dB de discrepancia).
        assert e_airy / e_cos2 > 10

    def test_reflexion_requiere_geometria_y_degrada_sin_ella(self, monkeypatch):
        """Sin altura del blanco el efecto no se puede calcular: se omite.

        No es un fallo silencioso disimulado: `friis_diagnostics` no recibe la
        geometría vertical en su firma histórica, y los llamadores que sí la
        tienen la pasan explícita.
        """
        from src.engine import hpm_engine

        monkeypatch.setattr(cfg, "PROPAGATION_GROUND_REFLECTION", True)
        sin_geo = hpm_engine.friis_diagnostics(25.0, 100.0, 15.0, 0.0)["campo_e_v_m"]
        monkeypatch.setattr(cfg, "PROPAGATION_GROUND_REFLECTION", False)
        control = hpm_engine.friis_diagnostics(25.0, 100.0, 15.0, 0.0)["campo_e_v_m"]
        assert sin_geo == pytest.approx(control)

        monkeypatch.setattr(cfg, "PROPAGATION_GROUND_REFLECTION", True)
        con_geo = hpm_engine.friis_diagnostics(
            25.0, 100.0, 15.0, 0.0, rango_horizontal_m=100.0, altura_rx_m=40.0
        )["campo_e_v_m"]
        assert con_geo != pytest.approx(control)


class TestInforme:
    def test_estructura_y_coherencia(self):
        inf = informe_propagacion(rango_horizontal_m=300.0, altura_rx_m=100.0)
        assert inf["franjas"]["resoluble"] is False
        assert inf["estadistica_en_banda"]["media_potencia_db"] == pytest.approx(3.01, abs=0.2)
        assert inf["estadistica_en_banda"]["p95_db"] == pytest.approx(6.0, abs=0.2)
        assert inf["estadistica_en_banda"]["p5_db"] < -10
        assert inf["patron_antena"]["primer_lobulo_lateral_db"] == pytest.approx(-17.57, abs=0.2)

    def test_serializable(self):
        import json
        json.dumps(informe_propagacion())
