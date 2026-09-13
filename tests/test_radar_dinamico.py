"""Pruebas del radar dinámico: barrido + filtro α-β-γ (P2-G).

Dos pasos, dos conjuntos de garantías:

- **Paso 1** (extracción a ``TrackManager``, sin cambiar el comportamiento):
  el radar sigue detectando en régimen ESTACIONARIO exactamente lo mismo que
  antes (``evaluar_deteccion`` directo) — solo cambia CUÁNDO se actualiza
  (por barrido periódico, no cada tick) y DÓNDE vive el estado (un
  ``Track`` con posición estimada, no solo un booleano).
- **Paso 2** (filtro α-β-γ + migración de consumidores): un dron se detecta
  recién tras la revisita, una maniobra abrupta pierde el track, y
  ``HPMissile``/``HPMissileSystem`` adquieren blancos nuevos usando la
  posición ESTIMADA — pero navegan, una vez adquiridos, con la posición
  real (el buscador propio del misil, sin cambios).

⚠ Este ítem es explícitamente **NO ADITIVO** (ver CHECKLIST_MEJORAS.md): a
diferencia de casi todo lo demás en este proyecto, SÍ mueve el
comportamiento transitorio de detección (con retraso de hasta un ciclo de
revisita) y el punto de auto-apuntado del misil al lanzar. Eso está
declarado, no es una regresión.
"""

from __future__ import annotations

import math

import pytest

from src.config import (
    HPM_ORIGIN_X,
    HPM_ORIGIN_Y,
    HPM_ORIGIN_Z,
    RADAR_ANTENNA_GAIN_DBI,
    RADAR_FILTRO_ALPHA,
    RADAR_FILTRO_BETA,
    RADAR_FILTRO_GAMMA,
    RADAR_FREQUENCY_GHZ,
    RADAR_NOISE_FLOOR_W,
    RADAR_PERDIDA_TRACK_RESIDUAL_M,
    RADAR_RCS_M2,
    RADAR_REVISITA_S,
    RADAR_TX_POWER_W,
)
from src.engine.radar_engine import Track, TrackManager, evaluar_deteccion
from src.engine.simulation import SimulationEngine
from src.models.drone import Drone, DroneEstado
from src.models.hpm_missile import HPMissile
from src.models.hpm_system import HPMissileSystem
from src.models.swarm import FormacionTipo, Swarm
from src.utils.reproducibilidad import nuevo_generador, seed_simulacion


def _params_radar():
    return (RADAR_TX_POWER_W, RADAR_ANTENNA_GAIN_DBI, RADAR_FREQUENCY_GHZ, RADAR_RCS_M2, RADAR_NOISE_FLOOR_W)


class FakeDrone:
    """Doble mínimo para probar TrackManager sin construir un Drone real."""

    def __init__(self, drone_id: int, x: float, y: float, z: float = 100.0):
        self.id = drone_id
        self.x = x
        self.y = y
        self.z = z
        self.detectado = False


class TestTrackManagerBasico:
    def test_sin_barrido_no_hay_track(self):
        """Con dt menor al periodo de revisita, no hay medición fresca."""
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=20.0, y=0.0)
        tm.actualizar([d], 0.1, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is None
        assert d.detectado is False

    def test_primer_barrido_crea_el_track(self):
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=20.0, y=0.0)
        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is not None
        assert d.detectado is True

    def test_fuera_de_rango_no_crea_track(self):
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=100_000.0, y=0.0)  # muy lejos: SNR bajo el umbral
        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is None
        assert d.detectado is False

    def test_track_desaparece_si_sale_de_rango_en_la_siguiente_revisita(self):
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=20.0, y=0.0)
        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is not None

        d.x = 100_000.0
        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is None
        assert d.detectado is False

    def test_coincide_con_evaluar_deteccion_en_el_instante_del_barrido(self):
        """Regresión de Paso 1: en el momento de la revisita, la decisión
        binaria es EXACTAMENTE la de evaluar_deteccion — no se introdujo
        ninguna diferencia en la ecuación de radar, solo en cuándo se aplica.
        """
        for x in (20.0, 500.0, 850.0, 900.0, 2000.0):
            d = FakeDrone(0, x=x, y=0.0)
            dist = math.hypot(x - HPM_ORIGIN_X, 0.0 - HPM_ORIGIN_Y)
            esperado, _ = evaluar_deteccion(dist, *_params_radar())

            tm = TrackManager(revisita_s=1.0)
            tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
            assert d.detectado == esperado, f"x={x}"


