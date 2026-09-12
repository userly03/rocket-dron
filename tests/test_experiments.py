"""Pruebas del runner de experimentos Monte Carlo y del step síncrono."""

import json
import math
import time

import pytest
from fastapi.testclient import TestClient

from src.engine.experiments import (
    ExperimentConfig,
    ExperimentManager,
    WeaponPolicy,
    Z_95,
    intervalo_bootstrap,
    intervalo_t,
    run_replica,
    _T_975,
    t_critico_975,
    wilson_interval,
)
from src.engine.hpm_engine import (
    apply_hardening_odds,
    calculate_neutralization_probability_friis,
    target_angle_from_origin,
)
from src.engine.simulation import SimulationEngine
from src.utils.helpers import distance3d
from src.utils.reproducibilidad import nuevo_generador, seed_simulacion


class TestWilsonInterval:
    def test_intervalo_valores_conocidos(self):
        # k=50/100 con z=1.95996 → (≈0.4040, ≈0.5963)
        lo, hi = wilson_interval(50, 100)
        assert lo == pytest.approx(0.4040, abs=0.001)
        assert hi == pytest.approx(0.5963, abs=0.001)

    def test_proporcion_extrema_no_se_sale_de_0_1(self):
        lo, hi = wilson_interval(0, 500)
        assert 0.0 <= lo <= hi <= 1.0
        lo, hi = wilson_interval(500, 500)
        assert 0.0 <= lo <= hi <= 1.0

    def test_n_cero_devuelve_cero(self):
        assert wilson_interval(0, 0) == (0.0, 0.0)


class TestTickSincrono:
    def test_tick_avanza_sin_hilo(self):
        sim = SimulationEngine(swarm_size=3)
        dt = 1.0 / 30.0
        for _ in range(30):
            sim._tick(dt)
        assert sim.tiempo == pytest.approx(1.0, abs=1e-6)
        assert sim.tick == 30
        # Nunca arrancó el hilo del bucle.
        assert sim._thread is None or not sim._thread.is_alive()

    def test_tick_pausado_no_mueve_enjambre(self):
        sim = SimulationEngine(swarm_size=3)
        x0 = [d.x for d in sim.swarm.drones]
        y0 = [d.y for d in sim.swarm.drones]
        sim._tick(1.0 / 30.0, mover_enjambre=False)
        assert [d.x for d in sim.swarm.drones] == x0
        assert [d.y for d in sim.swarm.drones] == y0
        assert sim.tiempo == pytest.approx(1.0 / 30.0)

    def test_tick_mueve_enjambre(self):
        sim = SimulationEngine(swarm_size=3)
        pos0 = [(d.x, d.y) for d in sim.swarm.drones]
        sim._tick(1.0 / 30.0)
        pos1 = [(d.x, d.y) for d in sim.swarm.drones]
        assert pos1 != pos0


class TestReplica:
    def test_replica_deterministica(self):
        cfg = ExperimentConfig(
            formacion="cuadrada",
            cantidad=10,
            replicas=2,
            t_max_s=2.0,
            semilla=99,
            arma=WeaponPolicy(tipo="canion", delay_s=0.5, potencia=80, direccion=45),
        )
        r1 = run_replica(cfg, 0)
        r2 = run_replica(cfg, 0)
        assert r1 == r2
        assert r1["neutralizados"] <= r1["total"]

    def test_ic_contiene_probabilidad_teorica(self, monkeypatch):
        """
        Caso de referencia con probabilidad teórica exacta: formación circular
        de 1 dron queda fijo en (700, 500, 40) (anillo i=0, capa z=0). El cañón
        dispara al azimut exacto (offset 0) desde el origen. La probabilidad
        teórica mezcla el 80/20 estándar/blindado del enjambre. Con N grande,
        la tasa empírica debe caer dentro del IC95% de Wilson — valida a la
        vez el generador aleatorio y el modelo de daño.
        """
        # Forzar huella de susceptibilidad resonante (acoplamiento = 1) para
        # que la probabilidad teórica de abajo sea exacta; sin esto, el
        # sorteo de cableado/polarización del dron introduciría un factor
        # que la fórmula teórica no contempla.
        cable_res = 299_792_458.0 / (2 * 2.45e9)
        monkeypatch.setattr("src.models.drone.DRONE_CABLE_LENGTH_MIN_M", cable_res)
        monkeypatch.setattr("src.models.drone.DRONE_CABLE_LENGTH_MAX_M", cable_res)
        monkeypatch.setattr("src.models.drone.DRONE_POLARIZATION_MIN", 1.0)

        dist = distance3d(0, 0, 8, 700, 500, 40)
        bearing = target_angle_from_origin(0, 0, 700, 500)
        p_std = calculate_neutralization_probability_friis(50, dist, 15.0, 0.0)
        p_mix = 0.8 * p_std + 0.2 * apply_hardening_odds(p_std, 2.5)

        n = 400
        kills = 0
        for i in range(n):
            seed_simulacion(5000 + i)
            sim = SimulationEngine(swarm_size=1)
            sim.configure_swarm("circular", 1)
            eventos = sim.fire(potencia=50, direccion=bearing)["eventos"]
            kills += sum(1 for e in eventos if e["neutralizado"])

        lo, hi = wilson_interval(kills, n)
        assert lo <= p_mix <= hi, (
            f"IC95% ({lo:.4f}, {hi:.4f}) no contiene la probabilidad teórica "
            f"{p_mix:.4f} (empírica {kills}/{n})"
        )


