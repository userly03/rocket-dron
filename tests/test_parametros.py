"""Pruebas del Monte Carlo de parámetros (P1-B) y del modelo de subsistemas (P1-C).

ESTADO: P1-B verificado; P1-C **bloqueado** — ver
``TestModeloSubsistemasBloqueado``, que fija las tres señales de inconsistencia
medidas para que no se pierdan y para que se note si alguien las mueve.
"""

import math

import numpy as np
import pytest
from dataclasses import replace

from src import config as cfg
from src.engine.experiments import monte_carlo_blanco_unico
from src.engine.hpm_engine import (
    antenna_gain_from_aperture,
    antenna_gain_from_dish,
    campo_acoplado_v_m,
    dish_beamwidth_deg,
    probabilidad_dano_sistema,
    probabilidad_dano_subsistema,
)
from src.engine.parametros import (
    Constante,
    EspecificacionMC,
    Normal,
    NormalRelativa,
    Rayleigh,
    Uniforme,
)
from src.utils.reproducibilidad import nuevo_generador


class TestDistribuciones:
    def test_constante_no_consume_variabilidad(self):
        g = nuevo_generador(1)
        d = Constante(7.5)
        assert [d.muestrear(g) for _ in range(5)] == [7.5] * 5
        assert d.es_constante

    def test_normal_respeta_media_y_sigma(self):
        g = nuevo_generador(2)
        d = Normal(25.0, 1.25)
        x = np.array([d.muestrear(g) for _ in range(20000)])
        assert x.mean() == pytest.approx(25.0, abs=0.05)
        assert x.std(ddof=1) == pytest.approx(1.25, abs=0.05)

    def test_normal_acota_por_abajo(self):
        """Una potencia negativa no es física y no debe propagarse en silencio."""
        g = nuevo_generador(3)
        d = Normal(1.0, 100.0, minimo=0.0)
        assert all(d.muestrear(g) >= 0.0 for _ in range(500))

    def test_rayleigh_es_el_modulo_de_un_error_2d(self):
        """Rayleigh(σ) tiene media σ·√(π/2) y es siempre no negativa.

        Es la distribución correcta para el error de apuntado: el desapunte
        tiene dos componentes gaussianas y lo que atenúa el haz es la MAGNITUD
        del desvío, no su signo.
        """
        g = nuevo_generador(4)
        d = Rayleigh(1.0)
        x = np.array([d.muestrear(g) for _ in range(20000)])
        assert (x >= 0).all()
        assert x.mean() == pytest.approx(math.sqrt(math.pi / 2), abs=0.02)

    def test_uniforme_en_rango(self):
        g = nuevo_generador(5)
        d = Uniforme(0.50, 0.60)
        x = [d.muestrear(g) for _ in range(1000)]
        assert min(x) >= 0.50 and max(x) < 0.60

    def test_normal_relativa_usa_el_15pc_como_una_sigma(self):
        """±15% se interpreta como UNA σ, no como intervalo de confianza.

        La otra lectura daría la mitad de varianza; la elección está declarada
        en el docstring de la clase y este test la fija.
        """
        g = nuevo_generador(6)
        d = NormalRelativa(200.0, 0.15)
        x = np.array([d.muestrear(g) for _ in range(20000)])
        assert x.mean() == pytest.approx(200.0, rel=0.01)
        assert x.std(ddof=1) == pytest.approx(30.0, rel=0.05)

    def test_to_dict_va_al_manifiesto(self):
        """Las distribuciones deben ser serializables: entran al manifiesto."""
        for d in (Constante(1.0), Normal(1.0, 0.1), Uniforme(0, 1),
                  Rayleigh(1.0), NormalRelativa(100.0)):
            dd = d.to_dict()
            assert "tipo" in dd


