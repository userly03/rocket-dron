"""Pruebas del presupuesto energético y térmico del arma (P2-F).

Ver el comentario de ``HPM_DISPARO_DURACION_S`` en ``src/config.py`` para la
justificación del problema de escala energía-de-pulso-vs-energía-de-disparo,
y el docstring de ``HPMWeapon`` para el diseño general.
"""

from __future__ import annotations

import math

import pytest

from src.config import (
    HPM_CAPACIDAD_TERMICA_KJ_C,
    HPM_DEFAULT_POWER,
    HPM_DISIPACION_KW_C,
    HPM_DISPARO_DURACION_S,
    HPM_EFICIENCIA_AMPLIFICADOR,
    HPM_ENERGIA_ALMACENADA_KJ,
    HPM_RECARGA_KW,
    HPM_TEMP_AMBIENTE_C,
    HPM_TEMP_MAX_C,
)
from src.models.drone import Drone
from src.models.hpm_weapon import HPMWeapon


def _disparos_predichos_por_termico(potencia: float = HPM_DEFAULT_POWER) -> int:
    """
    Predicción "a mano" (réplica independiente del cálculo, no una llamada a
    ``HPMWeapon``): cuántos disparos consecutivos SIN enfriar caben antes de
    que la temperatura cruce el límite, a partir del balance de energía/calor
    declarado en ``src/config.py``.

    Cada disparo consume ``E = potencia · HPM_DISPARO_DURACION_S`` kJ y deja
    ``calor = (1 - eficiencia) · E`` kJ de calor, que sube la temperatura en
    ``ΔT = calor / capacidad_termica`` °C. El arma dispara mientras la
    temperatura ANTES del disparo n-ésimo sea menor que el límite:

        T_antes(n) = T_ambiente + ΔT·(n-1) < T_max
        n - 1 < (T_max - T_ambiente) / ΔT
    """
    energia_por_disparo = potencia * HPM_DISPARO_DURACION_S
    calor_por_disparo = (1.0 - HPM_EFICIENCIA_AMPLIFICADOR) * energia_por_disparo
    delta_t_por_disparo = calor_por_disparo / HPM_CAPACIDAD_TERMICA_KJ_C
    margen = HPM_TEMP_MAX_C - HPM_TEMP_AMBIENTE_C
    # -1e-9: margen numérico para no colarnos un disparo de más si el
    # cociente cae justo en un entero por redondeo de punto flotante.
    return math.floor(margen / delta_t_por_disparo - 1e-9) + 1


class TestCadenciaSostenidaAcotadaPorTermico:
    """Criterio de aceptación del ítem: la cadencia sostenida la corta el
    límite térmico, y el número de disparos que logra es el que predice el
    balance energético calculado a mano (no tautológico: la predicción no
    llama a ningún método del arma)."""

    def test_rafaga_sin_enfriar_se_detiene_exactamente_donde_predice_el_calculo(self):
        weapon = HPMWeapon()
        esperados = _disparos_predichos_por_termico()

        exitosos = 0
        motivo_corte = None
        # Drones vacíos: aísla el presupuesto energético/térmico de la
        # física de daño sobre un blanco (esa ya tiene su propia cobertura
        # en test_duty_cycle.py / test_simulation.py). El presupuesto se
        # descuenta igual con o sin drones en el cono (un disparo al aire
        # también gasta energía real).
        for _ in range(esperados + 10):
            weapon.disparar([])
            if weapon.ultimo_rechazo is None:
                exitosos += 1
            else:
                motivo_corte = weapon.ultimo_rechazo
                break

        assert exitosos == esperados
        assert motivo_corte is not None
        assert "temperatura" in motivo_corte

    def test_el_corte_es_termico_no_energetico(self):
        """Verifica la premisa de diseño (config.py): a los defaults, el
        banco de energía queda con margen de sobra cuando el térmico ya
        cortó la ráfaga — igual que en Leonidas/THOR, el cuello de botella
        es la refrigeración, no la energía disponible."""
        weapon = HPMWeapon()
        esperados = _disparos_predichos_por_termico()

        for _ in range(esperados):
            weapon.disparar([])
        assert weapon.ultimo_rechazo is None  # los `esperados` primeros no fallan

        energia_consumida = HPM_ENERGIA_ALMACENADA_KJ - weapon.energia_actual_kj
        assert energia_consumida < HPM_ENERGIA_ALMACENADA_KJ
        assert weapon.energia_actual_kj > 0.0

        # El siguiente disparo SÍ se rechaza, y es por temperatura.
        weapon.disparar([])
        assert weapon.ultimo_rechazo is not None
        assert "temperatura" in weapon.ultimo_rechazo


