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

    def test_dron_blindado_resiste_mas_que_estandar(self):
        estandar = Drone(0, x=10, y=0, blindaje="estandar", e_threshold_mult=1.0)
        blindado = Drone(1, x=10, y=0, blindaje="blindado", e_threshold_mult=2.5)
        estandar.recibir_daño(potencia=30, distancia=50, angulo_offset=0)
        blindado.recibir_daño(potencia=30, distancia=50, angulo_offset=0)
        assert blindado.ultima_probabilidad < estandar.ultima_probabilidad


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


class TestFlocking:
    def test_dron_sin_vecinos_mantiene_rumbo(self):
        from src.engine.flocking import compute_headings

        drones = [Drone(0, x=0, y=0, angulo=90)]
        angulos = compute_headings(drones, dt=0.1)
        assert angulos[0] == pytest.approx(90.0)

    def test_separacion_aumenta_distancia_entre_drones_cercanos(self):
        from src.engine.flocking import compute_headings
        from src.engine.physics import update_position
        from src.utils.helpers import distance

        # Dos drones muy cercanos: tras varios ticks, la separación debería
        # aumentar la distancia entre ellos (el giro está limitado por
        # tick, así que hace falta iterar, no un solo paso).
        a = Drone(0, x=0, y=0, angulo=0)
        b = Drone(1, x=5, y=0, angulo=180)
        dist_inicial = distance(a.x, a.y, b.x, b.y)

        dt = 0.1
        for _ in range(30):
            angulos = compute_headings([a, b], dt)
            a.angulo, b.angulo = angulos[0], angulos[1]
            a.x, a.y = update_position(a.x, a.y, a.velocidad, a.angulo, dt)
            b.x, b.y = update_position(b.x, b.y, b.velocidad, b.angulo, dt)

        dist_final = distance(a.x, a.y, b.x, b.y)
        assert dist_final > dist_inicial

    def test_dron_lejos_de_la_zona_de_patrulla_gira_hacia_ella(self):
        """
        Regresión: separación+alineación+cohesión puras no tienen ninguna
        tendencia a quedarse en una zona — el enjambre podía migrar entero y
        alejarse sin límite del alcance de radar/armas. La 4ta regla ("zona
        de patrulla") debe hacer que un dron muy alejado del centro de
        formación gire de vuelta hacia él.
        """
        from src.engine.flocking import compute_headings
        from src.config import BOIDS_HOME_RADIUS

        home_x, home_y = 500.0, 500.0
        # Bien lejos del centro, apuntando en dirección opuesta (alejándose).
        drone = Drone(0, x=home_x + BOIDS_HOME_RADIUS * 3, y=home_y, angulo=0)
        angulos = compute_headings([drone], dt=0.5, home_x=home_x, home_y=home_y)
        # Girando desde 0° (alejándose en +x) hacia el centro (que está en -x
        # desde su posición) el nuevo rumbo debe acercarse a 180°.
        assert angulos[0] != pytest.approx(0.0)

    def test_dron_dentro_de_la_zona_de_patrulla_no_es_forzado(self):
        from src.engine.flocking import compute_headings

        home_x, home_y = 500.0, 500.0
        drone = Drone(0, x=home_x + 10, y=home_y, angulo=45)
        angulos = compute_headings([drone], dt=0.5, home_x=home_x, home_y=home_y)
        assert angulos[0] == pytest.approx(45.0)

    def test_alineacion_atrae_rumbo_hacia_vecinos(self):
        from src.engine.flocking import compute_headings

        # Un dron con rumbo distinto rodeado de vecinos alineados a 90°
        # debería empezar a girar hacia 90° (no seguir en línea recta a 0°).
        objetivo = Drone(0, x=500, y=500, angulo=0)
        vecinos = [Drone(i, x=500 + i, y=500, angulo=90) for i in range(1, 6)]
        angulos = compute_headings([objetivo] + vecinos, dt=0.5)
        # No debería quedar exactamente en 0° (algo de giro hacia el rumbo vecino).
        assert angulos[0] != pytest.approx(0.0)


class TestRadar:
    def test_probabilidad_deteccion_decrece_con_distancia(self):
        from src.engine.radar_engine import detection_probability, radar_received_power_w, wavelength_m

        wl = wavelength_m(2.45)
        pr_cerca = radar_received_power_w(10, 10 ** (25 / 10), wl, 0.02, 200)
        pr_lejos = radar_received_power_w(10, 10 ** (25 / 10), wl, 0.02, 1500)
        p_cerca = detection_probability(pr_cerca, 1e-13)
        p_lejos = detection_probability(pr_lejos, 1e-13)
        assert p_cerca > p_lejos

    def test_evaluar_deteccion_cerca_vs_lejos(self):
        from src.engine.radar_engine import evaluar_deteccion

        detectado_cerca, _ = evaluar_deteccion(100, 10, 25, 2.45, 0.02, 1e-13)
        detectado_lejos, _ = evaluar_deteccion(3000, 10, 25, 2.45, 0.02, 1e-13)
        assert detectado_cerca is True
        assert detectado_lejos is False

    def test_dron_recien_creado_esta_detectado_por_defecto(self):
        # Evita que drones construidos directamente (fuera de Swarm) queden
        # indetectables por omisión, rompiendo el auto-apuntado existente.
        drone = Drone(0, x=100, y=100)
        assert drone.detectado is True


class TestJammer:
    def test_jammer_inactivo_no_interfiere(self):
        from src.models.jammer import Jammer

        jammer = Jammer()  # activo=False por defecto
        drone = Drone(0, x=50, y=0, z=0)
        eventos = jammer.actualizar([drone])
        assert eventos == []
        assert drone.estado == DroneEstado.ACTIVO

    def test_jammer_interfiere_dron_en_cono_y_lo_congela(self):
        from src.models.jammer import Jammer

        jammer = Jammer()
        jammer.iniciar(direccion=0, potencia=50, apertura_cono=45)
        drone = Drone(0, x=30, y=0, z=0, velocidad=10, angulo=90)

        eventos = jammer.actualizar([drone])
        assert any(e["tipo"] == "dron_interferido" for e in eventos)
        assert drone.estado == DroneEstado.INTERFERIDO

        x_antes = drone.x
        drone.mover(dt=1.0)
        assert drone.x == x_antes  # congelado: no responde a control

    def test_jammer_fuera_del_cono_no_interfiere(self):
        from src.models.jammer import Jammer

        jammer = Jammer()
        jammer.iniciar(direccion=0, potencia=50, apertura_cono=20)
        drone = Drone(0, x=0, y=30, z=0)  # a 90° del eje del cono
        eventos = jammer.actualizar([drone])
        assert eventos == []
        assert drone.estado == DroneEstado.ACTIVO

    def test_dron_recupera_enlace_al_detener_jammer(self):
        from src.models.jammer import Jammer

        jammer = Jammer()
        jammer.iniciar(direccion=0, potencia=50, apertura_cono=45)
        drone = Drone(0, x=30, y=0, z=0)
        jammer.actualizar([drone])
        assert drone.estado == DroneEstado.INTERFERIDO

        jammer.detener()
        eventos = jammer.actualizar([drone])
        assert any(e["tipo"] == "dron_recuperado" for e in eventos)
        assert drone.estado == DroneEstado.ACTIVO


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