class TestEspecificacionMC:
    def test_nominal_es_todo_constante(self):
        """La especificación nominal reproduce el comportamiento previo a P1-B."""
        espec = EspecificacionMC.nominal()
        assert espec.todo_constante
        g = nuevo_generador(7)
        a, b = espec.muestrear(g), espec.muestrear(g)
        assert a.to_dict() == b.to_dict()

    def test_del_paper_varia(self):
        espec = EspecificacionMC.del_paper()
        assert not espec.todo_constante
        g = nuevo_generador(8)
        a, b = espec.muestrear(g), espec.muestrear(g)
        assert a.to_dict() != b.to_dict()

    def test_del_paper_tiene_las_ocho_fuentes(self):
        """Tabla 2 de arXiv:2602.08477: 6 escalares + E50 y σ_E por subsistema."""
        espec = EspecificacionMC.del_paper()
        assert isinstance(espec.potencia_kw, Normal)
        assert isinstance(espec.diametro_plato_m, Normal)
        assert isinstance(espec.eficiencia_apertura, Uniforme)
        assert isinstance(espec.error_apuntado_deg, Rayleigh)
        assert isinstance(espec.angulo_polarizacion_rad, Uniforme)
        assert isinstance(espec.longitud_cable_m, Uniforme)
        assert len(espec.umbrales_subsistemas) == 5

    def test_error_de_apuntado_existe_y_no_es_cero(self):
        """No existía antes de P1-B. Es la fuente que faltaba por completo."""
        espec = EspecificacionMC.del_paper()
        g = nuevo_generador(9)
        errores = [espec.muestrear(g).error_apuntado_deg for _ in range(200)]
        assert max(errores) > 0.5
        assert all(e >= 0 for e in errores)

    def test_polarizacion_es_cos2_de_angulo_uniforme(self):
        """η_pol = cos²φ con φ~U[0,π], NO un uniforme sobre el factor.

        No es lo mismo: cos² de un ángulo uniforme concentra masa cerca de 0 y
        de 1 (tipo arcoseno). El modelo viejo (``Uniforme[0.3, 1.0]``) era
        plano y **subestimaba la varianza**, justo en la variable que el paper
        señala como dominante.
        """
        espec = EspecificacionMC.del_paper()
        g = nuevo_generador(10)
        etas = np.array([espec.muestrear(g).eta_polarizacion for _ in range(20000)])
        # Piso aplicado.
        assert etas.min() >= cfg.DRONE_POLARIZATION_MIN_ETA - 1e-12
        # Bimodal: más masa en los extremos que en el centro — la firma de la
        # arcoseno, que un uniforme no tiene.
        en_extremos = ((etas < 0.2) | (etas > 0.8)).mean()
        en_centro = ((etas > 0.4) & (etas < 0.6)).mean()
        assert en_extremos > 2 * en_centro

    def test_muestreo_reproducible_con_la_misma_semilla(self):
        espec = EspecificacionMC.del_paper()
        a = [espec.muestrear(nuevo_generador(11)).to_dict() for _ in range(3)]
        b = [espec.muestrear(nuevo_generador(11)).to_dict() for _ in range(3)]
        assert a == b

    def test_to_dict_serializable(self):
        import json
        json.dumps(EspecificacionMC.del_paper().to_dict())


class TestGananciaDePlato:
    """P1-B: la fórmula de plato real cierra el sesgo de −6.4% en campo."""

    def test_reproduce_los_21_2_dbi_del_paper(self):
        """D=0.60 m, η=0.55, 2.45 GHz ⇒ 21.16 dBi contra los 21.2 publicados."""
        g = antenna_gain_from_dish(0.60, 0.55, 2.45)
        dbi = 10 * math.log10(g)
        assert dbi == pytest.approx(21.2, abs=0.1)

    def test_mejora_sobre_la_aproximacion_de_apertura(self):
        """La aproximación 26000/θ² da 20.63 dBi: 0.57 dB por debajo.

        Ese déficit es exactamente el −6.4% en campo E que
        tests/test_calibracion.py midió idéntico en los dos puntos de
        calibración (10^(−0.57/20) = 0.936).
        """
        dbi_plato = 10 * math.log10(antenna_gain_from_dish(0.60, 0.55, 2.45))
        dbi_apert = 10 * math.log10(antenna_gain_from_aperture(15.0))
        deficit_db = dbi_plato - dbi_apert
        assert deficit_db == pytest.approx(0.53, abs=0.08)
        # Déficit en amplitud de campo.
        assert 10 ** (-deficit_db / 20) == pytest.approx(0.936, abs=0.01)

    def test_escala_con_el_cuadrado_del_diametro(self):
        """G ∝ D²: duplicar el diámetro cuadruplica la ganancia."""
        assert antenna_gain_from_dish(1.2, 0.55, 2.45) == pytest.approx(
            4 * antenna_gain_from_dish(0.6, 0.55, 2.45), rel=1e-9
        )

    def test_escala_con_el_cuadrado_de_la_frecuencia(self):
        """G ∝ (1/λ)² ∝ f²."""
        assert antenna_gain_from_dish(0.6, 0.55, 4.90) == pytest.approx(
            4 * antenna_gain_from_dish(0.6, 0.55, 2.45), rel=1e-9
        )

    def test_ancho_de_haz_coherente_con_la_apertura_configurada(self):
        """θ ≈ 70λ/D da 14.28° para el plato del paper, contra HPM_CONE_APERTURE=15.

        Las dos rutas describen la misma antena: difieren en la constante de la
        fórmula de ganancia, no en la geometría.
        """
        assert dish_beamwidth_deg(0.60, 2.45) == pytest.approx(14.28, abs=0.1)
        assert abs(dish_beamwidth_deg(0.60, 2.45) - cfg.HPM_CONE_APERTURE) < 1.0


