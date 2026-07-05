"""Pruebas básicas del simulador EW."""

import time

import numpy as np
import pytest

from src.engine.hpm_engine import calculate_neutralization_probability
from src.engine.physics import update_position
from src.engine.simulation import SimulationEngine, SimulationState
from src.models.drone import Drone, DroneEstado
from src.models.hpm_weapon import HPMWeapon
from src.models.swarm import FormacionTipo, Swarm


class TestDrone:
    def test_mover_actualiza_posicion(self):
        drone = Drone(0, x=0, y=0, velocidad=10, angulo=0)
        drone.mover(dt=1.0)
        assert drone.x == pytest.approx(10.0)
        assert drone.y == pytest.approx(0.0)

    def test_neutralizado_no_se_mueve(self):
        drone = Drone(0, x=5, y=5, velocidad=10, angulo=0)
        drone.estado = DroneEstado.NEUTRALIZADO
        drone.mover(dt=1.0)
        assert drone.x == 5
        assert drone.y == 5

    def test_recibir_daño_cerca_alta_probabilidad(self):
        np.random.seed(42)
        drone = Drone(0, x=10, y=0)
        neutralizado = drone.recibir_daño(potencia=100, distancia=5, angulo_offset=0)
        assert neutralizado or drone.salud < 100


class TestHPMEngine:
    def test_probabilidad_decrece_con_distancia(self):
        p_cerca = calculate_neutralization_probability(25, 10, 0, 30)
        p_lejos = calculate_neutralization_probability(25, 100, 0, 30)
        assert p_cerca > p_lejos

    def test_fuera_del_cono_probabilidad_cero(self):
        p = calculate_neutralization_probability(25, 10, 20, 30)
        assert p == 0.0

    def test_formula_exponencial(self):
        p = calculate_neutralization_probability(25, 50, 0, 90, k=0.015)
        expected = 1 - np.exp(-0.015 * 25 / (50**2))
        assert p == pytest.approx(expected, rel=0.01)


class TestHPMWeapon:
    def test_disparar_afecta_drones_en_cono(self):
        weapon = HPMWeapon(potencia=50, direccion=0, apertura_cono=60, origen_x=0, origen_y=0)
        drones = [
            Drone(0, x=100, y=0),
            Drone(1, x=100, y=200),
        ]
        np.random.seed(0)
        eventos = weapon.disparar(drones)
        assert len(eventos) >= 1
        assert eventos[0]["drone_id"] == 0


class TestSwarm:
    def test_formacion_cuadrada(self):
        swarm = Swarm(formacion=FormacionTipo.CUADRADA)
        swarm.inicializar_formacion("cuadrada", 16)
        assert len(swarm.drones) == 16

    def test_formacion_circular(self):
        swarm = Swarm(formacion=FormacionTipo.CIRCULAR)
        swarm.inicializar_formacion("circular", 10)
        assert len(swarm.drones) == 10

    def test_formacion_aleatoria(self):
        swarm = Swarm(formacion=FormacionTipo.ALEATORIA)
        swarm.inicializar_formacion("aleatoria", 5)
        assert len(swarm.drones) == 5

    def test_formacion_linea(self):
        swarm = Swarm(formacion=FormacionTipo.LINEA)
        swarm.inicializar_formacion("linea", 8)
        assert len(swarm.drones) == 8
        ys = {d.y for d in swarm.drones}
        assert len(ys) == 1, "todos los drones de la línea deben compartir la misma Y inicial"

    def test_formacion_v(self):
        swarm = Swarm(formacion=FormacionTipo.V)
        swarm.inicializar_formacion("v", 9)
        assert len(swarm.drones) == 9
        apex = swarm.drones[0]
        assert apex.x == swarm.centro_x and apex.y == swarm.centro_y

    def test_velocidad_en_rango_realista(self):
        swarm = Swarm()
        swarm.inicializar_formacion("aleatoria", 30)
        assert all(10.0 <= d.velocidad <= 30.0 for d in swarm.drones)

    def test_actualizar_mueve_drones(self):
        swarm = Swarm()
        swarm.inicializar_formacion("cuadrada", 1)
        x_inicial = swarm.drones[0].x
        y_inicial = swarm.drones[0].y
        swarm.actualizar(1.0)
        moved = (
            swarm.drones[0].x != x_inicial or swarm.drones[0].y != y_inicial
        )
        assert moved


class TestPhysics:
    def test_update_position_angulo_90(self):
        x, y = update_position(0, 0, 10, 90, 1.0)
        assert x == pytest.approx(0.0, abs=1e-6)
        assert y == pytest.approx(10.0, abs=1e-6)


class TestSimulationEngine:
    def test_inicializacion(self):
        sim = SimulationEngine(swarm_size=10)
        assert len(sim.swarm.drones) == 10
        assert sim.estado == SimulationState.DETENIDA

    def test_start_stop(self):
        sim = SimulationEngine(swarm_size=5)
        result = sim.start()
        assert result["estado"] == "ejecutando"
        assert sim.estado == SimulationState.EJECUTANDO

        result = sim.stop()
        assert result["estado"] == "pausada"
        sim.shutdown()

    def test_fire_registra_eventos(self):
        sim = SimulationEngine(swarm_size=5)
        result = sim.fire(potencia=50, direccion=45)
        assert "eventos" in result
        assert sim.hpm.disparos == 1
        sim.shutdown()

    def test_set_speed_ajusta_time_scale(self):
        sim = SimulationEngine(swarm_size=3)
        result = sim.set_speed(5)
        assert result["time_scale"] == 5
        assert sim.time_scale == 5
        sim.shutdown()

    def test_set_speed_clampea_limites(self):
        sim = SimulationEngine(swarm_size=3)
        assert sim.set_speed(1000)["time_scale"] == 10.0
        assert sim.set_speed(-5)["time_scale"] == 0.1
        sim.shutdown()

    def test_time_scale_acelera_avance_de_tiempo(self):
        sim = SimulationEngine(swarm_size=3)
        sim.set_speed(10)
        sim.start()
        time.sleep(0.3)
        sim.stop()
        tiempo_acelerado = sim.tiempo
        sim.shutdown()

        sim2 = SimulationEngine(swarm_size=3)
        sim2.start()
        time.sleep(0.3)
        sim2.stop()
        tiempo_normal = sim2.tiempo
        sim2.shutdown()

        assert tiempo_acelerado > tiempo_normal

    def test_get_status_estructura(self):
        sim = SimulationEngine(swarm_size=3)
        status = sim.get_status()
        assert "drones" in status
        assert "conteo_estados" in status
        assert status["conteo_estados"]["activo"] == 3
        sim.shutdown()
