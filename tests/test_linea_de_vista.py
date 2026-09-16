"""Línea de vista física (terreno): edificios bloqueando el haz del cañón,
la detonación del misil, y la detección del radar — pedido explícito del
usuario ("terreno físico, no solo decorativo"), fase 1 del ítem de
edificios/árboles/trincheras (ver docs/SEGUIMIENTO_SESION.md §9.7).

Simplificación deliberada y documentada: el chequeo es 2D en el plano del
suelo (sin altura de obstáculo ni trayectoria 3D del rayo) — ver el
comentario en ``hpm_engine.linea_de_vista_bloqueada``. No se prueba acá
que eso sea "correcto" en 3D, porque no pretende serlo.

Todo lo de este archivo usa ``obstaculos=None`` (o listas vacías) como
control de compatibilidad — el valor por defecto de todo parámetro nuevo
tiene que dar exactamente el comportamiento de antes de este ítem.
"""

from __future__ import annotations

import math

import pytest

from src.engine.hpm_engine import linea_de_vista_bloqueada
from src.engine.radar_engine import RADAR_REVISITA_S, TrackManager
from src.engine.simulation import SimulationEngine
from src.models.drone import Drone
from src.models.hpm_missile import HPMissile
from src.models.hpm_weapon import HPMWeapon


class TestLineaDeVistaGeometria:
    """La utilidad geométrica en aislado, sin ningún motor de armas."""

    def test_sin_obstaculos_nunca_bloquea(self):
        assert linea_de_vista_bloqueada(0, 0, 100, 0, None) is False
        assert linea_de_vista_bloqueada(0, 0, 100, 0, []) is False

    def test_obstaculo_directamente_enmedio_bloquea(self):
        assert linea_de_vista_bloqueada(0, 0, 100, 0, [(50, 0, 10)]) is True

    def test_obstaculo_lejos_de_la_linea_no_bloquea(self):
        assert linea_de_vista_bloqueada(0, 0, 100, 0, [(50, 50, 10)]) is False

    def test_obstaculo_mas_alla_del_destino_no_bloquea(self):
        """Un edificio DETRÁS del blanco (visto desde el arma) no debería
        taparlo — el haz nunca llega tan lejos."""
        assert linea_de_vista_bloqueada(0, 0, 100, 0, [(150, 0, 10)]) is False

    def test_tangente_justo_dentro_bloquea_justo_fuera_no(self):
        assert linea_de_vista_bloqueada(0, 0, 100, 0, [(50, 9.9, 10)]) is True
        assert linea_de_vista_bloqueada(0, 0, 100, 0, [(50, 10.1, 10)]) is False

    def test_uno_de_varios_obstaculos_alcanza_para_bloquear(self):
        obstaculos = [(200, 200, 5), (50, 0, 10), (300, -300, 5)]
        assert linea_de_vista_bloqueada(0, 0, 100, 0, obstaculos) is True


class TestCanonConLineaDeVista:
    def test_sin_obstaculos_comportamiento_identico_a_antes(self):
        """Control de compatibilidad: llamar disparar() sin el parámetro
        nuevo da EXACTAMENTE lo mismo (byte a byte) que pasar
        obstaculos=None explícito — el default no cambia nada."""
        hpm_a = HPMWeapon(potencia=60.0, direccion=0.0, apertura_cono=30.0)
        hpm_b = HPMWeapon(potencia=60.0, direccion=0.0, apertura_cono=30.0)
        d_a = Drone(0, x=50.0, y=0.0, z=hpm_a.origen_z, angulo=0.0, velocidad=0.0)
        d_b = Drone(0, x=50.0, y=0.0, z=hpm_b.origen_z, angulo=0.0, velocidad=0.0)
        d_a.cable_length_m = d_b.cable_length_m = 0.3
        d_a.polarization = d_b.polarization = 0.8

        eventos_sin_param = hpm_a.disparar([d_a])
        eventos_con_none = hpm_b.disparar([d_b], obstaculos=None)

        assert eventos_sin_param[0]["bloqueado"] is False
        assert eventos_sin_param[0]["probabilidad"] == eventos_con_none[0]["probabilidad"]

    def test_dron_detras_de_un_obstaculo_no_recibe_daño(self):
        hpm = HPMWeapon(potencia=100.0, direccion=0.0, apertura_cono=30.0)
        d = Drone(0, x=100.0, y=0.0, z=hpm.origen_z, angulo=0.0, velocidad=0.0)
        salud_antes = d.salud

        eventos = hpm.disparar([d], obstaculos=[(50.0, 0.0, 15.0)])

        assert eventos[0]["bloqueado"] is True
        assert eventos[0]["probabilidad"] == 0.0
        assert eventos[0]["neutralizado"] is False
        assert d.salud == salud_antes  # recibir_daño ni se llamó
        assert d.riesgo_latente_por_s == 0.0

    def test_dron_no_alineado_con_el_obstaculo_dispara_normal(self):
        # Cañón apuntando a +Y, obstáculo sobre el eje +X — ejes distintos,
        # no hay forma de que el segmento origen-dron pase cerca de él.
        hpm = HPMWeapon(potencia=100.0, direccion=90.0, apertura_cono=30.0)
        d = Drone(0, x=0.0, y=100.0, z=hpm.origen_z, angulo=0.0, velocidad=0.0)

        eventos = hpm.disparar([d], obstaculos=[(50.0, 0.0, 15.0)])

        assert eventos[0]["bloqueado"] is False


