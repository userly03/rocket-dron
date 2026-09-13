"""Pruebas de upset vs damage + fallo latente (P2-D).

Reemplaza la premisa cortada de P3-09 (thermal runaway de batería — falla
el presupuesto energético por ~10⁹, ver docs/AUDITORIA_CHECKLIST.md §3.6) con
el mecanismo correcto: la literatura de vulnerabilidad EMI separa UPSET
(recuperable) de DAMAGE (permanente), y una exposición sub-letal significativa
deja una tasa de riesgo (hazard rate) que decae — la mayoría de los drones se
recuperan, algunos maduran en una neutralización DIFERIDA, atribuida al
disparo/detonación original.

⚠ Ninguno de estos tests depende de valores absolutos de probabilidad de
neutralización sin fijar la huella de susceptibilidad del dron
(``cable_length_m``/``polarization``): dos drones con huellas sorteadas
distintas NO son comparables entre sí — el factor de acoplamiento varía más
que los efectos que se quieren medir acá. Fue exactamente lo que hizo que
``test_dron_blindado_resiste_mas_que_estandar`` fallara en 3 de 5 semillas
antes de P1-F. Todos los drones de este archivo fijan cable/polarización a
un valor conocido.
"""

from __future__ import annotations

import math

import pytest

from src.config import (
    DRONE_RIESGO_LATENTE_DECAY_TAU_S,
    DRONE_RIESGO_LATENTE_MAX_POR_S,
    HPM_LOGLOGISTIC_B,
    HPM_LOGLOGISTIC_E50_V_M,
    HPM_MISSILE_LOGLOGISTIC_B,
    HPM_MISSILE_LOGLOGISTIC_E50_V_M,
    HPM_SUBSISTEMAS,
    HPM_UPSET_DB_GAP_FIELD,
)
from src.engine.analytics import PhysicsAnalytics
from src.engine.hpm_engine import (
    calculate_area_neutralization_probability_friis as pf_area,
    calculate_neutralization_probability_friis as pf,
    e50_upset_desde_damage,
    energia_absorbida_j,
)
from src.engine.simulation import SimulationEngine
from src.models.drone import Drone, EstadoSalud
from src.models.swarm import Swarm
from src.utils.reproducibilidad import nuevo_generador, seed_simulacion

# Cableado resonante a 2.45 GHz + polarización óptima ⇒ factor de acoplamiento
# exactamente 1: aísla los efectos de P2-D de la huella de susceptibilidad de
# P2-04, que de lo contrario introduciría una segunda fuente de variación no
# controlada (ver la advertencia del docstring del módulo).
_CABLE_RESONANTE_M = 0.0612
_POLARIZACION_OPTIMA = 1.0


def _drone(drone_id: int = 0, x: float = 0.0, y: float = 0.0, rng=None) -> Drone:
    return Drone(
        drone_id, x=x, y=y,
        cable_length_m=_CABLE_RESONANTE_M, polarization=_POLARIZACION_OPTIMA,
        rng=rng,
    )