class TestExperimentManager:
    def _esperar(self, mgr: ExperimentManager, exp_id: str, timeout_s: float = 30.0) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            registro = mgr.get(exp_id)
            if registro["status"] in ("completado", "error"):
                return registro
            time.sleep(0.05)
        raise AssertionError("experimento no terminó a tiempo")

    def test_manager_completa_y_resume(self):
        mgr = ExperimentManager()
        cfg = ExperimentConfig(
            formacion="cuadrada",
            cantidad=8,
            replicas=6,
            t_max_s=4.0,
            semilla=7,
            arma=WeaponPolicy(tipo="canion", delay_s=0.5, potencia=100, direccion=45),
        )
        exp_id = mgr.start(cfg)
        registro = self._esperar(mgr, exp_id)

        assert registro["status"] == "completado"
        resumen = registro["resumen"]
        assert resumen["replicas"] == 6
        # MODIFICADO en P1-A: la métrica primaria pasó de ``p_hat``
        # (P(aniquilación total), que vale 0 en casi todo el espacio de
        # operación) a ``fraccion_media`` con IC por bootstrap sobre réplicas.
        # El test viejo verificaba la coherencia de un estimador ciego; ahora
        # verifica la del que sí mide. La capacidad vieja no se perdió: sigue
        # en ``aniquilacion_total``, y se verifica abajo.
        assert 0.0 <= resumen["fraccion_media"] <= 1.0
        lo, hi = resumen["ic95_bootstrap"]
        assert lo <= resumen["fraccion_media"] <= hi
        t_lo, t_hi = resumen["ic95_t"]
        assert t_lo <= resumen["fraccion_media"] <= t_hi

        aniq = resumen["aniquilacion_total"]
        assert 0.0 <= aniq["proporcion"] <= 1.0
        a_lo, a_hi = aniq["ic95_wilson"]
        assert a_lo <= aniq["proporcion"] <= a_hi
        assert len(resumen["convergencia"]) == 6
        assert registro["manifest"]["config"]["HPM_MODEL"] == "friis"

    def test_manager_con_misil(self):
        mgr = ExperimentManager()
        cfg = ExperimentConfig(
            formacion="circular",
            cantidad=6,
            replicas=4,
            t_max_s=10.0,
            semilla=11,
            arma=WeaponPolicy(tipo="misil", delay_s=0.5, misil_potencia=100, misil_radio=150),
        )
        exp_id = mgr.start(cfg)
        registro = self._esperar(mgr, exp_id)
        assert registro["status"] == "completado"
        assert registro["resumen"]["replicas"] == 4

    def test_get_desconocido_devuelve_none(self):
        mgr = ExperimentManager()
        assert mgr.get("exp-inexistente") is None


