"""Modelo de dron para la simulación EW."""

from __future__ import annotations

import math
from enum import Enum

from numpy.random import Generator

from src.config import (
    BOIDS_MAX_TURN_RATE_DEG_S,
    DRONE_BOB_AMPLITUDE_M,
    DRONE_BOB_PERIOD_S,
    DRONE_CABLE_LENGTH_MAX_M,
    DRONE_CABLE_LENGTH_MIN_M,
    DRONE_LOST_LINK_ATERRIZAR_FRACTION,
    DRONE_LOST_LINK_DESCENT_RATE_M_S,
    DRONE_LOST_LINK_FLYAWAY_FRACTION,
    DRONE_LOST_LINK_HOVER_FRACTION,
    DRONE_LOST_LINK_RTH_FRACTION,
    DRONE_POLARIZATION_MIN,
    DRONE_RIESGO_LATENTE_DECAY_TAU_S,
    DRONE_RIESGO_LATENTE_MAX_POR_S,
    HPM_DISPARO_DURACION_S,
    HPM_FREQUENCY_GHZ,
    HPM_LOGLOGISTIC_B,
    HPM_LOGLOGISTIC_E50_V_M,
    HPM_MODEL,
    HPM_SUBSISTEMAS,
    THREAT_MEMORY_DECAY_TAU_S,
)
from src.engine.hpm_engine import (
    apply_hardening_odds,
    calculate_neutralization_probability,
    calculate_neutralization_probability_friis,
    e50_upset_desde_damage,
    energia_absorbida_j,
    resonance_frequency_ghz,
    susceptibility_coupling_factor,
)
from src.engine.physics import update_position
from src.utils.helpers import angle_difference
from src.utils.reproducibilidad import rng as global_rng


class DroneEstado(str, Enum):
    """
    Estado COMBINADO del dron, tal como lo consumen el frontend, la API y
    la mayoría del código existente (``Swarm``, ``HPMWeapon``, ``HPMissile``,
    ``HPMissileSystem``, ``Jammer``). Se conserva sin cambios de valores por
    compatibilidad — ver ``Drone.estado`` (propiedad derivada) para la
    partición real en dos ejes ortogonales (P2-E, Parte 1).
    """

    ACTIVO = "activo"
    NEUTRALIZADO = "neutralizado"
    DANADO = "danado"
    INTERFERIDO = "interferido"


class EstadoSalud(str, Enum):
    """
    Eje de SALUD del dron (daño físico/electrónico), ortogonal al enlace de
    control. Antes vivía mezclado con ``INTERFERIDO`` dentro de
    ``DroneEstado`` — ver la nota de Parte 1 en ``Drone.estado``.
    """

    ACTIVO = "activo"
    DANADO = "danado"
    NEUTRALIZADO = "neutralizado"


class EstadoEnlace(str, Enum):
    """Eje de ENLACE de control (radio), ortogonal a la salud."""

    OK = "ok"
    INTERFERIDO = "interferido"


class PerfilLostLink(str, Enum):
    """
    Comportamiento de contingencia programado que un dron ejecuta mientras
    tiene el enlace de control perdido (``EstadoEnlace.INTERFERIDO``), en
    vez de congelarse. Se sortea por dron al crearlo (ver
    ``DRONE_LOST_LINK_*_FRACTION`` en ``src/config.py``), como el blindaje.
    """

    HOVER = "hover"
    ATERRIZAR = "aterrizar"
    RTH = "rth"
    FLYAWAY = "flyaway"


