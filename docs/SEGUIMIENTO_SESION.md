# Seguimiento: papers, hallazgos y frontend pendiente

Documento único para no perder el hilo. Se actualiza cada vez que algo
cambia de estado. Todo lo de acá tiene el detalle completo en
`ESTADO_DEL_ARTE_HPM.md`, `ESTADO_DEL_ARTE_BIOMIMESIS.md` y
`research/NOTA_ESTIMADOR_CIEGO.md` — esto es el mapa corto para ubicarse.

---

## 1. Papers — estado y para qué sirve cada uno

### 1.1 HPM / daño en drones — verificados, usables

| Paper | Qué aporta | Sirve para |
|---|---|---|
| Mao et al. (2023), IEEE Trans. Plasma Science | Hardware real: drones irradiados, fallan ESC y motor de rotor | Validar cualitativamente el subsistema ESC. **Falta el PDF completo** (paywall IEEE) |
| Xing et al. (2025), Micromachines | GaN HEMT (componente del ESC): sobrevive 800 pulsos a 42.5 dBm, falla en 10 a 43 dBm | Calibración de componente para ESC — transición abrupta real |
| Zhao, J. et al. (2025), Scientific Reports | GaN HEMT: quemado catastrófico a ~53 dBm (~200W), mecanismo de avalancha | Segundo punto de calibración de ESC, mecanismo distinto al de Xing |
| Zhao, J. et al. (2022), Scientific Reports | GaN HEMT: interferencia/corrimiento de umbral, NO destructivo | Contexto del mecanismo previo al quemado; no es específico de drones |
| Khalil, Wang, Choi, arXiv:2510.16495 (v2) | Framework independiente, umbrales en energía de pulso (J), sensibilidad: alcance domina | Contraste metodológico — otra forma de medir lo mismo |
| Lee et al. (2026), Drones (MDPI) | Mecanismo "soft-kill": corrupción de PWM, 55 kV/m, RECUPERABLE con reinicio | Confirma que existe un mecanismo distinto al térmico — pero a un campo 2 órdenes de magnitud arriba del umbral de daño del proyecto (487 V/m). **No aplica al rango de operación del arma modelada** |
| Kubacki et al. (2025), Electronics (MDPI) | Umbrales EMC reales: 10 V/m (estándar), 15-30 V/m (disrupción), 200 V/m (militar) | Chequeo de orden de magnitud del umbral de *upset* ya calibrado del proyecto (154 V/m) — no lo recalibra con precisión, pero confirma que no es descabellado |
| Yang et al. (2024), J. Electromagnetic Eng. and Science | Cámara CMOS: 40.4 kV/m para 95% interrupción funcional, pulso corto | Mismo patrón que Lee et al. — mecanismo real, campo muy por encima del rango del proyecto |
| Micromachines 17(9):1054 (2025) | LNA de RF (GaAs pHEMT, no específico de GPS): quemado a 45 dBm/2GHz/43ns | Componente análogo al de GPS/GNSS LNA, mecanismo similar al de ESC |

### 1.2 Descartados o marcados como alerta

- **"GPS LNA burnout ≈ 150 V/m"** (de una búsqueda web): es el mismo número de la Tabla 1 del paper cuestionado (arXiv:2602.08477) reapareciendo en el resumen de búsqueda — **circular, no es fuente independiente**. Descartado.
- **Revista *Iranian Journal of Chemical and Chemical Engineering*** publicando sobre EMP en drones — revista fuera de campo, señal de bajo estándar. Descartado.
- **arXiv:2306.05111** ("AutoCharge") — el usuario lo encontró pero es sobre estaciones de carga autónoma para drones, sin relación con HPM/EMP. Descartado.

### 1.3 Encontrados, no verificados (paywall/bloqueo)

- *"Investigation on Falling and Damage Mechanisms of UAV Illuminated by HPM Pulses"* (ResearchGate).

### 1.4 Huecos reales — todavía sin buen paper

- **BMS/MOSFET**: ningún resultado de daño físico por HPM/EMP específico para MOSFET de gestión de batería. Candidato: literatura de electrónica de potencia/automotriz sobre endurecimiento ante EMP o transitorios — **pendiente que el usuario busque, dominio distinto al de guerra electrónica**.
- **Flight controller** bajo onda continua: nada más allá del mecanismo de Lee et al. (pulsado).
- **Mao et al. 2023 completo**: seguimos sin el PDF (paywall IEEE Xplore).

