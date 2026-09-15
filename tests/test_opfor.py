"""
Tests de OPFOR reactivo (P2-E): estado partido en dos ejes ortogonales,
memoria de amenaza con repulsor decadente, y perfiles de pérdida de enlace.

Deliberadamente NO se prueba letalidad/conteo de neutralizados en ningún
test de este archivo: el modelo de daño (P1-F, log-logística) se está
recalibrando en paralelo y mueve todas las probabilidades. Lo que se prueba
acá es COMPORTAMIENTO — posiciones, rumbos y estados — que es ortogonal al
modelo de daño. Donde hace falta una "detonación"/"disparo" se fuerza el
estado o se llama directamente al método relevante, nunca se depende de que
el modelo efectivamente mate a nadie.
"""

from __future__ import annotations

import numpy as np
import pytest

import src.engine.flocking as flocking
from src.config import HPM_ORIGIN_X, HPM_ORIGIN_Y
from src.engine.simulation import SimulationEngine
from src.models.drone import (
    Drone,
    DroneEstado,
    EstadoEnlace,
    EstadoSalud,
    PerfilLostLink,
)
from src.models.structure import Estructura
from src.models.swarm import Swarm
from src.utils.helpers import distance


# ---------------------------------------------------------------------------
# Parte 1: estado partido en dos ejes ortogonales
# ---------------------------------------------------------------------------


class TestEstadoPartido:
    def test_por_defecto_activo_y_enlace_ok(self):
        drone = Drone(0, x=0, y=0)
        assert drone.estado_salud == EstadoSalud.ACTIVO
        assert drone.estado_enlace == EstadoEnlace.OK
        assert drone.estado == DroneEstado.ACTIVO

    def test_danado_e_interferido_son_representables_a_la_vez(self):
        """
        Antes de P2-E esta combinación no existía: un único enum no puede
        representar "dañado Y sin enlace". Con los dos ejes ortogonales,
        es un estado normal y válido — y la propiedad derivada ``estado``
        debe reportar INTERFERIDO (el enlace perdido "gana", igual que
        reportaba el modelo de un solo enum).
        """
        drone = Drone(0, x=0, y=0)
        drone.estado_salud = EstadoSalud.DANADO
        drone.estado_enlace = EstadoEnlace.INTERFERIDO

        assert drone.estado_salud == EstadoSalud.DANADO
        assert drone.estado_enlace == EstadoEnlace.INTERFERIDO
        assert drone.estado == DroneEstado.INTERFERIDO

        # Al recuperar el enlace, la salud (que nunca se tocó) vuelve a ser
        # observable en la vista derivada.
        drone.estado_enlace = EstadoEnlace.OK
        assert drone.estado == DroneEstado.DANADO

    def test_neutralizado_es_terminal_por_encima_del_enlace(self):
        drone = Drone(0, x=0, y=0)
        drone.estado_salud = EstadoSalud.NEUTRALIZADO
        drone.estado_enlace = EstadoEnlace.INTERFERIDO
        assert drone.estado == DroneEstado.NEUTRALIZADO

    def test_setter_de_compatibilidad_no_cruza_los_ejes(self):
        """
        ``drone.estado = DroneEstado.X`` es el camino de compatibilidad que
        sigue usando código externo no tocado por este ítem (p. ej.
        ``HPMissile.detonar``). Debe escribir SOLO el eje correspondiente:
        un valor de salud no debe tocar el enlace, y viceversa.
        """
        interferido_y_luego_danado = Drone(0, x=0, y=0)
        interferido_y_luego_danado.estado = DroneEstado.INTERFERIDO
        interferido_y_luego_danado.estado = DroneEstado.DANADO
        assert interferido_y_luego_danado.estado_enlace == EstadoEnlace.INTERFERIDO
        assert interferido_y_luego_danado.estado_salud == EstadoSalud.DANADO

        danado_y_luego_interferido = Drone(1, x=0, y=0)
        danado_y_luego_interferido.estado = DroneEstado.DANADO
        danado_y_luego_interferido.estado = DroneEstado.INTERFERIDO
        assert danado_y_luego_interferido.estado_salud == EstadoSalud.DANADO
        assert danado_y_luego_interferido.estado_enlace == EstadoEnlace.INTERFERIDO

    def test_estado_derivado_cubre_los_cuatro_valores_de_siempre(self):
        """``estado`` sigue devolviendo exactamente los 4 valores del enum
        combinado en cada combinación alcanzable — la interfaz vieja
        (frontend/API/tests) no ve ninguna diferencia."""
        drone = Drone(0, x=0, y=0)
        assert drone.estado == DroneEstado.ACTIVO

        drone.estado_salud = EstadoSalud.DANADO
        assert drone.estado == DroneEstado.DANADO

        drone.estado_salud = EstadoSalud.ACTIVO
        drone.estado_enlace = EstadoEnlace.INTERFERIDO
        assert drone.estado == DroneEstado.INTERFERIDO

        drone.estado_enlace = EstadoEnlace.OK
        drone.estado_salud = EstadoSalud.NEUTRALIZADO
        assert drone.estado == DroneEstado.NEUTRALIZADO


# ---------------------------------------------------------------------------
# Parte 2: memoria de amenaza + repulsor con decaimiento
# ---------------------------------------------------------------------------


def _formacion_compacta(centro: tuple[float, float]) -> list[Drone]:
    """Seis drones apretados alrededor de ``centro`` — suficientemente cerca
    para que separación/alineación/cohesión estén activas (dentro de
    BOIDS_NEIGHBOR_RADIUS) y dentro de BOIDS_HOME_RADIUS (el término home
    no interfiere)."""
    cx, cy = centro
    offsets = [(0, 0), (10, 0), (0, 10), (-10, 0), (0, -10), (10, 10)]
    return [
        Drone(i, x=cx + dx, y=cy + dy, angulo=0.0, velocidad=15.0)
        for i, (dx, dy) in enumerate(offsets)
    ]


def _correr_simulacion(drones: list[Drone], centro, pasos: int, dt: float) -> None:
    swarm = Swarm(centro_x=centro[0], centro_y=centro[1])
    swarm.drones = drones
    for _ in range(pasos):
        swarm.actualizar(dt)
        swarm.actualizar_amenazas(dt)


