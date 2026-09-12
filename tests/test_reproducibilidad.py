"""Pruebas de reproducibilidad (semilla determinista), manifiesto y export CSV."""

import csv
import io

from fastapi.testclient import TestClient

from src.engine.simulation import SimulationEngine
from src.utils.reproducibilidad import build_manifest, seed_simulacion


def _estado_enjambre(sim: SimulationEngine) -> list[tuple]:
    return [(d.x, d.y, d.z, d.angulo, d.salud, d.estado.value) for d in sim.swarm.drones]


class TestDeterminismo:
    def test_misma_semilla_misma_corrida(self):
        """
        El contrato de reproducibilidad con RNG global es de corrida completa:
        re-sembrar antes de TODA la secuencia (construcción + disparos) da
        resultados bit a bit idénticos. Dos motores entrelazados compartiendo
        el stream no pueden disparar en orden cruzado y esperar igualdad —
        eso exigiría RNG por motor (anotado como trabajo futuro).
        """

        def corrida() -> tuple[list[tuple], list[bool]]:
            sim = SimulationEngine(swarm_size=10)
            sim.configure_swarm("circular", 10)
            eventos = sim.fire(potencia=80, direccion=45)["eventos"]
            return _estado_enjambre(sim), [e["neutralizado"] for e in eventos]

        seed_simulacion(42)
        estado_a, kills_a = corrida()
        seed_simulacion(42)
        estado_b, kills_b = corrida()

        assert estado_a == estado_b
        assert kills_a == kills_b

    def test_semilla_distinta_da_resultado_distinto(self):
        # Formación aleatoria: las posiciones sí dependen del sorteo (la
        # circular es determinista por construcción: anillo + capas fijas).
        seed_simulacion(1)
        sim_a = SimulationEngine(swarm_size=10)
        sim_a.configure_swarm("aleatoria", 10)

        seed_simulacion(2)
        sim_b = SimulationEngine(swarm_size=10)
        sim_b.configure_swarm("aleatoria", 10)

        assert _estado_enjambre(sim_a) != _estado_enjambre(sim_b)

    def test_semilla_none_no_rompe(self):
        seed_simulacion(None)
        sim = SimulationEngine(swarm_size=5)
        sim._tick(1.0 / 30.0)
        assert sim.tick == 1


class TestManifest:
    def test_manifest_contiene_seed_y_config(self):
        seed_simulacion(77)
        manifest = build_manifest()
        assert manifest["sim_seed"] == 77
        assert manifest["hpm_model"] in ("friis", "legacy")
        assert "HPM_E_THRESHOLD_V_M" in manifest["config"]
        assert manifest["config"]["HPM_E_THRESHOLD_V_M"] > 0

    def test_manifest_extra(self):
        manifest = build_manifest({"experimento": {"id": "x"}})
        assert manifest["experimento"]["id"] == "x"


class TestExportRoutes:
    def test_export_disparos_csv(self):
        from src.main import app

        with TestClient(app) as client:
            client.post("/api/fire", json={"potencia": 50, "direccion": 45})
            resp = client.get("/api/export?tipo=disparos")
            assert resp.status_code == 200
            assert "text/csv" in resp.headers["content-type"]

            filas = list(csv.DictReader(io.StringIO(resp.text)))
            assert len(filas) == 1
            assert filas[0]["tipo"] == "cañon"
            assert float(filas[0]["potencia_kw"]) == 50.0

    def test_export_eventos_csv(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/api/export?tipo=eventos")
            assert resp.status_code == 200
            filas = list(csv.DictReader(io.StringIO(resp.text)))
            # Al menos el evento de inicialización está en el log.
            assert len(filas) >= 1
            assert {"timestamp", "tick", "evento", "datos"} <= set(filas[0].keys())

    def test_export_tipo_invalido_400(self):
        from src.main import app

        with TestClient(app) as client:
            assert client.get("/api/export?tipo=nope").status_code == 400

    def test_manifest_endpoint(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.get("/api/manifest")
            assert resp.status_code == 200
            assert "config" in resp.json()