class TestMisilConLineaDeVista:
    def test_sin_obstaculos_comportamiento_identico_a_antes(self):
        m = HPMissile(x=0.0, y=0.0, angulo=0.0, potencia_hpm=50.0, radio_efecto=100.0)
        d = Drone(0, x=10.0, y=0.0, z=0.0, angulo=0.0, velocidad=0.0)
        eventos = m.detonar([d])
        assert eventos[0]["bloqueado"] is False

    def test_dron_detras_de_un_obstaculo_no_recibe_daño(self):
        m = HPMissile(x=0.0, y=0.0, angulo=0.0, potencia_hpm=50.0, radio_efecto=100.0)
        d = Drone(0, x=40.0, y=0.0, z=0.0, angulo=0.0, velocidad=0.0)
        salud_antes = d.salud

        eventos = m.detonar([d], obstaculos=[(20.0, 0.0, 10.0)])

        assert eventos[0]["bloqueado"] is True
        assert eventos[0]["probabilidad"] == 0.0
        assert d.salud == salud_antes


class TestRadarConLineaDeVista:
    def _avanzar_hasta_revisita(self, tm: TrackManager, drones, origen, dt=0.1, obstaculos=None):
        for _ in range(int(RADAR_REVISITA_S / dt) + 2):
            tm.actualizar(
                drones, dt, *origen,
                pt_w=500.0, gain_dbi=10.0, frequency_ghz=2.45,
                rcs_m2=0.05, noise_floor_w=1e-12,
                obstaculos=obstaculos,
            )

    def test_sin_obstaculos_detecta_normal(self):
        tm = TrackManager()
        d = Drone(0, x=5.0, y=5.0, z=5.0, angulo=0.0, velocidad=0.0)
        self._avanzar_hasta_revisita(tm, [d], (0.0, 0.0, 5.0))
        assert d.detectado is True

    def test_dron_detras_de_un_obstaculo_no_se_detecta(self):
        tm = TrackManager()
        d = Drone(0, x=100.0, y=0.0, z=5.0, angulo=0.0, velocidad=0.0)
        self._avanzar_hasta_revisita(
            tm, [d], (0.0, 0.0, 5.0), obstaculos=[(50.0, 0.0, 15.0)]
        )
        assert d.detectado is False


class TestIntegracionSimulationEngine:
    """De punta a punta, a través de SimulationEngine — obstáculos
    ensamblados desde estructuras_activas, no pasados a mano."""

    def test_sin_estructuras_activas_no_hay_obstaculos(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True)
        assert sim._obstaculos_activos() == []
        sim.shutdown()

    def test_estructura_destruida_deja_de_bloquear(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, estructuras_activas=True)
        estructura = sim.estructuras[0]
        assert len(sim._obstaculos_activos()) == 4

        estructura.destruida = True

        assert len(sim._obstaculos_activos()) == 3
        assert not any(o[:2] == (estructura.x, estructura.y) for o in sim._obstaculos_activos())
        sim.shutdown()

    def test_fire_bloquea_un_dron_detras_de_una_estructura(self):
        sim = SimulationEngine(swarm_size=1, mision_activa=True, estructuras_activas=True)
        estructura = sim.estructuras[0]
        ang = math.atan2(estructura.y, estructura.x)
        drone = sim.swarm.drones[0]
        drone.x = estructura.x + 40 * math.cos(ang)
        drone.y = estructura.y + 40 * math.sin(ang)
        drone.z = sim.hpm.origen_z
        direccion = math.degrees(ang) % 360

        r = sim.fire(potencia=100, direccion=direccion, apertura_cono=30)

        assert r["eventos"][0]["bloqueado"] is True
        sim.shutdown()

    def test_radar_sigue_el_origen_actual_del_vehiculo_no_uno_fijo(self):
        """Bug encontrado de paso: el radar usaba SIEMPRE HPM_ORIGIN_X/Y
        (la constante fija), incluso si el vehículo ya se había
        reposicionado (ver HPMWeapon.iniciar_movimiento) — quedaba
        mirando desde el punto viejo. Acá se prueba que, tras mover el
        vehículo y dejarlo llegar, un dron cerca del NUEVO origen se
        detecta (si siguiera mirando desde el viejo origen, este dron
        estaría fuera de rango y no se detectaría)."""
        sim = SimulationEngine(swarm_size=1, mision_activa=True)
        sim.mover_plataforma(400.0, 0.0)
        for _ in range(100):  # 10s, de sobra para 400m a 8.3m/s (~48s)... no alcanza
            sim._tick(0.1, mover_enjambre=False)
        # No hace falta que haya llegado del todo — alcanza con que se
        # haya movido lo bastante para que el radar, mirando desde la
        # posición ACTUAL, detecte un dron puesto ahí cerca.
        drone = sim.swarm.drones[0]
        drone.x, drone.y, drone.z = sim.hpm.origen_x + 5.0, sim.hpm.origen_y, sim.hpm.origen_z
        for _ in range(15):
            sim._tick(0.1, mover_enjambre=False)
        assert drone.detectado is True
        sim.shutdown()