class TestUmbralDeUpset:
    """El umbral de upset, derivado del de daño ya calibrado."""

    def test_e50_upset_es_e50_damage_sobre_el_factor_declarado(self):
        factor = 10.0 ** (HPM_UPSET_DB_GAP_FIELD / 20.0)
        assert e50_upset_desde_damage(HPM_LOGLOGISTIC_E50_V_M) == pytest.approx(
            HPM_LOGLOGISTIC_E50_V_M / factor
        )
        assert factor == pytest.approx(3.1623, abs=0.001)

    def test_e50_upset_menor_que_e50_damage(self):
        assert e50_upset_desde_damage(HPM_LOGLOGISTIC_E50_V_M) < HPM_LOGLOGISTIC_E50_V_M
        assert e50_upset_desde_damage(HPM_MISSILE_LOGLOGISTIC_E50_V_M) < HPM_MISSILE_LOGLOGISTIC_E50_V_M

    @pytest.mark.parametrize("distancia", [10.0, 20.0, 30.0, 50.0, 80.0])
    def test_p_upset_nunca_menor_que_p_damage_al_mismo_campo(self, distancia):
        """Garantía matemática (log-logística monótona en E₅₀), no un
        invariante que dependa de los valores numéricos concretos.
        """
        e50u = e50_upset_desde_damage(HPM_LOGLOGISTIC_E50_V_M)
        p_damage = pf(25.0, distancia, 15.0, 0.0)
        p_upset = pf(25.0, distancia, 15.0, 0.0, e50=e50u, b=HPM_LOGLOGISTIC_B)
        assert p_upset >= p_damage

    def test_zona_de_upset_tiene_ancho_positivo_en_rango_de_combate(self):
        """A distancias donde el cañón es parcialmente efectivo, la zona
        [p_damage, p_upset) no es degenerada — si lo fuera, P2-D nunca
        tendría efecto observable.
        """
        e50u = e50_upset_desde_damage(HPM_LOGLOGISTIC_E50_V_M)
        for r in (20.0, 30.0, 40.0, 60.0):
            p_damage = pf(25.0, r, 15.0, 0.0)
            p_upset = pf(25.0, r, 15.0, 0.0, e50=e50u, b=HPM_LOGLOGISTIC_B)
            assert (p_upset - p_damage) > 0.05, f"zona degenerada a {r} m"

    def test_umbral_del_misil_tambien_definido(self):
        e50u = e50_upset_desde_damage(HPM_MISSILE_LOGLOGISTIC_E50_V_M)
        p_damage = pf_area(50.0, 60.0)
        p_upset = pf_area(50.0, 60.0, e50=e50u, b=HPM_MISSILE_LOGLOGISTIC_B)
        assert p_upset >= p_damage


class TestEntrarEnRiesgoLatente:
    """El punto de entrada compartido cañón/misil."""

    def test_severidad_maxima_da_el_hazard_maximo(self):
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=1.0, distancia_m=30.0)
        assert d.riesgo_latente_por_s == pytest.approx(DRONE_RIESGO_LATENTE_MAX_POR_S)

    def test_severidad_nula_da_hazard_nulo(self):
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=0.0, distancia_m=30.0)
        assert d.riesgo_latente_por_s == 0.0

    def test_severidad_fuera_de_rango_se_recorta(self):
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=5.0, distancia_m=30.0)
        assert d.riesgo_latente_por_s == pytest.approx(DRONE_RIESGO_LATENTE_MAX_POR_S)
        d2 = _drone(1)
        d2.entrar_en_riesgo_latente(severidad=-3.0, distancia_m=30.0)
        assert d2.riesgo_latente_por_s == 0.0

    def test_estado_salud_pasa_a_danado(self):
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=0.5, distancia_m=30.0)
        assert d.estado_salud == EstadoSalud.DANADO

    def test_subsistema_afectado_es_uno_de_los_cinco_publicados(self):
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=0.5, distancia_m=30.0)
        assert d.subsistema_en_riesgo in HPM_SUBSISTEMAS

    def test_origen_shot_id_queda_pendiente_hasta_atribucion_externa(self):
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=0.5, distancia_m=30.0)
        assert d.origen_riesgo_shot_id is None
        assert d.origen_riesgo_distancia_m == 30.0

    def test_subsistema_mas_debil_es_el_mas_probable(self):
        """Sorteo ponderado 1/E₅₀: el GPS/GNSS LNA (E₅₀=150, el más bajo de
        la Tabla 1) debe ser el más frecuente entre 2000 sorteos.
        """
        conteos: dict[str, int] = {}
        for i in range(2000):
            gen = nuevo_generador(30_000 + i)
            d = _drone(rng=gen)
            d.entrar_en_riesgo_latente(severidad=0.5, distancia_m=30.0)
            conteos[d.subsistema_en_riesgo] = conteos.get(d.subsistema_en_riesgo, 0) + 1
        assert max(conteos, key=conteos.get) == "gps_gnss_lna"