class TestMemoriaDeAmenaza:
    def test_dispersion_post_impacto_aumenta_distancia_vs_control_sin_memoria(
        self, monkeypatch
    ):
        """
        EL test central de la Parte 2: tras una "detonación" en el centro
        de la formación, la distancia MEDIA del enjambre a ese punto debe
        aumentar más que en un control idéntico (mismo escenario, mismas
        posiciones/velocidades iniciales) con el término de amenaza
        desactivado (``BOIDS_THREAT_WEIGHT = 0``). Sin el control, este
        test no probaría nada: separación/cohesión ya mueven algo a los
        drones incluso sin memoria de amenaza.
        """
        centro = (500.0, 500.0)
        dt = 0.3
        pasos = 15

        # --- Caso CON memoria de amenaza (comportamiento por defecto) ---
        drones_con = _formacion_compacta(centro)
        for d in drones_con:
            d.registrar_impacto(*centro, intensidad=1.0)
        _correr_simulacion(drones_con, centro, pasos, dt)
        dist_media_con = sum(
            distance(d.x, d.y, *centro) for d in drones_con
        ) / len(drones_con)

        # --- Control: mismo escenario, término de amenaza anulado ---
        monkeypatch.setattr(flocking, "BOIDS_THREAT_WEIGHT", 0.0)
        drones_control = _formacion_compacta(centro)
        for d in drones_control:
            d.registrar_impacto(*centro, intensidad=1.0)
        _correr_simulacion(drones_control, centro, pasos, dt)
        dist_media_control = sum(
            distance(d.x, d.y, *centro) for d in drones_control
        ) / len(drones_control)

        assert dist_media_con > dist_media_control

    def test_intensidad_decae_con_el_tiempo(self):
        drone = Drone(0, x=0, y=0)
        drone.registrar_impacto(10.0, 10.0, intensidad=1.0)
        assert drone.amenaza_intensidad == pytest.approx(1.0)

        drone.actualizar_amenaza(dt=5.0)
        intensidad_tras_un_tau = drone.amenaza_intensidad
        assert 0.0 < intensidad_tras_un_tau < 1.0

        drone.actualizar_amenaza(dt=50.0)
        assert drone.amenaza_intensidad == 0.0

    def test_sin_memoria_activa_el_termino_no_aporta_nada(self):
        """Un dron nunca atacado (amenaza_intensidad == 0 por defecto) debe
        producir el MISMO rumbo con o sin el término de amenaza en el
        cálculo — el término es condicional, no un sesgo permanente."""
        from src.engine.flocking import compute_headings

        drone = Drone(0, x=0, y=0, angulo=45.0)
        assert drone.amenaza_intensidad == 0.0
        angulos = compute_headings([drone], dt=0.5)
        assert angulos[0] == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# Parte 3: perfiles de pérdida de enlace
# ---------------------------------------------------------------------------


class TestPerfilesLostLink:
    def test_hover_mantiene_posicion(self):
        drone = Drone(
            0, x=100.0, y=100.0, velocidad=15.0, angulo=45.0,
            perfil_lost_link=PerfilLostLink.HOVER,
        )
        drone.estado_enlace = EstadoEnlace.INTERFERIDO
        x0, y0 = drone.x, drone.y

        for _ in range(10):
            drone.mover(dt=0.5)

        assert drone.x == pytest.approx(x0, abs=1e-9)
        assert drone.y == pytest.approx(y0, abs=1e-9)

    def test_flyaway_se_aleja_monotonamente_a_rumbo_fijo(self):
        origen = (0.0, 0.0)
        drone = Drone(
            0, x=0.0, y=0.0, velocidad=20.0, angulo=30.0,
            perfil_lost_link=PerfilLostLink.FLYAWAY,
        )
        drone.estado_enlace = EstadoEnlace.INTERFERIDO

        distancias = []
        for _ in range(10):
            drone.mover(dt=0.5)
            distancias.append(distance(*origen, drone.x, drone.y))

        assert all(b > a for a, b in zip(distancias, distancias[1:]))
        # Rumbo fijo: nadie (ni compute_headings ni el propio perfil) toca
        # el ángulo de un flyaway aislado.
        assert drone.angulo == pytest.approx(30.0)

    def test_rth_reduce_distancia_al_centro(self):
        home = (500.0, 500.0)
        drone = Drone(
            0, x=800.0, y=500.0, velocidad=30.0, angulo=90.0,
            perfil_lost_link=PerfilLostLink.RTH,
        )
        drone.estado_enlace = EstadoEnlace.INTERFERIDO
        dist_inicial = distance(drone.x, drone.y, *home)

        for _ in range(40):
            drone.mover(dt=0.5, home_x=home[0], home_y=home[1])

        dist_final = distance(drone.x, drone.y, *home)
        assert dist_final < dist_inicial

    def test_aterrizar_reduce_z_hasta_el_suelo_y_se_queda(self):
        drone = Drone(
            0, x=200.0, y=200.0, z=10.0, velocidad=15.0, angulo=0.0,
            perfil_lost_link=PerfilLostLink.ATERRIZAR,
        )
        drone.estado_enlace = EstadoEnlace.INTERFERIDO

        for _ in range(10):
            drone.mover(dt=1.0)

        assert drone.z == 0.0
        assert drone.aterrizado is True
        # Aterrizaje en el sitio: sin desplazamiento horizontal.
        assert drone.x == pytest.approx(200.0)
        assert drone.y == pytest.approx(200.0)

        # Inerte para siempre, incluso si recupera el enlace.
        drone.estado_enlace = EstadoEnlace.OK
        drone.mover(dt=5.0)
        assert (drone.x, drone.y, drone.z) == (pytest.approx(200.0), pytest.approx(200.0), 0.0)

    def test_perfil_se_sortea_con_rng_inyectado_no_global(self):
        """Mismo criterio que blindaje/cable_length_m (P0-B): dos drones
        con el MISMO generador (mismo seed) sortean el MISMO perfil, y la
        tirada no debe depender del generador global."""
        d1 = Drone(0, x=0, y=0, rng=np.random.default_rng(7))
        d2 = Drone(1, x=0, y=0, rng=np.random.default_rng(7))
        assert d1.perfil_lost_link == d2.perfil_lost_link

    def test_las_cuatro_fracciones_aparecen_en_una_muestra_grande(self):
        """Sanity check estadístico de las fracciones configuradas: con una
        muestra grande deben aparecer los cuatro perfiles, y ninguno debe
        ser cero (en particular FLYAWAY, el caso adverso deliberadamente
        no-nulo)."""
        rng = np.random.default_rng(2024)
        conteo: dict[PerfilLostLink, int] = {}
        n = 3000
        for i in range(n):
            perfil = Drone(i, x=0, y=0, rng=rng).perfil_lost_link
            conteo[perfil] = conteo.get(perfil, 0) + 1

        assert set(conteo) == {
            PerfilLostLink.HOVER,
            PerfilLostLink.RTH,
            PerfilLostLink.ATERRIZAR,
            PerfilLostLink.FLYAWAY,
        }
        for cantidad in conteo.values():
            assert cantidad > 0