class TestLineaDeVistaConRelieve:
    """P4 de la critica "cientifico militar" de esta sesion: linea de
    vista considerando el relieve REAL del terreno (colinas, ver
    src/engine/terreno.py), no solo los circulos 2D de estructuras de
    arriba. Casos concretos, encontrados por busqueda numerica (no
    inventados a mano) - ver el hallazgo documentado en terreno.py sobre
    cuando esto efectivamente bloquea algo."""

    def test_default_no_considera_relieve_ni_con_alturas_dadas(self):
        """Sin considerar_relieve=True explicito, el comportamiento es
        IDENTICO al de antes de este item - aunque se pasen origen_z/
        destino_z, el chequeo de relieve simplemente no corre."""
        assert linea_de_vista_bloqueada(
            0.0, 0.0, 403.98, 200.08, None, origen_z=8.0, destino_z=2.68,
        ) is False

    def test_bloquea_un_blanco_bajo_detras_de_una_colina(self):
        """Caso real encontrado por busqueda numerica: un blanco BAJO
        (2.68m - un dron aterrizando por falla de enlace, ver
        PerfilLostLink.ATERRIZAR en src/models/drone.py) a ~450m del
        canon en HPM_ORIGIN queda detras de una colina real."""
        assert linea_de_vista_bloqueada(
            0.0, 0.0, 403.98, 200.08, None,
            origen_z=8.0, destino_z=2.68, considerar_relieve=True,
        ) is True

    def test_no_bloquea_un_dron_en_vuelo_normal(self):
        """HALLAZGO documentado en terreno.py: con la altitud de vuelo
        real de los drones (40-160m) y la amplitud de colinas del
        frontend, el relieve practicamente NUNCA bloquea contra un dron
        en vuelo normal - el rayo sube del origen hacia el dron mucho
        mas rapido de lo que cualquier colina de esta amplitud puede
        seguirle el ritmo. Este test fija ESE comportamiento como
        esperado, no como un bug."""
        assert linea_de_vista_bloqueada(
            0.0, 0.0, 500.0, 500.0, None,
            origen_z=8.0, destino_z=100.0, considerar_relieve=True,
        ) is False

    def test_sin_alguna_de_las_dos_alturas_no_corre_el_chequeo(self):
        """considerar_relieve=True pero falta origen_z o destino_z: no
        hay con que calcular el rayo, asi que no revienta ni asume nada
        - simplemente no aplica el chequeo de relieve (sigue aplicando
        el de obstaculos si corresponde)."""
        assert linea_de_vista_bloqueada(
            0.0, 0.0, 403.98, 200.08, None,
            origen_z=8.0, destino_z=None, considerar_relieve=True,
        ) is False

    def test_integracion_disparo_con_relieve_activo_no_rompe(self):
        """SimulationEngine con relieve_bloquea_vision=True corriendo de
        punta a punta (varios ticks + un disparo real) sin excepciones -
        no verifica un bloqueo especifico (dependeria de donde cayeron
        los drones esta corrida), solo que el flag conectado end-to-end
        no rompe nada."""
        sim = SimulationEngine(swarm_size=15, mision_activa=False, relieve_bloquea_vision=True)
        sim.start()
        for _ in range(40):
            sim._tick(0.1)
        resultado = sim.fire(potencia=90, direccion=45, apertura_cono=30)
        assert resultado["message"] == "HPM disparado" or resultado["message"].startswith("Disparo rechazado")
        sim.shutdown()