class TestExperimentRoutes:
    def test_endpoint_flujo_completo(self):
        from src.main import app

        with TestClient(app) as client:
            resp = client.post(
                "/api/experiments",
                json={
                    "formacion": "cuadrada",
                    "cantidad": 6,
                    "replicas": 4,
                    "t_max_s": 3.0,
                    "semilla": 5,
                    "arma_tipo": "canion",
                    "arma_delay_s": 0.5,
                    "potencia": 100,
                    "direccion": 45,
                },
            )
            assert resp.status_code == 200
            exp_id = resp.json()["experiment_id"]

            t0 = time.time()
            while time.time() - t0 < 30.0:
                registro = client.get(f"/api/experiments/{exp_id}").json()
                if registro["status"] == "completado":
                    break
                time.sleep(0.05)
            assert registro["status"] == "completado"
            # MODIFICADO en P1-A: la clave ``ic95`` (Wilson sobre
            # aniquilación total) dejó de ser la métrica primaria. Se verifica
            # que viajen por la API las tres: el IC primario, su contraste por
            # t, y el secundario de aniquilación.
            assert "ic95_bootstrap" in registro["resumen"]
            assert "ic95_t" in registro["resumen"]
            assert "ic95_wilson" in registro["resumen"]["aniquilacion_total"]
            assert "cv" in registro["resumen"]

            lista = client.get("/api/experiments").json()
            assert any(e["id"] == exp_id for e in lista["experimentos"])

            assert client.get("/api/experiments/exp-nope").status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# P1-A · Estimador con señal: la réplica es la unidad de muestreo
# ═══════════════════════════════════════════════════════════════════════════

class TestIntervaloBootstrap:
    """El bootstrap de percentiles sobre fracciones de réplica."""

    def test_determinista(self):
        """Mismos datos ⇒ mismo intervalo. Un IC que varía no es reportable."""
        datos = [0.0, 0.1, 0.2, 0.05, 0.3, 0.0, 0.15]
        assert intervalo_bootstrap(datos) == intervalo_bootstrap(datos)

    def test_contenido_en_0_1_y_contiene_la_media(self):
        datos = [0.0, 0.1, 0.2, 0.05, 0.3, 0.0, 0.15]
        lo, hi = intervalo_bootstrap(datos)
        media = sum(datos) / len(datos)
        assert 0.0 <= lo <= media <= hi <= 1.0

    def test_se_estrecha_al_aumentar_replicas(self):
        """Más réplicas ⇒ IC más estrecho. Es la propiedad que justifica correr N grande.

        Se usa el mismo proceso generador (Bernoulli(0.3) por dron, 20 drones
        por réplica) con distinto número de réplicas.
        """
        gen = nuevo_generador(4242)
        pocas = [float(gen.binomial(20, 0.3) / 20) for _ in range(8)]
        muchas = [float(gen.binomial(20, 0.3) / 20) for _ in range(200)]
        lo_p, hi_p = intervalo_bootstrap(pocas)
        lo_m, hi_m = intervalo_bootstrap(muchas)
        assert (hi_m - lo_m) < (hi_p - lo_p)

    def test_cubre_la_verdad_conocida(self):
        """VERDAD CONOCIDA: con drones Bernoulli(p) iid, la fracción esperada es p.

        Éste es el criterio de "done" del ítem P1-A. El ground truth es
        analítico y no depende del motor físico: si cada uno de los ``m``
        drones de una réplica cae con probabilidad ``p`` de forma
        independiente, la fracción neutralizada de la réplica tiene
        esperanza exactamente ``p``. Se generan réplicas de ese proceso y se
        verifica que el IC del 95% contiene ``p``.

        Con 60 réplicas y 25 drones el IC es estrecho (~±0.03), así que el
        test SÍ puede fallar: si el bootstrap estuviera mal centrado o mal
        escalado, p quedaría fuera.
        """
        p_verdadero = 0.35
        gen = nuevo_generador(31415)
        fracciones = [float(gen.binomial(25, p_verdadero) / 25) for _ in range(60)]
        lo, hi = intervalo_bootstrap(fracciones)
        assert lo <= p_verdadero <= hi, f"IC=[{lo}, {hi}] no contiene p={p_verdadero}"
        # Y el IC es informativo, no trivialmente ancho.
        assert (hi - lo) < 0.15

    def test_caso_degenerado_todas_iguales(self):
        """Todas las réplicas idénticas ⇒ IC colapsa a un punto, sin NaN ni inversión.

        Ocurre de verdad: un arma inefectiva a larga distancia da todas 0.
        El bootstrap debe decir "no hay variabilidad observada", no inventar
        un intervalo.
        """
        for valor in (0.0, 1.0):
            lo, hi = intervalo_bootstrap([valor] * 10)
            assert lo == pytest.approx(valor)
            assert hi == pytest.approx(valor)
            assert lo <= hi

    def test_una_sola_observacion(self):
        lo, hi = intervalo_bootstrap([0.4])
        assert lo == pytest.approx(0.4) and hi == pytest.approx(0.4)

    def test_sin_observaciones(self):
        assert intervalo_bootstrap([]) == (0.0, 0.0)