### 1.5 Biomimesis — verificados

| Paper | Qué aporta | Estado de aplicación |
|---|---|---|
| Chen & Kolokolnikov (2014), arXiv:1403.3250 | Régimen no monótono: fuerza del depredador determina escape/confusión/persecución/captura | Hipótesis testeable con las herramientas ya existentes (barrido de potencia × formación) — no implementado |
| Olson et al. (2013), arXiv:1209.3330 | Confusión del depredador basta para evolucionar enjambramiento (algoritmo evolutivo) | Anclaje teórico para P3-B (coevolución), ya implementado — no cambia código |
| Attanasi et al., Nature Physics / arXiv:1303.7097 | Ondas de agitación en bandadas: la alarma se propaga más rápido que el grupo | Brecha real encontrada: `P2-E` (amenaza) es individual, no se propaga a vecinos — no implementado |
| Nature Communications (raptores, PMC9399121) | Rapaces reales apuntan a un punto fijo del enjambre, no persiguen individuos | Valida una decisión ya tomada: `HPMissileSystem.lanzar` ya apunta al centroide — no requiere cambio |

---

## 2. Qué hicimos esta sesión (para no repetirlo)

1. Cerramos las 5 piezas del audit de frontend (riesgo latente, radar/tracks,
   WTA, laboratorio, coevolución genética) — todo commiteado y verificado
   en vivo en el navegador.
2. Escribimos `research/NOTA_ESTIMADOR_CIEGO.md` (+ traducción al inglés,
   sin publicar) — el hallazgo del estimador Monte Carlo ciego,
   autocontenido, no depende de ninguna fuente externa.
3. Catalogamos y verificamos 9 papers de HPM/daño en drones (con texto
   completo de 10 de los ~11 PDFs que el usuario descargó).
4. **Nos corregimos dos veces en el camino** (parte del método, no un
   error a esconder): primero, un análisis apurado que decía que el
   "soft-kill" era una brecha del proyecto — resultó ser el ítem `P2-D`,
   ya cerrado. Segundo, una comparación de escalas de campo mal hecha
   (55 kV/m de Lee et al. contra 487 V/m del proyecto, dos órdenes de
   magnitud de diferencia, no "el mismo patrón").
5. Barrimos literatura para los 4 subsistemas restantes del modelo de
   daño (GPS, cámara, flight controller, BMS) — 2 confirmaciones nuevas,
   1 alerta de circularidad descartada, 2 huecos honestos.
6. Catalogamos 4 papers de biomimesis/dinámica de enjambres, con
   distinción clara entre lo que ya está implementado, lo que es solo
   anclaje teórico, y una brecha real encontrada (propagación de alarma).

**Nada de la investigación de papers tocó código todavía** — todo quedó en
`docs/` y `research/`, documentado y citable, a la espera de decidir qué
vale la pena portar.

---

## 3. Frontend — qué falta exponer

De todo el trabajo de esta sesión, hay **una sola pieza con código ya
funcionando en el backend y cero interfaz**:

- **Panel "Experimentos Monte Carlo"** — expone `/api/experiments`, que es
  literalmente el estimador que corregimos y documentamos
  (`fraccion_media` + IC por bootstrap, CV, percentiles, y el indicador
  viejo `aniquilación total` al lado para que se vea la diferencia en
  vivo). Hoy es invisible en la app — el usuario configuraría arma,
  réplicas y cantidad de drones, y vería el resultado con su intervalo,
  igual que en la nota técnica pero interactivo.

Nada de lo investigado sobre papers (HPM de otras fuentes, biomimesis)
tiene todavía una pieza de código que mostrar en el frontend — son
hallazgos de literatura, no features implementadas. El único candidato de
esa línea que SÍ tocaría código (y por lo tanto eventualmente el frontend)
es la propagación de alarma entre drones (§1.5, brecha real de
`P2-E`) — pero no está implementado, es una idea evaluada, no una función
existente sin exponer.

**Pendiente de decisión, no de investigación**: ¿arrancamos con el panel
de Experimentos Monte Carlo (código ya existe, solo falta la UI), o
priorizamos que el usuario consiga el BMS/MOSFET y Mao et al. antes de
tocar más frontend?
