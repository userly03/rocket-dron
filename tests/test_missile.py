"""Pruebas del sistema de misiles HPM."""

import numpy as np
import pytest

from src.engine.hpm_engine import calculate_area_neutralization_probability
from src.engine.simulation import SimulationEngine
from src.models.drone import Drone, DroneEstado
from src.models.hpm_missile import HPMissile, MissileEstado
from src.models.hpm_system import HPMissileSystem


class TestAreaDamage:
    def test_probabilidad_area_decrece_con_distancia(self):
        p_cerca = calculate_area_neutralization_probability(50, 10)
        p_lejos = calculate_area_neutralization_probability(50, 100)
        assert p_cerca > p_lejos

    def test_formula_area_exponencial(self):
        p = calculate_area_neutralization_probability(50, 50, k=0.015)
        expected = 1 - np.exp(-0.015 * 50 / (50**2))
        assert p == pytest.approx(expected, rel=0.01)


class TestHPMissile:
    def test_mover_actualiza_posicion(self):
        misil = HPMissile(x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=100)
        misil.mover(1.0)
        assert misil.x > 0
        assert misil.estado == MissileEstado.VOLANDO

    def test_calcular_daño_fuera_de_radio(self):
        misil = HPMissile(x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=50)
        drone = Drone(0, x=200, y=0)
        assert misil.calcular_daño(drone, 200) == 0.0

    def test_detonar_soft_kill(self):
        np.random.seed(42)
        misil = HPMissile(
            x=500, y=500, angulo=0, potencia_hpm=100, radio_efecto=200
        )
        drones = [Drone(i, x=500 + i * 5, y=500) for i in range(5)]
        eventos = misil.detonar(drones)
        assert misil.estado == MissileEstado.DETONADO
        assert len(eventos) == 5
        assert any(e["tipo"] == "soft_kill" for e in eventos)

    def test_debe_detonar_espera_al_punto_de_maxima_cercania(self):
        """
        Regresión: antes detonaba apenas cruzaba detonacion_distancia (el
        peor momento posible, menor probabilidad), en vez de esperar a que
        la distancia empiece a aumentar (punto de máxima cercanía real,
        como un fusible de proximidad real).
        """
        misil = HPMissile(
            x=400, y=500, angulo=0, potencia_hpm=50, radio_efecto=100,
            detonacion_distancia=80,
        )
        # Mismo z que el misil recién lanzado: el test verifica proximidad
        # horizontal, no el perfil de altitud (cubierto en tests dedicados).
        drones = [Drone(0, x=480, y=500, z=misil.z)]

        # Primer cruce del umbral (80m exactos): arma el fusible, no detona todavía.
        assert not misil.debe_detonar(drones)

        # Se sigue acercando (60m): tampoco detona, sigue cerrando distancia.
        drones[0].x = 460
        assert not misil.debe_detonar(drones)

        # Empieza a alejarse (70m, más que el mínimo de 60m visto): ahí sí detona.
        drones[0].x = 470
        assert misil.debe_detonar(drones)

    def test_mover_retrocompatible_sin_drones(self):
        """mover(dt) sin lista de drones sigue funcionando (vuelo balístico)."""
        misil = HPMissile(x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=100)
        angulo_inicial = misil.angulo
        misil.mover(1.0)
        misil.mover(1.0)
        assert misil.angulo == angulo_inicial

    def test_altitud_asciende_desde_el_lanzamiento(self):
        misil = HPMissile(
            x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=100,
            tiempo_detonacion=20.0,
        )
        z_inicial = misil.z
        for _ in range(20):
            misil.mover(0.5)
        assert misil.z > z_inicial

    def test_descenso_alcanza_altitud_del_blanco_cerca_de_la_detonacion(self):
        """
        Regresión: el descenso solía depender de una fracción del tiempo
        ESTIMADO al lanzar, así que si la detonación por proximidad ocurría
        antes de lo estimado, el misil detonaba aún en altitud de crucero,
        muy por encima de los drones (ver docs/FISICA_Y_MATEMATICA.md).
        Ahora el descenso se dispara por proximidad horizontal real: al
        llegar a la distancia de detonación, el misil ya debe estar cerca
        de la altitud del blanco.
        """
        misil = HPMissile(
            x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=150,
            tiempo_detonacion=30.0, detonacion_distancia=80, guiado=False,
        )
        # Distancia de compromiso típica del campo (ver docs/FISICA_Y_MATEMATICA.md);
        # a rango de "quemarropa" el misil no alcanza a corregir del todo la
        # altitud, eso es una limitación física esperada, no lo que este test cubre.
        objetivo = Drone(0, x=700, y=0, z=100.0)

        dt = 0.05
        for _ in range(200):
            if misil.x >= objetivo.x - misil.detonacion_distancia:
                break
            misil.mover(dt, [objetivo])

        assert abs(misil.z - objetivo.z) < 20.0

    def test_guiado_corrige_rumbo_hacia_el_objetivo(self):
        """Con guiado activo, el misil debe curvar su rumbo hacia un blanco
        que no está en su línea de vuelo inicial (navegación proporcional)."""
        misil = HPMissile(
            x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=100,
            tiempo_detonacion=30.0, guiado=True,
        )
        # Objetivo desviado respecto al rumbo inicial (0°): más al norte.
        drones = [Drone(0, x=300, y=200, z=misil.z)]

        for _ in range(10):
            misil.mover(0.1, drones)

        assert misil.angulo != pytest.approx(0.0)
        assert misil.target_id == 0

    def test_guiado_respeta_limite_de_giro(self):
        from src.config import MISSILE_MAX_TURN_RATE_DEG_S

        misil = HPMissile(
            x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=100,
            tiempo_detonacion=30.0, guiado=True,
        )
        drones = [Drone(0, x=1, y=1000, z=misil.z)]  # objetivo casi perpendicular

        dt = 0.1
        misil.mover(dt, drones)  # primer tick solo fija el LOS previo
        angulo_previo = misil.angulo
        misil.mover(dt, drones)
        giro = abs(((misil.angulo - angulo_previo + 180) % 360) - 180)
        assert giro <= MISSILE_MAX_TURN_RATE_DEG_S * dt + 1e-6

    def test_sin_guiado_vuela_balistico(self):
        misil = HPMissile(
            x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=100,
            tiempo_detonacion=30.0, guiado=False,
        )
        drones = [Drone(0, x=300, y=200, z=misil.z)]
        for _ in range(10):
            misil.mover(0.1, drones)
        assert misil.angulo == pytest.approx(0.0)


