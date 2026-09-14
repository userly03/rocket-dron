# Estado del arte: armas de microondas de alta potencia (HPM) y guerra electrónica anti-drones

Este documento es un *research brief* — un mapa del panorama real, actual
(2025-2026), de la tecnología en la que se inspira este simulador. No es
física ni matemática (eso está en `FISICA_Y_MATEMATICA.md`); es **contexto
de la industria, los programas militares y la investigación académica**
detrás de las armas HPM y sus alternativas, para que puedas seguir
investigando por tu cuenta con nombres, cifras y fuentes concretas.

Todo lo que sigue está armado a partir de reportes públicos (prensa
especializada en defensa, comunicados de las propias empresas, informes de
mercado) — no hay nada acá que no esté ya publicado abiertamente.

---

## 1. Por qué esto existe: el problema que resuelve

Los enjambres de drones baratos (cientos a pocos miles de dólares cada uno)
volvieron obsoleto el cálculo económico de la defensa aérea tradicional:
gastar un interceptor kinético de $10,000-$2,000,000 contra un drone de
$500 es insostenible a escala, sobre todo contra un *enjambre* de decenas o
cientos de unidades simultáneas. Esto se conoce como el **"desequilibrio de
costos"** (*cost imbalance*), y es la razón concreta por la que EEUU, China,
India, Israel y otros están invirtiendo fuerte en armas de energía dirigida
(HPM y láser): ambas cuestan, por disparo, solo la electricidad consumida —
centavos, no miles de dólares — y no dependen de un depósito de munición
que se agota.

---

## 2. Programas y sistemas reales, por país

### Estados Unidos

| Sistema | Desarrollador | Tipo | Estado (2025-2026) |
|---|---|---|---|
| **Leonidas** | Epirus | HPM, estado sólido (GaN) | En despliegue activo. Contrato de $66.1M (Ejército, IFPC-HPM), $43.5M adicionales para Gen II (jul. 2025), sistemas ya desplegados en CENTCOM desde inicios de 2025 y evaluados en NAWS China Lake (oct. 2025). Versión "Expeditionary" (ExDECS) entregada a la Marina/Infantería de Marina (abr. 2025). Demostró 100% de efectividad contra 61 drones en 5 escenarios (ago. 2025) y derribó 49 de una vez en otra prueba. |
| **THOR** | AFRL (Fuerza Aérea) | HPM, tubo de vacío | Demostrador tecnológico para defensa de bases aéreas; en desarrollo su sucesor **Mjolnir**, con mejoras de capacidad y manufactura. |
| **CHAMP** | Boeing / AFRL | Misil HPM de área (histórico — es la inspiración directa del `HPMissile` de este simulador) | Programa de demostración de $38M (2009); ya no es el sistema activo actual, pero sentó las bases conceptuales que hoy continúan Leonidas/THOR. |

