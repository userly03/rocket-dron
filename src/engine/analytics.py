"""Analíticas físicas, historial de disparos y mapas de cobertura HPM."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.config import (
    FIELD_HEIGHT,
    FIELD_WIDTH,
    HPM_BEAM_SIGMA,
    HPM_COUPLING_K,
    HPM_DUTY_CYCLE,
    HPM_E_THRESHOLD_V_M,
    HPM_FREQUENCY_GHZ,
    HPM_K_CONSTANT,
    HPM_MODEL,
    HPM_PULSE_DURATION_NS,
)
from src.engine.hpm_engine import compute_target_parameters, friis_diagnostics


@dataclass
class PhysicsAnalytics:
    """Seguimiento de métricas físicas, disparos y cobertura HPM."""

    # Parámetro INTERNO de gaussian_neutralization_prob, usado solo para
    # pintar el heatmap (get_heatmap) — no gobierna ninguna baja y no se
    # publica por get_physics_panel (ver docs/AUDITORIA_CHECKLIST.md §4.1).
    coupling_k: float = HPM_COUPLING_K
    frequency_ghz: float = HPM_FREQUENCY_GHZ
    pulse_duration_ns: float = HPM_PULSE_DURATION_NS
    beam_sigma: float = HPM_BEAM_SIGMA
    total_energy_mj: float = field(default=0.0, init=False)
    peak_power_gw: float = field(default=0.0, init=False)
    shot_counter: int = field(default=0, init=False)
    shot_history: deque = field(default_factory=lambda: deque(maxlen=100), init=False)
    distance_stats: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._init_distance_bins()

    def _init_distance_bins(self) -> None:
        self.distance_stats = {
            label: {"intentos": 0, "neutralizados": 0}
            for label in ("0-50", "50-100", "100-200", "200-400", "400+")
        }

    def _distance_bin(self, distancia: float) -> str:
        if distancia <= 50:
            return "0-50"
        if distancia <= 100:
            return "50-100"
        if distancia <= 200:
            return "100-200"
        if distancia <= 400:
            return "200-400"
        return "400+"

    def _record_hit(self, distancia: float, neutralizado: bool) -> None:
        label = self._distance_bin(distancia)
        self.distance_stats[label]["intentos"] += 1
        if neutralizado:
            self.distance_stats[label]["neutralizados"] += 1

    def _pulse_energy_mj(self, potencia_kw: float) -> float:
        """E = P · t → energía del pulso en mJ."""
        potencia_w = potencia_kw * 1000.0
        tiempo_s = self.pulse_duration_ns * 1e-9
        return potencia_w * tiempo_s * 1000.0

    def _update_energy_metrics(self, potencia_kw: float) -> None:
        energy_mj = self._pulse_energy_mj(potencia_kw)
        self.total_energy_mj += energy_mj
        peak_w = energy_mj * 1e-3 / (self.pulse_duration_ns * 1e-9)
        peak_gw = peak_w / 1e9
        self.peak_power_gw = max(self.peak_power_gw, peak_gw)

    def gaussian_neutralization_prob(
        self, potencia_kw: float, distancia: float, sigma: float | None = None
    ) -> float:
        """
        Modelo gaussiano: P = 1 - exp(-k · P · exp(-r²/2σ²))

        Uso exclusivo: intensidad del mapa de calor (``get_heatmap``) — un
        perfil suave, barato de calcular en una grilla, para PINTAR dónde el
        haz es más intenso. NO es el modelo de daño: ni la rama ``friis``
        (Friis + campo E + sigmoide de susceptibilidad) ni la ``legacy``
        (exponencial sobre ``HPM_K_CONSTANT``, ver ``calculate_neutralization
        _probability``) usan esta gaussiana para decidir si un dron muere —
        ``Drone.recibir_daño``/``HPMissile.calcular_daño`` no la llaman en
        ningún punto. Publicarla en ``get_physics_panel`` como si gobernara
        las bajas fue el defecto documentado en docs/AUDITORIA_CHECKLIST.md
        §4.1 y corregido en P0-C: un tercer modelo con apariencia física en
        pantalla que no mataba a nadie. No exponer ``coupling_k`` ni esta
        fórmula fuera de ``get_heatmap``.
        """
        sigma = sigma or self.beam_sigma
        if distancia <= 0:
            return 1.0
        gaussian = math.exp(-(distancia**2) / (2.0 * sigma**2))
        exponent = -self.coupling_k * potencia_kw * gaussian
        return float(np.clip(1.0 - math.exp(exponent), 0.0, 1.0))

    def record_cannon_shot(
        self,
        potencia: float,
        direccion: float,
        eventos: list[dict],
        tiempo: float,
        origen_x: float,
        origen_y: float,
    ) -> dict:
        self.shot_counter += 1
        self._update_energy_metrics(potencia)

        distancias = [e.get("distancia", 0) for e in eventos]
        dist_prom = sum(distancias) / len(distancias) if distancias else 0.0
        neutralizados = sum(1 for e in eventos if e.get("neutralizado"))

        for e in eventos:
            self._record_hit(e.get("distancia", 0), e.get("neutralizado", False))

        entry = {
            "id": self.shot_counter,
            "tipo": "cañon",
            "tiempo": round(tiempo, 3),
            "potencia_kw": potencia,
            "direccion": direccion,
            "afectados": len(eventos),
            "neutralizados": neutralizados,
            "distancia_promedio": round(dist_prom, 2),
            "tasa_exito": round(neutralizados / len(eventos), 3) if eventos else 0.0,
            # Bajas atribuidas DESPUÉS del disparo por fallo latente (P2-D),
            # nunca al crear la entrada — ver record_delayed_kill.
            "bajas_diferidas": 0,
        }
        self.shot_history.append(entry)
        return entry

    def record_missile_detonation(
        self,
        potencia: float,
        radio: float,
        impactos: list[dict],
        tiempo: float,
        misil_id: str,
    ) -> dict:
        self.shot_counter += 1
        self._update_energy_metrics(potencia)

        neutralizados = sum(1 for i in impactos if i.get("neutralizado"))
        distancias = [i.get("distancia", 0) for i in impactos]
        dist_prom = sum(distancias) / len(distancias) if distancias else 0.0

        for i in impactos:
            self._record_hit(i.get("distancia", 0), i.get("neutralizado", False))

        entry = {
            "id": self.shot_counter,
            "tipo": "misil",
            "tiempo": round(tiempo, 3),
            "misil_id": misil_id,
            "potencia_kw": potencia,
            "radio_efecto": radio,
            "afectados": len(impactos),
            "neutralizados": neutralizados,
            "distancia_promedio": round(dist_prom, 2),
            "tasa_exito": round(neutralizados / len(impactos), 3) if impactos else 0.0,
            "bajas_diferidas": 0,
        }
        self.shot_history.append(entry)
        return entry

    def get_physics_panel(
        self,
        potencia_kw: float,
        radio_efecto: float | None = None,
        hpm: dict[str, Any] | None = None,
        upset_damage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        radio = radio_efecto or self.beam_sigma * 2
        energy_mj = self._pulse_energy_mj(potencia_kw)
        area_m2 = math.pi * radio**2
        field_intensity = (potencia_kw * 1000.0) / area_m2 if area_m2 > 0 else 0.0

        # "formula" refleja SIEMPRE el modelo que de verdad decide las bajas
        # (ver Drone.recibir_daño/HPMissile.calcular_daño), nunca la gaussiana
        # de gaussian_neutralization_prob (esa es solo para pintar el
        # heatmap — ver su docstring). Default = modelo "legacy"
        # (P = 1 - exp(-k·potencia/d²), con la k que ese modelo SÍ usa,
        # HPM_K_CONSTANT); la rama "friis" de abajo la sobreescribe con la
        # fórmula real de ese modelo. docs/AUDITORIA_CHECKLIST.md §4.1.
        panel = {
            "modelo_hpm": HPM_MODEL,
            "potencia_kw": potencia_kw,
            "frecuencia_ghz": self.frequency_ghz,
            "radio_efecto_m": round(radio, 2),
            "beam_sigma": self.beam_sigma,
            "pulse_duration_ns": self.pulse_duration_ns,
            "formula": f"P = 1 - exp(-k · potencia / d²)  (k = HPM_K_CONSTANT = {HPM_K_CONSTANT})",
            "energia_pulso_mj": round(energy_mj, 4),
            "intensidad_campo_w_m2": round(field_intensity, 2),
            "total_energy_mj": round(self.total_energy_mj, 4),
            "total_energy_mj_unit": "mJ",
            "total_energy_mj_display": f"{self.total_energy_mj / 1000:.4f}",
            "total_energy_mj_display_unit": "MJ",
            "peak_power_gw": round(self.peak_power_gw, 6),
        }

        if HPM_MODEL == "friis":
            diag = friis_diagnostics(
                potencia_kw,
                distancia=radio / 2,
                apertura_cono=360.0,
                duty_cycle=HPM_DUTY_CYCLE,
            )
            panel.update(
                {
                    "formula": "S = P_pico·G/(4πr²)  →  E = √(S·377)  →  E_eff = E·g(τ)  →  P = sigmoide(E_eff, E_umbral)",
                    "ganancia_antena_dbi": round(10 * math.log10(max(diag["ganancia_antena"], 1e-9)), 2),
                    "densidad_potencia_w_m2": diag["densidad_potencia_w_m2"],
                    "campo_e_v_m": diag["campo_e_v_m"],
                    "campo_e_efectivo_v_m": diag["campo_e_efectivo_v_m"],
                    "campo_e_umbral_v_m": HPM_E_THRESHOLD_V_M,
                    "potencia_pico_kw": diag["potencia_pico_kw"],
                    "duty_cycle": diag["duty_cycle"],
                    "acoplamiento_pulso": diag["acoplamiento_pulso"],
                }
            )

        if hpm:
            # Presupuesto energético/térmico del arma (P2-F): lo que
            # gobierna la cadencia sostenida real (ver HPMWeapon), no un
            # tercer modelo decorativo — mismo criterio que P0-C aplicó a
            # gaussian_neutralization_prob (docs/FISICA_Y_MATEMATICA.md
            # hallazgo 8): el panel solo publica lo que gobierna las bajas o
            # el estado real del sistema.
            panel["presupuesto_arma"] = {
                "energia_actual_kj": hpm.get("energia_actual_kj"),
                "energia_maxima_kj": hpm.get("energia_maxima_kj"),
                "temperatura_c": hpm.get("temperatura_c"),
                "temperatura_max_c": hpm.get("temperatura_max_c"),
                "listo_para_disparar": hpm.get("listo_para_disparar"),
                "ultimo_rechazo": hpm.get("ultimo_rechazo"),
            }

        if upset_damage:
            # Upset vs damage (P2-D): mismo criterio — es el estado REAL del
            # enjambre (Swarm.contar_upset_damage), no una métrica decorativa.
            panel["upset_damage"] = upset_damage

        return panel

    def record_delayed_kill(self, shot_id: int, distancia: float | None) -> bool:
        """
        Atribuye una baja DIFERIDA (fallo latente, P2-D) al disparo o
        detonación ORIGINAL, en vez de perderla sin registrar. Es la
        maquinaria valiosa que se conservó de la premisa cortada de P3-09
        (ver docs/AUDITORIA_CHECKLIST.md §3.6: el mecanismo de thermal
        runaway fallaba el presupuesto energético por ~10⁹, pero "kills
        atribuidos al disparo original ticks después" seguía siendo un
        efecto real y valioso — solo hacía falta la causa correcta).

        A diferencia de ``record_cannon_shot``/``record_missile_detonation``,
        NO crea una entrada nueva en ``shot_history``: MUTA la entrada
        ORIGINAL in-place — ``shot_history`` guarda referencias a los mismos
        dicts que se le agregaron, así que buscarla por ``id`` y modificarla
        ahí es válido y es justamente lo que hace que la curva de
        efectividad refleje la baja en el disparo que la causó, aunque haya
        ocurrido varios ticks después.

        Returns:
            True si se encontró y actualizó el disparo original. False si
            el id ya salió de la ventana de ``shot_history``
            (``maxlen=100``) — la baja diferida no se pierde del conteo de
            drones (eso ya lo maneja ``Drone.actualizar_riesgo_latente``),
            solo de la atribución/diagnóstico, aceptable para un disparo
            viejo que ya salió de la ventana reciente.
        """
        entry = next((s for s in self.shot_history if s["id"] == shot_id), None)
        if entry is None:
            return False

        entry["neutralizados"] += 1
        entry["tasa_exito"] = (
            round(entry["neutralizados"] / entry["afectados"], 3)
            if entry["afectados"] else 0.0
        )
        entry["bajas_diferidas"] = entry.get("bajas_diferidas", 0) + 1

        if distancia is not None:
            self._upgrade_hit(distancia)

        return True

    def _upgrade_hit(self, distancia: float) -> None:
        """
        Sube a "neutralizado" un intento YA CONTADO en ``distance_stats``
        (por ``_record_hit`` en el momento del disparo original, con
        ``neutralizado=False``) sin volver a incrementar ``intentos`` — eso
        contaría el mismo intento dos veces. Usa la distancia del disparo
        ORIGINAL (guardada en ``Drone.origen_riesgo_distancia_m``), no la
        posición actual del dron, que pudo moverse entre el disparo y la
        baja diferida.
        """
        label = self._distance_bin(distancia)
        self.distance_stats[label]["neutralizados"] += 1

    def get_effectiveness_curve(self) -> list[dict]:
        curve = []
        for label, stats in self.distance_stats.items():
            intentos = stats["intentos"]
            tasa = stats["neutralizados"] / intentos if intentos > 0 else 0.0
            curve.append(
                {
                    "distancia": label,
                    "intentos": intentos,
                    "neutralizados": stats["neutralizados"],
                    "tasa_exito": round(tasa * 100, 1),
                }
            )
        return curve

    def get_shot_history(self, limit: int = 20) -> list[dict]:
        return list(self.shot_history)[-limit:]

    def get_heatmap(
        self,
        origen_x: float,
        origen_y: float,
        direccion: float,
        potencia: float,
        apertura_cono: float,
        grid_size: int = 25,
        missile_zones: list[dict] | None = None,
    ) -> dict:
        """Mapa de calor de intensidad HPM sobre el campo."""
        rows = grid_size
        cols = grid_size
        grid: list[list[float]] = []

        for row in range(rows):
            row_vals: list[float] = []
            for col in range(cols):
                wx = (col + 0.5) * FIELD_WIDTH / cols
                wy = (row + 0.5) * FIELD_HEIGHT / rows

                dist, ang_offset = compute_target_parameters(
                    origen_x, origen_y, direccion, wx, wy
                )
                intensity = 0.0
                if abs(ang_offset) <= apertura_cono / 2.0 and dist > 0:
                    intensity = self.gaussian_neutralization_prob(potencia, dist)

                if missile_zones:
                    for zone in missile_zones:
                        if zone.get("estado") == "detonado":
                            dx = wx - zone["x"]
                            dy = wy - zone["y"]
                            d = math.hypot(dx, dy)
                            if d <= zone.get("radio_efecto", 100):
                                z_int = self.gaussian_neutralization_prob(
                                    zone.get("potencia_hpm", potencia), d, zone.get("radio_efecto", 100) / 2
                                )
                                intensity = max(intensity, z_int)

                row_vals.append(round(intensity, 4))
            grid.append(row_vals)

        return {
            "grid_size": grid_size,
            "width": FIELD_WIDTH,
            "height": FIELD_HEIGHT,
            "values": grid,
            "max": max(max(r) for r in grid) if grid else 0.0,
        }

    def get_spectrum(self, potencia_kw: float | None = None) -> dict:
        """Espectro de frecuencias con perfil gaussiano."""
        center = self.frequency_ghz
        bandwidth = 0.5
        freqs = [round(f, 2) for f in np.linspace(center - 1.5, center + 1.5, 31)]
        amplitudes = []
        p_factor = (potencia_kw or 50.0) / 100.0

        for f in freqs:
            amp = p_factor * math.exp(-((f - center) ** 2) / (2 * bandwidth**2))
            amplitudes.append(round(amp, 4))

        return {
            "center_ghz": center,
            "frequencies_ghz": freqs,
            "amplitudes": amplitudes,
            "unit": "potencia normalizada",
        }

    def reset(self) -> None:
        self.total_energy_mj = 0.0
        self.peak_power_gw = 0.0
        self.shot_counter = 0
        self.shot_history.clear()
        self._init_distance_bins()

    def to_snapshot(
        self, hpm: dict, missiles: list | None = None, swarm: Any = None
    ) -> dict:
        zones = []
        for m in missiles or []:
            if hasattr(m, "to_dict"):
                d = m.to_dict()
            else:
                d = m
            zones.append(d)

        potencia = hpm.get("potencia", 25)
        upset_damage = swarm.contar_upset_damage() if swarm is not None else None
        return {
            "physics": self.get_physics_panel(potencia, hpm=hpm, upset_damage=upset_damage),
            "metrics": {
                "total_energy_mj": round(self.total_energy_mj, 4),
                "total_energy_mj_mega": round(self.total_energy_mj / 1e6, 6),
                "peak_power_gw": round(self.peak_power_gw, 6),
                "disparos_totales": self.shot_counter,
            },
            "effectiveness": self.get_effectiveness_curve(),
            "shot_history": self.get_shot_history(10),
            "heatmap": self.get_heatmap(
                hpm.get("origen_x", 0),
                hpm.get("origen_y", 0),
                hpm.get("direccion", 0),
                potencia,
                hpm.get("apertura_cono", 30),
                missile_zones=zones,
            ),
            "spectrum": self.get_spectrum(potencia),
        }