class TestFriisModel:
    def test_ganancia_decrece_con_apertura(self):
        from src.engine.hpm_engine import antenna_gain_from_aperture

        g_estrecho = antenna_gain_from_aperture(10)
        g_ancho = antenna_gain_from_aperture(60)
        assert g_estrecho > g_ancho

    def test_densidad_potencia_decrece_con_distancia(self):
        from src.engine.hpm_engine import power_density

        s_cerca = power_density(50000, 1.0, 10)
        s_lejos = power_density(50000, 1.0, 100)
        assert s_cerca > s_lejos

    def test_campo_e_formula_impedancia_vacio(self):
        from src.engine.hpm_engine import efield_from_power_density

        # E = sqrt(S * 377); con S=1 W/m^2, E = sqrt(377)
        assert efield_from_power_density(1.0) == pytest.approx(np.sqrt(377.0), rel=1e-6)

    def test_probabilidad_friis_decrece_con_distancia(self):
        from src.engine.hpm_engine import calculate_neutralization_probability_friis

        p_cerca = calculate_neutralization_probability_friis(80, 10, apertura_cono=30)
        p_lejos = calculate_neutralization_probability_friis(80, 300, apertura_cono=30)
        assert p_cerca > p_lejos

    def test_probabilidad_friis_fuera_del_cono_es_cero(self):
        from src.engine.hpm_engine import calculate_neutralization_probability_friis

        p = calculate_neutralization_probability_friis(80, 10, apertura_cono=30, angulo_offset=45)
        assert p == 0.0

    def test_probabilidad_area_friis_decrece_con_distancia(self):
        from src.engine.hpm_engine import calculate_area_neutralization_probability_friis

        p_cerca = calculate_area_neutralization_probability_friis(80, 10)
        p_lejos = calculate_area_neutralization_probability_friis(80, 300)
        assert p_cerca > p_lejos


class TestHardeningOdds:
    def test_factor_1_no_cambia_la_probabilidad(self):
        from src.engine.hpm_engine import apply_hardening_odds

        assert apply_hardening_odds(0.5, 1.0) == pytest.approx(0.5)

    def test_reduccion_proporcional_no_se_dispara(self):
        """
        Regresión: aplicar el factor de blindaje multiplicando el umbral de
        campo E (en vez de en espacio de momios) daba reducciones de 14x a
        821x según la distancia — no el 2.5x pretendido — dejando a los
        drones blindados prácticamente invencibles en todo el rango de
        combate real. La reducción real ahora debe quedar acotada cerca del
        factor configurado, no dispararse órdenes de magnitud.
        """
        from src.engine.hpm_engine import apply_hardening_odds

        for p_base in [0.05, 0.2, 0.5, 0.8, 0.99]:
            p_blindado = apply_hardening_odds(p_base, 2.5)
            reduccion = p_base / p_blindado
            assert reduccion < 3.0
            assert p_blindado < p_base

    def test_factor_alto_no_llega_a_cero_absoluto(self):
        from src.engine.hpm_engine import apply_hardening_odds

        assert apply_hardening_odds(0.9, 10.0) > 0.0


