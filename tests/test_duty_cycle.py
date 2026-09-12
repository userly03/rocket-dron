"""Pruebas del modelo duty cycle (potencia pico vs promedio, duración de pulso)."""

import pytest

from src.engine.hpm_engine import (
    alcance_para_probabilidad,
    calculate_area_neutralization_probability_friis,
    calculate_neutralization_probability_friis,
    friis_diagnostics,
    pulse_coupling_factor,
)
from src.models.drone import Drone
from src.models.hpm_missile import HPMissile
from src.models.hpm_weapon import HPMWeapon
from src.utils.reproducibilidad import seed_simulacion


class TestPulseCoupling:
    def test_referencia_da_factor_1(self):
        assert pulse_coupling_factor(100.0, reference_ns=100.0) == pytest.approx(1.0)
        assert pulse_coupling_factor(None, reference_ns=100.0) == pytest.approx(1.0)

    def test_pulso_largo_acopla_mas(self):
        """Un pulso más largo acopla más, con el exponente 1/4 (no 1/2).

        MODIFICADO en P1-E. Antes este test exigía
        ``pulse_coupling_factor(400, ref=100) == 2.0``, o sea el exponente 1/2
        — que era **una raíz de más**: Wunsch-Bell da un umbral de POTENCIA y
        la sigmoide de este motor opera sobre CAMPO, así que falta el paso
        ``E_fail ∝ √P_fail`` y el exponente correcto en el régimen de difusión
        térmica es 1/4. El test viejo no estaba verificando física: estaba
        fijando el error. Ver el docstring de ``pulse_coupling_factor`` para la
        derivación y docs/FISICA_Y_MATEMATICA.md §3.5.
        """
        # (400/100)^(1/4) = 4^0.25 = √2
        assert pulse_coupling_factor(400.0, reference_ns=100.0) == pytest.approx(2.0**0.5)
        assert pulse_coupling_factor(400.0, reference_ns=100.0) < 2.0

    def test_satura_en_el_regimen_estacionario_no_en_un_tope_arbitrario(self):
        """El techo es físico: (τ₂/τ₁)^(1/4), alcanzado en τ₂ = 10 µs.

        MODIFICADO en P1-E. Antes el techo era ``HPM_PULSE_COUPLING_MAX = 3.0``,
        un número mágico. Resulta que el VALOR estaba casi bien por casualidad
        —(10000/100)^(1/4) = 3.1623— pero la saturación ocurría a τ ≈ 900 ns
        (donde √(τ/τ_ref) llega a 3) en vez de a los 10 µs físicos. Los dos
        defectos se cancelaban parcialmente.
        """
        techo = (10_000.0 / 100.0) ** 0.25
        assert techo == pytest.approx(3.1623, abs=1e-4)
        assert pulse_coupling_factor(10_000.0, reference_ns=100.0) == pytest.approx(techo)
        # Ya en estado estacionario, τ deja de importar.
        assert pulse_coupling_factor(20_000.0, reference_ns=100.0) == pytest.approx(techo)
        assert pulse_coupling_factor(1_000_000.0, reference_ns=100.0) == pytest.approx(techo)
        # Y a 900 ns NO satura (era el defecto del modelo viejo).
        assert pulse_coupling_factor(900.0, reference_ns=100.0) < techo * 0.99

    def test_continuidad_en_los_quiebres_de_regimen(self):
        """g(τ) es continua en τ₁ y τ₂. Una discontinuidad sería un error físico.

        No derivable en los quiebres (es un cambio de régimen), pero continua
        en valor. Se aproxima por ambos lados con un ε relativo.
        """
        for quiebre in (100.0, 10_000.0):
            izq = pulse_coupling_factor(quiebre * (1 - 1e-9), reference_ns=100.0)
            der = pulse_coupling_factor(quiebre * (1 + 1e-9), reference_ns=100.0)
            assert izq == pytest.approx(der, abs=1e-6), (
                f"salto en τ={quiebre} ns: izq={izq} der={der}"
            )

    def test_exponentes_por_tramo(self):
        """Los exponentes derivados, verificados numéricamente.

        Duplicar τ multiplica g por 2^(1/4) en difusión térmica y por 2^(1/2)
        en el régimen adiabático. Es el contenido falsable de la ley: si
        alguien vuelve a poner el exponente de potencia sobre el campo, estos
        dos asserts fallan.
        """
        # Difusión térmica (τ > τ₁ = 100 ns): exponente 1/4.
        assert pulse_coupling_factor(200.0) / pulse_coupling_factor(100.0) == pytest.approx(2.0**0.25)
        assert pulse_coupling_factor(2000.0) / pulse_coupling_factor(1000.0) == pytest.approx(2.0**0.25)
        # Adiabático (τ < τ₁): exponente 1/2.
        assert pulse_coupling_factor(50.0) / pulse_coupling_factor(25.0) == pytest.approx(2.0**0.5)

    def test_pulso_muy_corto_penaliza(self):
        """En el régimen adiabático un pulso más corto que la referencia acopla MENOS.

        Consecuencia física, no convención: si el calor no difunde, la falla
        depende de la energía total, y un pulso más corto a igual potencia
        inyecta menos energía.
        """
        assert pulse_coupling_factor(10.0, reference_ns=100.0) < 1.0
        assert pulse_coupling_factor(10.0, reference_ns=100.0) == pytest.approx(0.1**0.5)

    def test_tau_cero_no_rompe(self):
        assert pulse_coupling_factor(0.0, reference_ns=100.0) == 1.0