class TestIntervaloT:
    def test_coincide_con_calculo_a_mano(self):
        """Contraste verificable: media ± t·s/√n con la t tabulada."""
        datos = [0.1, 0.2, 0.3, 0.4, 0.5]
        media = 0.3
        s = (sum((x - media) ** 2 for x in datos) / (len(datos) - 1)) ** 0.5
        semiancho = t_critico_975(5) * s / (5**0.5)
        lo, hi = intervalo_t(datos)
        assert lo == pytest.approx(media - semiancho)
        assert hi == pytest.approx(media + semiancho)

    def test_recortado_a_0_1(self):
        """Un límite fuera de [0,1] no es interpretable como fracción."""
        lo, hi = intervalo_t([0.95, 0.98, 1.0, 0.99, 1.0])
        assert lo >= 0.0 and hi <= 1.0

    def test_df_no_tabulado_usa_el_inferior_y_es_conservador(self):
        """df intermedio ⇒ t del df tabulado inferior (intervalo algo más ancho).

        Equivocarse hacia el lado ancho es el lado correcto en un intervalo de
        confianza. df=31 no está tabulado, así que toma el de df=30.
        """
        assert t_critico_975(32) == pytest.approx(_T_975[30])
        assert t_critico_975(32) > t_critico_975(41)  # más df ⇒ t menor

    def test_convergencia_lenta_de_t_a_la_normal(self):
        """La t converge a la normal LENTO: a df=30 el error es ~4%, no <1%.

        Este test documenta el motivo de que la tabla llegue a df=120 en vez de
        a 30 (un descuido que se corrigió: la primera versión del comentario
        afirmaba "<1% a df=30", que es falso).
        """
        error_df30 = (_T_975[30] - Z_95) / Z_95
        assert error_df30 == pytest.approx(0.042, abs=0.005)
        error_df120 = (_T_975[120] - Z_95) / Z_95
        assert error_df120 < 0.011
        # Por encima de la tabla sí se usa la normal.
        assert t_critico_975(200) == pytest.approx(Z_95)

    def test_una_sola_observacion_no_rompe(self):
        lo, hi = intervalo_t([0.4])
        assert lo == pytest.approx(0.4) and hi == pytest.approx(0.4)


class TestResumenP1A:
    """Coherencia interna del resumen y no-degeneración del estimador."""

    @staticmethod
    def _resultados(fracciones: list[float], drones: int = 30) -> list[dict]:
        """Construye resultados sintéticos de réplica con fracciones dadas."""
        return [
            {
                "replica": i,
                "semilla": 1000 + i,
                "neutralizados": round(f * drones),
                "total": drones,
                "fraccion": f,
                "t_sim": 10.0,
                "exito": f >= 1.0,
            }
            for i, f in enumerate(fracciones)
        ]

    def test_fraccion_media_coincide_con_la_media_de_las_fracciones(self):
        fracciones = [0.0, 0.1, 0.2, 0.3, 0.4]
        s = ExperimentManager._summarize(self._resultados(fracciones))
        assert s["fraccion_media"] == pytest.approx(sum(fracciones) / len(fracciones))
        assert s["fracciones_por_replica"] == pytest.approx(fracciones)

    def test_cv_coincide_con_sigma_sobre_mu(self):
        fracciones = [0.1, 0.2, 0.3, 0.4, 0.5]
        s = ExperimentManager._summarize(self._resultados(fracciones))
        assert s["cv"] == pytest.approx(
            s["desviacion_estandar"] / s["fraccion_media"], rel=1e-3
        )

    def test_cv_es_none_si_la_media_es_cero(self):
        """El CV no está definido con media 0: devolver 0 o inf sería mentir."""
        s = ExperimentManager._summarize(self._resultados([0.0] * 5))
        assert s["cv"] is None

    def test_aniquilacion_total_es_metrica_secundaria_separada(self):
        """La métrica vieja sigue disponible, pero separada y con Wilson."""
        s = ExperimentManager._summarize(self._resultados([0.0, 0.5, 1.0, 1.0]))
        aniq = s["aniquilacion_total"]
        assert aniq["replicas_con_enjambre_aniquilado"] == 2
        assert aniq["proporcion"] == pytest.approx(0.5)
        assert aniq["ic95_wilson"] == pytest.approx(list(wilson_interval(2, 4)), abs=1e-4)
        # Y ya no se publica como si fuera "la" probabilidad de baja.
        assert "p_hat" not in s
        assert "ic95" not in s

    def test_percentiles_ordenados(self):
        s = ExperimentManager._summarize(self._resultados([0.0, 0.1, 0.2, 0.5, 0.9]))
        p = s["percentiles"]
        assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]

    def test_convergencia_sigue_la_metrica_primaria(self):
        """La serie de convergencia es de la fracción media, no de la aniquilación."""
        fracciones = [0.0, 0.2, 0.4, 0.1, 0.3]
        s = ExperimentManager._summarize(self._resultados(fracciones))
        conv = s["convergencia"]
        assert len(conv) == len(fracciones)
        assert "fraccion_media" in conv[0]
        # El último punto de la serie es la media total.
        assert conv[-1]["fraccion_media"] == pytest.approx(s["fraccion_media"], abs=1e-4)

    def test_resumen_serializable_a_json(self):
        """El registro viaja por la API: nada de escalares numpy."""
        s = ExperimentManager._summarize(self._resultados([0.0, 0.1, 0.33]))
        json.dumps(s)  # levanta TypeError si hay np.float64 suelto

    def test_sin_replicas_no_rompe(self):
        assert ExperimentManager._summarize([]) == {"replicas": 0}


