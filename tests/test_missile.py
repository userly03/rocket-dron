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

    def test_debe_detonar_cerca_del_enjambre(self):
        misil = HPMissile(
            x=400, y=500, angulo=0, potencia_hpm=50, radio_efecto=100,
            detonacion_distancia=80,
        )
        drones = [Drone(0, x=480, y=500)]
        assert misil.debe_detonar(drones)


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