class TestDutyCycleEnProbabilidad:
    def test_defaults_igual_al_modelo_calibrado(self):
        # duty=1.0, τ=referencia → E_eff = E(promedio): idéntico al modelo friis original.
        p_base = calculate_neutralization_probability_friis(50, 500, 15.0, 0.0)
        p_explicito = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, duty_cycle=1.0, pulse_duration_ns=100.0
        )
        assert p_base == pytest.approx(p_explicito, rel=1e-9)

    def test_pulsado_supera_a_cw_a_igual_potencia_promedio(self):
        p_cw = calculate_neutralization_probability_friis(50, 500, 15.0, 0.0, duty_cycle=1.0)
        p_pulsado = calculate_neutralization_probability_friis(50, 500, 15.0, 0.0, duty_cycle=0.1)
        assert p_pulsado > p_cw

    def test_pulso_largo_supera_a_corto_a_igual_pico(self):
        p_corto = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, duty_cycle=1.0, pulse_duration_ns=100.0
        )
        p_largo = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, duty_cycle=1.0, pulse_duration_ns=900.0
        )
        assert p_largo > p_corto

    def test_misil_mismo_comportamiento(self):
        p_cw = calculate_area_neutralization_probability_friis(50, 80, duty_cycle=1.0)
        p_pulsado = calculate_area_neutralization_probability_friis(50, 80, duty_cycle=0.05)
        assert p_pulsado > p_cw

    def test_fuera_del_cono_sigue_siendo_cero(self):
        p = calculate_neutralization_probability_friis(50, 100, 15.0, 30.0, duty_cycle=0.01)
        assert p == 0.0


class TestDiagnostics:
    def test_reporta_pico_y_duty(self):
        diag = friis_diagnostics(50, 500, 15.0, 0.0, duty_cycle=0.25)
        assert diag["potencia_promedio_kw"] == pytest.approx(50.0)
        assert diag["potencia_pico_kw"] == pytest.approx(200.0)
        assert diag["duty_cycle"] == pytest.approx(0.25)
        assert diag["campo_e_efectivo_v_m"] >= diag["campo_e_v_m"]

    def test_duty_default_no_cambia_campo(self):
        diag_default = friis_diagnostics(50, 500, 15.0, 0.0)
        diag_cw = friis_diagnostics(50, 500, 15.0, 0.0, duty_cycle=1.0, pulse_duration_ns=100.0)
        assert diag_default["campo_e_efectivo_v_m"] == pytest.approx(
            diag_cw["campo_e_efectivo_v_m"], rel=1e-9
        )