class TestRecuperacionYFalloConRelojControlado:
    """La propiedad central de P2-D: con reloj controlado, un dron con
    upset recupera (usualmente) y uno con damage no (nunca).
    """

    def test_dron_neutralizado_por_damage_inmediato_nunca_se_recupera(self):
        """DAMAGE es terminal: ``actualizar_riesgo_latente`` no revive a un
        dron neutralizado, sin importar cuántos ticks pasen.
        """
        d = _drone()
        d.estado_salud = EstadoSalud.NEUTRALIZADO
        d.riesgo_latente_por_s = 5.0  # valor absurdo a propósito: NO debe importar
        for _ in range(50):
            murio = d.actualizar_riesgo_latente(1.0)
            assert murio is False
            assert d.estado_salud == EstadoSalud.NEUTRALIZADO

    def test_severidad_baja_se_recupera_con_reloj_controlado(self):
        """Severidad muy baja (roce mínimo con la zona de upset): tras 100 s
        (25× la constante de decaimiento) el hazard decayó por debajo del
        umbral y el dron volvió a ACTIVO — determinista para severidad tan
        baja, no hace falta estadística.
        """
        d = _drone()
        d.entrar_en_riesgo_latente(severidad=0.02, distancia_m=30.0)
        for _ in range(200):
            d.actualizar_riesgo_latente(0.5)  # 200×0.5s = 100 s
        assert d.estado_salud == EstadoSalud.ACTIVO
        assert d.riesgo_latente_por_s == 0.0
        assert d.subsistema_en_riesgo is None
        assert d.salud == 100.0

    def test_probabilidad_de_falla_eventual_coincide_con_formula_cerrada(self):
        """P(falla alguna vez) = 1 − exp(−h₀·τ) para un hazard que decae
        exponencialmente. Verificado empíricamente, no solo declarado.
        """
        n = 1500

        def prob_empirica(severidad: float) -> float:
            muertes = 0
            for i in range(n):
                gen = nuevo_generador(40_000 + i)
                d = _drone(rng=gen)
                d.entrar_en_riesgo_latente(severidad=severidad, distancia_m=30.0)
                for _ in range(600):  # 600×0.2s = 120 s ≫ 30·τ
                    if d.actualizar_riesgo_latente(0.2):
                        muertes += 1
                        break
                    if d.riesgo_latente_por_s <= 0.0:
                        break
            return muertes / n

        for severidad in (0.3, 1.0):
            h0 = severidad * DRONE_RIESGO_LATENTE_MAX_POR_S
            p_teorica = 1.0 - math.exp(-h0 * DRONE_RIESGO_LATENTE_DECAY_TAU_S)
            p_empirica = prob_empirica(severidad)
            assert p_empirica == pytest.approx(p_teorica, abs=0.05), (
                f"severidad={severidad}: teórica={p_teorica:.3f} empírica={p_empirica:.3f}"
            )

    def test_severidad_maxima_es_un_lanzamiento_de_moneda_no_certeza(self):
        """Confirma la elección de diseño declarada en config.py: en el PEOR
        punto de la zona de upset, la mitad se recupera y la mitad no —
        NO es determinista en ninguna dirección.
        """
        n = 800
        muertes = 0
        for i in range(n):
            gen = nuevo_generador(50_000 + i)
            d = _drone(rng=gen)
            d.entrar_en_riesgo_latente(severidad=1.0, distancia_m=30.0)
            for _ in range(600):
                if d.actualizar_riesgo_latente(0.2):
                    muertes += 1
                    break
                if d.riesgo_latente_por_s <= 0.0:
                    break
        fraccion = muertes / n
        assert 0.35 < fraccion < 0.65, f"esperado ~0.5, medido {fraccion}"

    def test_dt_cero_o_riesgo_cero_no_hace_nada(self):
        d = _drone()
        assert d.actualizar_riesgo_latente(0.0) is False
        d.entrar_en_riesgo_latente(0.5, 30.0)
        h_antes = d.riesgo_latente_por_s
        d.actualizar_riesgo_latente(0.0)
        assert d.riesgo_latente_por_s == h_antes  # dt=0 no decae ni mata