class Drone:
    """Representa un dron con posición, movimiento y resistencia al HPM."""

    def __init__(
        self,
        drone_id: int,
        x: float = 0.0,
        y: float = 0.0,
        velocidad: float = 5.0,
        angulo: float = 0.0,
        salud: float = 100.0,
        z: float = 100.0,
        blindaje: str = "estandar",
        e_threshold_mult: float = 1.0,
        cable_length_m: float | None = None,
        polarization: float | None = None,
        perfil_lost_link: PerfilLostLink | None = None,
        rng: Generator | None = None,
    ) -> None:
        self.id = drone_id
        self.x = x
        self.y = y
        self.velocidad = velocidad
        self.angulo = angulo
        self.salud = salud

        # Estado partido en dos ejes ortogonales (P2-E, Parte 1): salud
        # (daño físico/electrónico) y enlace de control (radio), donde antes
        # había un único ``DroneEstado``. Ver la propiedad ``estado`` más
        # abajo para el porqué y la regla de compatibilidad.
        self.estado_salud = EstadoSalud.ACTIVO
        self.estado_enlace = EstadoEnlace.OK

        # RNG por instancia (P0-B): None conserva el generador global (mismo
        # comportamiento que antes). Debe fijarse ANTES de los sorteos de
        # cable_length_m/polarization/_bob_phase de abajo, que dependen de
        # ``self._rng()``. Cuando ``Swarm`` construye el dron le pasa su
        # propio generador, para que una réplica de experimento y la
        # simulación interactiva nunca compartan estado aleatorio.
        self.rng = rng

        # Blindaje heterogéneo: un enjambre real no es homogéneo — algunas
        # unidades llevan mejor apantallado/protección que otras, lo que se
        # traduce en un umbral de susceptibilidad (V/m) más alto.
        self.blindaje = blindaje
        self.e_threshold_mult = e_threshold_mult

        # Huella de susceptibilidad: longitud de cableado interno (fija su
        # frecuencia de resonancia y por tanto η(f) a la frecuencia del arma)
        # y factor de mismatch de polarización [0,1]. None → sorteo al crear
        # el dron, como el blindaje.
        self.cable_length_m = (
            cable_length_m
            if cable_length_m is not None
            else float(self._rng().uniform(DRONE_CABLE_LENGTH_MIN_M, DRONE_CABLE_LENGTH_MAX_M))
        )
        self.polarization = (
            polarization
            if polarization is not None
            else float(self._rng().uniform(DRONE_POLARIZATION_MIN, 1.0))
        )

        # Perfil de contingencia lost-link (P2-E, Parte 3): comportamiento
        # que ejecuta el dron mientras tiene el enlace perdido, en vez de
        # congelarse. Mismo patrón que cable_length_m/polarization: None →
        # sorteo con el generador de esta instancia, nunca el global.
        self.perfil_lost_link = (
            perfil_lost_link
            if perfil_lost_link is not None
            else self._sortear_perfil_lost_link()
        )
        # True una vez que el perfil ATERRIZAR completó el descenso: el dron
        # queda inerte en el suelo — ni el flocking ni la recuperación de
        # enlace lo vuelven a mover (ver ``mover``/``_descender``).
        self.aterrizado = False

        # Memoria de amenaza (P2-E, Parte 2): posición del último impacto
        # (detonación de misil o exposición al cañón) que recibió este dron,
        # con una intensidad en [0,1] que decae exponencialmente (ver
        # ``actualizar_amenaza``). Cero por defecto: sin memoria activa, el
        # repulsor de ``compute_headings`` no aporta nada — un dron que
        # nunca fue atacado se comporta exactamente como antes de P2-E.
        self.amenaza_x = 0.0
        self.amenaza_y = 0.0
        self.amenaza_intensidad = 0.0

        # Fallo latente (P2-D, Parte 3): hazard rate (1/s) de una degradación
        # RECUPERABLE en curso. 0.0 = sin riesgo pendiente. Se activa en
        # ``recibir_daño`` cuando una exposición cae en la zona de UPSET
        # (por debajo del umbral de daño, por encima del umbral de upset —
        # ver ``e50_upset_desde_damage``); decae cada tick hacia la
        # recuperación (ver ``actualizar_riesgo_latente``), pero puede
        # madurar en una neutralización DIFERIDA antes de decaer del todo
        # ("un enjambre que se desordena y se recupera", o a veces no).
        self.riesgo_latente_por_s = 0.0
        # Qué subsistema manifestó el upset más reciente (nombre de
        # ``HPM_SUBSISTEMAS``), sorteado por debilidad relativa — solo
        # diagnóstico/comportamiento degradado (ver ``mover``), NO gobierna
        # ninguna probabilidad: el modelo de 5 subsistemas de P1-C sigue
        # bloqueado (docs/FISICA_Y_MATEMATICA.md §3.6) y esta huella no
        # depende de su calibración.
        self.subsistema_en_riesgo: str | None = None
        # A qué disparo/detonación atribuir una baja diferida si el riesgo
        # latente madura en neutralización ticks después. Se deja en None
        # hasta que ``SimulationEngine`` conoce el id real del disparo (se
        # asigna DESPUÉS de que ``analytics`` lo registra — ver
        # ``HPMWeapon.disparar``/``HPMissile.detonar`` y
        # ``SimulationEngine._atribuir_riesgo_latente``).
        self.origen_riesgo_shot_id: int | None = None
        self.origen_riesgo_distancia_m: float | None = None

        # Energía acumulada absorbida (P2-D, Parte 2), en julios —
        # contabilidad con UNIDADES REALES que reemplaza la aritmética
        # ``probabilidad·potencia·0.5`` (dimensionalmente vacía, ver
        # docs/AUDITORIA_CHECKLIST.md §4.5). Puramente informativa: no
        # gobierna ningún estado, es la suma de ``energia_absorbida_j`` de
        # cada exposición.
        self.energia_absorbida_j = 0.0

        # Radar: si el dron fue detectado por el radar en el tick actual
        # (gobierna la selección automática de blancos, no la física del
        # daño). Default True: "conocido" hasta que Swarm.actualizar() lo
        # reevalúe con el modelo real — evita que drones recién creados (o
        # construidos directamente en tests, sin pasar por Swarm) queden
        # indetectables por omisión.
        self.detectado = True

        # Altitud: cada dron mantiene una altitud de crucero (z_base) y
        # oscila suavemente alrededor de ella (hover/patrulla), no gana ni
        # pierde altitud por su velocidad horizontal.
        self.z_base = z
        self.z = z
        self._bob_phase = float(self._rng().uniform(0, 2 * math.pi))
        self._tiempo_vuelo = 0.0

        # Última probabilidad de neutralización calculada (para reportes/validación).
        self.ultima_probabilidad = 0.0

    def _rng(self) -> Generator:
        """Generador de esta instancia, o el global si no se inyectó ninguno."""
        return self.rng if self.rng is not None else global_rng()

    def _sortear_perfil_lost_link(self) -> PerfilLostLink:
        """
        Sorteo por cuantiles acumulados sobre las cuatro fracciones de
        ``src/config.py`` (RTH/HOVER/ATERRIZAR/FLYAWAY, en ese orden). Usa
        ``self._rng()`` — nunca el generador global — para que una réplica
        de experimento y la simulación interactiva no compartan esta tirada.
        """
        u = float(self._rng().random())
        c1 = DRONE_LOST_LINK_RTH_FRACTION
        c2 = c1 + DRONE_LOST_LINK_HOVER_FRACTION
        c3 = c2 + DRONE_LOST_LINK_ATERRIZAR_FRACTION
        if u < c1:
            return PerfilLostLink.RTH
        if u < c2:
            return PerfilLostLink.HOVER
        if u < c3:
            return PerfilLostLink.ATERRIZAR
        return PerfilLostLink.FLYAWAY

    def _sortear_subsistema_afectado(self) -> str:
        """
        Qué subsistema manifiesta el upset (P2-D, Parte 3), por sorteo
        ponderado inversamente al umbral de daño de cada uno
        (``HPM_SUBSISTEMAS`` — Tabla 1 del paper, valores publicados y NO
        ajustados). El más débil (menor E₅₀) es el más probable, consistente
        con el hallazgo de sensibilidad de P1-C/P2-A: a campo bajo domina el
        subsistema más débil del OR-gate (ver docs/FISICA_Y_MATEMATICA.md
        §3.6). Es un sorteo de RANKING relativo, no depende de que el modelo
        de subsistemas esté calibrado en términos absolutos — solo de que la
        Tabla 1 esté bien ordenada, que sí está verificado.
        """
        nombres = list(HPM_SUBSISTEMAS.keys())
        pesos = [1.0 / HPM_SUBSISTEMAS[n][0] for n in nombres]
        total = sum(pesos)
        u = float(self._rng().random()) * total
        acumulado = 0.0
        for nombre, peso in zip(nombres, pesos):
            acumulado += peso
            if u < acumulado:
                return nombre
        return nombres[-1]

    @property
    def estado(self) -> DroneEstado:
        """
        Estado combinado, derivado de los dos ejes reales (``estado_salud``,
        ``estado_enlace``). Se conserva como propiedad — en vez de eliminar
        el atributo — porque ``drone.estado`` se lee (y en un par de
        lugares se ASIGNA) en muchísimo código que esta fase no toca:
        ``Swarm``, ``HPMWeapon``, ``HPMissile``/``HPMissileSystem``,
        ``utils.helpers.drone_to_dict`` (y por lo tanto la API y el
        frontend), y varios tests existentes. Partir el estado sin romper
        esa interfaz exige que ``estado`` siga existiendo, ahora como VISTA
        derivada de los dos campos primarios en vez de dato primario él
        mismo (ver el setter de compatibilidad más abajo).

        Prioridad (igual jerarquía observable que el enum único de antes):
        1. NEUTRALIZADO — terminal. Todo el código que muta el enlace
           (``Jammer.actualizar``) ya excluye explícitamente a los drones
           neutralizados, así que en la práctica un dron neutralizado nunca
           vuelve a tener ``estado_enlace`` relevante.
        2. INTERFERIDO — el enlace perdido "gana" sobre un daño no letal,
           igual que en el modelo de un solo enum: un dron dañado que
           además pierde el enlace se reporta como interferido (que es la
           condición operativamente urgente), no como dañado.
        3. DANADO / ACTIVO — según la salud.
        """
        if self.estado_salud == EstadoSalud.NEUTRALIZADO:
            return DroneEstado.NEUTRALIZADO
        if self.estado_enlace == EstadoEnlace.INTERFERIDO:
            return DroneEstado.INTERFERIDO
        if self.estado_salud == EstadoSalud.DANADO:
            return DroneEstado.DANADO
        return DroneEstado.ACTIVO

    @estado.setter
    def estado(self, value: DroneEstado) -> None:
        """
        Setter de compatibilidad: código externo que sigue escribiendo
        ``drone.estado = DroneEstado.X`` directamente (``HPMissile.detonar``,
        y varios tests) sigue funcionando exactamente igual, pero el efecto
        recae en el eje real correspondiente. Asignar un valor de SALUD
        (ACTIVO/DANADO/NEUTRALIZADO) no toca el enlace; asignar INTERFERIDO
        no toca la salud — son los dos ejes independientes que esta parte
        introduce, y es la razón por la que antes un dron interferido Y
        dañado no era representable.
        """
        valor = DroneEstado(value)
        if valor == DroneEstado.INTERFERIDO:
            self.estado_enlace = EstadoEnlace.INTERFERIDO
        elif valor == DroneEstado.ACTIVO:
            self.estado_salud = EstadoSalud.ACTIVO
        elif valor == DroneEstado.DANADO:
            self.estado_salud = EstadoSalud.DANADO
        else:
            self.estado_salud = EstadoSalud.NEUTRALIZADO

    def factor_acoplamiento(self, frequency_ghz: float = HPM_FREQUENCY_GHZ) -> float:
        """Factor de amplitud acoplada a esta frecuencia: √(η(f_res)·pol)."""
        return susceptibility_coupling_factor(
            self.cable_length_m, self.polarization, frequency_ghz
        )

    def frecuencia_resonancia_ghz(self) -> float:
        return resonance_frequency_ghz(self.cable_length_m)

    def mover(
        self,
        dt: float,
        home_x: float | None = None,
        home_y: float | None = None,
    ) -> None:
        """
        Actualiza posición y altitud.

        Con enlace OK, es el vuelo normal (rumbo gobernado externamente por
        ``compute_headings``). Con el enlace perdido (P2-E, Parte 3) ejecuta
        el perfil de contingencia sorteado (``self.perfil_lost_link``) en
        vez de congelarse — ``home_x``/``home_y`` (típicamente el centro de
        formación, ver ``Swarm.actualizar``) es el punto de retorno del
        perfil RTH; sin él, RTH degrada a mantener el rumbo actual.

        Un dron ya ``aterrizado`` (perfil ATERRIZAR que completó el
        descenso) queda inerte para siempre, sin importar el estado del
        enlace: aterrizar es la única contingencia que deja al dron
        inservible incluso tras recuperar la señal.
        """
        if self.aterrizado or self.estado_salud == EstadoSalud.NEUTRALIZADO:
            return

        if self.estado_enlace == EstadoEnlace.INTERFERIDO:
            if self.perfil_lost_link == PerfilLostLink.ATERRIZAR:
                self._descender(dt)
                return  # la altitud la gobierna el descenso, no el bobbing normal
            self._mover_perfil_lost_link(dt, home_x, home_y)
        else:
            self.x, self.y = update_position(
                self.x, self.y, self.velocidad, self.angulo, dt
            )

        self._tiempo_vuelo += dt
        omega = 2 * math.pi / DRONE_BOB_PERIOD_S
        self.z = self.z_base + DRONE_BOB_AMPLITUDE_M * math.sin(
            omega * self._tiempo_vuelo + self._bob_phase
        )

    def _mover_perfil_lost_link(
        self, dt: float, home_x: float | None, home_y: float | None
    ) -> None:
        """
        Aplica el perfil de contingencia (salvo ATERRIZAR, que ``mover``
        despacha aparte porque gobierna la altitud, no el plano horizontal).

        - HOVER: mantiene posición — no llama a ``update_position``. Es el
          comportamiento más parecido al "congelamiento" que tenía el
          simulador antes de este ítem, pero ahora es una elección de
          perfil legítima (failsafe "Loiter"/"Brake"), no la única opción.
        - RTH: gira hacia ``(home_x, home_y)`` a la tasa de giro acotada de
          boids (``BOIDS_MAX_TURN_RATE_DEG_S`` — reutilizada por ser el
          mismo tipo de restricción física, un dron autónomo no gira de
          golpe) y avanza.
        - FLYAWAY: avanza en línea recta al rumbo que tenía al perder el
          enlace. No hace falta "congelar" el ángulo explícitamente: como
          ``Swarm.actualizar`` deja de asignarle nuevos rumbos de flocking
          mientras está interferido (ver ese método), ``self.angulo`` ya
          queda fijo por construcción — es el caso adverso real de un
          dron sin enlace que sigue volando.
        """
        if self.perfil_lost_link == PerfilLostLink.HOVER:
            return
        if self.perfil_lost_link == PerfilLostLink.RTH:
            self._girar_hacia_home(dt, home_x, home_y)

        self.x, self.y = update_position(
            self.x, self.y, self.velocidad, self.angulo, dt
        )

    def _girar_hacia_home(
        self, dt: float, home_x: float | None, home_y: float | None
    ) -> None:
        # P2-D, Parte 3 — comportamiento degradado: sin GPS/GNSS (LNA en
        # upset) el dron no puede calcular su posición ni, por tanto, el
        # rumbo hacia el punto de retorno — RTH degrada a "mantener rumbo",
        # reutilizando el mismo camino de degradación elegante que ya existe
        # para cuando no se pasa ``home_x``/``home_y`` en absoluto.
        if home_x is None or home_y is None or self.subsistema_en_riesgo == "gps_gnss_lna":
            return
        angulo_deseado = math.degrees(math.atan2(home_y - self.y, home_x - self.x)) % 360
        max_giro = BOIDS_MAX_TURN_RATE_DEG_S * dt
        giro = angle_difference(self.angulo, angulo_deseado)
        giro = max(-max_giro, min(max_giro, giro))
        self.angulo = (self.angulo + giro) % 360

    def _descender(self, dt: float) -> None:
        """
        Perfil ATERRIZAR: descenso vertical controlado a
        ``DRONE_LOST_LINK_DESCENT_RATE_M_S``, sin desplazamiento horizontal
        (aterrizaje en el sitio, no un planeo). Al tocar el suelo (z=0)
        queda inerte (``aterrizado=True``, velocidad 0) — ver ``mover``.
        """
        self.z = max(0.0, self.z - DRONE_LOST_LINK_DESCENT_RATE_M_S * dt)
        if self.z <= 0.0:
            self.z = 0.0
            self.aterrizado = True
            self.velocidad = 0.0

    def registrar_impacto(self, x: float, y: float, intensidad: float = 1.0) -> None:
        """
        Memoria de amenaza (P2-E, Parte 2): registra la posición del último
        impacto/exposición HPM que recibió este dron (detonación de misil o
        disparo de cañón — ver ``SimulationEngine.fire``/
        ``_process_missile_events``), con la intensidad de la reacción
        repulsiva subsiguiente en ``compute_headings``.

        Sustituye cualquier memoria previa: solo importa la amenaza MÁS
        RECIENTE, no un historial acumulado — modela un enjambre con
        control reactivo simple (reacciona al último evento), consistente
        con el resto del OPFOR reactivo de este ítem, no una función de
        utilidad que integra todo el historial de combate.
        """
        self.amenaza_x = x
        self.amenaza_y = y
        self.amenaza_intensidad = max(0.0, min(1.0, intensidad))

    def actualizar_amenaza(self, dt: float) -> None:
        """
        Decae la intensidad de la memoria de amenaza exponencialmente
        (constante de tiempo ``THREAT_MEMORY_DECAY_TAU_S``, ver
        ``src/config.py``). Se llama una vez por tick de simulación, sea
        cual sea su origen (bucle de 60 FPS o runner Monte Carlo) — ver
        ``SimulationEngine._tick``.
        """
        if self.amenaza_intensidad <= 0.0 or dt <= 0.0:
            return
        self.amenaza_intensidad *= math.exp(-dt / THREAT_MEMORY_DECAY_TAU_S)
        if self.amenaza_intensidad < 1e-4:
            self.amenaza_intensidad = 0.0

    def actualizar_riesgo_latente(self, dt: float) -> bool:
        """
        Decae el riesgo latente (P2-D, Parte 3) y sortea si madura en una
        neutralización DIFERIDA este tick. Se llama desde
        ``SimulationEngine._tick`` (mismo patrón que ``actualizar_amenaza``:
        avanza siempre que avanza el reloj de simulación, tanto en el bucle
        de 60 FPS como en el runner Monte Carlo).

        La conversión hazard-rate → probabilidad-por-tick es la estándar
        para un proceso de riesgo constante dentro del tick:
        ``P_falla = 1 − exp(−h·dt)`` (no la aproximación lineal ``h·dt``,
        exacta incluso si el tick es largo o el hazard alto).

        Si el dron sobrevive el tick, el hazard decae exponencialmente
        (constante ``DRONE_RIESGO_LATENTE_DECAY_TAU_S``) hacia la
        recuperación — cuando cae por debajo de un umbral despreciable, el
        dron se declara recuperado (``estado_salud`` vuelve a ``ACTIVO``,
        se limpia el origen de atribución): la mayoría de los drones en
        riesgo latente terminan así, "un enjambre que se desordena y se
        recupera".

        Returns:
            True si el dron acaba de ser neutralizado por fallo latente EN
            ESTE TICK (para que ``SimulationEngine`` lo atribuya al disparo
            original vía ``origen_riesgo_shot_id`` antes de que este método
            lo borre).
        """
        if self.riesgo_latente_por_s <= 0.0 or dt <= 0.0:
            return False
        if self.estado_salud == EstadoSalud.NEUTRALIZADO:
            return False

        probabilidad_falla_tick = 1.0 - math.exp(-self.riesgo_latente_por_s * dt)
        if float(self._rng().random()) < probabilidad_falla_tick:
            self.estado_salud = EstadoSalud.NEUTRALIZADO
            self.salud = 0.0
            self.riesgo_latente_por_s = 0.0
            self.subsistema_en_riesgo = None
            self.velocidad = 0.0
            return True

        self.riesgo_latente_por_s *= math.exp(-dt / DRONE_RIESGO_LATENTE_DECAY_TAU_S)
        if self.riesgo_latente_por_s < 1e-4:
            self.riesgo_latente_por_s = 0.0
            self.subsistema_en_riesgo = None
            self.origen_riesgo_shot_id = None
            self.origen_riesgo_distancia_m = None
            self.estado_salud = EstadoSalud.ACTIVO
            self.salud = 100.0
        else:
            # Salud DERIVADA (indicador para la UI, no causal): refleja
            # cuánto hazard remanente queda, no cuánta "energía" absorbió.
            fraccion_riesgo = min(1.0, self.riesgo_latente_por_s / DRONE_RIESGO_LATENTE_MAX_POR_S)
            self.salud = round(100.0 * (1.0 - 0.8 * fraccion_riesgo), 2)

        return False

    def entrar_en_riesgo_latente(self, severidad: float, distancia_m: float) -> None:
        """
        Marca a este dron en riesgo latente (P2-D, Parte 3) con la
        ``severidad`` dada (en [0,1]; 1.0 = justo debajo del umbral de daño,
        el caso más grave dentro de la zona de upset; →0 = roce mínimo con
        el umbral de upset).

        Punto de entrada COMÚN para el cañón (``recibir_daño``, llamado
        sobre ``self``) y el misil (``HPMissile.detonar``, llamado sobre un
        dron externo) — evita duplicar la selección de subsistema y la
        conversión severidad→hazard rate en dos lugares.
        """
        severidad = min(1.0, max(0.0, float(severidad)))
        self.riesgo_latente_por_s = severidad * DRONE_RIESGO_LATENTE_MAX_POR_S
        self.subsistema_en_riesgo = self._sortear_subsistema_afectado()
        # El id real del disparo lo completa SimulationEngine DESPUÉS de que
        # analytics lo asigna (ver _atribuir_riesgo_latente).
        self.origen_riesgo_shot_id = None
        self.origen_riesgo_distancia_m = distancia_m
        self.estado_salud = EstadoSalud.DANADO
        self.salud = round(100.0 * (1.0 - 0.8 * severidad), 2)

    def recibir_daño(
        self,
        potencia: float,
        distancia: float,
        angulo_offset: float = 0.0,
        apertura_cono: float = 30.0,
        duty_cycle: float = 1.0,
        pulse_duration_ns: float | None = None,
    ) -> bool:
        """
        Calcula probabilidad de neutralización según el modelo HPM y — en el
        modelo ``friis`` — resuelve upset vs damage con energía absorbida en
        unidades reales (P2-D).

        ``duty_cycle`` separa potencia promedio de pico (daño latchup por
        campo instantáneo); 1.0 = CW, compatible con el modelo calibrado.

        Returns:
            True si el dron fue neutralizado en este impacto (inmediato —
            una neutralización DIFERIDA por fallo latente la reporta
            ``actualizar_riesgo_latente``, no este método).
        """
        if self.estado_salud == EstadoSalud.NEUTRALIZADO:
            return False

        if HPM_MODEL != "friis":
            # Modelo "legacy": exponencial ad-hoc, ya etiquetado como tal
            # (ver hpm_engine.py) y sin pretensión de física real — se
            # conserva TAL CUAL, aritmética de "puntos de salud" incluida.
            # P2-D solo reemplaza esa aritmética en la rama "friis", que sí
            # pretende ser física real (ver docs/AUDITORIA_CHECKLIST.md
            # §4.5): tocar acá el modelo ad-hoc no aporta rigor, porque
            # nunca reclamó tenerlo.
            probabilidad = calculate_neutralization_probability(
                potencia=potencia,
                distancia=distancia,
                angulo_offset=angulo_offset,
                apertura_cono=apertura_cono,
            )
            self.ultima_probabilidad = probabilidad
            impacto = float(self._rng().random()) < probabilidad
            dano = probabilidad * potencia * 0.5
            self.salud = max(0.0, self.salud - dano)
            if impacto or self.salud <= 0:
                self.estado_salud = EstadoSalud.NEUTRALIZADO
                return True
            if self.salud < 50:
                self.estado_salud = EstadoSalud.DANADO
            return False

        # ── Modelo "friis": daño real + upset/damage + energía absorbida ──
        kwargs_campo = dict(
            potencia_kw=potencia,
            distancia=distancia,
            apertura_cono=apertura_cono,
            angulo_offset=angulo_offset,
            duty_cycle=duty_cycle,
            pulse_duration_ns=pulse_duration_ns,
            cable_length_m=self.cable_length_m,
            polarization=self.polarization,
            frequency_ghz=HPM_FREQUENCY_GHZ,
        )

        probabilidad = calculate_neutralization_probability_friis(**kwargs_campo)
        # Blindaje: reducción proporcional en espacio de momios, no
        # desplazando el umbral E (ver apply_hardening_odds — desplazar el
        # umbral colapsaba la probabilidad a ~0 en casi todo el rango de
        # combate, no la reducía de forma proporcional).
        probabilidad = apply_hardening_odds(probabilidad, self.e_threshold_mult)
        self.ultima_probabilidad = probabilidad

        # Umbral de UPSET: mismo campo, umbral más bajo (ver
        # e50_upset_desde_damage — decisión de modelado, categoría 3, NO
        # dato del paper). Se le aplica el MISMO factor de blindaje: el
        # apantallado de un dron blindado protege contra cualquier campo,
        # no solo contra el que causa daño permanente.
        p_upset = calculate_neutralization_probability_friis(
            **{**kwargs_campo, "e50": e50_upset_desde_damage(HPM_LOGLOGISTIC_E50_V_M),
               "b": HPM_LOGLOGISTIC_B}
        )
        p_upset = apply_hardening_odds(p_upset, self.e_threshold_mult)
        # p_upset >= probabilidad está garantizado matemáticamente (E50 más
        # bajo ⇒ P mayor a igual campo, log-logística monótona) — no un
        # invariante que dependa de los valores concretos.

        # Energía absorbida (Parte 2): contabilidad con unidades reales,
        # reemplaza ``probabilidad·potencia·0.5``. Puramente informativa, no
        # decide ningún estado.
        self.energia_absorbida_j += energia_absorbida_j(
            potencia_kw=potencia,
            distancia=distancia,
            apertura_cono=apertura_cono,
            angulo_offset=angulo_offset,
            duty_cycle=duty_cycle,
            cable_length_m=self.cable_length_m,
            duracion_exposicion_s=HPM_DISPARO_DURACION_S,
            pulse_duration_ns=pulse_duration_ns,
        )

        u = float(self._rng().random())

        if u < probabilidad:
            # DAMAGE: falla permanente, inmediata.
            self.estado_salud = EstadoSalud.NEUTRALIZADO
            self.riesgo_latente_por_s = 0.0
            self.subsistema_en_riesgo = None
            self.salud = 0.0
            return True

        if u < p_upset:
            # UPSET: exposición significativa pero no letal de inmediato.
            # ``severidad`` es qué tan adentro de la zona [probabilidad,
            # p_upset) cayó el sorteo — 1.0 justo bajo el umbral de daño
            # (upset severo, mayor hazard inicial), →0 en el borde de la
            # zona de upset (roce mínimo, hazard casi nulo).
            ancho_zona = max(p_upset - probabilidad, 1e-12)
            severidad = (p_upset - u) / ancho_zona
            self.entrar_en_riesgo_latente(severidad, distancia)
            return False

        # Miss limpio: ni daño ni upset. No se toca ningún riesgo latente
        # que ya estuviera pendiente de una exposición anterior — un miss no
        # cura nada, la recuperación la gobierna el decaimiento por tick.
        return False