class TestDutyCycleEndToEnd:
    def _disparos_con_duty(self, duty: float) -> int:
        seed_simulacion(123)
        weapon = HPMWeapon(
            potencia=60, direccion=45, apertura_cono=15, duty_cycle=duty,
            origen_x=0, origen_y=0,
        )
        # Huella resonante explícita (acoplamiento = 1): la variable bajo
        # prueba es el duty cycle, no el sorteo de susceptibilidad.
        cable_res = 299_792_458.0 / (2 * 2.45e9)
        drones = [
            Drone(i, x=200 + i * 10, y=200, z=100,
                  cable_length_m=cable_res, polarization=1.0)
            for i in range(12)
        ]
        eventos = weapon.disparar(drones)
        return sum(1 for e in eventos if e["neutralizado"])

    def test_arma_pulsada_neutraliza_mas_que_cw(self):
        kills_cw = self._disparos_con_duty(1.0)
        kills_pulsado = self._disparos_con_duty(0.01)
        assert kills_pulsado > kills_cw

    def test_misil_pulsado_mayor_probabilidad(self):
        dron = Drone(0, x=100, y=0, z=100)
        misil_cw = HPMissile(x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=150, duty_cycle=1.0)
        misil_pulsado = HPMissile(x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=150, duty_cycle=0.1)
        dist = 100.0
        p_cw = misil_cw.calcular_daño(dron, dist)
        p_pulsado = misil_pulsado.calcular_daño(dron, dist)
        assert p_pulsado > p_cw
        assert misil_pulsado.to_dict()["duty_cycle"] == pytest.approx(0.1)


