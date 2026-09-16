"""Sensor RF pasivo (P5 de la crítica "científico militar" de esta sesión
— ver src/engine/rf_sensor.py para el porqué del enlace unidireccional y
el hallazgo de alcance).

Dos capas de garantías, igual que test_radar_dinamico.py:

- ``evaluar_deteccion_rf`` por sí sola: monotonía con la distancia y el
  hallazgo numérico congelado como regresión (a la diagonal del mapa, el
  radar ya no detecta pero el sensor RF sí).
- ``TrackManager.actualizar(..., considerar_sensor_rf=...)``: el OR con
  el radar, el opt-in por defecto False, la atribución de fuente, y que
  la línea de vista (obstáculos) sigue gobernando a ambos sensores por
  igual.
"""

from __future__ import annotations

import pytest

from src.config import (
    DRONE_TX_GAIN_DBI,
    DRONE_TX_POWER_W,
    HPM_ORIGIN_X,
    HPM_ORIGIN_Y,
    HPM_ORIGIN_Z,
    RADAR_NOISE_FLOOR_W,
    RF_SENSOR_FREQUENCY_GHZ,
    RF_SENSOR_GAIN_DBI,
)
from src.engine.radar_engine import TrackManager
from src.engine.rf_sensor import evaluar_deteccion_rf, rf_received_power_w
from src.engine.simulation import SimulationEngine

# Mismos parámetros que src.config para no duplicar drift si cambian.
_PARAMS_RF = (DRONE_TX_POWER_W, DRONE_TX_GAIN_DBI, RF_SENSOR_GAIN_DBI, RF_SENSOR_FREQUENCY_GHZ)


class FakeDrone:
    """Doble mínimo, igual que en test_radar_dinamico.py."""

    def __init__(self, drone_id: int, x: float, y: float, z: float = 100.0):
        self.id = drone_id
        self.x = x
        self.y = y
        self.z = z
        self.detectado = False


class TestEvaluarDeteccionRf:
    def test_potencia_recibida_decrece_con_la_distancia(self):
        """Enlace unidireccional (r², no r⁴) — igual debe ser monótono
        decreciente, aunque caiga más lento que el del radar."""
        gt = 10.0 ** (DRONE_TX_GAIN_DBI / 10.0)
        gr = 10.0 ** (RF_SENSOR_GAIN_DBI / 10.0)
        from src.engine.radar_engine import wavelength_m

        wl = wavelength_m(RF_SENSOR_FREQUENCY_GHZ)
        p_cerca = rf_received_power_w(DRONE_TX_POWER_W, gt, gr, wl, 100.0)
        p_lejos = rf_received_power_w(DRONE_TX_POWER_W, gt, gr, wl, 1000.0)
        assert p_cerca > p_lejos > 0.0

    def test_detecta_a_la_diagonal_del_mapa_donde_el_radar_ya_no(self):
        """Hallazgo central de esta feature (ver el docstring del módulo):
        con los valores por defecto, a ~1414m (diagonal de un mapa de
        1000x1000) el radar ya cayó bajo SNR pero el sensor RF sigue
        detectando con margen — congelado acá como regresión."""
        from src.config import RADAR_ANTENNA_GAIN_DBI, RADAR_FREQUENCY_GHZ, RADAR_RCS_M2, RADAR_TX_POWER_W
        from src.engine.radar_engine import evaluar_deteccion

        r = 1414.0
        det_radar, _ = evaluar_deteccion(
            r, RADAR_TX_POWER_W, RADAR_ANTENNA_GAIN_DBI, RADAR_FREQUENCY_GHZ, RADAR_RCS_M2, RADAR_NOISE_FLOOR_W
        )
        det_rf, _ = evaluar_deteccion_rf(r, *_PARAMS_RF, RADAR_NOISE_FLOOR_W)
        assert det_radar is False
        assert det_rf is True

    def test_mas_alla_de_unos_4km_ya_no_detecta(self):
        """El sensor SÍ tiene un techo (no es omnisciente) — muy por
        fuera del mapa (1000x1000m), consistente con el ~3948m calculado
        a mano en el docstring del módulo."""
        det_rf, _ = evaluar_deteccion_rf(6000.0, *_PARAMS_RF, RADAR_NOISE_FLOOR_W)
        assert det_rf is False