class TestOrGateSubsistemas:
    """P1-C: la mecánica del OR-gate (ecuación 7) — esto sí está verificado."""

    def test_sigmoide_de_subsistema_en_e50_da_la_mitad(self):
        assert probabilidad_dano_subsistema(150.0, 150.0, 30.0) == pytest.approx(0.5)

    def test_or_gate_supera_a_cualquier_subsistema_solo(self):
        """P_sistema ≥ max(pᵢ): el dron cae si cae CUALQUIERA."""
        E = 200.0
        individuales = [
            probabilidad_dano_subsistema(E, e50, se)
            for e50, se in cfg.HPM_SUBSISTEMAS.values()
        ]
        assert probabilidad_dano_sistema(E) >= max(individuales)

    def test_or_gate_es_el_producto_de_supervivencias(self):
        E = 220.0
        superv = 1.0
        for e50, se in cfg.HPM_SUBSISTEMAS.values():
            superv *= 1.0 - probabilidad_dano_subsistema(E, e50, se)
        assert probabilidad_dano_sistema(E) == pytest.approx(1.0 - superv)

    def test_monotono_creciente_en_campo(self):
        campos = [0, 50, 100, 150, 200, 300, 500]
        probs = [probabilidad_dano_sistema(e) for e in campos]
        assert probs == sorted(probs)

    def test_domina_el_subsistema_mas_debil_a_campo_bajo(self):
        """A campo bajo manda el LNA de GPS (E₅₀=150), no el promedio.

        Es la razón estructural por la que una sola sigmoide agregada no puede
        reproducir la forma de la curva de un OR-gate de cinco.
        """
        E = 100.0
        individuales = {
            nombre: probabilidad_dano_subsistema(E, e50, se)
            for nombre, (e50, se) in cfg.HPM_SUBSISTEMAS.items()
        }
        # El más débil (LNA de GPS, E₅₀=150) es el mayor contribuyente único.
        assert max(individuales, key=individuales.get) == "gps_gnss_lna"
        p_sys = probabilidad_dano_sistema(E)
        # Aporta ~52% de la probabilidad del sistema: más que cualquier otro,
        # pero NO la mayoría absoluta — medido, no supuesto.
        assert individuales["gps_gnss_lna"] / p_sys == pytest.approx(0.52, abs=0.05)
        # Y más del doble que el segundo.
        segundo = sorted(individuales.values())[-2]
        assert individuales["gps_gnss_lna"] > 2 * segundo

    def test_acoplamiento_atenua(self):
        assert campo_acoplado_v_m(500.0) < 500.0
        assert campo_acoplado_v_m(500.0, 1.0) == pytest.approx(500.0)
        assert campo_acoplado_v_m(-10.0) == 0.0


class TestMonteCarloBlancoUnico:
    """El runner de MC de parámetros: mecánica verificada, calibración bloqueada."""

    def test_nominal_no_tiene_varianza(self):
        """Con la especificación nominal todas las tiradas son idénticas."""
        d = monte_carlo_blanco_unico(
            20.0, espec=EspecificacionMC.nominal(), n=200, modelo_dano="subsistemas"
        )
        assert d["desviacion_estandar"] == pytest.approx(0.0, abs=1e-12)

    def test_reproducible_con_la_misma_semilla(self):
        a = monte_carlo_blanco_unico(20.0, n=300, seed=99)
        b = monte_carlo_blanco_unico(20.0, n=300, seed=99)
        assert a["probabilidad_media"] == b["probabilidad_media"]
        assert a["ic95_bootstrap"] == b["ic95_bootstrap"]

    def test_probabilidad_decrece_con_la_distancia(self):
        p20 = monte_carlo_blanco_unico(20.0, n=800)["probabilidad_media"]
        p40 = monte_carlo_blanco_unico(40.0, n=800)["probabilidad_media"]
        p80 = monte_carlo_blanco_unico(80.0, n=800)["probabilidad_media"]
        assert p20 > p40 > p80

    def test_campo_incidente_sigue_uno_sobre_r(self):
        """Verificación de la cadena de Friis dentro del MC: E ∝ 1/r."""
        e20 = monte_carlo_blanco_unico(20.0, n=600)["campo_incidente_medio_v_m"]
        e40 = monte_carlo_blanco_unico(40.0, n=600)["campo_incidente_medio_v_m"]
        assert e20 / e40 == pytest.approx(2.0, rel=0.02)

    def test_modelo_desconocido_falla_explicito(self):
        with pytest.raises(ValueError, match="modelo_dano"):
            monte_carlo_blanco_unico(20.0, n=10, modelo_dano="inventado")

    def test_registra_la_especificacion_usada(self):
        """El manifiesto de la corrida lleva las DISTRIBUCIONES, no solo escalares."""
        d = monte_carlo_blanco_unico(20.0, n=50)
        assert d["espec"]["error_apuntado_deg"]["tipo"] == "rayleigh"
        assert d["espec"]["todo_constante"] is False