class TestEstimadorTieneSenalEnElMotorReal:
    """El estimador mide el efecto en vez de reportar 0 (el defecto de v1).

    Contraste medido contra el comportamiento de v1 con la misma
    configuración por defecto (cañón 25 kW, azimut 45°, enjambre circular a
    ~700 m): v1 daba ``p̂ = 0.0`` con ``IC = [0, 0.3244]`` teniendo 1 baja en
    240 exposiciones. Ver docs/AUDITORIA_CHECKLIST.md §1.2.
    """

    def test_reporta_el_efecto_y_un_ic_mucho_mas_estrecho_que_v1(self):
        """El estimador mide el efecto cuando HAY efecto, con IC estrecho.

        MODIFICADO en P1-F, y el motivo importa. Este test usaba el cañón
        contra el enjambre por defecto (~700 m) y verificaba `bajas > 0`.
        Tras eliminar el piso de la sigmoide, ese escenario da **exactamente
        0 bajas en 12 réplicas** — y ése es el resultado FÍSICAMENTE CORRECTO:
        un cañón de 25 kW con un haz de 15° contra un enjambre a 700 m no hace
        nada. Las bajas que el test veía antes eran el piso del 2.30 % a campo
        cero, no física (ver docs/FISICA_Y_MATEMATICA.md §3.7: a 700 m el
        90.7 % del número reportado era artefacto).

        Así que el escenario pasa al arma que **sí engancha**: el misil, que
        vuela hasta el enjambre y detona a ~80 m. El propósito del test se
        conserva intacto —demostrar que el estimador mide en vez de reportar
        0— sin fabricar señal a partir de un artefacto.
        """
        cfg = ExperimentConfig(
            replicas=10, cantidad=30, t_max_s=20.0,
            arma=WeaponPolicy(tipo="misil", delay_s=1.0),
        )
        resultados = [run_replica(cfg, i) for i in range(cfg.replicas)]
        s = ExperimentManager._summarize(resultados)

        bajas = sum(r["neutralizados"] for r in resultados)
        assert bajas > 0, "el escenario no produjo ninguna baja; test sin contenido"

        # El estimador ya NO reporta 0 cuando hubo bajas — el defecto de v1.
        assert s["fraccion_media"] > 0.0

        # Y el IC es mucho más estrecho que el [0, 0.3244] de Wilson sobre
        # aniquilación total que reportaba v1.
        lo, hi = s["ic95_bootstrap"]
        assert (hi - lo) < 0.10, f"IC demasiado ancho: [{lo}, {hi}]"

        # La métrica vieja sigue siendo 0 acá: se conserva, pero ya no es la
        # que se lee como "probabilidad de baja".
        assert s["aniquilacion_total"]["proporcion"] == 0.0

    def test_el_canion_a_700m_no_hace_nada_y_el_estimador_lo_dice(self):
        """NUEVO en P1-F: el escenario por defecto da 0, y es la respuesta correcta.

        Complemento del test anterior: verifica que el estimador reporta
        **cero** cuando de verdad no hay efecto, en vez del 0.0056 que
        reportaba cuando el piso de la sigmoide inyectaba bajas espurias. Un
        estimador que nunca dice cero no sirve para decidir nada.
        """
        cfg = ExperimentConfig(
            replicas=8, cantidad=30, t_max_s=12.0,
            arma=WeaponPolicy(tipo="canion", delay_s=1.0),
        )
        resultados = [run_replica(cfg, i) for i in range(cfg.replicas)]
        s = ExperimentManager._summarize(resultados)
        assert sum(r["neutralizados"] for r in resultados) == 0
        assert s["fraccion_media"] == 0.0
        assert s["ic95_bootstrap"] == [0.0, 0.0]

    def test_a_quemarropa_contra_verdad_conocida_del_motor(self):
        """VERDAD CONOCIDA a través del motor real, no sintética.

        Construcción: todos los drones a 20 m del cañón, EN EL EJE del haz
        (offset angular 0), a la altitud del cañón, con cableado sintonizado
        a la frecuencia del arma (L = c/2f ⇒ η = 1) y polarización 1.0
        ⇒ factor de acoplamiento exactamente 1. Sin blindaje.

        Con eso cada dron es Bernoulli(p) con la MISMA p, y p se obtiene
        directamente de ``calculate_neutralization_probability_friis``. La
        esperanza de la fracción por réplica es exactamente p, así que el IC
        del 95% debe contenerla.

        NOTA sobre un diseño anterior que descarté: abrir el cono a 180° para
        "cubrir" a todos los drones NO sirve — la ganancia es
        G ≈ 26000/apertura², así que 180° da G ≈ 0.80, por debajo de un
        radiador isotrópico, y la probabilidad colapsa incluso a 1000 kW. Es
        un recordatorio de que en este modelo la apertura no es un parámetro
        de conveniencia: paga ganancia.
        """
        from src.config import HPM_CONE_APERTURE, HPM_FREQUENCY_GHZ
        from src.engine.radar_engine import SPEED_OF_LIGHT_M_S

        POTENCIA_KW = 25.0
        DISTANCIA_M = 20.0
        DIRECCION = 45.0
        # Cableado resonante con la frecuencia del arma: η(f_res) = 1.
        L_RESONANTE = SPEED_OF_LIGHT_M_S / (2.0 * HPM_FREQUENCY_GHZ * 1e9)

        p_teorica = calculate_neutralization_probability_friis(
            potencia_kw=POTENCIA_KW,
            distancia=DISTANCIA_M,
            apertura_cono=HPM_CONE_APERTURE,
            angulo_offset=0.0,
            cable_length_m=L_RESONANTE,
            polarization=1.0,
        )
        # El escenario tiene que ser informativo: ni saturado ni nulo.
        assert 0.05 < p_teorica < 0.95, f"p teórica degenerada: {p_teorica}"

        rad = math.radians(DIRECCION)
        fracciones = []
        for i in range(40):
            gen = nuevo_generador(77_000 + i)
            sim = SimulationEngine(swarm_size=8, rng=gen)
            sim.swarm.inicializar_formacion("cuadrada", 8)
            for d in sim.swarm.drones:
                # Sobre el eje del haz, a distancia 3D exacta, misma altitud
                # que el cañón (así el slant range es la distancia pedida).
                d.x = sim.hpm.origen_x + DISTANCIA_M * math.cos(rad)
                d.y = sim.hpm.origen_y + DISTANCIA_M * math.sin(rad)
                d.z = sim.hpm.origen_z
                d.cable_length_m = L_RESONANTE
                d.polarization = 1.0
                d.e_threshold_mult = 1.0
                d.blindaje = "estandar"

            eventos = sim.fire(potencia=POTENCIA_KW, direccion=DIRECCION)["eventos"]
            assert len(eventos) == 8, "algún dron quedó fuera del cono"
            # Todos ven la misma probabilidad: es el invariante del diseño.
            probs = {round(e["probabilidad"], 6) for e in eventos}
            assert len(probs) == 1, f"probabilidades distintas: {probs}"
            assert probs.pop() == pytest.approx(p_teorica, abs=1e-4)

            conteo = sim.swarm.contar_por_estado()
            fracciones.append(conteo["neutralizado"] / 8)

        lo, hi = intervalo_bootstrap(fracciones)
        assert lo <= p_teorica <= hi, (
            f"IC=[{lo}, {hi}] no contiene la p teórica del motor ({p_teorica})"
        )
