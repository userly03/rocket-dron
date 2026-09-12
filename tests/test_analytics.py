"""Pruebas del módulo de analíticas físicas."""

import pytest

from src.config import HPM_K_CONSTANT
from src.engine.analytics import PhysicsAnalytics


class TestPhysicsAnalytics:
    def test_gaussian_probabilidad(self):
        a = PhysicsAnalytics()
        p_cerca = a.gaussian_neutralization_prob(50, 10)
        p_lejos = a.gaussian_neutralization_prob(50, 200)
        assert p_cerca > p_lejos

    def test_panel_no_publica_gaussiana_fantasma(self):
        """
        P0-C: gaussian_neutralization_prob es solo para el heatmap — el panel
        físico no debe publicar ``coupling_k`` ni ``probabilidad_referencia``
        (un tercer modelo que no gobierna ninguna baja). Ver
        docs/AUDITORIA_CHECKLIST.md §4.1.
        """
        a = PhysicsAnalytics()
        panel = a.get_physics_panel(50)
        assert "coupling_k" not in panel
        assert "probabilidad_referencia" not in panel

    def test_panel_formula_refleja_modelo_legacy_activo(self, monkeypatch):
        """Con HPM_MODEL='legacy', 'formula' debe ser la del modelo legacy
        (con HPM_K_CONSTANT, la k que ese modelo sí usa), no la gaussiana."""
        monkeypatch.setattr("src.engine.analytics.HPM_MODEL", "legacy")
        a = PhysicsAnalytics()
        panel = a.get_physics_panel(50)
        assert "exp(-k · potencia / d²)" in panel["formula"]
        assert str(HPM_K_CONSTANT) in panel["formula"]

    def test_panel_formula_refleja_modelo_friis_activo(self, monkeypatch):
        monkeypatch.setattr("src.engine.analytics.HPM_MODEL", "friis")
        a = PhysicsAnalytics()
        panel = a.get_physics_panel(50)
        assert "sigmoide" in panel["formula"]

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
