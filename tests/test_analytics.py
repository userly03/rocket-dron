"""Pruebas del módulo de analíticas físicas."""

import pytest

from src.engine.analytics import PhysicsAnalytics


class TestPhysicsAnalytics:
    def test_gaussian_probabilidad(self):
        a = PhysicsAnalytics()
        p_cerca = a.gaussian_neutralization_prob(50, 10)
        p_lejos = a.gaussian_neutralization_prob(50, 200)
        assert p_cerca > p_lejos

    def test_record_cannon_shot(self):
        a = PhysicsAnalytics()
        eventos = [{"distancia": 30, "neutralizado": True}, {"distancia": 80, "neutralizado": False}]
        shot = a.record_cannon_shot(50, 45, eventos, 1.0, 0, 0)
        assert shot["neutralizados"] == 1
        assert a.shot_counter == 1
        assert a.total_energy_mj > 0

    def test_effectiveness_curve(self):
        a = PhysicsAnalytics()
        a.record_cannon_shot(50, 0, [{"distancia": 20, "neutralizado": True}], 0, 0, 0)
        curve = a.get_effectiveness_curve()
        assert curve[0]["distancia"] == "0-50"
        assert curve[0]["intentos"] == 1

    def test_heatmap_structure(self):
        a = PhysicsAnalytics()
        hm = a.get_heatmap(0, 0, 45, 50, 30, grid_size=10)
        assert len(hm["values"]) == 10
        assert hm["max"] >= 0

    def test_spectrum(self):
        a = PhysicsAnalytics()
        spec = a.get_spectrum(50)
        assert len(spec["frequencies_ghz"]) == len(spec["amplitudes"])

    def test_reset(self):
        a = PhysicsAnalytics()
        a.record_cannon_shot(50, 0, [], 0, 0, 0)
        a.reset()
        assert a.shot_counter == 0
        assert a.total_energy_mj == 0
