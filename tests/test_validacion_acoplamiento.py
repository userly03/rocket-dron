"""Pruebas del arreglo a los falsos positivos de ``check_shot_invariants``
por acoplamiento (deuda técnica menor, CHECKLIST_MEJORAS.md).

Desde P2-04 (huella de susceptibilidad) la probabilidad de un dron depende,
además de distancia y offset angular, del factor de acoplamiento
``√(η·pol)`` sorteado por dron (``Drone.factor_acoplamiento()``). Dos drones
a distancia y offset casi iguales pueden tener acoplamientos muy distintos,
así que la monotonía probabilidad-vs-distancia NO es un invariante válido
entre ellos — el chequeo tiene que condicionar también por acoplamiento
comparable, degradando con elegancia (no reportar) cuando el dato no está.

Nota sobre alcance de archivo: el resto de la tarea usa
``tests/test_presupuesto_arma.py`` como único archivo de test nuevo
autorizado explícitamente; este archivo cubre el segundo ítem encargado
(arreglo de ``check_shot_invariants``), que requiere su propia cobertura
para demostrar el arreglo — ver el reporte final de la tarea para la nota
de desviación correspondiente.
"""

from __future__ import annotations

import pytest

from src.engine.validation import check_shot_invariants
from src.models.drone import Drone
from src.models.hpm_missile import HPMissile
from src.models.hpm_weapon import HPMWeapon


class TestNoFalsoPositivoPorAcoplamientoDistinto:
    def test_caso_real_observado_no_genera_aviso(self):
        """Reproduce el caso observado en corridas reales (ver
        CHECKLIST_MEJORAS.md / docstring de check_shot_invariants):
        d=898.67m→p=0.0097 vs d=899.1m→p=0.0244, con acoplamientos muy
        distintos (uno casi desintonizado, el otro casi resonante)."""
        eventos = [
            {
                "drone_id": 0,
                "distancia": 898.67,
                "angulo_offset": 0.3,
                "probabilidad": 0.0097,
                "neutralizado": False,
                "factor_acoplamiento": 0.15,
            },
            {
                "drone_id": 1,
                "distancia": 899.10,
                "angulo_offset": 0.4,
                "probabilidad": 0.0244,
                "neutralizado": False,
                "factor_acoplamiento": 0.95,
            },
        ]

        avisos = check_shot_invariants(eventos)

        assert avisos == []

    def test_acoplamientos_extremos_opuestos_no_generan_aviso(self):
        eventos = [
            {
                "drone_id": 0,
                "distancia": 100.0,
                "angulo_offset": 0.0,
                "probabilidad": 0.05,
                "neutralizado": False,
                "factor_acoplamiento": 0.1,
            },
            {
                "drone_id": 1,
                "distancia": 120.0,
                "angulo_offset": 0.0,
                "probabilidad": 0.5,
                "neutralizado": False,
                "factor_acoplamiento": 1.0,
            },
        ]

        avisos = check_shot_invariants(eventos)

        assert avisos == []


class TestSiDetectaViolacionRealConAcoplamientoComparable:
    """El test que prueba que NO se rompió el chequeo: con acoplamientos
    comparables (dentro de la tolerancia relativa) y una monotonía
    realmente violada, la advertencia debe seguir apareciendo."""

    def test_monotonia_violada_con_acoplamiento_comparable_si_genera_aviso(self):
        eventos = [
            {
                "drone_id": 0,
                "distancia": 100.0,
                "angulo_offset": 0.0,
                "probabilidad": 0.5,
                "neutralizado": False,
                "factor_acoplamiento": 0.90,
            },
            {
                "drone_id": 1,
                "distancia": 150.0,
                "angulo_offset": 0.0,
                "probabilidad": 0.7,
                "neutralizado": False,
                # 0.92 vs 0.90: ~2.2% de diferencia relativa, muy por
                # debajo de la tolerancia (15%) -> "mismo acoplamiento".
                "factor_acoplamiento": 0.92,
            },
        ]

        avisos = check_shot_invariants(eventos)

        assert any("no decrece" in a for a in avisos)

    def test_acoplamiento_con_diferencia_moderada_dentro_de_tolerancia_si_genera_aviso(self):
        # Diferencia relativa ~9%, dentro del 15% de tolerancia.
        eventos = [
            {
                "drone_id": 0,
                "distancia": 200.0,
                "angulo_offset": 1.0,
                "probabilidad": 0.2,
                "neutralizado": False,
                "factor_acoplamiento": 0.80,
            },
            {
                "drone_id": 1,
                "distancia": 250.0,
                "angulo_offset": 1.0,
                "probabilidad": 0.35,
                "neutralizado": False,
                "factor_acoplamiento": 0.88,
            },
        ]

        avisos = check_shot_invariants(eventos)

        assert any("no decrece" in a for a in avisos)


class TestDegradacionElegante:
    def test_sin_factor_acoplamiento_no_reporta_ni_confirma(self):
        """Eventos "legacy" (sin factor_acoplamiento, p. ej. HPM_MODEL=
        legacy o eventos generados antes de esta corrección): el chequeo se
        abstiene de comparar en vez de arriesgar un falso positivo, incluso
        cuando la monotonía de hecho está rota."""
        eventos = [
            {"drone_id": 0, "distancia": 100.0, "angulo_offset": 0.0, "probabilidad": 0.5, "neutralizado": False},
            {"drone_id": 1, "distancia": 150.0, "angulo_offset": 0.0, "probabilidad": 0.7, "neutralizado": False},
        ]

        avisos = check_shot_invariants(eventos)

        assert avisos == []

    def test_un_solo_evento_sin_el_dato_tambien_degrada(self):
        eventos = [
            {
                "drone_id": 0,
                "distancia": 100.0,
                "angulo_offset": 0.0,
                "probabilidad": 0.5,
                "neutralizado": False,
                "factor_acoplamiento": 0.9,
            },
            {
                "drone_id": 1,
                "distancia": 150.0,
                "angulo_offset": 0.0,
                "probabilidad": 0.7,
                "neutralizado": False,
                # sin factor_acoplamiento
            },
        ]

        avisos = check_shot_invariants(eventos)

        assert avisos == []


class TestFactorAcoplamientoEnEventosDeImpacto:
    """Verifica que HPMWeapon.disparar() y HPMissile.detonar() de verdad
    incluyen el dato que check_shot_invariants necesita — sin esto, el
    arreglo de arriba nunca se activaría con eventos reales."""

    def test_hpmweapon_disparar_incluye_factor_acoplamiento(self):
        weapon = HPMWeapon(apertura_cono=360.0)
        drone = Drone(
            0, x=50.0, y=0.0, z=weapon.origen_z,
            cable_length_m=0.05, polarization=0.8,
        )

        eventos = weapon.disparar([drone])

        assert len(eventos) == 1
        assert eventos[0]["factor_acoplamiento"] == pytest.approx(
            drone.factor_acoplamiento(), abs=1e-4
        )

    def test_hpmissile_detonar_incluye_factor_acoplamiento(self):
        misil = HPMissile(x=0, y=0, angulo=0, potencia_hpm=50, radio_efecto=200)
        drone = Drone(0, x=50.0, y=0.0, cable_length_m=0.05, polarization=0.8)

        eventos = misil.detonar([drone])

        assert len(eventos) == 1
        assert eventos[0]["factor_acoplamiento"] == pytest.approx(
            drone.factor_acoplamiento(), abs=1e-4
        )