class TestAlcance90PorCiento:
    """Criterio de aceptación de P1-E: alcance de 90% de baja, CW vs pulsado.

    Reemplaza el criterio tautológico de v1 del checklist ("a igual energía
    total, un pulso corto de alto pico neutraliza a más distancia que CW"), que
    no podía fallar: el modelo define pico = promedio/duty, así que duty↓ ⇒ E↑
    ⇒ P↑ por álgebra. Ver docs/AUDITORIA_CHECKLIST.md §2.

    Blanco publicado (arXiv:2602.08477 §5, ver
    docs/REFERENCIA_PAPER_2602.08477.md §5):
        CW      25 kW, plato de 60 cm  →  alcance de 90% de baja ≈ 18 m
        Pulsado 500 kW pico, 1% duty   →  alcance de 90% de baja ≈ 88 m

    HONESTIDAD SOBRE QUÉ VALIDA CADA TEST: el COCIENTE entre alcances es, en
    este modelo, una identidad algebraica (√ del cociente de potencias pico),
    así que verificarlo comprueba la IMPLEMENTACIÓN del escalado de pico y la
    geometría 1/r, no la física del pulso. El contenido físico falsable de
    P1-E está en TestPulseCoupling (continuidad, exponentes, techo). Los
    valores ABSOLUTOS sí son un contraste externo, y no cierran — ver
    ``test_brecha_absoluta_documentada``.
    """

    POTENCIA_CW_KW = 25.0
    # 500 kW pico al 1% de duty ⇒ 5 kW promedio (así lo parametriza el paper).
    POTENCIA_PULSADA_PROMEDIO_KW = 5.0
    DUTY_PULSADO = 0.01

    def _alcance(self, potencia_kw: float, duty: float) -> float:
        r = alcance_para_probabilidad(0.90, potencia_kw, duty_cycle=duty)
        assert r is not None, "el arma no alcanza 90% de baja a ninguna distancia"
        return r

    def test_pulsado_extiende_el_alcance_por_el_factor_de_campo_pico(self):
        """El cociente de alcances es √(pico_pulsado / pico_cw) = √20 ≈ 4.47.

        Identidad algebraica del modelo, no validación física: se verifica para
        detectar que el escalado de pico o la geometría 1/r se rompan.
        """
        cw = self._alcance(self.POTENCIA_CW_KW, 1.0)
        pulsado = self._alcance(self.POTENCIA_PULSADA_PROMEDIO_KW, self.DUTY_PULSADO)
        pico_cw = self.POTENCIA_CW_KW
        pico_pulsado = self.POTENCIA_PULSADA_PROMEDIO_KW / self.DUTY_PULSADO
        assert pulsado / cw == pytest.approx((pico_pulsado / pico_cw) ** 0.5, rel=1e-4)

    def test_brecha_absoluta_documentada(self):
        """Los alcances absolutos NO reproducen los 18 m / 88 m del paper, y
        la brecha está cuantificada y atribuida.

        Medido: CW ≈ 11.74 m (paper 18 m), pulsado ≈ 52.50 m (paper 88 m) —
        un 35% y un 40% por debajo.

        CAUSA DOMINANTE (cuantificada, no conjeturada): el umbral AGREGADO del
        simulador exige E = E₀ + ln(9)/k = 500 + ln(9)/0.0075 = **793 V/m**
        para llegar al 90% de baja. A 18 m el simulador tiene 517 V/m y el
        paper 552 V/m — o sea que el paper declara 90% de baja a ~552 V/m,
        menos del 70% del campo que el umbral agregado necesita. La diferencia
        de ganancia (20.6 vs 21.2 dBi, −6.4% en campo) explica solo una parte
        pequeña: corregida sola, movería el alcance a ~12.5 m, no a 18 m.

        Lo que falta es el modelo de 5 subsistemas en OR-gate del paper
        (P_system = 1 − Π(1−pᵢ), con E₅₀ de 150 a 350 V/m): cinco
        oportunidades de fallar alcanzan el 90% a un campo mucho menor que una
        única sigmoide centrada en 500 V/m. Eso es exactamente el ítem P1-C del
        checklist, y esta brecha es su evidencia cuantitativa.

        Este test NO afloja una tolerancia hasta pasar: fija la brecha medida
        para que quede visible y falle si cambia, en cualquier dirección. Si
        P1-C cierra la brecha, este test debe fallar y actualizarse — eso es
        lo que se quiere.
        """
        cw = self._alcance(self.POTENCIA_CW_KW, 1.0)
        pulsado = self._alcance(self.POTENCIA_PULSADA_PROMEDIO_KW, self.DUTY_PULSADO)

        assert cw == pytest.approx(11.74, abs=0.15)
        assert pulsado == pytest.approx(52.50, abs=0.60)
        # La brecha va en la dirección esperada: el umbral agregado es más
        # exigente que el OR-gate del paper, así que el alcance queda corto.
        assert cw < 18.0
        assert pulsado < 88.0

    def test_el_alcance_decrece_al_subir_el_umbral(self):
        """Chequeo de sanidad direccional del buscador de alcance."""
        from src.config import HPM_E_THRESHOLD_V_M

        laxo = alcance_para_probabilidad(
            0.90, self.POTENCIA_CW_KW, e_threshold=HPM_E_THRESHOLD_V_M * 0.5
        )
        estricto = alcance_para_probabilidad(
            0.90, self.POTENCIA_CW_KW, e_threshold=HPM_E_THRESHOLD_V_M * 2.0
        )
        assert laxo is not None and estricto is not None
        assert laxo > estricto

    def test_objetivo_inalcanzable_devuelve_none(self):
        """Un arma que nunca llega al objetivo devuelve None, no un número falso."""
        assert alcance_para_probabilidad(0.90, 0.001, duty_cycle=1.0) is None
