"""Pruebas de desacople entre la frecuencia del ARMA y la del RADAR (P0-A).

Antes de este cambio, ``Swarm.actualizar`` pasaba ``HPM_FREQUENCY_GHZ`` (la
frecuencia del cañón/misil) a ``evaluar_deteccion``. Como la ecuación de
radar lleva λ², barrer la frecuencia del arma para estudiar resonancia de
acoplamiento (ver ``DRONE_CABLE_LENGTH_*``/``HPM_COUPLING_Q``) cambiaba
también, como efecto colateral, el alcance de detección del radar — y por
lo tanto a cuántos drones se les dispara. Ver docs/AUDITORIA_CHECKLIST.md §3.2.

Estas pruebas verifican, de forma falsable:

1. que ``evaluar_deteccion`` SÍ depende de la frecuencia que recibe (si no
   dependiera, el desacople no tendría sentido);
2. que ``Swarm.actualizar`` usa efectivamente ``RADAR_FREQUENCY_GHZ`` (variar
   esa constante cambia la detección);
3. que ``Swarm.actualizar`` NO usa ``HPM_FREQUENCY_GHZ`` (la frecuencia del
   arma, sea la que sea, no puede alterar la detección) — el criterio de
   aceptación explícito de P0-A/CHECKLIST_MEJORAS.md.
"""

from __future__ import annotations

import pytest

import src.models.swarm as swarm_mod
from src.config import (
    RADAR_ANTENNA_GAIN_DBI,
    RADAR_NOISE_FLOOR_W,
    RADAR_RCS_M2,
    RADAR_TX_POWER_W,
)
from src.engine.radar_engine import evaluar_deteccion
from src.models.swarm import FormacionTipo, Swarm
from src.utils.reproducibilidad import seed_simulacion


class TestEvaluarDeteccionDependeDeFrecuencia:
    def test_probabilidad_cambia_con_la_frecuencia(self):
        """Sanity check del mecanismo: sin λ² variable, el desacople no importaría."""
        distancia = 700.0
        probabilidades = [
            evaluar_deteccion(
                distancia,
                RADAR_TX_POWER_W,
                RADAR_ANTENNA_GAIN_DBI,
                freq,
                RADAR_RCS_M2,
                RADAR_NOISE_FLOOR_W,
            )[1]
            for freq in (1.0, 2.0, 4.0, 6.0, 8.0)
        ]
        # No todas iguales: la frecuencia sí entra en la física del radar.
        assert len(set(round(p, 6) for p in probabilidades)) > 1


class TestSwarmUsaFrecuenciaDeRadar:
    def _contar_detectados(self, seed: int = 42) -> int:
        """
        MODIFICADO en P2-G: el radar ya no decide instantáneamente cada
        tick — hace falta que se cumpla al menos un ciclo de revisita
        (``RADAR_REVISITA_S``) para que el ``TrackManager`` tome la primera
        medición. Antes, ``dt=0.0`` alcanzaba porque la detección era
        instantánea; con barrido, ``dt=0.0`` nunca dispara un barrido y este
        helper habría devuelto 0 SIEMPRE, dejando los dos tests que lo usan
        pasando de forma vacía (0 == 0) en vez de comparar conteos reales —
        se detectó exactamente así al migrar (ver CHECKLIST_MEJORAS.md P2-G).
        Se fuerza el reloj de barrido al umbral para obtener una medición
        inmediata sin mover a los drones (dt=0.0 en el resto del pipeline).
        """
        from src.config import RADAR_REVISITA_S

        seed_simulacion(seed)
        swarm = Swarm(formacion=FormacionTipo.CIRCULAR)
        swarm.inicializar_formacion(FormacionTipo.CIRCULAR.value, 30)
        swarm.track_manager._reloj_barrido_s = RADAR_REVISITA_S
        swarm.actualizar(dt=0.0)
        return sum(1 for d in swarm.drones if d.detectado)

    def test_variar_radar_frequency_ghz_cambia_la_deteccion(self, monkeypatch):
        """Swarm.actualizar SÍ debe reaccionar a RADAR_FREQUENCY_GHZ."""
        monkeypatch.setattr(swarm_mod, "RADAR_FREQUENCY_GHZ", 2.45)
        detectados_baja = self._contar_detectados()

        monkeypatch.setattr(swarm_mod, "RADAR_FREQUENCY_GHZ", 35.0)
        detectados_alta = self._contar_detectados()

        assert detectados_baja != detectados_alta

    @pytest.mark.parametrize("frecuencia_arma_ghz", [1.0, 2.0, 4.0, 6.0, 8.0])
    def test_variar_hpm_frequency_ghz_no_cambia_la_deteccion(
        self, monkeypatch, frecuencia_arma_ghz
    ):
        """
        Criterio de aceptación de P0-A: barrer la frecuencia del ARMA (la que
        estudia el experimento de resonancia de P2-04) en [1, 2, 4, 6, 8] GHz
        no debe cambiar el conteo de drones detectados por el radar.

        ``Swarm.actualizar`` ya no importa ``HPM_FREQUENCY_GHZ`` en absoluto
        (ver src/models/swarm.py) — se monkeypatchea igual sobre el módulo
        de configuración para que el test sea honesto ante una futura
        regresión que la reintroduzca como import de nivel de módulo.
        """
        import src.config as config_mod

        monkeypatch.setattr(config_mod, "HPM_FREQUENCY_GHZ", frecuencia_arma_ghz)
        monkeypatch.setattr(swarm_mod, "RADAR_FREQUENCY_GHZ", 2.45)

        detectados = self._contar_detectados()

        # Referencia: misma semilla, misma RADAR_FREQUENCY_GHZ, arma a 2.45GHz.
        monkeypatch.setattr(config_mod, "HPM_FREQUENCY_GHZ", 2.45)
        monkeypatch.setattr(swarm_mod, "RADAR_FREQUENCY_GHZ", 2.45)
        detectados_referencia = self._contar_detectados()

        assert detectados == detectados_referencia