class TestRecuperacionDeEnlace:
    def test_recupera_enlace_y_retoma_flocking_normal(self):
        drone = Drone(
            0, x=0.0, y=0.0, velocidad=10.0, angulo=0.0,
            perfil_lost_link=PerfilLostLink.HOVER,
        )
        drone.estado_enlace = EstadoEnlace.INTERFERIDO
        drone.mover(dt=1.0)
        assert drone.x == pytest.approx(0.0)  # perfil hover: sin movimiento

        drone.estado_enlace = EstadoEnlace.OK
        drone.mover(dt=1.0)
        assert drone.x == pytest.approx(10.0)  # vuelo normal retomado

    def test_aterrizado_no_retoma_flocking_pese_a_recuperar_enlace(self):
        drone = Drone(
            0, x=50.0, y=50.0, z=2.0, velocidad=10.0, angulo=0.0,
            perfil_lost_link=PerfilLostLink.ATERRIZAR,
        )
        drone.estado_enlace = EstadoEnlace.INTERFERIDO
        drone.mover(dt=1.0)  # z: 2.0 -> 0.0, aterriza en este mismo tick
        assert drone.aterrizado is True

        drone.estado_enlace = EstadoEnlace.OK
        x_antes, y_antes = drone.x, drone.y
        drone.mover(dt=5.0)
        assert drone.x == x_antes
        assert drone.y == y_antes
        assert drone.z == 0.0


# ---------------------------------------------------------------------------
# Bug corregido: un dron interferido debe seguir afectando el flocking de
# sus vecinos (Swarm.actualizar lo excluía por completo del cálculo).
# ---------------------------------------------------------------------------


class TestVecinoInterferidoSigueAfectandoFlocking:
    def test_compute_headings_incluye_al_interferido_como_vecino(self):
        """Comparación directa a nivel de compute_headings: el rumbo que
        recibe un vecino cambia según si el dron interferido está o no en
        la lista — si no cambiara, el interferido sería invisible para el
        cálculo (el bug original)."""
        from src.engine.flocking import compute_headings

        def _vecino_y_interferido():
            vecino = Drone(1, x=10.0, y=0.0, angulo=0.0, velocidad=10.0)
            interferido = Drone(
                0, x=0.0, y=0.0, angulo=0.0, velocidad=10.0,
                perfil_lost_link=PerfilLostLink.HOVER,
            )
            interferido.estado_enlace = EstadoEnlace.INTERFERIDO
            return vecino, interferido

        vecino_con, interferido = _vecino_y_interferido()
        angulos_con = compute_headings([vecino_con, interferido], dt=0.5)

        vecino_sin, _ = _vecino_y_interferido()
        angulos_sin = compute_headings([vecino_sin], dt=0.5)

        assert angulos_con[vecino_con.id] != pytest.approx(angulos_sin[vecino_sin.id])

    def test_swarm_actualizar_no_excluye_al_interferido_del_calculo(self):
        """
        Mismo test pero a nivel de integración (``Swarm.actualizar``, donde
        vivía el bug real, auditoría §3.4). Posiciones lejos de los bordes
        del campo (centro en (500,500), no en el origen) para que
        ``check_boundary_collision`` no confunda el resultado — un dron
        justo en el borde se refleja SIEMPRE, con o sin vecino interferido,
        y eso no es lo que este test quiere aislar.
        """
        vecino = Drone(0, x=510.0, y=500.0, angulo=0.0, velocidad=10.0)
        interferido = Drone(
            1, x=500.0, y=500.0, angulo=0.0, velocidad=10.0,
            perfil_lost_link=PerfilLostLink.HOVER,
        )
        interferido.estado_enlace = EstadoEnlace.INTERFERIDO

        swarm_con = Swarm(centro_x=500.0, centro_y=500.0)
        swarm_con.drones = [vecino, interferido]
        swarm_con.actualizar(dt=0.5)

        vecino_solo = Drone(0, x=510.0, y=500.0, angulo=0.0, velocidad=10.0)
        swarm_sin = Swarm(centro_x=500.0, centro_y=500.0)
        swarm_sin.drones = [vecino_solo]
        swarm_sin.actualizar(dt=0.5)

        assert vecino.angulo != pytest.approx(vecino_solo.angulo)

    def test_el_propio_interferido_no_seguido_por_flocking_propio(self):
        """El dron interferido SÍ entra al cálculo como vecino, pero su
        PROPIO rumbo no lo gobierna compute_headings sino su perfil
        lost-link — con HOVER, ni siquiera avanza. Posiciones lejos del
        borde del campo, mismo motivo que el test anterior."""
        vecino = Drone(0, x=510.0, y=500.0, angulo=0.0, velocidad=10.0)
        interferido = Drone(
            1, x=500.0, y=500.0, angulo=90.0, velocidad=10.0,
            perfil_lost_link=PerfilLostLink.HOVER,
        )
        interferido.estado_enlace = EstadoEnlace.INTERFERIDO

        swarm = Swarm(centro_x=500.0, centro_y=500.0)
        swarm.drones = [vecino, interferido]
        swarm.actualizar(dt=0.5)

        assert interferido.angulo == pytest.approx(90.0)
        assert interferido.x == pytest.approx(500.0)
        assert interferido.y == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# Integración: los eventos de disparo/detonación siembran la memoria, y el