class TestModeloSubsistemasBloqueado:
    """P1-C está BLOQUEADO. Estos tests fijan las tres señales de inconsistencia.

    No son tests de que el modelo funcione: son tests de que el modelo **no
    cierra**, con los números medidos, para que (a) no se pierda el
    diagnóstico y (b) si alguien lo arregla, estos tests fallen y haya que
    actualizarlos — que es el único modo de saber que se arregló.

    Diagnóstico completo en docs/FISICA_Y_MATEMATICA.md §3.6.
    """

    # Márgenes que el propio paper declara sobre sus dos puntos.
    OBJ = {20.0: (0.514, 0.010), 40.0: (0.131, 0.007)}

    def test_senal_1_no_reproduce_los_puntos_publicados(self):
        """Con el ajuste correcto (MC en el lazo), los residuos quedan fuera."""
        residuos = {}
        for r, (obj, _margen) in self.OBJ.items():
            p = monte_carlo_blanco_unico(r, n=4000)["probabilidad_media"]
            residuos[r] = p - obj

        # A 20 m queda por debajo, a 40 m muy por encima: residuos de signo
        # OPUESTO, o sea que ningún valor único de k los cierra a la vez.
        assert residuos[20.0] < 0
        assert residuos[40.0] > 0
        # Y el de 40 m es varias veces el margen declarado (±0.7 pp).
        assert residuos[40.0] > 3 * self.OBJ[40.0][1]

    def test_senal_2_el_sesgo_va_en_direccion_opuesta_al_paper(self):
        """El paper: MC "systematically lower than deterministic". Acá es al revés.

        Es la señal más informativa: indica que la varianza está inyectada en
        la zona CONVEXA de la curva (cola baja), donde promediar SUBE la media
        (Jensen), mientras el paper opera en la zona cóncava.
        """
        d = monte_carlo_blanco_unico(40.0, n=4000, modelo_dano="subsistemas")
        # Determinista equivalente: el campo medio, con acoplamiento medio.
        espec = EspecificacionMC.del_paper()
        g = nuevo_generador(8477)
        muestras = [espec.muestrear(g) for _ in range(4000)]
        media_raiz_eta = float(
            np.mean([m.eta_polarizacion**0.5 for m in muestras])
        )
        e_det = campo_acoplado_v_m(d["campo_incidente_medio_v_m"]) * media_raiz_eta
        p_det = probabilidad_dano_sistema(e_det)
        assert d["probabilidad_media"] > p_det, (
            "si esto falla, la dirección del sesgo se corrigió: revisar §3.6"
        )

    def test_senal_3_el_cv_es_demasiado_alto(self):
        """CV ≈ 0.63 a 30 m contra el ≈0.39 que reporta el paper."""
        cv = monte_carlo_blanco_unico(30.0, n=4000)["cv"]
        assert cv > 0.50, f"CV medido {cv}: si bajó, revisar §3.6"

    def test_la_polarizacion_es_la_fuente_dominante_de_varianza(self):
        """Atribución: apagar la polarización baja el CV de ~0.63 a ~0.28.

        Coincide con la conclusión del paper sobre CUÁL parámetro domina
        (polarización y orientación del cable), y localiza el problema: la
        magnitud de la dispersión, no la identidad del culpable. Nótese que
        sin polarización el CV cae POR DEBAJO del 0.39 del paper, así que la
        verdad está en medio.
        """
        base = EspecificacionMC.del_paper()
        sin_pol = replace(base, angulo_polarizacion_rad=Constante(0.0))
        cv_base = monte_carlo_blanco_unico(30.0, espec=base, n=3000)["cv"]
        cv_sin = monte_carlo_blanco_unico(30.0, espec=sin_pol, n=3000)["cv"]
        assert cv_base > cv_sin
        assert (cv_base - cv_sin) > 0.25, "la polarización debe dominar la varianza"
        assert cv_sin < 0.39, "sin polarización el CV cae por debajo del paper"

    def test_el_modelo_agregado_sigue_siendo_el_default(self):
        """Nada del comportamiento por defecto depende del modelo bloqueado."""
        assert cfg.HPM_DAMAGE_MODEL == "agregado"