class TestTrackManagerConSensorRf:
    def _params_radar(self):
        from src.config import RADAR_ANTENNA_GAIN_DBI, RADAR_FREQUENCY_GHZ, RADAR_RCS_M2, RADAR_TX_POWER_W

        return (RADAR_TX_POWER_W, RADAR_ANTENNA_GAIN_DBI, RADAR_FREQUENCY_GHZ, RADAR_RCS_M2, RADAR_NOISE_FLOOR_W)

    def test_por_defecto_no_considera_rf(self):
        """considerar_sensor_rf=False (default): un dron fuera del rango
        del radar pero dentro del rango RF NO obtiene track — mismo
        comportamiento que antes de esta feature."""
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=HPM_ORIGIN_X + 1414.0, y=HPM_ORIGIN_Y)
        tm.actualizar([d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *self._params_radar())
        assert tm.get_track(0) is None
        assert d.detectado is False

    def test_con_rf_activo_detecta_mas_alla_del_radar(self):
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=HPM_ORIGIN_X + 1414.0, y=HPM_ORIGIN_Y)
        tm.actualizar(
            [d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *self._params_radar(),
            considerar_sensor_rf=True,
        )
        track = tm.get_track(0)
        assert track is not None
        assert d.detectado is True
        assert track.fuente_deteccion == "rf"

    def test_dentro_del_rango_de_radar_la_fuente_sigue_siendo_radar(self):
        """Con considerar_sensor_rf=True, si el radar YA detecta, no se
        evalúa ni se atribuye al sensor RF — el radar tiene prioridad."""
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=HPM_ORIGIN_X + 50.0, y=HPM_ORIGIN_Y)
        tm.actualizar(
            [d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *self._params_radar(),
            considerar_sensor_rf=True,
        )
        track = tm.get_track(0)
        assert track is not None
        assert track.fuente_deteccion == "radar"

    def test_obstaculo_bloquea_tambien_al_sensor_rf(self):
        """La línea de vista es la MISMA para los dos sensores — un dron
        detrás de un obstáculo no se detecta ni siquiera con RF activo."""
        tm = TrackManager(revisita_s=1.0)
        # Dron alineado con el origen a 1414m, con un obstáculo grande
        # justo en el medio del segmento.
        d = FakeDrone(0, x=HPM_ORIGIN_X + 1414.0, y=HPM_ORIGIN_Y)
        obstaculo = (HPM_ORIGIN_X + 700.0, HPM_ORIGIN_Y, 50.0)
        tm.actualizar(
            [d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *self._params_radar(),
            obstaculos=[obstaculo], considerar_sensor_rf=True,
        )
        assert tm.get_track(0) is None
        assert d.detectado is False

    def test_mas_alla_del_alcance_rf_tampoco_detecta(self):
        tm = TrackManager(revisita_s=1.0)
        d = FakeDrone(0, x=HPM_ORIGIN_X + 6000.0, y=HPM_ORIGIN_Y)
        tm.actualizar(
            [d], 1.0, HPM_ORIGIN_X, HPM_ORIGIN_Y, HPM_ORIGIN_Z, *self._params_radar(),
            considerar_sensor_rf=True,
        )
        assert tm.get_track(0) is None


class TestIntegracionSimulationEngine:
    def test_sensor_rf_activo_no_rompe_el_motor(self):
        """Smoke test: el flag opt-in a nivel SimulationEngine corre
        varios ticks completos sin excepciones — mismo patrón que
        test_linea_de_vista.py::test_integracion_disparo_con_relieve_activo_no_rompe."""
        motor = SimulationEngine(swarm_size=15, mision_activa=False, sensor_rf_activo=True)
        motor.start()
        for _ in range(40):
            motor._tick(0.1)
        motor.shutdown()