# decaimiento avanza en SimulationEngine._tick.
# ---------------------------------------------------------------------------


class TestIntegracionSimulationEngine:
    def test_fire_siembra_memoria_en_los_drones_impactados(self):
        sim = SimulationEngine(swarm_size=1)
        drone = Drone(0, x=100.0, y=0.0, z=sim.hpm.origen_z)
        sim.swarm.drones = [drone]

        resultado = sim.fire(potencia=80, direccion=0, apertura_cono=60)

        assert resultado["eventos"], "el disparo debería alcanzar al dron alineado con el cañón"
        assert drone.amenaza_intensidad > 0.0
        assert (drone.amenaza_x, drone.amenaza_y) == (sim.hpm.origen_x, sim.hpm.origen_y)
        sim.shutdown()

    def test_process_missile_events_siembra_memoria_en_el_punto_de_detonacion(self):
        sim = SimulationEngine(swarm_size=1)
        drone = sim.swarm.drones[0]
        assert drone.amenaza_intensidad == 0.0

        evento = {
            "tipo": "misil_detonado",
            "misil_id": "test-1",
            "x": 321.0,
            "y": 654.0,
            "radio_efecto": 100.0,
            "potencia_hpm": 50.0,
            "impactos": [{"drone_id": drone.id, "neutralizado": False}],
            "neutralizados": 0,
        }
        sim._process_missile_events([evento])

        assert drone.amenaza_intensidad > 0.0
        assert (drone.amenaza_x, drone.amenaza_y) == (321.0, 654.0)
        sim.shutdown()

    def test_tick_decae_la_memoria_de_amenaza_independientemente_del_flocking(self):
        sim = SimulationEngine(swarm_size=1)
        drone = sim.swarm.drones[0]
        drone.registrar_impacto(0.0, 0.0, intensidad=1.0)

        # mover_enjambre=False (rama "pausada con misiles en vuelo"): el
        # decaimiento debe avanzar igual, porque es función del tiempo, no
        # del flocking.
        sim._tick(dt=1.0, mover_enjambre=False)

        assert 0.0 < drone.amenaza_intensidad < 1.0
        sim.shutdown()


# ---------------------------------------------------------------------------
# Parte 4: propagación de la memoria de amenaza entre vecinos (biomimesis)
# ---------------------------------------------------------------------------


class TestPropagacionDeAlarma:
    def test_propaga_al_vecino_sin_amenaza_propia(self):
        golpeado = Drone(0, x=0.0, y=0.0)
        golpeado.registrar_impacto(100.0, 200.0, intensidad=1.0)
        vecino = Drone(1, x=10.0, y=0.0)  # bien dentro de BOIDS_NEIGHBOR_RADIUS (80)
        assert vecino.amenaza_intensidad == 0.0

        flocking.propagate_alarm([golpeado, vecino])

        assert vecino.amenaza_intensidad == pytest.approx(1.0 * flocking.BOIDS_ALARM_PROPAGATION_GAIN)
        assert (vecino.amenaza_x, vecino.amenaza_y) == (100.0, 200.0)
        # El dron impactado directamente no pierde su propia memoria.
        assert golpeado.amenaza_intensidad == pytest.approx(1.0)

    def test_no_propaga_mas_alla_del_radio_de_vecinos(self):
        golpeado = Drone(0, x=0.0, y=0.0)
        golpeado.registrar_impacto(0.0, 0.0, intensidad=1.0)
        lejano = Drone(1, x=1000.0, y=1000.0)  # muy fuera de BOIDS_NEIGHBOR_RADIUS

        flocking.propagate_alarm([golpeado, lejano])

        assert lejano.amenaza_intensidad == 0.0

    def test_no_reduce_una_amenaza_propia_mas_fuerte(self):
        """Un dron con memoria propia más intensa que lo que le contagiaría
        un vecino más débil no la pierde — max(propia, contagiada), nunca
        al revés."""
        fuerte = Drone(0, x=0.0, y=0.0)
        fuerte.registrar_impacto(5.0, 5.0, intensidad=1.0)
        debil = Drone(1, x=10.0, y=0.0)
        debil.registrar_impacto(500.0, 500.0, intensidad=0.1)

        flocking.propagate_alarm([fuerte, debil])

        assert fuerte.amenaza_intensidad == pytest.approx(1.0)
        assert (fuerte.amenaza_x, fuerte.amenaza_y) == (5.0, 5.0)

    def test_un_salto_por_llamada_no_varios_de_una_vez(self):
        """Núcleo del diseño (ver la nota de 'actualización sincrónica' en
        el docstring de propagate_alarm): A-B-C en línea, separados 20m
        entre consecutivos (vecinos directos: A-B y B-C, pero A y C NO son
        vecinos entre sí a 40m de distancia si BOIDS_NEIGHBOR_RADIUS < 40 —
        se fuerza con monkeypatch para que el test no dependa del valor por
        defecto). Con A impactado, UNA llamada debe alarmar a B pero NO
        a C todavía — si C se alarmara en la misma llamada, la propagación
        estaría saltando dos vecinos de una vez, un artefacto de orden de
        iteración, no del modelo."""
        import src.config as config_mod

        radio_original = flocking.BOIDS_NEIGHBOR_RADIUS
        try:
            flocking.BOIDS_NEIGHBOR_RADIUS = 25.0  # A-B y B-C vecinos; A-C no
            a = Drone(0, x=0.0, y=0.0)
            b = Drone(1, x=20.0, y=0.0)
            c = Drone(2, x=40.0, y=0.0)
            a.registrar_impacto(0.0, 0.0, intensidad=1.0)

            flocking.propagate_alarm([a, b, c])
            assert b.amenaza_intensidad > 0.0
            assert c.amenaza_intensidad == 0.0, "la alarma saltó dos vecinos en una sola llamada"

            # Segunda llamada (próximo tick): ahora sí, desde B (ya alarmado).
            flocking.propagate_alarm([a, b, c])
            assert c.amenaza_intensidad > 0.0
        finally:
            flocking.BOIDS_NEIGHBOR_RADIUS = radio_original

    def test_vecino_no_impactado_tambien_se_dispersa_mas_que_sin_propagacion(
        self, monkeypatch
    ):
        """El test biomimeticamente relevante: un VECINO que nunca fue
        impactado directamente (solo contagiado por propagación) debe
        dispersarse más del punto de impacto que en un control idéntico con
        la propagación anulada — si no, la 'onda de agitación' sería
        decorativa (el vecino se movería igual de todos modos por
        separación/cohesión, sin que la memoria de amenaza propagada
        aportara nada)."""
        centro_impacto = (500.0, 500.0)
        dt = 0.3
        pasos = 15

        def _correr_con_un_impactado(ganancia: float) -> float:
            monkeypatch.setattr(flocking, "BOIDS_ALARM_PROPAGATION_GAIN", ganancia)
            drones = _formacion_compacta(centro_impacto)
            drones[0].registrar_impacto(*centro_impacto, intensidad=1.0)
            swarm = Swarm(centro_x=centro_impacto[0], centro_y=centro_impacto[1])
            swarm.drones = drones
            for _ in range(pasos):
                swarm.actualizar(dt)
                swarm.actualizar_amenazas(dt)
            vecino = drones[1]  # nunca impactado directamente, solo contagiado
            return distance(vecino.x, vecino.y, *centro_impacto)

        dist_con_propagacion = _correr_con_un_impactado(flocking.BOIDS_ALARM_PROPAGATION_GAIN)
        dist_sin_propagacion = _correr_con_un_impactado(0.0)

        assert dist_con_propagacion > dist_sin_propagacion