class TestEnergiaAbsorbida:
    """Reemplazo de ``dano = probabilidad·potencia·0.5`` por unidades reales."""

    def test_formula_cerrada(self):
        """Contraste directo contra S_promedio·A_efectiva·duración."""
        from src.engine.hpm_engine import friis_diagnostics

        potencia, distancia, apertura, offset, duty, duracion = 25.0, 30.0, 15.0, 0.0, 1.0, 0.5
        diag = friis_diagnostics(potencia, distancia, apertura, offset, duty_cycle=duty)
        esperado = diag["densidad_potencia_w_m2"] * duty * (_CABLE_RESONANTE_M ** 2) * duracion
        medido = energia_absorbida_j(
            potencia, distancia, apertura, offset, duty, _CABLE_RESONANTE_M, duracion
        )
        assert medido == pytest.approx(esperado)

    def test_positiva_y_finita(self):
        e = energia_absorbida_j(25.0, 30.0, 15.0, 0.0, 1.0, _CABLE_RESONANTE_M, 0.5)
        assert 0.0 < e < float("inf")

    def test_escala_con_el_cuadrado_de_la_longitud_de_cable(self):
        """A_efectiva = cable_length_m²: duplicar el cable cuadruplica la energía."""
        e1 = energia_absorbida_j(25.0, 30.0, 15.0, 0.0, 1.0, 0.05, 0.5)
        e2 = energia_absorbida_j(25.0, 30.0, 15.0, 0.0, 1.0, 0.10, 0.5)
        assert e2 / e1 == pytest.approx(4.0, rel=1e-6)

    def test_escala_linealmente_con_la_duracion(self):
        e1 = energia_absorbida_j(25.0, 30.0, 15.0, 0.0, 1.0, _CABLE_RESONANTE_M, 0.5)
        e2 = energia_absorbida_j(25.0, 30.0, 15.0, 0.0, 1.0, _CABLE_RESONANTE_M, 1.0)
        assert e2 / e1 == pytest.approx(2.0, rel=1e-6)

    def test_decrece_con_la_distancia(self):
        e_cerca = energia_absorbida_j(25.0, 20.0, 15.0, 0.0, 1.0, _CABLE_RESONANTE_M, 0.5)
        e_lejos = energia_absorbida_j(25.0, 80.0, 15.0, 0.0, 1.0, _CABLE_RESONANTE_M, 0.5)
        assert e_cerca > e_lejos

    def test_acumula_en_el_dron_entre_exposiciones(self):
        """Dos exposiciones idénticas seguidas: la energía acumulada es el
        doble (si el dron no murió/no cambió de estado entre medio).
        """
        seed_simulacion(777)
        d = _drone()
        assert d.energia_absorbida_j == 0.0
        # Potencia baja + distancia grande para minimizar la chance de que
        # el dron muera o entre en upset y así poder comparar la energía
        # limpiamente entre dos llamadas idénticas.
        d.recibir_daño(potencia=1.0, distancia=500.0, angulo_offset=0.0, apertura_cono=15.0)
        primera = d.energia_absorbida_j
        assert primera > 0.0
        if d.estado_salud != EstadoSalud.NEUTRALIZADO:
            d.recibir_daño(potencia=1.0, distancia=500.0, angulo_offset=0.0, apertura_cono=15.0)
            assert d.energia_absorbida_j == pytest.approx(2 * primera)

    def test_modelo_legacy_no_toca_energia_absorbida(self, monkeypatch):
        """El camino ad-hoc (HPM_MODEL='legacy') conserva su aritmética
        original — P2-D solo reemplaza la rama 'friis'. Monkeypatch sobre el
        NOMBRE importado en drone.py, no sobre config: HPM_MODEL se importa
        como valor al cargar el módulo, así que parchear config.HPM_MODEL no
        tendría ningún efecto (la misma trampa que P1-D/P1-F destaparon).
        """
        monkeypatch.setattr("src.models.drone.HPM_MODEL", "legacy")
        d = _drone()
        d.recibir_daño(potencia=25.0, distancia=30.0, angulo_offset=0.0, apertura_cono=15.0)
        assert d.energia_absorbida_j == 0.0
        assert d.riesgo_latente_por_s == 0.0


