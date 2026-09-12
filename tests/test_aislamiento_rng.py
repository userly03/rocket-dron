"""Pruebas de aislamiento de RNG entre réplicas/experimentos/sim interactiva (P0-B).

Antes de este cambio, ``run_replica`` llamaba ``seed_simulacion(cfg.semilla + i)``,
que reescribe el ``_rng`` GLOBAL de ``src/utils/reproducibilidad.py`` — el mismo
objeto del que sortea el hilo de la simulación interactiva
(``SimulationEngine._run_loop``). Dos consumidores concurrentes del mismo
generador mutable se corrompen mutuamente (docstring de ``experiments.py``,
declarado ahí como "Limitación conocida (stopgap)"; ver también
docs/AUDITORIA_CHECKLIST.md §3.1).

Con la inyección de generador (``nuevo_generador`` + ``SimulationEngine.rng``
propagado a ``Swarm``/``HPMissileSystem``/``Drone``/``HPMissile``), cada
réplica queda aislada. Estas pruebas verifican esa garantía de forma directa.
"""

from __future__ import annotations

import threading
import time

from src.engine.experiments import ExperimentConfig, ExperimentManager, WeaponPolicy, run_replica
from src.engine.simulation import SimulationEngine
from src.utils.reproducibilidad import nuevo_generador, seed_simulacion, semilla_actual


def _esperar(mgr: ExperimentManager, exp_id: str, timeout_s: float = 30.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        registro = mgr.get(exp_id)
        if registro["status"] in ("completado", "error"):
            return registro
        time.sleep(0.02)
    raise AssertionError("experimento no terminó a tiempo")


class TestNuevoGenerador:
    def test_misma_semilla_misma_secuencia(self):
        g1 = nuevo_generador(42)
        g2 = nuevo_generador(42)
        assert (g1.uniform(size=20) == g2.uniform(size=20)).all()

    def test_no_altera_el_generador_global(self):
        """``nuevo_generador`` no debe tocar ``seed_simulacion``/``semilla_actual``."""
        seed_simulacion(7)
        antes = semilla_actual()

        nuevo_generador(999)
        nuevo_generador(123)
        nuevo_generador(None)

        assert semilla_actual() == antes == 7


class TestExperimentosConcurrentes:
    def test_misma_semilla_da_resultados_identicos_en_paralelo(self):
        """Dos experimentos concurrentes con la misma semilla no deben corromperse."""
        def cfg() -> ExperimentConfig:
            return ExperimentConfig(
                formacion="cuadrada",
                cantidad=6,
                replicas=4,
                t_max_s=2.0,
                dt=1.0 / 30.0,
                semilla=321,
                arma=WeaponPolicy(tipo="canion", delay_s=0.5, potencia=80, direccion=45),
            )

        mgr = ExperimentManager()
        exp_id_a = mgr.start(cfg())
        exp_id_b = mgr.start(cfg())

        registro_a = _esperar(mgr, exp_id_a)
        registro_b = _esperar(mgr, exp_id_b)

        assert registro_a["status"] == registro_b["status"] == "completado"
        assert registro_a["resultados"] == registro_b["resultados"]
        assert registro_a["resumen"] == registro_b["resumen"]


class TestExperimentoDuranteSimulacionInteractiva:
    def test_replicas_identicas_con_sim_interactiva_corriendo(self):
        """
        Correr un experimento MIENTRAS la simulación interactiva está viva y
        disparando (consumiendo el generador GLOBAL) debe dar réplicas bit a
        bit idénticas a correrlo aislado — la inyección de generador por
        réplica las hace inmunes a esa actividad concurrente.
        """
        cfg = ExperimentConfig(
            formacion="cuadrada",
            cantidad=5,
            replicas=3,
            t_max_s=2.0,
            dt=1.0 / 30.0,
            semilla=555,
            arma=WeaponPolicy(tipo="canion", delay_s=0.5, potencia=80, direccion=45),
        )

        resultados_aislado = [run_replica(cfg, i) for i in range(cfg.replicas)]

        # Sim interactiva viva, disparando en bucle desde otro hilo — fuerza
        # sorteos reales sobre el generador GLOBAL mientras corren las réplicas.
        seed_simulacion(1)
        sim_interactiva = SimulationEngine(swarm_size=20)
        sim_interactiva.start()

        detener = threading.Event()

        def _disparar_en_bucle() -> None:
            while not detener.is_set():
                sim_interactiva.fire(potencia=50, direccion=0)
                time.sleep(0.001)

        hilo_ruido = threading.Thread(target=_disparar_en_bucle, daemon=True)
        hilo_ruido.start()
        try:
            resultados_bajo_carga = [run_replica(cfg, i) for i in range(cfg.replicas)]
        finally:
            detener.set()
            hilo_ruido.join(timeout=2.0)
            sim_interactiva.shutdown()

        assert resultados_bajo_carga == resultados_aislado