# ---------------------------------------------------------------------------
# Misión ofensiva del enjambre: el enjambre avanza hacia un objetivo y
# "llegar" es una brecha de la defensa, no una baja (ver src/config.py,
# bloque "Misión ofensiva del enjambre", y flocking._final_approach_vector).
# ---------------------------------------------------------------------------


class TestMisionOfensiva:
    def test_sin_objetivo_la_formacion_no_se_mueve(self):
        """Control de compatibilidad — objetivo_x/y=None (el default) debe
        dejar el comportamiento idéntico a antes de este ítem: el ancla de
        cohesión no se mueve sola."""
        swarm = Swarm(centro_x=500.0, centro_y=500.0)
        swarm.drones = [Drone(0, x=500.0, y=500.0, angulo=0.0, velocidad=15.0)]
        assert swarm.objetivo_x is None

        for _ in range(20):
            llegaron = swarm.actualizar(dt=0.1)
            assert llegaron == []

        assert swarm.formacion_x == pytest.approx(500.0)
        assert swarm.formacion_y == pytest.approx(500.0)

    def test_formacion_avanza_hacia_el_objetivo(self):
        swarm = Swarm(centro_x=500.0, centro_y=500.0)
        swarm.drones = [Drone(0, x=500.0, y=500.0, angulo=0.0, velocidad=15.0)]
        swarm.objetivo_x = 100.0
        swarm.objetivo_y = 500.0

        dist_inicial = distance(swarm.formacion_x, swarm.formacion_y, swarm.objetivo_x, swarm.objetivo_y)
        for _ in range(20):
            swarm.actualizar(dt=0.1)
        dist_final = distance(swarm.formacion_x, swarm.formacion_y, swarm.objetivo_x, swarm.objetivo_y)

        assert dist_final < dist_inicial

    def test_dron_que_llega_se_marca_y_deja_de_volar(self):
        """Un dron ya dentro de SWARM_OBJETIVO_RADIO_IMPACTO_M al primer
        tick se marca objetivo_alcanzado=True y, de ahí en más, no cambia
        de posición — misión cumplida, deja de estar bajo control de vuelo
        (mismo criterio que un neutralizado, ver Swarm.actualizar)."""
        swarm = Swarm(centro_x=100.0, centro_y=100.0)
        drone = Drone(0, x=110.0, y=100.0, angulo=180.0, velocidad=15.0)  # a 10m, dentro del radio (30m)
        swarm.drones = [drone]
        swarm.objetivo_x = 100.0
        swarm.objetivo_y = 100.0

        llegaron = swarm.actualizar(dt=0.1)
        assert llegaron == [drone]
        assert drone.objetivo_alcanzado is True

        x_al_llegar, y_al_llegar = drone.x, drone.y
        for _ in range(10):
            llegaron_de_nuevo = swarm.actualizar(dt=0.1)
            assert llegaron_de_nuevo == []  # ya está marcado, no "llega" otra vez
        assert (drone.x, drone.y) == (x_al_llegar, y_al_llegar)

    def test_reset_de_formacion_reinicia_el_avance(self):
        swarm = Swarm(centro_x=500.0, centro_y=500.0)
        swarm.drones = [Drone(0, x=500.0, y=500.0, angulo=0.0, velocidad=15.0)]
        swarm.objetivo_x = 0.0
        swarm.objetivo_y = 0.0
        for _ in range(20):
            swarm.actualizar(dt=0.1)
        assert (swarm.formacion_x, swarm.formacion_y) != (500.0, 500.0)

        swarm.inicializar_formacion("cuadrada", 5)
        assert swarm.formacion_x == pytest.approx(swarm.centro_x)
        assert swarm.formacion_y == pytest.approx(swarm.centro_y)
        # El objetivo en sí (a diferencia del avance) NO se reinicia — un
        # engagement nuevo sigue siendo contra la misma misión.
        assert swarm.objetivo_x == 0.0

    def test_simulationengine_sin_mision_activa_no_fija_objetivo(self):
        sim = SimulationEngine(swarm_size=3)
        assert sim.mision_activa is False
        assert sim.swarm.objetivo_x is None
        sim.shutdown()

    def test_simulationengine_con_mision_activa_apunta_al_origen_del_arma(self):
        sim = SimulationEngine(swarm_size=3, mision_activa=True)
        assert sim.swarm.objetivo_x == HPM_ORIGIN_X
        assert sim.swarm.objetivo_y == HPM_ORIGIN_Y
        sim.shutdown()

    def test_tick_loguea_una_brecha_cuando_un_dron_llega(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True)
        drone = sim.swarm.drones[0]
        drone.x, drone.y = HPM_ORIGIN_X + 5.0, HPM_ORIGIN_Y  # ya adentro del radio de impacto

        sim._tick(dt=0.1)

        eventos = [e for e in sim.logs if e["evento"] == "objetivo_alcanzado"]
        assert len(eventos) == 1
        assert eventos[0]["datos"]["drones"] == [drone.id]
        assert drone.objetivo_alcanzado is True
        sim.shutdown()

    def test_un_dron_converge_y_llega_al_objetivo_de_verdad(self):
        """El test central del ítem: no alcanza con que el ancla avance
        (ver el docstring de BOIDS_MISSION_WEIGHT en src/config.py — con
        un peso insuficiente el enjambre queda orbitando cerca del
        objetivo para siempre, verificado empíricamente). Acá se prueba
        el resultado real: un dron solo, con el motor real, corriendo
        `actualizar()` tick a tick, tiene que LLEGAR — no solo acercarse —
        dentro de un número acotado de ticks."""
        swarm = Swarm(centro_x=100.0, centro_y=40.0)
        swarm.drones = [Drone(0, x=100.0, y=40.0, angulo=90.0, velocidad=20.0)]
        swarm.objetivo_x = 40.0
        swarm.objetivo_y = 40.0

        for _ in range(100):  # 10s simulados — el caso calibrado converge en ~2.3s
            if swarm.actualizar(dt=0.1):
                break
        else:
            pytest.fail("el dron no llegó al objetivo en 10s simulados")

        assert swarm.contar_objetivo_alcanzado() == 1