class TestComportamientoDegradado:
    """Qué subsistema afecta qué — comportamiento, no solo diagnóstico."""

    def test_flight_controller_en_upset_congela_el_rumbo(self):
        """Con el flight controller en upset, el dron NO adopta el rumbo que
        compute_headings le asignaría — a diferencia de un vecino sin upset
        en el mismo enjambre, que sí lo adopta.

        Se construye el escenario en dos pasos para que el test sea
        falsable de verdad: primero se comprueba que ``compute_headings``
        REALMENTE propone un cambio de rumbo (si no lo hiciera, "el ángulo
        no cambió" no probaría nada); luego se comprueba que
        ``Swarm.actualizar`` no lo aplica al dron en upset, pero sí a un
        vecino sin upset en la misma formación.
        """
        from src.engine.flocking import compute_headings

        swarm = Swarm()
        swarm.inicializar_formacion("cuadrada", 4)
        for i, d in enumerate(swarm.drones):
            d.angulo = 0.0 if i % 2 == 0 else 180.0

        objetivo = swarm.drones[0]
        control = swarm.drones[1]

        propuestos = compute_headings(swarm.drones, dt=0.5, home_x=swarm.centro_x, home_y=swarm.centro_y)
        assert propuestos[objetivo.id] != pytest.approx(objetivo.angulo), (
            "el escenario no genera un cambio de rumbo real; ajustar el setup"
        )

        objetivo.subsistema_en_riesgo = "flight_controller"
        objetivo.riesgo_latente_por_s = 0.05
        angulo_objetivo_antes = objetivo.angulo
        angulo_control_antes = control.angulo

        swarm.actualizar(dt=0.5)

        assert objetivo.angulo == pytest.approx(angulo_objetivo_antes), (
            "el dron en upset de flight_controller NO debe adoptar el rumbo nuevo"
        )
        assert control.angulo != pytest.approx(angulo_control_antes), (
            "el vecino SIN upset sí debe adoptar el rumbo de boids (control)"
        )

    def test_gps_en_upset_degrada_rth_a_mantener_rumbo(self):
        from src.models.drone import EstadoEnlace, PerfilLostLink

        d = _drone(x=600.0, y=500.0)
        d.perfil_lost_link = PerfilLostLink.RTH
        d.estado_enlace = EstadoEnlace.INTERFERIDO
        d.subsistema_en_riesgo = "gps_gnss_lna"
        d.angulo = 90.0

        d.mover(0.5, home_x=500.0, home_y=500.0)

        # Sin GPS no puede calcular el rumbo hacia home: el ángulo no debe
        # haber girado hacia el centro (que estaría en ~180°, no en 90°).
        assert d.angulo == pytest.approx(90.0)

    def test_sin_gps_en_upset_rth_si_gira_hacia_home(self):
        """Control del test anterior: SIN el upset de GPS, el mismo
        escenario sí gira hacia home — confirma que la degradación tiene
        efecto real, no que RTH esté roto en general.
        """
        from src.models.drone import EstadoEnlace, PerfilLostLink

        d = _drone(x=600.0, y=500.0)
        d.perfil_lost_link = PerfilLostLink.RTH
        d.estado_enlace = EstadoEnlace.INTERFERIDO
        d.angulo = 90.0

        d.mover(0.5, home_x=500.0, home_y=500.0)

        assert d.angulo != pytest.approx(90.0)