Fuentes: [Epirus — contrato $66.1M](https://www.epirusinc.com/press-releases/u-s-army-awards-epirus-66-1m-contract-for-leonidas-tm-directed-energy-system), [Epirus — Gen II $43.5M](https://www.epirusinc.com/press-releases/epirus-receives-43-million-contract-from-u-s-army-for-ifpc-hpm-generation-ii-systems), [Breaking Defense — entrega a la Marina](https://breakingdefense.com/2025/04/defense-tech-company-epirus-delivers-counter-drone-swarms-to-navy/), [AFRL — THOR](https://afresearchlab.com/counter-swarm-high-power-weapon/), [Wikipedia — THOR](https://en.wikipedia.org/wiki/THOR_(weapon)).

### China

**Hurricane-3000** (Norinco) — sistema montado en camión, exhibido
públicamente por primera vez en el desfile militar de Beijing (sept. 2025).
Alcance efectivo declarado: **más de 3 km** contra drones pequeños y
enjambres. Usa un arreglo de microondas para generar pulsos
electromagnéticos que interrumpen los sistemas de control de los UAV.
Además, en febrero de 2026 China presentó una fuente de potencia de **20
gigavatios** para un arma HPM orientada a amenazar satélites Starlink en
órbita — una escala de potencia bastante mayor a los sistemas terrestres
anti-drone.

Fuentes: [Army Recognition — Hurricane-3000](https://www.armyrecognition.com/news/army-news/2025/exclusive-china-conducts-field-tests-of-new-hurricane-3000-high-power-microwave-weapon-to-counter-drone-swarms), [SCMP](https://www.scmp.com/news/china/military/article/3338877/chinas-powerful-new-microwave-weapon-system-can-destroy-drone-swarms-within-3km), [19FortyFive](https://www.19fortyfive.com/2026/01/china-deploys-new-hurricane-3000-microwave-super-weapon-for-operational-counter-drone-warfare/).

### India

DRDO (Centro de Investigación y Desarrollo de Tubos de Microondas,
Bengaluru) presentó un prototipo HPM en la Conferencia Internacional de
Guerra Electrónica 2026; ya deshabilitó drones clase DJI Phantom a **1 km**
de distancia en pruebas.

Fuente: [reportado en cobertura de mercado, ver §6](https://www.globenewswire.com/news-release/2026/01/21/3222585/28124/en/High-Power-Microwave-Directed-Energy-Weapons-Research-Report-2026-3-65-Bn-Market-Opportunities-Trends-Competitive-Landscape-Strategies-and-Forecasts-2020-2025-2025-2030F-2035F.html).

### Israel — **Iron Beam** (láser, no HPM, pero mismo ecosistema)

No es microondas — es un láser de **100 kW**, pero resuelve el mismo
problema económico (derriba drones/cohetes/morteros por unos centavos de
electricidad por disparo, vs. $10,000-$100,000+ por interceptor
convencional). Entregado operacionalmente a las FDI el 28 de diciembre de
2025 e integrado a la red de defensa aérea multicapa junto a Iron Dome,
David's Sling y Arrow. Una versión de menor potencia ya se usó en combate
real en octubre de 2024, derribando 35-40 drones de Hezbolá. Una unidad fue
enviada a EAU para ayudar a interceptar misiles/drones iraníes.

Fuentes: [Euronews](https://www.euronews.com/2025/12/02/israels-new-iron-beam-laser-system-passes-missile-and-drone-intercept-tests), [Jerusalem Post](https://www.jpost.com/defense-and-tech/article-881595), [Times of Israel](https://www.timesofisrael.com/israel-sent-laser-system-to-uae-to-help-intercept-iranian-missiles-and-drones-report/).

### Otros países con programas activos o declarados

Reino Unido, Francia, España, Alemania, Rusia e India tienen programas
militares de energía dirigida en desarrollo; Irán y Turquía declaran
tenerlos ya en servicio activo (no verificado independientemente en las
fuentes consultadas — a diferencia de EEUU/China/Israel, que tienen
demostraciones públicas documentadas).

Fuente: [informe de mercado, ver §6](https://www.globenewswire.com/news-release/2026/01/21/3222585/28124/en/High-Power-Microwave-Directed-Energy-Weapons-Research-Report-2026-3-65-Bn-Market-Opportunities-Trends-Competitive-Landscape-Strategies-and-Forecasts-2020-2025-2025-2030F-2035F.html).

### Ucrania (ver también `FISICA_Y_MATEMATICA.md` §9.2)

Prueba activamente sistemas de fabricantes externos (invitó a Epirus/
Leonidas a demostrar en condiciones de combate real) y desarrolla sistemas
propios vía la plataforma de innovación de defensa **Brave1**. El desafío
emergente ahí son los drones FPV guiados por **fibra óptica** (sin enlace
de radio), que son inmunes al jamming clásico pero siguen siendo
vulnerables a HPM (que ataca la electrónica interna, no el enlace).

---

## 3. Comparación de tecnologías anti-drone (2026)

| Tecnología | Alcance típico | Costo por disparo | Fortaleza | Debilidad |
|---|---|---|---|---|
| **HPM** (Leonidas, THOR, Hurricane-3000) | Cientos de metros a ~3 km | Centavos de electricidad | Ataca a **varios drones a la vez** (efecto de área/cono) — ideal contra enjambres. Funciona contra drones de fibra óptica (no depende de señal de radio). | Alcance menor al láser; requiere estar dentro del cono/radio de efecto. |
| **Láser** (Iron Beam) | Hasta ~10 km | Centavos de electricidad | Alcance mucho mayor, derriba en ~4 segundos. | Un blanco a la vez (no efecto de área); necesita "tiempo de permanencia" en el blanco; lo afectan clima/humo/nubes. |
| **Jamming / guerra electrónica** | Variable (según potencia) | Bajo | Protege contra 80-90% de amenazas de drones a bajo costo. | Inútil contra drones con enlace por fibra óptica (no hay señal de radio que interferir) — el desafío emergente en Ucrania. |
| **Cinético** (cañones, misiles, munición airburst) | Variable | Miles a millones de dólares por interceptor | Efectivo caso por caso, tecnología madura. | Insostenible económicamente contra enjambres de drones baratos ("desequilibrio de costos"). |

La doctrina emergente (2026) no elige una sola tecnología: la arquitectura
correcta es **por capas** — radar + detección RF pasiva + identificación
electro-óptica + ataque electrónico (jamming) + interceptores cinéticos +
láser + HPM, cada uno cubriendo el hueco del anterior. Este simulador ya
modela varias de esas capas: cañón/misil HPM, jamming de comunicaciones y
radar de detección (ver `FISICA_Y_MATEMATICA.md` §8).

Fuentes: [Army Recognition — comparación tecnologías 2026](https://www.armyrecognition.com/news/army-news/2026/us-accelerates-laser-and-microwave-weapons-deployment-to-counter-drone-swarms), [UAV Defence — tendencias 2024-2025](https://uav-defence.com/new-emerging-counter-drone-tech-lasers-high-power-microwaves-net-drones-2024-2025-trends/).

---

## 4. El mercado (para dimensionar el interés real)

El mercado global de armas de energía dirigida HPM se estima en **$2.31 mil
millones (2025) → $2.53 mil millones (2026)**, con una tasa de crecimiento
anual del 9.5%, proyectado a **$3.65 mil millones para 2030**. EEUU lidera
el mercado (Raytheon, Lockheed Martin, Northrop Grumman como jugadores
clave, además de Epirus como especialista en HPM), y Europa representa
~25% del mercado global.

Fuente: [GlobeNewswire — informe de mercado HPM 2026](https://www.globenewswire.com/news-release/2026/01/21/3222585/28124/en/High-Power-Microwave-Directed-Energy-Weapons-Research-Report-2026-3-65-Bn-Market-Opportunities-Trends-Competitive-Landscape-Strategies-and-Forecasts-2020-2025-2025-2030F-2035F.html).

---

## 5. Investigación académica reciente (más allá del paper ya citado)

**Toda la calibración de daño del proyecto hoy cuelga de un solo paper**
(arXiv:2602.08477, y éste con una inconsistencia interna propia — ver
`docs/HALLAZGO_TABLA1_VS_TABLA3.md`). Lo que sigue es una búsqueda
deliberada de **fuentes independientes** para reducir ese riesgo de fuente
única. Cada entrada dice explícitamente si el contenido fue verificado
leyendo el paper/abstract, o si solo se encontró la referencia sin poder
leerla (paywall/bloqueo anti-bot) — no se cita nada como confirmado sin
haberlo verificado.

### 5.1 Verificados — candidatos reales a segunda/tercera fuente de calibración

- **Mao, Xiang, Huang, Meng, Wang, Yang, Cui (2023)**, *"High-Power
  Microwave Pulse-Induced Failure on Unmanned Aerial Vehicle System"*,
  IEEE Transactions on Plasma Science 51(7):1885–1893,
  DOI [10.1109/TPS.2023.3236300](https://doi.org/10.1109/TPS.2023.3236300).
  **El más valioso identificado hasta ahora, todavía sin conseguir el PDF
  completo** (paywall de IEEE Xplore). Experimento real con hardware —drones
  comerciales de verdad irradiados con HPM, no simulación— que confirma que
  los componentes que fallan son **el motor del rotor y el ESC**. Coincide
  exactamente con el subsistema "ESC gate oxide" que ya usa el modelo de 5
  subsistemas del proyecto (`docs/FISICA_Y_MATEMATICA.md` §3.6.1). Vía la
  tabla comparativa de Lee et al. (2026, ver abajo), que sí lo cita con
  detalle, se sabe además que usa excitación **HPM banda-C y banda-L**, con
  acoplamiento de puerta trasera por las líneas ESC-motor — pero su umbral
  numérico de campo no se pudo extraer de esa cita secundaria con
  confianza. Sigue pendiente conseguir el original.
- **Xing, Liu, Su, Liu, Liu (2025)**, *"Degradation and Damage Effects in
  GaN HEMTs Induced by Low-Duty-Cycle High-Power Microwave Pulses"*,
  Micromachines 16(10):1137 (PDF completo verificado). Experimento real a
  nivel de **componente** (el GaN HEMT que efectivamente se usa en los ESC
  de un dron): a 42.5 dBm el dispositivo sobrevive 800 pulsos; a 43 dBm
  falla en 10 — una transición muy abrupta. Es potencia inyectada en el
  dispositivo (dBm), no campo incidente (V/m): compararlo contra el modelo
  requiere pasar por la misma cadena de acoplamiento cable→voltaje que el
  proyecto ya modela en `hpm_engine.py`.
- **Zhao, J., Zhao, G., Chen, Chen, Cao, Feng, Liu, Chen (2025)**,
  *"Damage effects in GaN high electron mobility transistor power amplifier
  induced by high power microwave pulses"*, Scientific Reports (PDF completo
  verificado). **Hallazgo nuevo, no en el catálogo anterior**: mismo grupo
  que el paper de 2022 de abajo, ahora describiendo un mecanismo de
  **quemado catastrófico** (no solo interferencia): a partir de ~53 dBm
  (~200 W) de potencia pico inyectada, ocurre ruptura por avalancha cerca
  de la compuerta que forma un canal de fuga y termina en quemado extenso
  del dispositivo. Segundo punto de calibración real e independiente para
  el subsistema ESC, distinto del de Xing et al. (mecanismo de falla
  diferente: avalancha/quemado vs. degradación gradual).
- **Khalil, Wang, Choi**, arXiv:[2510.16495](https://arxiv.org/abs/2510.16495)
  (PDF completo verificado, v2). **Corrección de título**: la v2 (jul-2026)
  cambió el título a *"Uncertainty-Aware Performance Modeling of
  High-Power Microwave Counter-UAV Engagements"* — el título anterior,
  citado antes en este documento, era el de una versión previa. Framework
  de simulación independiente (no el mismo grupo que arXiv:2602.08477), con
  umbrales en **energía de pulso** (10⁻²–10⁻¹ J) en vez de campo eléctrico,
  y un análisis de sensibilidad propio que identifica el alcance (*slant
  range*) como el factor dominante (elasticidad ≈ −2). Requiere conversión
  de unidades para comparar cifra a cifra contra el modelo del proyecto.
- **Zhao, J., Chen, Chen, Chen, Liu, Zhao, G. (2022)**, *"Interference
  effects in GaN high electron mobility transistor power amplifier induced
  by microwave pulses"*, Scientific Reports (PDF completo verificado —
  corrección sobre la entrada anterior de este documento, que la fechaba
  2025). **No es específico de drones** — física de componente GaN general
  (también relevante a radares/ECM), del mismo grupo que el paper de 2025
  de arriba pero describiendo un efecto previo, no destructivo
  (interferencia/corrimiento de umbral de compuerta, no quemado).
- **Lee, Kang, Park, Kim, Woo (2026)**, *"Analysis of High-Power
  Electromagnetic Pulses Effect on Unmanned Aerial Vehicles"*, Drones
  10(4):272 (PDF completo verificado — pasa de "no verificado" a
  verificado). **El hallazgo más importante de toda esta ronda de
  literatura, y no estaba anotado como hipótesis antes de leerlo**: el
  mecanismo de falla dominante que describen NO es destrucción de hardware
  ("hard-kill", lo único que el proyecto modela hoy), sino un **"soft-kill"
  por corrupción de la señal lógica PWM** que controla los motores — el
  pulso EMP distorsiona el nivel lógico de la señal PWM en las líneas del
  ESC, el enjambre pierde control de vuelo y cae, pero el drone **se
  recupera con un ciclo de apagado/encendido** — no hay daño permanente. Su
  umbral medido para ese efecto: **55 kV/m** con un pulso UWB de doble
  exponencial a 5 Hz de repetición. El paper además compara explícitamente
  contra Mao et al. (2023) y otro estudio, y concluye que **"los umbrales de
  disrupción pueden estar por debajo de los umbrales de destrucción"** — es
  decir, hay un régimen de falla temporal a un campo distinto (y, según la
  literatura EMC de más abajo, probablemente mucho menor) que el de daño
  permanente. **El proyecto no modela ningún régimen de "soft-kill"
  recuperable — solo probabilidad de daño permanente.** Ver §5.3.
- **Kubacki, Przesmycki, Bugaj (2025)**, *"Investigation on Electromagnetic
  Immunity of Unmanned Aerial Vehicles in Electromagnetic Environment"*,
  Electronics 14(21):4332 (PDF completo verificado — pasa de "no
  verificado" a verificado). Recopila umbrales de **inmunidad EMC real**
  para drones, muy por debajo del rango de daño del proyecto (150-350 V/m):
  **10 V/m** es el umbral EMC estándar para drones comerciales típicos
  (80 MHz–6 GHz); **15–30 V/m** ya produce retrasos de transmisión,
  inestabilidad del bus de comunicación y errores de posicionamiento;
  **20–60 V/m** causa interferencia significativa según la fuente que
  citan; **200 V/m** es el nivel de inmunidad exigido a equipos militares
  por el estándar Mil-Std-461G (procedimiento RS103); y citan un estudio
  de vuelo real donde **7.5 kV/m** causó interrupción funcional. Ver §5.3.

### 5.2 Encontrados, no verificados (paywall o bloqueo anti-bot al intentar leerlos)

*"Investigation on Falling and Damage Mechanisms of UAV Illuminated by HPM
Pulses"* (ResearchGate) sigue sin poder leerse completo. Se lista para no
perder el rastro, **no para citarlo como confirmado**.

**Bonus, fuera del dominio drones pero relacionado**: Tao et al. (2025),
*"Revealing the Intentional Electromagnetic Interference Impact on
State-of-Charge Estimation in Electric Vehicles"* (IEEE APEMC 2025, PDF
completo). Trata IEMI contra la estimación de carga de batería en
vehículos eléctricos — mismo dominio de amenaza (interferencia
electromagnética intencional) que el subsistema "BMS MOSFET" del modelo,
pero un mecanismo de ataque distinto (manipulación de la *estimación* de
estado de carga, no daño físico al MOSFET). No se usa como fuente de
calibración; se anota porque el usuario lo encontró buscando y podría
ser relevante si el proyecto alguna vez modela ataques a la lógica del BMS
en vez de solo su hardware.

**Señal de alerta encontrada y descartada**: un resultado sobre EMP en
drones publicado en el *Iranian Journal of Chemical and Chemical
Engineering* — un paper de física/EW en una revista de química es
indicio de revista de bajo estándar o fuera de su campo. No se usa como
fuente.

### 5.3 Corrección propia: NO es una brecha nueva — es el ítem `P2-D`, ya cerrado

**Esta subsección reemplaza una afirmación anterior de este documento**, que
decía que el proyecto "no modela ningún régimen de soft-kill" y que dos
fuentes independientes mostraban "el mismo patrón". Al revisar el código
antes de actuar sobre eso, encontré que es **falso en la primera parte y un
error de comparación de escalas en la segunda**:

- El proyecto **ya tiene** un modelo upset (recuperable) vs. damage
  (permanente): ítem `P2-D`, cerrado 2026-09-12, 38 tests
  (`tests/test_upset_damage.py`). El umbral de upset se deriva del de daño
  ya calibrado con una brecha de **-10 dB** (`e50_upset_desde_damage`,
  `src/engine/hpm_engine.py`): `E50_upset = E50_damage / 10^(10/20) ≈
  487.389 / 3.162 ≈ 154.13 V/m`. Está documentado explícitamente en
  `src/config.py` como **decisión de modelado** (categoría 3), tomada del
  extremo conservador de una convención general de literatura EMI/IEMI
  (rango 10-20 dB), sin una fuente numérica específica.
- Comparé mal las tres fuentes por no fijarme en la magnitud: **Lee et al.
  miden su soft-kill (crash por corrupción de PWM) a 55.000 V/m** — dos
  órdenes de magnitud POR ENCIMA del umbral de *daño* del proyecto
  (487 V/m), no por debajo. A los campos donde el arma del simulador ya
  destruye un dron, ese mecanismo específico de Lee et al. ni siquiera
  entra en juego — el dron ya está destruido por el mecanismo térmico
  mucho antes de llegar a ese campo. Es un hallazgo real, pero **fuera del
  rango de operación que este simulador modela**, no una brecha a llenar.
- Los umbrales de Kubacki et al. (10-60 V/m onda continua, hasta 200 V/m
  para el estándar militar) sí caen en el mismo orden de magnitud que el
  upset ya calibrado del proyecto (154 V/m) — pero miden un fenómeno
  distinto (degradación de comunicación/posicionamiento bajo onda
  continua, no el congelamiento de rumbo/degradación de RTH que modela
  `P2-D`). Sirven como **chequeo de orden de magnitud**, no como dato para
  recalibrar el número exacto: la brecha de -10dB, sin ser un dato citado
  de esta literatura específica, al menos aterriza en un rango
  real-mundo plausible (10-200 V/m) en vez de ser un número arbitrario.

**Conclusión honesta**: no hay nada que implementar acá. El upset ya
existe, su calibración sigue siendo una decisión de modelado declarada
como tal (no un dato validado), y la literatura nueva la sitúa en un rango
razonable sin poder reemplazarla por un número medido específico para
*este* comportamiento (congelamiento de rumbo). Si se quisiera cerrar esa
brecha de calibración con más rigor, haría falta un estudio que mida
específicamente el umbral de disrupción del **flight controller** de un
UAV bajo onda continua — ninguno de los papers de este catálogo lo hace
exactamente así.

### 5.4 Barrido de los otros 4 subsistemas del modelo

Mismo ejercicio que con el ESC (§5.1): buscar literatura independiente por
subsistema. Resultado desigual — dos confirmaciones reales, una alerta de
circularidad descartada, y un hueco genuino.

- **GPS/GNSS LNA — alerta de circularidad encontrada y descartada.** Una
  búsqueda inicial devolvió "umbral de quemado LNA de GPS ≈ 150 V/m" — el
  mismo valor exacto que la Tabla 1 de arXiv:2602.08477 (el paper
  cuestionado). Verificado: ese número salía del resumen del propio paper
  cuestionado apareciendo en los resultados de búsqueda, no de una fuente
  aparte. **No se cuenta como confirmación independiente.** Sí se confirmó
  un paper real y distinto sobre el mismo tipo de componente (LNA de RF en
  general, no específico de GPS): *"Mechanisms of Degradation and Damage in
  GaAs PHEMT Low-Noise Amplifier Under Ultra-Short Microwave Pulses"*,
  Micromachines 17(9):1054 (2025) — quemado bajo la compuerta en 43 ns con
  un pulso de 45 dBm a 2 GHz.
- **Cámara CMOS — confirmado, independiente.** Yang, Wen, Li, Zhou, Wang,
  Ding, Zhong, Meng, Fang, Guo (2024), *"Analysis of the Interference
  Effects in CMOS Image Sensors Caused by Strong Electromagnetic Pulses"*,
  Journal of Electromagnetic Engineering and Science 24(2). Umbral de
  interrupción funcional (95% de probabilidad de falla): **40.4 kV/m**,
  pulso de 71.2 ns de ancho, 1 Hz de repetición. Grupo de investigación
  distinto (instituciones chinas de física/microondas), sin relación con
  el paper cuestionado.
- **Flight controller — sin literatura específica nueva.** El upset de
  lógica de vuelo ya está cubierto conceptualmente por Lee et al. (§5.1,
  corrupción de PWM) — no se encontró un segundo estudio independiente
  específico de umbral de disrupción de un flight controller genérico bajo
  onda continua (que es, precisamente, lo que haría falta para recalibrar
  P2-D con datos en vez de con la convención de -10dB).
- **BMS/MOSFET — hueco real, sin resultado útil.** La búsqueda no encontró
  ningún paper que mida un umbral de daño por HPM/EMP específico para un
  MOSFET de gestión de batería. Sí aparece literatura sobre modos de falla
  general de MOSFET (fallo en cortocircuito, ruptura por avalancha) y sobre
  ataques IEMI que distorsionan la *estimación* de la batería (el paper de
  Tao et al. de §5.2), pero nada que mida un campo/potencia de quemado
  físico real para este componente específico. **Este es el subsistema
  candidato más claro para que el usuario busque por su cuenta** —
  probablemente en literatura de electrónica de potencia/automotriz sobre
  endurecimiento ante EMP o descargas transitorias, no en literatura de
  guerra electrónica per se.

**Patrón que se repite y vale la pena anotar**: los tres mecanismos de
"upset por pulso" confirmados hasta ahora en fuentes independientes (Lee
et al. 55 kV/m, Yang et al. 40.4 kV/m, y el umbral dBm de Xing et al.
convertido a través de la cadena de acoplamiento) caen consistentemente
uno o dos órdenes de magnitud por encima de los umbrales de daño/upset que
usa este proyecto (150-487 V/m). No es evidencia de que el proyecto esté
mal calibrado — al contrario, es una señal débil pero repetida de que el
rango de campo donde opera el arma modelada (cientos de V/m) es
consistente con destrucción térmica, no con estos mecanismos de upset por
pulso ultra-corto, que requieren mucho más campo.

---

## 6. Relación con este simulador — qué representa y qué no

| En el simulador | Sistema real que lo inspira |
|---|---|
| `HPMWeapon` (cañón estático, cono direccional) | Sistemas fijos tipo Leonidas/THOR/Hurricane-3000 |
| `HPMissile` (misil de área, soft-kill) | CHAMP (histórico) |
| `RadarSystem` (detección) | La capa de radar que precede a cualquier sistema real de la tabla §3 |
| `Jammer` (negación de enlace, continuo) | La capa de guerra electrónica/jamming clásica — con la misma limitación real que el jamming de verdad: no funciona contra el escenario "drones de fibra óptica" que Ucrania reporta como desafío emergente (este simulador tampoco lo modela — sería una extensión futura fiel a la realidad) |
| Blindaje heterogéneo por dron | Abstracción de que un enjambre real mezcla unidades con distinto nivel de protección/apantallado |

**Qué NO representa este simulador** (limitaciones honestas, ya en
`FISICA_Y_MATEMATICA.md` §4): no modela láseres, no distingue potencia pico
de promedio, no tiene el desafío de drones por fibra óptica, y usa
aproximaciones de ingeniería (sigmoides, ganancia de antena simplificada)
en vez de simulación electromagnética de campo completo (que requeriría
software especializado tipo FDTD/método de momentos, fuera del alcance de
un simulador interactivo en tiempo real).

---

## 7. Nota sobre uso responsable de esta información

Todo lo citado acá es información pública — reportes de prensa
especializada en defensa, comunicados de las propias empresas e informes
de mercado abiertos. No hay acá información técnica de diseño, manuales de
construcción, ni nada que no esté ya publicado. El propósito de este
documento (y del simulador en general) es educativo/de investigación: para
que el usuario entienda la física real y el contexto de una tecnología de
la que se habla cada vez más en la prensa de defensa, no para replicar
hardware real.

---

## 8. Para seguir investigando por tu cuenta

- **Términos de búsqueda útiles**: "high power microwave weapon",
  "directed energy weapon counter-UAS", "Leonidas Epirus", "IFPC-HPM",
  "Hurricane-3000 Norinco", "counter-drone swarm defense doctrine".
- **Fuentes de prensa especializada que citamos y son buenas para
  seguir**: Army Recognition, Breaking Defense, The War Zone (twz.com),
  Defense Post.
- **El paper técnico más relevante para este proyecto**:
  [arXiv:2602.08477](https://arxiv.org/abs/2602.08477) — el marco de
  simulación multi-física que inspiró el modelo `friis` de este simulador.