class TestKamikaze:
    """El dron que llega al objetivo (misión ofensiva) inutiliza la
    plataforma de verdad en vez de solo registrarse como brecha
    estadística — kamikaze_activo, opt-in y separado de mision_activa/
    con_mision (ver el comentario del campo en SimulationEngine)."""

    def test_apagado_por_defecto_la_brecha_sigue_siendo_solo_estadistica(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True)
        assert sim.kamikaze_activo is False
        drone = sim.swarm.drones[0]
        drone.x, drone.y = HPM_ORIGIN_X, HPM_ORIGIN_Y

        sim._tick(dt=0.1)

        assert sim.hpm.destruido is False
        assert sim.missile_system.destruido is False
        assert sim.hpm.listo_para_disparar() is True
        sim.shutdown()

    def test_activado_el_primer_dron_que_llega_destruye_canon_y_lanzador(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, kamikaze_activo=True)
        drone = sim.swarm.drones[0]
        drone.x, drone.y = HPM_ORIGIN_X, HPM_ORIGIN_Y

        sim._tick(dt=0.1)

        assert sim.hpm.destruido is True
        assert sim.missile_system.destruido is True
        assert sim.hpm.listo_para_disparar() is False

        eventos = [e for e in sim.logs if e["evento"] == "plataforma_destruida"]
        assert len(eventos) == 1
        assert eventos[0]["datos"]["drone_id"] == drone.id
        sim.shutdown()

    def test_canon_destruido_rechaza_disparar_sin_excepcion(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, kamikaze_activo=True)
        sim.swarm.drones[0].x, sim.swarm.drones[0].y = HPM_ORIGIN_X, HPM_ORIGIN_Y
        sim._tick(dt=0.1)

        eventos = sim.hpm.disparar(sim.swarm.drones)

        assert eventos == []
        assert sim.hpm.ultimo_rechazo is not None
        assert "destruid" in sim.hpm.ultimo_rechazo
        sim.shutdown()

    def test_lanzador_destruido_rechaza_lanzar_sin_excepcion(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, kamikaze_activo=True)
        sim.swarm.drones[0].x, sim.swarm.drones[0].y = HPM_ORIGIN_X, HPM_ORIGIN_Y
        sim._tick(dt=0.1)

        resultado = sim.missile_system.lanzar(
            x=HPM_ORIGIN_X, y=HPM_ORIGIN_Y, angulo=0.0, drones=sim.swarm.drones
        )

        assert resultado["success"] is False
        assert "destruid" in resultado["message"]
        sim.shutdown()

    def test_reset_repara_la_plataforma(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, kamikaze_activo=True)
        sim.swarm.drones[0].x, sim.swarm.drones[0].y = HPM_ORIGIN_X, HPM_ORIGIN_Y
        sim._tick(dt=0.1)
        assert sim.hpm.destruido is True

        sim.reset()

        assert sim.hpm.destruido is False
        assert sim.missile_system.destruido is False
        assert sim.hpm.listo_para_disparar() is True
        sim.shutdown()

    def test_no_afecta_con_mision_en_monte_carlo_por_no_estar_activado_ahi(self):
        """kamikaze_activo nunca se pasa a ExperimentConfig/run_replica —
        con_mision=True sigue midiendo lo mismo que antes de este ítem."""
        from src.engine.experiments import ExperimentConfig, run_replica

        cfg = ExperimentConfig(
            formacion="cuadrada", cantidad=5, replicas=1, t_max_s=3.0, semilla=7, con_mision=True
        )
        resultado = run_replica(cfg, 0)
        assert "fraccion_alcanzo_objetivo" in resultado