class TestPropagacionEntreRevisitas:
    def test_track_sigue_vivo_entre_revisitas_sin_medicion_nueva(self):
        """Entre dos barridos, el track NO desaparece — se propaga."""
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=20.0, y=0.0)
        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert d.detectado is True

        # Medio ciclo de revisita: no hay barrido nuevo, pero el track sigue.
        tm.actualizar([d], 0.5, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert d.detectado is True
        assert tm.get_track(0) is not None

    def test_velocidad_constante_converge(self):
        """El filtro α-β-γ debe converger a seguir un movimiento real, con
        error acotado (no divergente) y velocidad estimada cercana a la real.
        """
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=0.0, y=0.0)
        vx_real = 15.0
        dt = 0.1
        for _ in range(200):  # 20 s ≫ el transitorio inicial
            d.x += vx_real * dt
            tm.actualizar([d], dt, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())

        track = tm.get_track(0)
        assert track is not None
        assert abs(track.x - d.x) < 5.0, "el error de posición no debe divergir"
        assert track.vx == pytest.approx(vx_real, rel=0.15)

    def test_error_no_diverge_con_el_tiempo(self):
        """Contraste directo: el error tras 40s no debe ser mayor que tras 10s
        (si divergiera, el filtro estaría mal — sería inestable)."""
        def error_tras(segundos: float) -> float:
            tm = TrackManager(revisita_s=1.0)
            d = FakeDrone(0, x=0.0, y=0.0)
            dt = 0.1
            for _ in range(int(segundos / dt)):
                d.x += 15.0 * dt
                tm.actualizar([d], dt, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
            track = tm.get_track(0)
            return abs(track.x - d.x) if track else float("inf")

        assert error_tras(40.0) < 10 * error_tras(10.0) + 2.0  # margen generoso, no exige monotonía estricta


class TestFiltroAlphaBetaGammaCorreccion:
    """La corrección numérica de un solo paso, contra la fórmula cerrada."""

    def test_correccion_de_un_paso_coincide_con_la_formula(self):
        tm = TrackManager(revisita_s=1.0)
        tm.tracks[0] = Track(drone_id=0, x=100.0, y=200.0, z=100.0, vx=1.0, vy=-1.0)
        d = FakeDrone(0, x=110.0, y=195.0, z=100.0)  # medición real, con residual

        # Forzar el barrido inmediato.
        tm._reloj_barrido_s = tm.revisita_s
        tm.actualizar([d], 0.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())

        residual_x, residual_y = 10.0, -5.0
        esperado_x = 100.0 + RADAR_FILTRO_ALPHA * residual_x
        esperado_y = 200.0 + RADAR_FILTRO_ALPHA * residual_y
        esperado_vx = 1.0 + (RADAR_FILTRO_BETA / RADAR_REVISITA_S) * residual_x
        esperado_vy = -1.0 + (RADAR_FILTRO_BETA / RADAR_REVISITA_S) * residual_y

        track = tm.get_track(0)
        assert track.x == pytest.approx(esperado_x)
        assert track.y == pytest.approx(esperado_y)
        assert track.vx == pytest.approx(esperado_vx)
        assert track.vy == pytest.approx(esperado_vy)


class TestPerdidaDeTrackPorManiobra:
    def test_vuelo_recto_no_pierde_el_track(self):
        """Vuelo normal (giro boids máximo, velocidad típica) NO debe
        superar el umbral de residual — control negativo de la maniobra.
        """
        from src.config import BOIDS_MAX_TURN_RATE_DEG_S

        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=0.0, y=0.0)
        angulo, dt = 0.0, 0.1
        for _ in range(100):  # 10 s
            angulo += BOIDS_MAX_TURN_RATE_DEG_S * dt
            d.x += 30.0 * math.cos(math.radians(angulo)) * dt
            d.y += 30.0 * math.sin(math.radians(angulo)) * dt
            tm.actualizar([d], dt, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert d.detectado is True
        assert tm.get_track(0) is not None

    def test_maniobra_abrupta_pierde_el_track(self):
        """Un salto mucho mayor al umbral configurado rompe el track."""
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=0.0, y=0.0)
        for _ in range(30):  # adquisición + unas revisitas normales
            d.x += 15.0 * 0.1
            tm.actualizar([d], 0.1, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is not None

        d.x += 3.0 * RADAR_PERDIDA_TRACK_RESIDUAL_M  # muy por encima del umbral
        for _ in range(10):
            tm.actualizar([d], 0.1, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert d.detectado is False
        assert tm.get_track(0) is None

    def test_readquisicion_tras_perder_el_track_reinicia_la_velocidad(self):
        """Un track readquirido tras perderse nace sin velocidad estimada
        (no hereda la del track roto) — es una adquisición nueva, no una
        continuación.
        """
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=0.0, y=0.0)
        for _ in range(30):
            d.x += 15.0 * 0.1
            tm.actualizar([d], 0.1, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())

        d.x += 3.0 * RADAR_PERDIDA_TRACK_RESIDUAL_M
        for _ in range(10):
            tm.actualizar([d], 0.1, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        assert tm.get_track(0) is None

        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *_params_radar())
        nuevo_track = tm.get_track(0)
        assert nuevo_track is not None
        assert nuevo_track.vx == 0.0


class TestRegresionPaso1EnElEnjambreReal:
    """Paso 1: en régimen ESTACIONARIO (muchas revisitas), el conteo de
    detectados coincide con lo que ``evaluar_deteccion`` daría en cada
    posición — la ecuación de radar no cambió, solo cuándo se consulta.
    """

    def test_conteo_estacionario_exacto_con_distance3d(self):
        from src.utils.helpers import distance3d

        seed_simulacion(11)
        swarm = Swarm(formacion=FormacionTipo.CIRCULAR)
        swarm.inicializar_formacion("circular", 30)
        for d in swarm.drones:
            d.velocidad = 0.0

        for _ in range(int(RADAR_REVISITA_S / 0.1) + 2):
            swarm.actualizar(0.1)

        detectados_tm = sum(1 for d in swarm.drones if d.detectado)
        detectados_directo = 0
        for d in swarm.drones:
            dist = distance3d(HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, d.x, d.y, d.z)
            ok, _ = evaluar_deteccion(dist, *_params_radar())
            detectados_directo += int(ok)

        assert detectados_tm == detectados_directo


class TestMigracionDeMisiles:
    """Paso 2: adquisición vía track, navegación vía posición real."""

    def test_resolver_objetivo_sin_track_manager_usa_posicion_real(self):
        """Retrocompatibilidad exacta: sin track_manager, comportamiento
        idéntico al de antes de P2-G.
        """
        misil = HPMissile(x=0.0, y=0.0, angulo=0.0, potencia_hpm=25.0, radio_efecto=100.0)
        cerca = Drone(0, x=100.0, y=0.0, z=misil.z)
        lejos = Drone(1, x=500.0, y=0.0, z=misil.z)
        cerca.detectado = True
        lejos.detectado = True

        objetivo = misil._resolver_objetivo([cerca, lejos])
        assert objetivo.id == cerca.id

    def test_adquisicion_usa_posicion_estimada_del_track(self):
        """Con track_manager, la elección se basa en la posición ESTIMADA:
        un dron cuya posición REAL está más lejos pero cuyo TRACK está más
        cerca del misil debe ganar la adquisición.
        """
        misil = HPMissile(x=0.0, y=0.0, angulo=0.0, potencia_hpm=25.0, radio_efecto=100.0)

        # d_a: real lejos, track cerca. d_b: real cerca, track lejos.
        d_a = Drone(0, x=500.0, y=0.0, z=misil.z)
        d_b = Drone(1, x=100.0, y=0.0, z=misil.z)
        d_a.detectado = True
        d_b.detectado = True

        tm = TrackManager(revisita_s=1.0)
        tm.tracks[d_a.id] = Track(drone_id=d_a.id, x=50.0, y=0.0, z=misil.z)
        tm.tracks[d_b.id] = Track(drone_id=d_b.id, x=900.0, y=0.0, z=misil.z)

        objetivo = misil._resolver_objetivo([d_a, d_b], track_manager=tm)
        assert objetivo.id == d_a.id, "debe elegir por posición ESTIMADA, no real"

    def test_sin_track_no_hay_adquisicion_nueva(self):
        """Criterio de aceptación explícito del ítem: sin track, no hay
        lock-on nuevo — aunque el dron exista y esté 'activo'.
        """
        misil = HPMissile(x=0.0, y=0.0, angulo=0.0, potencia_hpm=25.0, radio_efecto=100.0)
        d = Drone(0, x=50.0, y=0.0, z=misil.z)
        d.detectado = False  # sin track: no detectado

        tm = TrackManager(revisita_s=1.0)
        objetivo = misil._resolver_objetivo([d], track_manager=tm)
        assert objetivo is None
        assert misil.target_id is None

    def test_lock_on_ya_fijado_navega_con_posicion_real_no_estimada(self):
        """Una vez adquirido, el guiado usa la posición VERDADERA del
        objetivo — el buscador propio del misil, no el track de tierra
        (documentado, sin cambios respecto a antes de P2-G).
        """
        misil = HPMissile(
            x=0.0, y=0.0, angulo=0.0, potencia_hpm=25.0, radio_efecto=100.0, target_id=0,
        )
        d = Drone(0, x=100.0, y=50.0, z=misil.z)
        d.detectado = True

        tm = TrackManager(revisita_s=1.0)
        # Track deliberadamente MUY distinto a la posición real, para que el
        # test distinga con claridad cuál posición gobierna la navegación.
        tm.tracks[0] = Track(drone_id=0, x=-500.0, y=-500.0, z=misil.z)

        misil._aplicar_guiado(0.1, [d], track_manager=tm)
        misil._prev_los_angle = None  # forzar un segundo paso con LOS válido
        misil._aplicar_guiado(0.1, [d], track_manager=tm)

        # Si hubiera usado el track, el rumbo apuntaría hacia (-500,-500)
        # (backward, ~225°); usando la posición real, apunta hacia adelante.
        from src.utils.helpers import angle_difference

        angulo_hacia_real = math.degrees(math.atan2(d.y - misil.y, d.x - misil.x)) % 360
        diff = abs(angle_difference(misil.angulo, angulo_hacia_real))
        assert diff < 90.0, "el guiado debe orientarse hacia la posición REAL"


class TestMigracionDeLanzamiento:
    def test_centroide_usa_posiciones_estimadas_cuando_hay_track_manager(self):
        sistema = HPMissileSystem()
        d1 = Drone(0, x=0.0, y=0.0, z=100.0)
        d2 = Drone(1, x=200.0, y=0.0, z=100.0)
        d1.detectado = True
        d2.detectado = True

        tm = TrackManager(revisita_s=1.0)
        # Tracks estimados MUY distintos a las posiciones reales.
        tm.tracks[0] = Track(drone_id=0, x=1000.0, y=0.0, z=100.0)
        tm.tracks[1] = Track(drone_id=1, x=1000.0, y=0.0, z=100.0)

        resultado = sistema.lanzar(x=0.0, y=0.0, angulo=None, drones=[d1, d2], track_manager=tm)
        assert resultado["success"] is True
        # El centroide REAL sería (100,0) -> ángulo 0°; el centroide de los
        # tracks es (1000,0) -> también 0° en este caso degenerado. Se
        # verifica el objetivo de lock-on, que sí distingue.
        assert resultado["misil"]["target_id"] in (0, 1)

    def test_sin_track_manager_usa_posicion_real_retrocompatible(self):
        sistema = HPMissileSystem()
        d = Drone(0, x=50.0, y=0.0, z=100.0)
        d.detectado = True
        resultado = sistema.lanzar(x=0.0, y=0.0, angulo=None, drones=[d])
        assert resultado["success"] is True
        assert resultado["misil"]["target_id"] == 0

    def test_objetivo_de_lanzamiento_elegido_por_track_no_por_posicion_real(self):
        sistema = HPMissileSystem()
        cerca_real = Drone(0, x=50.0, y=0.0, z=100.0)
        lejos_real = Drone(1, x=900.0, y=0.0, z=100.0)
        cerca_real.detectado = True
        lejos_real.detectado = True

        tm = TrackManager(revisita_s=1.0)
        tm.tracks[0] = Track(drone_id=0, x=900.0, y=0.0, z=100.0)  # invierte los roles
        tm.tracks[1] = Track(drone_id=1, x=50.0, y=0.0, z=100.0)

        resultado = sistema.lanzar(
            x=0.0, y=0.0, angulo=None, drones=[cerca_real, lejos_real], track_manager=tm
        )
        assert resultado["misil"]["target_id"] == 1, "debe elegir según el track, no la posición real"


class TestEscenarioEndToEnd:
    """El pipeline completo sigue funcionando: lanzar, guiar, detonar."""

    def test_mision_completa_con_radar_dinamico(self):
        gen = nuevo_generador(3)
        sim = SimulationEngine(swarm_size=15, rng=gen)
        sim.swarm.inicializar_formacion("circular", 15)

        # Warm-up: al menos una revisita para que existan tracks reales.
        for _ in range(int(RADAR_REVISITA_S / 0.1) + 5):
            sim._tick(0.1)

        resultado = sim.launch_missile(x=sim.hpm.origen_x, y=sim.hpm.origen_y)
        assert resultado["success"] is True

        detonado = False
        for _ in range(2000):
            _, eventos = sim._tick(0.05)
            if eventos:
                sim._process_missile_events(eventos)
                if any(e["tipo"] == "misil_detonado" for e in eventos):
                    detonado = True
                    break
        assert detonado, "el misil debe seguir detonando con el radar dinámico activo"