class TestValidation:
    def test_detecta_probabilidad_fuera_de_rango(self):
        from src.engine.validation import check_shot_invariants

        eventos = [{"drone_id": 0, "distancia": 10, "probabilidad": 1.5, "neutralizado": False}]
        avisos = check_shot_invariants(eventos)
        assert any("probabilidad" in a for a in avisos)

    def test_detecta_impacto_fuera_de_radio(self):
        from src.engine.validation import check_shot_invariants

        eventos = [{"drone_id": 0, "distancia": 150, "probabilidad": 0.4, "neutralizado": False}]
        avisos = check_shot_invariants(eventos, {"radio_efecto": 100})
        assert any("radio de efecto" in a for a in avisos)

    def test_sin_avisos_para_evento_consistente(self):
        from src.engine.validation import check_shot_invariants

        eventos = [
            {"drone_id": 0, "distancia": 10, "probabilidad": 0.9, "neutralizado": True},
            {"drone_id": 1, "distancia": 90, "probabilidad": 0.1, "neutralizado": False},
        ]
        avisos = check_shot_invariants(eventos, {"radio_efecto": 100})
        assert avisos == []

    def test_no_marca_falso_positivo_por_atenuacion_angular_del_cono(self):
        """Un dron más lejano pero más centrado en el cono puede tener mayor
        probabilidad que uno más cercano cerca del borde — no es un bug."""
        from src.engine.validation import check_shot_invariants

        eventos = [
            {"drone_id": 0, "distancia": 600, "angulo_offset": 40, "probabilidad": 0.01, "neutralizado": False},
            {"drone_id": 1, "distancia": 700, "angulo_offset": 2, "probabilidad": 0.03, "neutralizado": False},
        ]
        avisos = check_shot_invariants(eventos)
        assert avisos == []


class TestHPMissileSystem:
    def test_lanzar_consume_municion(self):
        sistema = HPMissileSystem(municion_total=5, municion_restante=5)
        drones = [Drone(0, x=500, y=500)]
        result = sistema.lanzar(x=0, y=0, angulo=45, potencia=50, radio=100, drones=drones)
        assert result["success"] is True
        assert result["municion_restante"] == 4
        assert len(sistema.misiles) == 1

    def test_lanzar_sin_municion_falla(self):
        sistema = HPMissileSystem(municion_total=0, municion_restante=0)
        result = sistema.lanzar(x=0, y=0, angulo=0, drones=[])
        assert result["success"] is False

    def test_recargar(self):
        sistema = HPMissileSystem(municion_total=10, municion_restante=3)
        result = sistema.recargar(5)
        assert result["añadido"] == 5
        assert result["municion_restante"] == 8

    def test_actualizar_misiles_detona(self):
        np.random.seed(0)
        sistema = HPMissileSystem(municion_total=10, municion_restante=10)
        drones = [Drone(0, x=500, y=500)]
        sistema.lanzar(x=420, y=500, angulo=0, potencia=100, radio=150, drones=drones)

        eventos = []
        for _ in range(200):
            eventos = sistema.actualizar_misiles(drones, 0.05)
            if eventos:
                break

        assert any(e["tipo"] == "misil_detonado" for e in eventos)


class TestSimulationMissile:
    def test_launch_missile(self):
        sim = SimulationEngine(swarm_size=5)
        result = sim.launch_missile(x=0, y=0, angulo=45, potencia=50, radio=100)
        assert result["success"] is True
        status = sim.get_missile_status()
        assert status["municion_restante"] == sim.missile_system.municion_total - 1
        sim.shutdown()

    def test_status_incluye_missiles(self):
        sim = SimulationEngine(swarm_size=3)
        status = sim.get_status()
        assert "missiles" in status
        assert "municion_restante" in status["missiles"]
        sim.shutdown()

    def test_reload_missiles(self):
        sim = SimulationEngine(swarm_size=3)
        sim.missile_system.municion_restante = 2
        result = sim.reload_missiles(3)
        assert result["municion_restante"] == 5
        sim.shutdown()