class TestVehiculoMovil:
    """"Shoot and scoot": el vehículo (cañón + misil + jammer, mismo
    emplazamiento) puede reposicionarse, pero no dispara/lanza EN
    TRÁNSITO — un HPM real necesita estar quieto para apuntar. El
    objetivo del enjambre (misión ofensiva) sigue la posición ACTUAL del
    arma, no la de cuando arrancó la simulación."""

    def test_en_reposo_por_defecto_puede_disparar(self):
        sim = SimulationEngine(swarm_size=2)
        assert sim.hpm.en_movimiento is False
        assert sim.hpm.listo_para_disparar() is True
        sim.shutdown()

    def test_mover_plataforma_la_pone_en_movimiento_y_bloquea_el_disparo(self):
        sim = SimulationEngine(swarm_size=2)
        r = sim.mover_plataforma(300.0, 300.0)
        assert r["success"] is True
        assert sim.hpm.en_movimiento is True
        assert sim.hpm.listo_para_disparar() is False

        eventos = sim.hpm.disparar(sim.swarm.drones)
        assert eventos == []
        assert "movimiento" in sim.hpm.ultimo_rechazo
        sim.shutdown()

    def test_lanzar_misil_en_movimiento_se_rechaza_sin_excepcion(self):
        sim = SimulationEngine(swarm_size=2)
        sim.mover_plataforma(300.0, 300.0)

        resultado = sim.launch_missile(x=sim.hpm.origen_x, y=sim.hpm.origen_y)

        assert resultado["success"] is False
        assert "movimiento" in resultado["message"]
        sim.shutdown()

    def test_llega_al_destino_exacto_y_vuelve_a_poder_disparar(self):
        sim = SimulationEngine(swarm_size=2)
        sim.mover_plataforma(100.0, 0.0)  # 100m, a VEHICULO_VELOCIDAD_M_S=8.3 -> ~12s

        for _ in range(300):  # 30s simulados, de sobra
            sim._tick(0.1, mover_enjambre=False)
            if not sim.hpm.en_movimiento:
                break
        else:
            pytest.fail("el vehículo no llegó a destino en 30s simulados")

        assert sim.hpm.origen_x == pytest.approx(100.0)
        assert sim.hpm.origen_y == pytest.approx(0.0)
        assert sim.hpm.listo_para_disparar() is True
        sim.shutdown()

    def test_jammer_sigue_al_vehiculo(self):
        sim = SimulationEngine(swarm_size=2)
        sim.mover_plataforma(50.0, 0.0)
        for _ in range(100):
            sim._tick(0.1, mover_enjambre=False)
            if not sim.hpm.en_movimiento:
                break
        assert sim.jammer.origen_x == pytest.approx(sim.hpm.origen_x)
        assert sim.jammer.origen_y == pytest.approx(sim.hpm.origen_y)
        sim.shutdown()

    def test_objetivo_del_enjambre_sigue_al_vehiculo_moviendose(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True)
        assert sim.swarm.objetivo_x == HPM_ORIGIN_X

        sim.mover_plataforma(400.0, 0.0)
        for _ in range(50):
            sim._tick(0.1, mover_enjambre=False)
        # Todavía en tránsito (400m a 8.3 m/s tarda ~48s) — el objetivo ya
        # tiene que estar siguiendo la posición ACTUAL, no la de arranque.
        assert sim.hpm.en_movimiento is True
        assert sim.swarm.objetivo_x == pytest.approx(sim.hpm.origen_x)
        assert sim.swarm.objetivo_x != HPM_ORIGIN_X
        sim.shutdown()

    def test_reset_detiene_el_movimiento_y_vuelve_al_origen(self):
        sim = SimulationEngine(swarm_size=2)
        sim.mover_plataforma(300.0, 300.0)
        for _ in range(50):
            sim._tick(0.1, mover_enjambre=False)
        assert sim.hpm.en_movimiento is True

        sim.reset()

        assert sim.hpm.en_movimiento is False
        assert sim.hpm.origen_x == HPM_ORIGIN_X
        assert sim.hpm.origen_y == HPM_ORIGIN_Y
        sim.shutdown()

    def test_plataforma_destruida_no_puede_moverse(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, kamikaze_activo=True)
        sim.swarm.drones[0].x, sim.swarm.drones[0].y = HPM_ORIGIN_X, HPM_ORIGIN_Y
        sim._tick(0.1)
        assert sim.hpm.destruido is True

        r = sim.mover_plataforma(300.0, 300.0)

        assert r["success"] is False
        assert sim.hpm.en_movimiento is False
        sim.shutdown()

    def test_redirigir_a_mitad_de_camino_sobreescribe_el_destino(self):
        sim = SimulationEngine(swarm_size=2)
        sim.mover_plataforma(1000.0, 0.0)
        for _ in range(20):  # avanza un poco, no llega
            sim._tick(0.1, mover_enjambre=False)
        assert sim.hpm.en_movimiento is True
        x_parcial = sim.hpm.origen_x

        sim.mover_plataforma(0.0, 0.0)  # cambia de destino a mitad de camino

        assert sim.hpm.destino_x == 0.0
        # Sigue en movimiento, pero ahora hacia el nuevo destino — no
        # saltó ni se congeló.
        assert sim.hpm.en_movimiento is True
        assert sim.hpm.origen_x == pytest.approx(x_parcial)
        sim.shutdown()


class TestEstructura:
    """Estructura en aislado, sin motor de simulación — salud propia,
    a diferencia del vehículo (un solo impacto kamikaze lo destruye)."""

    def test_arranca_con_salud_maxima_y_sin_destruir(self):
        e = Estructura(id=0, x=100.0, y=200.0)
        assert e.salud == e.salud_maxima
        assert e.destruida is False

    def test_un_impacto_no_alcanza_para_destruirla(self):
        e = Estructura(id=0, x=0.0, y=0.0)
        destruida_ahora = e.recibir_impacto_kamikaze()
        assert destruida_ahora is False
        assert e.destruida is False
        assert 0 < e.salud < e.salud_maxima

    def test_suficientes_impactos_la_destruyen(self):
        e = Estructura(id=0, x=0.0, y=0.0)
        destruida_ahora = False
        for _ in range(10):
            destruida_ahora = e.recibir_impacto_kamikaze()
            if destruida_ahora:
                break
        assert destruida_ahora is True
        assert e.destruida is True
        assert e.salud == 0.0

    def test_impactos_sobre_estructura_ya_destruida_son_no_op(self):
        e = Estructura(id=0, x=0.0, y=0.0)
        for _ in range(10):
            e.recibir_impacto_kamikaze()
        assert e.destruida is True

        destruida_ahora = e.recibir_impacto_kamikaze()

        assert destruida_ahora is False  # no "vuelve" a destruirse
        assert e.salud == 0.0

    def test_reset_repara_del_todo(self):
        e = Estructura(id=0, x=0.0, y=0.0)
        for _ in range(10):
            e.recibir_impacto_kamikaze()
        assert e.destruida is True

        e.reset()

        assert e.destruida is False
        assert e.salud == e.salud_maxima