class TestRecarga:
    def test_recarga_es_lineal(self):
        weapon = HPMWeapon()
        weapon.energia_actual_kj = 0.0
        weapon.recargar(dt=10.0)
        assert weapon.energia_actual_kj == pytest.approx(HPM_RECARGA_KW * 10.0)

        weapon.recargar(dt=5.0)
        assert weapon.energia_actual_kj == pytest.approx(HPM_RECARGA_KW * 15.0)

    def test_recarga_se_satura_en_el_maximo(self):
        weapon = HPMWeapon()
        weapon.energia_actual_kj = HPM_ENERGIA_ALMACENADA_KJ - 1.0
        # dt de sobra para superar el máximo varias veces si no saturara.
        weapon.recargar(dt=10_000.0)
        assert weapon.energia_actual_kj == pytest.approx(HPM_ENERGIA_ALMACENADA_KJ)

    def test_recarga_dt_no_positivo_no_hace_nada(self):
        weapon = HPMWeapon()
        weapon.energia_actual_kj = 10.0
        weapon.recargar(dt=0.0)
        assert weapon.energia_actual_kj == pytest.approx(10.0)


class TestEnfriamiento:
    """El enfriamiento es exponencial hacia el ambiente — se verifica contra
    la solución analítica cerrada, no contra el propio código de producción
    reescrito con otras palabras."""

    def _k(self) -> float:
        return HPM_DISIPACION_KW_C / HPM_CAPACIDAD_TERMICA_KJ_C

    def test_enfriamiento_sigue_la_formula_analitica(self):
        weapon = HPMWeapon()
        weapon.temperatura_c = 125.0
        t = 37.0

        weapon.enfriar(t)

        esperado = HPM_TEMP_AMBIENTE_C + (125.0 - HPM_TEMP_AMBIENTE_C) * math.exp(
            -self._k() * t
        )
        assert weapon.temperatura_c == pytest.approx(esperado, rel=1e-9)

    def test_constante_de_tiempo_deja_un_tercio_de_e_del_salto(self):
        """Tras t = 1/k (una constante de tiempo τ), queda exactamente 1/e
        del salto inicial sobre el ambiente — identidad de la exponencial,
        verificable sin reimplementar la fórmula del código de producción."""
        weapon = HPMWeapon()
        salto_inicial = 200.0
        weapon.temperatura_c = HPM_TEMP_AMBIENTE_C + salto_inicial

        tau = 1.0 / self._k()
        weapon.enfriar(tau)

        salto_restante = weapon.temperatura_c - HPM_TEMP_AMBIENTE_C
        assert salto_restante == pytest.approx(salto_inicial / math.e, rel=1e-9)

    def test_enfriamiento_nunca_baja_del_ambiente(self):
        weapon = HPMWeapon()
        weapon.temperatura_c = HPM_TEMP_AMBIENTE_C
        weapon.enfriar(1000.0)
        assert weapon.temperatura_c == pytest.approx(HPM_TEMP_AMBIENTE_C, abs=1e-6)

    def test_enfriamiento_dt_no_positivo_no_hace_nada(self):
        weapon = HPMWeapon()
        weapon.temperatura_c = 90.0
        weapon.enfriar(0.0)
        assert weapon.temperatura_c == pytest.approx(90.0)


