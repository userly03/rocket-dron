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

Además de arXiv:2602.08477 (ver `FISICA_Y_MATEMATICA.md` §6), hay líneas de
investigación activas relevantes:

- **Efectos de pulso electromagnético en componentes específicos**: estudios
  2025 sobre daño inducido por microondas en amplificadores de potencia GaN
  HEMT (publicado en *Scientific Reports*) — directamente relevante a
  `HPM_FREQUENCY_GHZ` y la idea de acoplamiento resonante por tipo de
  componente que quedó anotada como mejora futura.
  ([PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9547885/))
- **Efectos de HPM banda-C sobre sistemas UAV**: publicado en el *Journal of
  Electromagnetic Waves and Applications* (2025).
- **Fundamentos tecnológicos de efectos HPM para guerra electromagnética de
  próxima generación** — cobertura de *Military Aerospace* sobre el estado
  de la investigación en efectos de armas HPM.
  ([Military Aerospace](https://www.militaryaerospace.com/power/article/14276116/electromagnetic-warfare-high-power-microwave-weapons-effects))

Estas líneas de investigación son exactamente las que sustentarían, con
más rigor, los ítems ya anotados en el roadmap de `FISICA_Y_MATEMATICA.md`
§7 (acoplamiento resonante por frecuencia, potencia pico vs. promedio).

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