class TestEstructurasAtacables:
    """El enjambre elige el objetivo más cercano entre el vehículo y las
    estructuras (edificios) no destruidas — opt-in vía
    estructuras_activas, deliberadamente separado de mision_activa/
    con_mision (ver el comentario del campo en SimulationEngine)."""

    def test_apagado_por_defecto_no_hay_estructuras(self):
        sim = SimulationEngine(swarm_size=2, mision_activa=True)
        assert sim.estructuras_activas is False
        assert sim.estructuras == []
        sim.shutdown()

    def test_activado_crea_el_layout_por_defecto(self):
        sim = SimulationEngine(swarm_size=2, mision_activa=True, estructuras_activas=True)
        assert len(sim.estructuras) == 4
        assert all(not e.destruida for e in sim.estructuras)
        sim.shutdown()

    def test_sin_estructuras_activas_el_objetivo_siempre_es_el_vehiculo(self):
        """Mismo comportamiento que antes de este ítem, byte a byte."""
        sim = SimulationEngine(swarm_size=2, mision_activa=True)
        sim._elegir_objetivo_enjambre()
        assert sim._objetivo_actual == ("vehiculo", None)
        assert sim.swarm.objetivo_x == sim.hpm.origen_x
        assert sim.swarm.objetivo_y == sim.hpm.origen_y
        sim.shutdown()

    def test_elige_el_candidato_mas_cercano_a_la_formacion(self):
        sim = SimulationEngine(swarm_size=2, mision_activa=True, estructuras_activas=True)
        # El enjambre arranca cerca del centro del campo — más cerca del
        # pueblito (ver el layout en __post_init__) que del vehículo, que
        # está en la esquina (HPM_ORIGIN_X/Y).
        sim._elegir_objetivo_enjambre()
        assert sim._objetivo_actual[0] == "estructura"

        # Si en cambio el enjambre está pegado al vehículo, el vehículo
        # gana.
        sim.swarm.formacion_x, sim.swarm.formacion_y = HPM_ORIGIN_X, HPM_ORIGIN_Y
        sim._elegir_objetivo_enjambre()
        assert sim._objetivo_actual == ("vehiculo", None)
        sim.shutdown()

    def test_un_dron_que_llega_dana_la_estructura_no_la_destruye_solo(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, estructuras_activas=True)
        estructura = sim.estructuras[0]
        sim.swarm.drones[0].x, sim.swarm.drones[0].y = estructura.x, estructura.y
        sim.swarm.formacion_x, sim.swarm.formacion_y = estructura.x, estructura.y

        sim._tick(0.1, mover_enjambre=True)

        assert sim._objetivo_actual == ("estructura", estructura.id)
        assert 0 < estructura.salud < estructura.salud_maxima
        assert estructura.destruida is False
        eventos = [e for e in sim.logs if e["evento"] == "estructura_impactada"]
        assert len(eventos) == 1
        assert eventos[0]["datos"]["estructura_id"] == estructura.id
        sim.shutdown()

    def test_varios_drones_seguidos_la_destruyen_y_el_enjambre_redirige(self):
        sim = SimulationEngine(swarm_size=20, mision_activa=True, estructuras_activas=True)
        estructura = sim.estructuras[0]
        for d in sim.swarm.drones:
            d.x, d.y = estructura.x, estructura.y
        sim.swarm.formacion_x, sim.swarm.formacion_y = estructura.x, estructura.y

        sim._tick(0.1, mover_enjambre=True)

        assert estructura.destruida is True
        # El objetivo del PRÓXIMO tick ya no puede ser la estructura 0
        # (destruida) — redirige a otra cosa (otra estructura o el
        # vehículo), no se congela apuntando a algo que ya cayó.
        sim._elegir_objetivo_enjambre()
        assert sim._objetivo_actual != ("estructura", estructura.id)
        sim.shutdown()

    def test_kamikaze_en_vehiculo_no_toca_las_estructuras(self):
        sim = SimulationEngine(
            swarm_size=1, mision_activa=True, kamikaze_activo=True, estructuras_activas=True
        )
        sim.swarm.drones[0].x, sim.swarm.drones[0].y = HPM_ORIGIN_X, HPM_ORIGIN_Y
        sim.swarm.formacion_x, sim.swarm.formacion_y = HPM_ORIGIN_X, HPM_ORIGIN_Y

        sim._tick(0.1, mover_enjambre=True)

        assert sim.hpm.destruido is True
        assert all(e.salud == e.salud_maxima for e in sim.estructuras)
        sim.shutdown()

    def test_todo_destruido_el_enjambre_se_queda_sin_objetivo(self):
        sim = SimulationEngine(
            swarm_size=1, mision_activa=True, kamikaze_activo=True, estructuras_activas=True
        )
        sim.hpm.destruido = True
        for e in sim.estructuras:
            e.destruida = True

        sim._elegir_objetivo_enjambre()

        assert sim.swarm.objetivo_x is None
        assert sim.swarm.objetivo_y is None
        sim.shutdown()

    def test_reset_repara_todas_las_estructuras_y_vuelve_al_vehiculo(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, estructuras_activas=True)
        for e in sim.estructuras:
            e.recibir_impacto_kamikaze()
        sim._objetivo_actual = ("estructura", sim.estructuras[0].id)

        sim.reset()

        assert all(not e.destruida and e.salud == e.salud_maxima for e in sim.estructuras)
        assert sim._objetivo_actual == ("vehiculo", None)
        sim.shutdown()

    def test_snapshot_incluye_estructuras_y_tipo_de_objetivo(self):
        sim = SimulationEngine(swarm_size=2, mision_activa=True, estructuras_activas=True)
        sim._elegir_objetivo_enjambre()

        snap = sim._build_snapshot()

        assert len(snap["estructuras"]) == 4
        assert snap["mision"]["objetivo_tipo"] in ("vehiculo", "estructura")
        sim.shutdown()