class TestSinEnergiaNoDispara:
    def test_arma_sin_energia_no_dispara_y_declara_el_motivo(self):
        weapon = HPMWeapon(energia_actual_kj=0.0)
        drones = [Drone(0, x=1.0, y=0.0, z=weapon.origen_z)]

        eventos = weapon.disparar(drones)

        assert eventos == []
        assert weapon.ultimo_rechazo is not None
        assert "energía" in weapon.ultimo_rechazo
        assert weapon.disparos == 0  # el disparo rechazado no cuenta como disparo

    def test_arma_con_energia_insuficiente_para_la_rafaga_no_dispara(self):
        energia_media_rafaga = (HPM_DEFAULT_POWER * HPM_DISPARO_DURACION_S) / 2.0
        weapon = HPMWeapon(energia_actual_kj=energia_media_rafaga)

        eventos = weapon.disparar([])

        assert eventos == []
        assert weapon.ultimo_rechazo is not None
        assert weapon.energia_actual_kj == pytest.approx(energia_media_rafaga)


class TestConservacionDeEnergia:
    """Un disparo exitoso consume exactamente la energía que dice consumir,
    y el calor generado es exactamente la pérdida de eficiencia declarada."""

    def test_consumo_de_energia_por_disparo(self):
        weapon = HPMWeapon(potencia=40.0)
        antes = weapon.energia_actual_kj

        weapon.disparar([])

        consumido = antes - weapon.energia_actual_kj
        assert weapon.ultimo_rechazo is None
        assert consumido == pytest.approx(40.0 * HPM_DISPARO_DURACION_S)

    def test_calor_generado_es_la_perdida_de_eficiencia(self):
        weapon = HPMWeapon(potencia=40.0)
        t_antes = weapon.temperatura_c

        weapon.disparar([])

        consumido = 40.0 * HPM_DISPARO_DURACION_S
        calor_esperado = (1.0 - HPM_EFICIENCIA_AMPLIFICADOR) * consumido
        delta_t_esperado = calor_esperado / HPM_CAPACIDAD_TERMICA_KJ_C
        assert weapon.temperatura_c - t_antes == pytest.approx(
            delta_t_esperado, rel=1e-9
        )

    def test_disparo_rechazado_no_consume_nada(self):
        weapon = HPMWeapon(energia_actual_kj=0.0, temperatura_c=HPM_TEMP_AMBIENTE_C)
        t_antes = weapon.temperatura_c
        e_antes = weapon.energia_actual_kj

        weapon.disparar([])

        assert weapon.energia_actual_kj == pytest.approx(e_antes)
        assert weapon.temperatura_c == pytest.approx(t_antes)


class TestToDict:
    def test_to_dict_expone_presupuesto_y_disponibilidad(self):
        weapon = HPMWeapon()
        d = weapon.to_dict()

        assert d["energia_actual_kj"] == pytest.approx(HPM_ENERGIA_ALMACENADA_KJ)
        assert d["energia_maxima_kj"] == pytest.approx(HPM_ENERGIA_ALMACENADA_KJ)
        assert d["temperatura_c"] == pytest.approx(HPM_TEMP_AMBIENTE_C)
        assert d["temperatura_max_c"] == pytest.approx(HPM_TEMP_MAX_C)
        assert d["listo_para_disparar"] is True
        assert d["ultimo_rechazo"] is None

    def test_to_dict_refleja_no_disponible_tras_agotar_energia(self):
        weapon = HPMWeapon(energia_actual_kj=0.0)
        weapon.disparar([])  # rechazado, deja ultimo_rechazo seteado
        d = weapon.to_dict()

        assert d["listo_para_disparar"] is False
        assert d["ultimo_rechazo"] is not None


class TestNoRegresionComportamientoExistente:
    """Los defaults deben permitir que un disparo suelto (o unos pocos) siga
    funcionando exactamente igual que antes de este ítem."""

    def test_un_disparo_suelto_con_defaults_no_es_rechazado(self):
        weapon = HPMWeapon(apertura_cono=360.0)
        drones = [Drone(0, x=50.0, y=0.0, z=weapon.origen_z)]

        eventos = weapon.disparar(drones)

        assert weapon.ultimo_rechazo is None
        assert len(eventos) == 1

    def test_varios_disparos_seguidos_con_defaults_no_son_rechazados(self):
        """Unos pocos disparos (bien por debajo del límite térmico
        calculado arriba) deben seguir funcionando igual que antes."""
        weapon = HPMWeapon(apertura_cono=360.0)
        drones = [Drone(0, x=50.0, y=0.0, z=weapon.origen_z)]

        for _ in range(5):
            weapon.disparar(drones)
            assert weapon.ultimo_rechazo is None