class TestAtribucionDeBajaDiferida:
    """La maquinaria conservada de P3-09: la baja diferida se atribuye al
    disparo original en la curva de efectividad, no se pierde sin registrar.
    """

    def test_baja_diferida_se_atribuye_al_shot_id_original(self):
        gen = nuevo_generador(9001)
        sim = SimulationEngine(swarm_size=1, rng=gen)
        sim.swarm.inicializar_formacion("cuadrada", 1)
        drone = sim.swarm.drones[0]
        drone.x, drone.y, drone.z = sim.hpm.origen_x, sim.hpm.origen_y, sim.hpm.origen_z
        drone.cable_length_m = _CABLE_RESONANTE_M
        drone.polarization = _POLARIZACION_OPTIMA

        resultado = sim.fire(potencia=1e-6, direccion=0.0, apertura_cono=179.0)
        shot_id = resultado["hpm"] and sim.analytics.shot_history[-1]["id"]
        assert shot_id is not None

        # Fuerza la entrada en riesgo latente y un hazard grande para que la
        # muerte sea casi segura en pocos ticks — la ATRIBUCIÓN es lo que se
        # prueba acá, no la estadística de supervivencia (ya cubierta en
        # TestRecuperacionYFalloConRelojControlado).
        drone.entrar_en_riesgo_latente(severidad=1.0, distancia_m=42.0)
        sim._atribuir_riesgo_latente(
            [{"drone_id": drone.id, "entro_en_riesgo": True}], shot_id
        )
        assert drone.origen_riesgo_shot_id == shot_id
        drone.riesgo_latente_por_s = 100.0  # garantiza la muerte en el próximo tick

        intentos_antes = sum(v["intentos"] for v in sim.analytics.distance_stats.values())
        neutralizados_antes = sim.analytics.shot_history[-1]["neutralizados"]

        murio = False
        for _ in range(10):
            sim._tick(0.1)
            if drone.estado_salud == EstadoSalud.NEUTRALIZADO:
                murio = True
                break
        assert murio, "el dron no murió con hazard=100/s en 10 ticks — revisar el test"

        entry = next(s for s in sim.analytics.shot_history if s["id"] == shot_id)
        assert entry["neutralizados"] == neutralizados_antes + 1
        assert entry["bajas_diferidas"] == 1

        intentos_despues = sum(v["intentos"] for v in sim.analytics.distance_stats.values())
        assert intentos_despues == intentos_antes, "no debe duplicar el conteo de intentos"

    def test_shot_id_fuera_de_ventana_no_rompe(self):
        """Un shot_id que ya no existe en shot_history (ventana vieja) no
        lanza excepción — record_delayed_kill devuelve False.
        """
        analytics = PhysicsAnalytics()
        assert analytics.record_delayed_kill(shot_id=99999, distancia=30.0) is False

    def test_record_delayed_kill_no_crea_entrada_nueva(self):
        analytics = PhysicsAnalytics()
        entry = analytics.record_cannon_shot(25.0, 0.0, [], 0.0, 0.0, 0.0)
        n_antes = len(analytics.shot_history)
        analytics.record_delayed_kill(entry["id"], distancia=None)
        assert len(analytics.shot_history) == n_antes


class TestPanelUpsetDamage:
    def test_swarm_reporta_fracciones(self):
        swarm = Swarm()
        swarm.inicializar_formacion("cuadrada", 10)
        swarm.drones[0].entrar_en_riesgo_latente(0.5, 30.0)
        swarm.drones[1].estado_salud = EstadoSalud.NEUTRALIZADO

        stats = swarm.contar_upset_damage()
        assert stats["total"] == 10
        assert stats["en_riesgo_upset"] == 1
        assert stats["danados_permanente"] == 1
        assert stats["intactos"] == 8

    def test_panel_fisico_expone_upset_damage_cuando_se_pasa(self):
        analytics = PhysicsAnalytics()
        swarm = Swarm()
        swarm.inicializar_formacion("cuadrada", 5)
        swarm.drones[0].entrar_en_riesgo_latente(0.5, 30.0)

        panel = analytics.get_physics_panel(25.0, hpm={}, upset_damage=swarm.contar_upset_damage())
        assert "upset_damage" in panel
        assert panel["upset_damage"]["en_riesgo_upset"] == 1

    def test_panel_no_reintroduce_campos_gaussianos(self):
        """P0-C sigue vigente: el panel no debe volver a exponer coupling_k
        ni probabilidad_referencia al añadir upset_damage.
        """
        analytics = PhysicsAnalytics()
        panel = analytics.get_physics_panel(25.0)
        assert "coupling_k" not in panel
        assert "probabilidad_referencia" not in panel


class TestDeterminismo:
    def test_secuencia_de_fallos_reproducible_con_mismo_generador(self):
        def simular(seed: int) -> list[bool]:
            gen = nuevo_generador(seed)
            d = _drone(rng=gen)
            d.entrar_en_riesgo_latente(0.6, 30.0)
            resultado = []
            for _ in range(50):
                murio = d.actualizar_riesgo_latente(0.2)
                resultado.append(murio)
                if murio or d.riesgo_latente_por_s <= 0.0:
                    break
            return resultado

        assert simular(4242) == simular(4242)
