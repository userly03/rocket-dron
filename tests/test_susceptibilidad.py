"""Pruebas de la huella de susceptibilidad: resonancia de cableado + polarización."""

import pytest

from src.engine.hpm_engine import (
    calculate_area_neutralization_probability_friis,
    calculate_neutralization_probability_friis,
    frequency_coupling,
    resonance_frequency_ghz,
    susceptibility_coupling_factor,
)
from src.models.drone import Drone
from src.models.swarm import Swarm
from src.utils.helpers import drone_to_dict
from src.utils.reproducibilidad import seed_simulacion

# Longitud exacta de cableado resonante a 2.45 GHz (dipolo de media onda).
CABLE_RES = 299_792_458.0 / (2 * 2.45e9)


class TestResonancia:
    def test_frecuencia_media_onda(self):
        # L = c/(2f): a 2.45 GHz, L ≈ CABLE_RES m.
        f = resonance_frequency_ghz(CABLE_RES)
        assert f == pytest.approx(2.449, abs=0.01)

    def test_acoplamiento_maximo_en_resonancia(self):
        cable_res = 299_792_458.0 / (2 * 2.45e9)  # longitud exacta de media onda
        assert frequency_coupling(cable_res, frequency_ghz=2.45) == pytest.approx(1.0, abs=1e-9)

    def test_acoplamiento_ca_fuera_de_resonancia(self):
        cerca = frequency_coupling(CABLE_RES, frequency_ghz=2.6)
        lejos = frequency_coupling(CABLE_RES, frequency_ghz=5.0)
        assert cerca > lejos > 0.0

    def test_factor_amplitud_sin_huella_es_1(self):
        assert susceptibility_coupling_factor(None, None) == 1.0

    def test_factor_amplitud_resonante_mayor_que_desintonizado(self):
        f_res = resonance_frequency_ghz(CABLE_RES)
        resonante = susceptibility_coupling_factor(CABLE_RES, 1.0, f_res)
        desintonizado = susceptibility_coupling_factor(0.04, 1.0, f_res)
        assert resonante > desintonizado


class TestProbabilidadConHuella:
    def test_sin_huella_igual_al_modelo_calibrado(self):
        p_base = calculate_neutralization_probability_friis(50, 500, 15.0, 0.0)
        p_sin = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=None, polarization=None
        )
        assert p_base == pytest.approx(p_sin, rel=1e-9)

    def test_resonante_no_peor_que_sin_huella(self):
        # η=1, pol=1 → factor 1 → misma probabilidad que el modelo base.
        p_base = calculate_neutralization_probability_friis(50, 500, 15.0, 0.0)
        p_res = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=CABLE_RES, polarization=1.0, frequency_ghz=2.45
        )
        assert p_res == pytest.approx(p_base, rel=1e-9)

    def test_desintonizado_menor_que_resonante(self):
        p_res = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=CABLE_RES, polarization=1.0, frequency_ghz=2.45
        )
        p_des = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=0.02, polarization=1.0, frequency_ghz=2.45
        )
        assert p_des < p_res

    def test_polarizacion_mala_reduce_probabilidad(self):
        p_buena = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=CABLE_RES, polarization=1.0
        )
        p_mala = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=CABLE_RES, polarization=0.3
        )
        assert p_mala < p_buena

    def test_frecuencia_del_arma_cambia_el_daño(self):
        # Mismo dron: cerca de su resonancia el arma daña más que lejos de ella.
        cable = CABLE_RES  # f_res ≈ 2.45 GHz
        cerca = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=cable, polarization=1.0, frequency_ghz=2.45
        )
        lejos = calculate_neutralization_probability_friis(
            50, 500, 15.0, 0.0, cable_length_m=cable, polarization=1.0, frequency_ghz=6.0
        )
        assert cerca > lejos

    def test_misil_responde_a_la_huella(self):
        p_res = calculate_area_neutralization_probability_friis(
            50, 80, cable_length_m=CABLE_RES, polarization=1.0, frequency_ghz=2.45
        )
        p_des = calculate_area_neutralization_probability_friis(
            50, 80, cable_length_m=0.02, polarization=1.0, frequency_ghz=2.45
        )
        assert p_des < p_res


class TestDroneHuella:
    def test_sorteo_en_constructor(self):
        seed_simulacion(5)
        drone = Drone(0, x=0, y=0)
        assert drone.cable_length_m > 0
        assert 0.0 < drone.polarization <= 1.0
        assert drone.frecuencia_resonancia_ghz() > 0

    def test_valores_explicitos_no_se_sortean(self):
        seed_simulacion(5)
        drone = Drone(0, x=0, y=0, cable_length_m=CABLE_RES, polarization=0.9)
        assert drone.cable_length_m == pytest.approx(CABLE_RES)
        assert drone.polarization == pytest.approx(0.9)

    def test_recibir_daño_usa_la_huella(self):
        resonante = Drone(0, x=100, y=0, cable_length_m=CABLE_RES, polarization=1.0)
        desintonizado = Drone(1, x=100, y=0, cable_length_m=0.02, polarization=1.0)
        resonante.recibir_daño(potencia=50, distancia=500, angulo_offset=0, apertura_cono=15)
        desintonizado.recibir_daño(potencia=50, distancia=500, angulo_offset=0, apertura_cono=15)
        assert resonante.ultima_probabilidad > desintonizado.ultima_probabilidad

    def test_enjambre_genera_huellas_variadas(self):
        seed_simulacion(9)
        swarm = Swarm()
        swarm.inicializar_formacion("aleatoria", 30)
        longitudes = {d.cable_length_m for d in swarm.drones}
        assert len(longitudes) > 1
        for d in swarm.drones:
            assert 0.02 <= d.cable_length_m <= 0.15

    def test_drone_to_dict_expone_huella(self):
        drone = Drone(0, x=0, y=0, cable_length_m=CABLE_RES, polarization=0.8)
        data = drone_to_dict(drone)
        # drone_to_dict redondea a 4 decimales.
        assert data["cable_length_m"] == pytest.approx(CABLE_RES, abs=1e-4)
        assert data["f_res_ghz"] == pytest.approx(2.45, abs=0.01)
        assert data["acoplamiento"] > 0
