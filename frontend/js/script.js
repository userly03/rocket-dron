/**
 * Simulador EW — orquestación principal, demo y modos de vista.
 * El renderizado espacial (mapa 3D) vive en render3d.js; este archivo
 * maneja estado de UI, llamadas a la API y el WebSocket.
 */
(function () {
  "use strict";

  const apiOverride = new URLSearchParams(window.location.search).get("api");
  const API_BASE = apiOverride || (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : `${window.location.protocol}//${window.location.hostname}:8000`);

  const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws";

  const canvas3d = document.getElementById("tactical-map-3d");

  const ui = {
    demoBanner: document.getElementById("demo-banner"),
    connectionStatus: document.getElementById("connection-status"),
    connectionLabel: document.getElementById("connection-label"),
    metricTotal: document.getElementById("metric-total"),
    metricActive: document.getElementById("metric-active"),
    metricNeutralized: document.getElementById("metric-neutralized"),
    metricRiesgo: document.getElementById("metric-riesgo"),
    riskList: document.getElementById("risk-list"),
    riskCount: document.getElementById("risk-count"),
    metricSuccess: document.getElementById("metric-success"),
    metricTime: document.getElementById("metric-time"),
    metricLastFire: document.getElementById("metric-last-fire"),
    metricMissilesActive: document.getElementById("metric-missiles-active"),
    metricMunition: document.getElementById("metric-munition"),
    metricEnergy: document.getElementById("metric-energy"),
    metricPeak: document.getElementById("metric-peak"),
    munitionDisplay: document.getElementById("munition-display"),
    simStateBadge: document.getElementById("sim-state-badge"),
    logList: document.getElementById("log-list"),
    mapTitle: document.getElementById("map-title"),
    btnCameraTop: document.getElementById("btn-camera-top"),
    toggleTracks: document.getElementById("toggle-tracks"),
    powerSlider: document.getElementById("power-slider"),
    powerValue: document.getElementById("power-value"),
    directionSlider: document.getElementById("direction-slider"),
    directionValue: document.getElementById("direction-value"),
    missilePowerSlider: document.getElementById("missile-power-slider"),
    missilePowerValue: document.getElementById("missile-power-value"),
    missileRadiusSlider: document.getElementById("missile-radius-slider"),
    missileRadiusValue: document.getElementById("missile-radius-value"),
    missileAngleSlider: document.getElementById("missile-angle-slider"),
    missileAngleValue: document.getElementById("missile-angle-value"),
    missileAutoAim: document.getElementById("missile-auto-aim"),
    missileGuiado: document.getElementById("missile-guiado"),
    jamPowerSlider: document.getElementById("jam-power-slider"),
    jamPowerValue: document.getElementById("jam-power-value"),
    jamDirectionSlider: document.getElementById("jam-direction-slider"),
    jamDirectionValue: document.getElementById("jam-direction-value"),
    jamApertureSlider: document.getElementById("jam-aperture-slider"),
    jamApertureValue: document.getElementById("jam-aperture-value"),
    btnJamStart: document.getElementById("btn-jam-start"),
    btnJamStop: document.getElementById("btn-jam-stop"),
    formationSelect: document.getElementById("formation-select"),
    swarmSize: document.getElementById("swarm-size"),
    scenarioSelect: document.getElementById("scenario-select"),
    btnLoadScenario: document.getElementById("btn-load-scenario"),
    btnFire: document.getElementById("btn-fire"),
    btnLaunchMissile: document.getElementById("btn-launch-missile"),
    btnReloadMissile: document.getElementById("btn-reload-missile"),
    btnWtaPlan: document.getElementById("btn-wta-plan"),
    btnWtaExecute: document.getElementById("btn-wta-execute"),
    wtaSummary: document.getElementById("wta-summary"),
    wtaTotal: document.getElementById("wta-total"),
    wtaList: document.getElementById("wta-list"),
    btnLabSensibilidad: document.getElementById("btn-lab-sensibilidad"),
    labSensDistancia: document.getElementById("lab-sens-distancia"),
    labSensResult: document.getElementById("lab-sens-result"),
    labSensBars: document.getElementById("lab-sens-bars"),
    labSensAmenazas: document.getElementById("lab-sens-amenazas"),
    btnLabDosis: document.getElementById("btn-lab-dosis"),
    labDosisResult: document.getElementById("lab-dosis-result"),
    btnLabSubsistemas: document.getElementById("btn-lab-subsistemas"),
    labSubsDistancia: document.getElementById("lab-subs-distancia"),
    labSubsResult: document.getElementById("lab-subs-result"),
    coevoGeneraciones: document.getElementById("coevo-generaciones"),
    coevoPoblacion: document.getElementById("coevo-poblacion"),
    coevoReplicas: document.getElementById("coevo-replicas"),
    btnCoevoStart: document.getElementById("btn-coevo-start"),
    coevoProgress: document.getElementById("coevo-progress"),
    coevoStatusLine: document.getElementById("coevo-status-line"),
    coevoGenBars: document.getElementById("coevo-gen-bars"),
    coevoResult: document.getElementById("coevo-result"),
    btnStart: document.getElementById("btn-start"),
    btnStop: document.getElementById("btn-stop"),
    btnReset: document.getElementById("btn-reset"),
    speedButtons: document.querySelectorAll(".speed-btn"),
    chartEffectiveness: document.getElementById("chart-effectiveness"),
    chartHeatmap: document.getElementById("chart-heatmap"),
    chartSpectrum: document.getElementById("chart-spectrum"),
    shotHistoryList: document.getElementById("shot-history-list"),
    viewButtons: document.querySelectorAll(".view-btn"),
  };

  const state = {
    viewMode: "tactical",
    field: { width: 1000, height: 1000 },
    munition: { total: 10, restante: 10 },
    missilesActivos: 0,
    hpm: { potencia: 45, direccion: 45, apertura_cono: 30, origen_x: 0, origen_y: 0, disparos: 0 },
    analytics: null,
    simEstado: "detenida",
    simTime: 0,
    timeScale: 1,
    conteoEstados: { activo: 0, danado: 0, neutralizado: 0 },
    lastFireWallTime: null,
    processedLogKeys: new Set(),
    userAdjustingHpm: false,
    demoRunning: false,
    wtaPlan: null,
    coevoJobId: null,
    coevoPollTimer: null,
  };

  let wsClient = null;

  function updateMunitionUI() {
    const { total, restante } = state.munition;
    ui.munitionDisplay.textContent = `${restante} / ${total}`;
    ui.metricMunition.textContent = `${restante}/${total}`;
    ui.metricMissilesActive.textContent = state.missilesActivos;
    ui.btnLaunchMissile.disabled = restante <= 0;

    const empty = restante <= 0;
    const low = !empty && restante <= 2;
    ui.munitionDisplay.classList.toggle("munition-low", low);
    ui.munitionDisplay.classList.toggle("munition-empty", empty);
    ui.metricMunition.classList.toggle("munition-low", low);
    ui.metricMunition.classList.toggle("munition-empty", empty);
  }

  function updateMissilesSummary(missiles) {
    if (!missiles) return;
    state.munition = { total: missiles.municion_total ?? 10, restante: missiles.municion_restante ?? 0 };
    state.missilesActivos = (missiles.misiles || []).filter(
      (m) => m.estado === "lanzado" || m.estado === "volando"
    ).length;
    updateMunitionUI();
  }

  function updateAnalyticsUI(analytics) {
    if (!analytics) return;
    state.analytics = analytics;
    Charts.updatePhysicsPanel(document.getElementById("physics-panel"), analytics.physics);
    Charts.drawEffectiveness(ui.chartEffectiveness, analytics.effectiveness);
    Charts.drawHeatmap(ui.chartHeatmap, analytics.heatmap);
    Charts.drawSpectrum(ui.chartSpectrum, analytics.spectrum);
    Charts.updateShotHistory(ui.shotHistoryList, analytics.shot_history);

    if (analytics.metrics) {
      ui.metricEnergy.textContent = `${analytics.metrics.total_energy_mj_mega} MJ`;
      ui.metricPeak.textContent = `${analytics.metrics.peak_power_gw} GW`;
    }
  }

  const SUBSISTEMA_LABEL = {
    gps_gnss_lna: "GPS/GNSS (LNA)",
    flight_controller: "Controlador de vuelo",
    esc_gate_oxide: "ESC (gate oxide)",
    camara_cmos: "Cámara (CMOS)",
    bms_mosfet: "BMS (MOSFET)",
  };

  // Riesgo latente (P2-D): drones que recibieron un impacto que no los
  // neutralizó de inmediato pero los deja en una ventana de vulnerabilidad
  // — pueden recuperarse o fallar más tarde. Ver drone.riesgo_latente_por_s
  // en el motor; acá solo se lista lo que ya viene calculado.
  function updateRiesgoLatente(drones) {
    if (!drones) return;
    const enRiesgo = drones.filter((d) => (d.riesgo_latente_severidad ?? 0) > 0);
    ui.metricRiesgo.textContent = enRiesgo.length;
    ui.riskCount.textContent = enRiesgo.length;
    if (enRiesgo.length === 0) {
      ui.riskList.innerHTML = '<li class="shot-empty">Ningún dron en ventana de riesgo</li>';
      return;
    }
    enRiesgo.sort((a, b) => (b.riesgo_latente_severidad ?? 0) - (a.riesgo_latente_severidad ?? 0));
    ui.riskList.innerHTML = enRiesgo.slice(0, 12).map((d) => {
      const sub = SUBSISTEMA_LABEL[d.subsistema_en_riesgo] ?? d.subsistema_en_riesgo ?? "desconocido";
      const pct = Math.round((d.riesgo_latente_severidad ?? 0) * 100);
      return `<li>#${d.id} — ${sub} — ${pct}%</li>`;
    }).join("");
  }

  // Plan óptimo arma-blanco (P3-A, WTA): agrupa lo que el RADAR detecta
  // (tracks, no la posición real — ver P2-G) y sugiere qué disparo
  // conviene a cuál grupo. Es una sugerencia para confirmar, no un
  // disparo automático — el usuario decide si ejecutarla.
  function bearingHaciaCentroide(cx, cy) {
    const dx = cx - state.hpm.origen_x;
    const dy = cy - state.hpm.origen_y;
    return ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;
  }

  function renderWtaPlan(plan) {
    state.wtaPlan = plan;
    const asign = plan.asignacion || [];
    if (asign.length === 0) {
      ui.wtaSummary.classList.add("hidden");
      ui.btnWtaExecute.classList.add("hidden");
      ui.wtaList.innerHTML = '<li class="shot-empty">Sin blancos detectados o sin disparos disponibles</li>';
      window.Render3D?.setWtaPlan(null);
      return;
    }
    ui.wtaTotal.textContent = plan.bajas_esperadas_total.toFixed(2);
    ui.wtaSummary.classList.remove("hidden");
    ui.btnWtaExecute.classList.remove("hidden");
    // Agrupado por (cluster, arma): con pocos clusters y mucho presupuesto
    // disponible, la asignación óptima suele apilar varios disparos del
    // mismo tipo sobre el mismo grupo — listar cada uno por separado sería
    // repetitivo sin agregar información.
    const grupos = new Map();
    for (const a of asign) {
      const key = `${a.cluster_id}:${a.tipo}`;
      const g = grupos.get(key) ?? { ...a, n: 0, bajas_suma: 0 };
      g.n += 1;
      g.bajas_suma += a.bajas_esperadas_aisladas;
      grupos.set(key, g);
    }
    ui.wtaList.innerHTML = [...grupos.values()].map((g) => {
      const arma = g.tipo === "canion" ? "🔥 Cañón" : "🚀 Misil";
      const cuenta = g.n > 1 ? `${g.n}× ` : "";
      return `<li class="wta-${g.tipo}">${cuenta}${arma} → cluster ${g.cluster_id} (${g.cluster_tamano} drones), ~${g.bajas_suma.toFixed(2)} bajas esp.</li>`;
    }).join("");
    window.Render3D?.setWtaPlan(plan);
  }

  // Laboratorio (P2-A/P2-B/P1-C): análisis puramente informativos, ninguno
  // toca el estado de la simulación en vivo — cada botón llama a un
  // endpoint de solo lectura y muestra el resultado acá mismo.
  function labBarRow(label, valor01, noCalibrado, valorTexto) {
    const pct = Math.max(0, Math.min(100, valor01 * 100));
    return `<div class="lab-bar-row${noCalibrado ? " no-calibrado" : ""}">
      <span class="lab-bar-label" title="${label}">${label}</span>
      <span class="lab-bar-track"><span class="lab-bar-fill" style="width:${pct}%"></span></span>
      <span class="lab-bar-value">${valorTexto}</span>
    </div>`;
  }

  async function runLabButton(btn, fn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳ CALCULANDO...";
    try {
      await fn();
    } catch (e) {
      addLog(`Laboratorio: ${e.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  // Coevolución (P3-B): un job en background (POST arranca, GET pollea) —
  // una corrida real tarda demasiado para un solo request síncrono. Ver
  // src/api/coevolucion_jobs.py.
  function renderCoevoProgress(job) {
    ui.coevoProgress.classList.remove("hidden");
    ui.coevoStatusLine.textContent =
      `Generación ${job.progreso.length}/${job.parametros.n_generaciones} — corriendo...`;
    ui.coevoGenBars.innerHTML = job.progreso.map((p) =>
      `<div class="coevo-gen-row">
        <span class="lab-bar-label">Gen ${p.generacion + 1}</span>
        <span>arma media=${p.fitness_arma_media.toFixed(4)}</span>
        <span>defensa media=${p.fitness_defensa_media.toFixed(4)}</span>
      </div>`
    ).join("");
  }

  function renderCoevoResultado(resultado) {
    const armaF = resultado.mejor_arma_final;
    const defF = resultado.mejor_defensa_final;
    const fmtFrontera = (frontera, campo1, campo2) =>
      frontera.length
        ? frontera.map((p) => `(${p[campo1]}, ${p[campo2]})`).join(" · ")
        : "sin puntos no-dominados";
    ui.coevoResult.innerHTML = `
      <div><strong>Arma final:</strong> potencia=${armaF.potencia_kw}kW, apertura=${armaF.apertura_cono}°, duty_cycle=${armaF.duty_cycle}</div>
      <div><strong>Defensa final:</strong> formación=${defF.formacion}, cantidad=${defF.cantidad}</div>
      <div style="margin-top:6px">Frontera de Pareto arma (potencia_kw, fracción neutralizada):<br>${fmtFrontera(resultado.frontera_pareto_arma, "potencia_kw", "fraccion_neutralizada")}</div>
      <div style="margin-top:4px">Frontera de Pareto defensa (cantidad, supervivencia):<br>${fmtFrontera(resultado.frontera_pareto_defensa, "cantidad", "supervivencia")}</div>
    `;
    ui.coevoResult.classList.remove("hidden");
  }

  function pollCoevoJob(jobId) {
    state.coevoJobId = jobId;
    if (state.coevoPollTimer) clearInterval(state.coevoPollTimer);
    state.coevoPollTimer = setInterval(async () => {
      let job;
      try {
        job = await api(`/api/coevolucion/status/${jobId}`);
      } catch (e) {
        clearInterval(state.coevoPollTimer);
        addLog(`Coevolución: ${e.message}`, "error");
        ui.btnCoevoStart.disabled = false;
        return;
      }
      renderCoevoProgress(job);
      if (job.estado === "completado") {
        clearInterval(state.coevoPollTimer);
        ui.coevoStatusLine.textContent = `Completado — ${job.parametros.n_generaciones} generaciones.`;
        renderCoevoResultado(job.resultado);
        addLog("Coevolución: corrida completada", "info");
        ui.btnCoevoStart.disabled = false;
      } else if (job.estado === "error") {
        clearInterval(state.coevoPollTimer);
        ui.coevoStatusLine.textContent = `Error: ${job.error}`;
        addLog(`Coevolución: ${job.error}`, "error");
        ui.btnCoevoStart.disabled = false;
      }
    }, 1500);
  }

  function clearWtaPlan() {
    state.wtaPlan = null;
    ui.wtaSummary.classList.add("hidden");
    ui.btnWtaExecute.classList.add("hidden");
    ui.wtaList.innerHTML = "";
    window.Render3D?.setWtaPlan(null);
  }

  function updateMetrics(snapshot) {
    const c = snapshot.conteo_estados || state.conteoEstados;
    const total = Object.values(c).reduce((a, b) => a + b, 0) || 0;
    ui.metricTotal.textContent = total;
    ui.metricActive.textContent = (c.activo || 0) + (c.danado || 0);
    ui.metricNeutralized.textContent = c.neutralizado || 0;
    ui.metricSuccess.textContent = `${total ? Math.round(((c.neutralizado || 0) / total) * 100) : 0}%`;
    ui.metricTime.textContent = `${(snapshot.tiempo ?? state.simTime).toFixed(1)} s`;
    if (state.lastFireWallTime) {
      const s = Math.floor((Date.now() - state.lastFireWallTime) / 1000);
      ui.metricLastFire.textContent = s === 0 ? "Ahora" : `Hace ${s} s`;
    }
  }

  function updateSimBadge(est) {
    const b = ui.simStateBadge;
    b.className = "sim-badge " + ({ ejecutando: "sim-running", pausada: "sim-paused" }[est] || "sim-stopped");
    b.textContent = ({ ejecutando: "EJECUTANDO", pausada: "PAUSADA" }[est] || "DETENIDA");
  }

  function setConnectionStatus(st) {
    const dot = ui.connectionStatus.querySelector(".status-dot");
    dot.className = "status-dot " + ({ connected: "status-connected", connecting: "status-connecting" }[st] || "status-disconnected");
    ui.connectionLabel.textContent = ({ connected: "Conectado", connecting: "Reconectando…" }[st] || "Desconectado");
  }

  function addLog(msg, type) {
    const li = document.createElement("li");
    li.className = `log-entry log-${type || "info"}`;
    li.innerHTML = `<span class="log-time">[${new Date().toLocaleTimeString("es-ES", { hour12: false })}]</span> ${msg}`;
    ui.logList.insertBefore(li, ui.logList.firstChild);
    while (ui.logList.children.length > 100) ui.logList.removeChild(ui.logList.lastChild);
  }

  function formatBackendLog(entry) {
    const key = `${entry.tick}-${entry.evento}-${JSON.stringify(entry.datos)}`;
    if (state.processedLogKeys.has(key)) return null;
    state.processedLogKeys.add(key);
    const d = entry.datos || {};
    switch (entry.evento) {
      case "simulacion_inicializada": return { msg: `Sistema init — ${d.drones} drones`, type: "info" };
      case "simulacion_iniciada": return { msg: "Simulación iniciada", type: "start" };
      case "simulacion_pausada": return { msg: "Simulación pausada", type: "stop" };
      case "demo_iniciada": return { msg: `Demo: ${d.drones} drones ${d.formacion}`, type: "start" };
      case "escenario_cargado": return { msg: `Escenario cargado: ${d.nombre}`, type: "info" };
      case "velocidad_cambiada": return { msg: `Velocidad de simulación: ${d.escala}x`, type: "info" };
      case "hpm_disparo":
        state.lastFireWallTime = Date.now();
        window.Render3D?.triggerCannonPulse(state.hpm.origen_x, state.hpm.origen_y);
        window.Render3D?.flashHits(d.impactos);
        return { msg: `Cañón — ${d.potencia}kW @ ${Math.round(d.direccion)}° (${d.neutralizados} neutralizados)`, type: "fire" };
      case "misil_lanzado": return { msg: `Misil ${d.misil_id} lanzado (${d.municion_restante} restantes)`, type: "missile" };
      case "misil_detonado":
        window.Render3D?.flashHits(d.impactos);
        return { msg: `Detonación EMP — ${d.neutralizados}/${d.afectados} soft-kill`, type: "missile" };
      case "misil_recarga": return { msg: `Recarga +${d.añadido} misiles`, type: "info" };
      case "jamming_iniciado": return { msg: `Jamming activado — ${d.potencia}kW @ ${Math.round(d.direccion)}°`, type: "fire" };
      case "jamming_detenido": return { msg: "Jamming desactivado", type: "stop" };
      case "dron_interferido": return { msg: `Enlace perdido — drones: ${d.drones.join(", ")}`, type: "missile" };
      case "dron_recuperado": return { msg: `Enlace recuperado — drones: ${d.drones.join(", ")}`, type: "info" };
      default: return null;
    }
  }

  function applySnapshot(snap) {
    if (snap.field) state.field = snap.field;
    if (snap.hpm && !state.userAdjustingHpm) {
      state.hpm = { ...state.hpm, ...snap.hpm };
      ui.powerSlider.value = state.hpm.potencia;
      ui.powerValue.textContent = Math.round(state.hpm.potencia);
      ui.directionSlider.value = Math.round(state.hpm.direccion);
      ui.directionValue.textContent = Math.round(state.hpm.direccion);
    }
    if (snap.estado) { state.simEstado = snap.estado; updateSimBadge(snap.estado); }
    if (snap.tiempo !== undefined) state.simTime = snap.tiempo;
    if (snap.time_scale !== undefined) setActiveSpeedButton(snap.time_scale);
    if (snap.conteo_estados) state.conteoEstados = snap.conteo_estados;
    if (snap.missiles) updateMissilesSummary(snap.missiles);
    if (snap.analytics) updateAnalyticsUI(snap.analytics);
    window.Render3D?.updateSnapshot(snap);
    updateMetrics(snap);
    updateRiesgoLatente(snap.drones);
    snap.logs_recientes?.forEach((e) => { const f = formatBackendLog(e); if (f) addLog(f.msg, f.type); });
  }

  async function api(path, opts) {
    const r = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(typeof e.detail === "string" ? e.detail : "Error API");
    }
    return r.json();
  }

  async function loadScenarios() {
    try {
      const { escenarios } = await api("/api/scenarios");
      escenarios.forEach((esc) => {
        const opt = document.createElement("option");
        opt.value = esc.id;
        opt.textContent = esc.nombre;
        opt.title = esc.descripcion || "";
        ui.scenarioSelect.appendChild(opt);
      });
    } catch (err) {
      addLog(`Error cargando escenarios: ${err.message}`, "error");
    }
  }

  async function loadInitialState() {
    try {
      const status = await api("/api/status");
      applySnapshot(status);
      addLog("Sistema cargado — modos Táctico / Físico / Espectro disponibles", "info");
    } catch (err) {
      addLog(`Error API: ${err.message}`, "error");
    }
  }

  async function runAutoDemo() {
    try {
      const cfg = await api("/api/demo/config");
      if (!cfg.enabled) return;

      state.demoRunning = true;
      ui.demoBanner.classList.remove("hidden");
      ui.formationSelect.value = cfg.formacion;
      ui.swarmSize.value = cfg.drones;

      await api("/api/demo/start", { method: "POST" });
      addLog(`¡DEMO EN EJECUCIÓN! — ${cfg.drones} drones formación ${cfg.formacion}`, "start");

      const baseBanner = ui.demoBanner.textContent;
      const delayS = Math.max(1, Math.round(cfg.missile_delay_s || 3));
      let remaining = delayS;
      ui.demoBanner.textContent = `${baseBanner} — MISIL EN ${remaining}s`;
      const countdown = setInterval(() => {
        remaining -= 1;
        ui.demoBanner.textContent = remaining > 0
          ? `${baseBanner} — MISIL EN ${remaining}s`
          : baseBanner;
        if (remaining <= 0) clearInterval(countdown);
      }, 1000);

      setTimeout(async () => {
        try {
          await api("/api/missile/launch", {
            method: "POST",
            body: JSON.stringify({
              x: state.hpm.origen_x,
              y: state.hpm.origen_y,
              potencia: parseFloat(ui.missilePowerSlider.value),
              radio: parseFloat(ui.missileRadiusSlider.value),
            }),
          });
          addLog("Demo: misil HPM auto-lanzado", "missile");
        } catch (e) {
          addLog(`Demo misil: ${e.message}`, "error");
        }
      }, delayS * 1000);
    } catch (err) {
      addLog(`Demo: ${err.message}`, "error");
    }
  }

  function setViewMode(mode) {
    state.viewMode = mode;
    document.body.classList.remove("view-tactical", "view-physical", "view-spectrum");
    document.body.classList.add(`view-${mode}`);
    ui.viewButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.view === mode));

    const titles = { tactical: "🗺️ Mapa Táctico 3D", physical: "🌡️ Mapa Físico + Calor 3D", spectrum: "📡 Modo Espectro" };
    ui.mapTitle.textContent = titles[mode] || titles.tactical;

    window.Render3D?.setViewMode(mode);
    document.getElementById("spectrum-box")?.classList.toggle("hidden", mode !== "spectrum");
  }

  function setActiveSpeedButton(scale) {
    state.timeScale = scale;
    ui.speedButtons.forEach((btn) => btn.classList.toggle("active", parseFloat(btn.dataset.speed) === scale));
  }

  function bindControls() {
    ui.viewButtons.forEach((btn) => btn.addEventListener("click", () => setViewMode(btn.dataset.view)));

    ui.btnCameraTop.addEventListener("click", () => window.Render3D?.resetCamera());
    ui.toggleTracks.addEventListener("change", () => window.Render3D?.setShowTracks(ui.toggleTracks.checked));

    ui.speedButtons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        const escala = parseFloat(btn.dataset.speed);
        try {
          const r = await api("/api/speed", { method: "POST", body: JSON.stringify({ escala }) });
          setActiveSpeedButton(r.time_scale);
          addLog(r.message, "info");
        } catch (e) { addLog(e.message, "error"); }
      });
    });

    ["pointerdown", "pointerup"].forEach((ev, i) => {
      ui.powerSlider.addEventListener(ev, () => { state.userAdjustingHpm = i === 0; });
      ui.directionSlider.addEventListener(ev, () => { state.userAdjustingHpm = i === 0; });
    });

    ui.powerSlider.addEventListener("input", () => {
      ui.powerValue.textContent = ui.powerSlider.value;
      state.hpm.potencia = parseFloat(ui.powerSlider.value);
    });
    ui.directionSlider.addEventListener("input", () => {
      ui.directionValue.textContent = ui.directionSlider.value;
      state.hpm.direccion = parseFloat(ui.directionSlider.value);
    });
    ui.missilePowerSlider.addEventListener("input", () => { ui.missilePowerValue.textContent = ui.missilePowerSlider.value; });
    ui.missileRadiusSlider.addEventListener("input", () => { ui.missileRadiusValue.textContent = ui.missileRadiusSlider.value; });
    ui.jamPowerSlider.addEventListener("input", () => { ui.jamPowerValue.textContent = ui.jamPowerSlider.value; });
    ui.jamDirectionSlider.addEventListener("input", () => { ui.jamDirectionValue.textContent = ui.jamDirectionSlider.value; });
    ui.jamApertureSlider.addEventListener("input", () => { ui.jamApertureValue.textContent = ui.jamApertureSlider.value; });
    ui.missileAngleSlider.addEventListener("input", updateMissileAngleUI);
    ui.missileAutoAim.addEventListener("change", updateMissileAngleUI);

    ui.btnStart.addEventListener("click", async () => {
      try {
        const r = await api("/api/start", { method: "POST", body: JSON.stringify({ formacion: ui.formationSelect.value, cantidad: +ui.swarmSize.value || 50 }) });
        addLog(r.message, "start");
        wsClient?.requestStatus();
      } catch (e) { addLog(e.message, "error"); }
    });

    ui.btnStop.addEventListener("click", async () => {
      try {
        const r = await api("/api/stop", { method: "POST" });
        addLog(r.message, "stop");
      } catch (e) { addLog(e.message, "error"); }
    });

    ui.btnReset.addEventListener("click", async () => {
      if (!confirm("¿Reiniciar la simulación? Se perderán drones, misiles y métricas actuales.")) return;
      try {
        const r = await api("/api/reset", { method: "POST" });
        state.processedLogKeys.clear();
        ui.logList.innerHTML = "";
        addLog(r.message, "stop");
        wsClient?.requestStatus();
      } catch (e) { addLog(e.message, "error"); }
    });

    ui.btnLoadScenario.addEventListener("click", async () => {
      const id = ui.scenarioSelect.value;
      if (!id) { addLog("Elegí un escenario para cargar", "error"); return; }
      try {
        await api(`/api/scenarios/${id}/load`, { method: "POST" });
        const opt = ui.scenarioSelect.selectedOptions[0];
        addLog(`Escenario cargado: ${opt ? opt.textContent : id}`, "info");
        wsClient?.requestStatus();
      } catch (e) { addLog(`Error al cargar escenario: ${e.message}`, "error"); }
    });

    ui.btnFire.addEventListener("click", async () => {
      try {
        const body = { potencia: +ui.powerSlider.value, direccion: +ui.directionSlider.value };
        await api("/api/fire", { method: "POST", body: JSON.stringify(body) });
        state.lastFireWallTime = Date.now();
        window.Render3D?.triggerCannonPulse(state.hpm.origen_x, state.hpm.origen_y);
        addLog(`Cañón ${body.potencia}kW @ ${body.direccion}°`, "fire");
        wsClient?.requestStatus();
      } catch (e) { addLog(e.message, "error"); }
    });

    ui.btnLaunchMissile.addEventListener("click", async () => {
      ui.btnLaunchMissile.disabled = true;
      try {
        const body = {
          x: state.hpm.origen_x,
          y: state.hpm.origen_y,
          potencia: +ui.missilePowerSlider.value,
          radio: +ui.missileRadiusSlider.value,
          guiado: ui.missileGuiado.checked,
        };
        if (!ui.missileAutoAim.checked) body.angulo = +ui.missileAngleSlider.value;
        const r = await api("/api/missile/launch", { method: "POST", body: JSON.stringify(body) });
        state.munition.restante = r.municion_restante;
        updateMunitionUI();
        addLog(`Misil HPM lanzado${body.guiado ? " (guiado)" : " (balístico)"}`, "missile");
        wsClient?.requestStatus();
      } catch (e) { addLog(e.message, "error"); }
      finally { updateMunitionUI(); }
    });

    ui.btnReloadMissile.addEventListener("click", async () => {
      try {
        const r = await api("/api/missile/reload", { method: "POST", body: JSON.stringify({ cantidad: 5 }) });
        state.munition.restante = r.municion_restante;
        updateMunitionUI();
        addLog(r.message, "info");
      } catch (e) { addLog(e.message, "error"); }
    });

    ui.btnWtaPlan.addEventListener("click", async () => {
      ui.btnWtaPlan.disabled = true;
      const textoOriginal = ui.btnWtaPlan.textContent;
      // El cálculo es Monte Carlo real (no una heurística instantánea): con
      // muchas opciones de disparo disponibles puede tardar varios
      // segundos — se avisa explícitamente para que no parezca colgado.
      // n_muestras más bajo que el default del backend (200) es un
      // trade-off deliberado acá: más rápido para una sugerencia
      // interactiva, a costa de algo más de ruido en la estimación — la
      // ejecución del plan no depende de esta precisión.
      ui.btnWtaPlan.textContent = "⏳ CALCULANDO...";
      try {
        const plan = await api("/api/targeting/plan?n_muestras=40");
        renderWtaPlan(plan);
        addLog(
          plan.asignacion.length
            ? `Plan óptimo: ${plan.asignacion.length} disparo(s), ~${plan.bajas_esperadas_total.toFixed(2)} bajas esperadas`
            : "Plan óptimo: sin blancos detectados o sin disparos disponibles",
          "info",
        );
      } catch (e) { addLog(`Error calculando plan: ${e.message}`, "error"); }
      finally { ui.btnWtaPlan.disabled = false; ui.btnWtaPlan.textContent = textoOriginal; }
    });

    ui.btnWtaExecute.addEventListener("click", async () => {
      const plan = state.wtaPlan;
      if (!plan || !plan.asignacion?.length) return;
      ui.btnWtaExecute.disabled = true;
      // El plan se calculó con el presupuesto disponible AL MOMENTO de
      // pedirlo (energía del cañón, munición de misiles) — ejecutarlo
      // dispara en orden, pero cada disparo real puede rechazarse si el
      // presupuesto ya se agotó mientras tanto (ej. otro disparo manual
      // entre medio, o el cañón sin tiempo de recargar entre tiros de este
      // mismo plan). El backend no lanza error en ese caso — devuelve un
      // mensaje de rechazo con 200 OK — así que hay que revisarlo a mano.
      let disparados = 0, rechazados = 0, fallidos = 0;
      for (const a of plan.asignacion) {
        const [cx, cy] = a.cluster_centroide;
        const direccion = bearingHaciaCentroide(cx, cy);
        try {
          if (a.tipo === "canion") {
            const r = await api("/api/fire", { method: "POST", body: JSON.stringify({ potencia: state.hpm.potencia, direccion }) });
            if (r.message?.startsWith("Disparo rechazado")) {
              rechazados += 1;
            } else {
              disparados += 1;
              state.lastFireWallTime = Date.now();
              window.Render3D?.triggerCannonPulse(state.hpm.origen_x, state.hpm.origen_y);
            }
          } else {
            const r = await api("/api/missile/launch", {
              method: "POST",
              body: JSON.stringify({ x: state.hpm.origen_x, y: state.hpm.origen_y, angulo: direccion, guiado: true }),
            });
            state.munition.restante = r.municion_restante;
            updateMunitionUI();
            disparados += 1;
          }
        } catch (e) { fallidos += 1; }
      }
      addLog(
        `Plan ejecutado: ${disparados} disparo(s) realizado(s)` +
        (rechazados ? `, ${rechazados} rechazado(s) por presupuesto` : "") +
        (fallidos ? `, ${fallidos} con error` : ""),
        rechazados || fallidos ? "error" : "fire",
      );
      wsClient?.requestStatus();
      clearWtaPlan();
      ui.btnWtaExecute.disabled = false;
    });

    ui.btnLabSensibilidad.addEventListener("click", () => runLabButton(ui.btnLabSensibilidad, async () => {
      const distancia = +ui.labSensDistancia.value || 30;
      const d = await api(`/api/sensibilidad?distancia_m=${distancia}&n_base=128&r_morris=15`);
      const params = [...d.sobol.parametros].sort((a, b) => b.st - a.st).slice(0, 8);
      ui.labSensBars.innerHTML = params.map((p) =>
        labBarRow(p.nombre, p.st, !p.calibrado, `S_T=${p.st.toFixed(3)}`)
      ).join("");
      const amenazas = d.amenazas_a_la_validez || [];
      ui.labSensAmenazas.innerHTML = amenazas.length
        ? `⚠ Domina la incertidumbre y NO está calibrado contra el paper: ` +
          amenazas.map((a) => `<strong>${a.nombre}</strong> (S_T=${a.st.toFixed(3)})`).join(", ")
        : "✅ Ningún parámetro no calibrado domina la varianza a esta distancia.";
      ui.labSensResult.classList.remove("hidden");
      addLog(`Sensibilidad @ ${distancia}m: dominan ${d.dominantes.slice(0, 3).join(", ")}`, "info");
    }));

    ui.btnLabDosis.addEventListener("click", () => runLabButton(ui.btnLabDosis, async () => {
      const d = await api("/api/dosis-respuesta?n_por_distancia=150&n_bootstrap=500");
      const a = d.ajuste, c = d.comparacion;
      const badge = c.recupera_la_calibracion
        ? '<span class="lab-badge-ok">✅ recupera la calibración</span>'
        : '<span class="lab-badge-bad">⚠ NO recupera la calibración</span>';
      ui.labDosisResult.innerHTML = `
        <div>Función de enlace: <strong>${a.link_function}</strong></div>
        <div>E₅₀ ajustado: <strong>${a.e50_v_m.toFixed(1)} V/m</strong> (IC95%: ${a.ic95_e50_v_m[0].toFixed(1)}–${a.ic95_e50_v_m[1].toFixed(1)}) — configurado: ${c.e50_configurado.toFixed(1)}</div>
        <div>Parámetro de forma: <strong>${a.parametro_forma.toFixed(3)}</strong> (IC95%: ${a.ic95_parametro_forma[0].toFixed(3)}–${a.ic95_parametro_forma[1].toFixed(3)}) — configurado: ${c.parametro_forma_configurado.toFixed(3)}</div>
        <div style="margin-top:6px">${badge}</div>
      `;
      ui.labDosisResult.classList.remove("hidden");
      addLog(`Dosis-respuesta: ${c.recupera_la_calibracion ? "recupera" : "NO recupera"} la calibración configurada`, "info");
    }));

    ui.btnLabSubsistemas.addEventListener("click", () => runLabButton(ui.btnLabSubsistemas, async () => {
      const distancia = +ui.labSubsDistancia.value || 30;
      const d = await api(`/api/subsistemas?distancia_m=${distancia}`);
      const filas = d.subsistemas.map((s) =>
        labBarRow(`${s.nombre} (E₅₀=${s.e50_v_m}V/m)`, s.probabilidad, false, `${(s.probabilidad * 100).toFixed(1)}%`)
      ).join("");
      ui.labSubsResult.innerHTML = `
        <div style="margin-bottom:6px">Campo a ${distancia}m: <strong>${d.campo_v_m} V/m</strong> — probabilidad de sistema (OR-gate): <strong>${(d.probabilidad_sistema_or_gate * 100).toFixed(1)}%</strong></div>
        ${filas}
      `;
      ui.labSubsResult.classList.remove("hidden");
      addLog(`Desglose @ ${distancia}m: subsistema más vulnerable ${d.subsistemas[0].nombre} (${(d.subsistemas[0].probabilidad * 100).toFixed(1)}%)`, "info");
    }));

    ui.btnCoevoStart.addEventListener("click", async () => {
      ui.btnCoevoStart.disabled = true;
      ui.coevoResult.classList.add("hidden");
      ui.coevoGenBars.innerHTML = "";
      ui.coevoProgress.classList.remove("hidden");
      ui.coevoStatusLine.textContent = "Arrancando...";
      try {
        const body = {
          n_generaciones: +ui.coevoGeneraciones.value || 6,
          tam_poblacion: +ui.coevoPoblacion.value || 8,
          replicas_por_evaluacion: +ui.coevoReplicas.value || 4,
        };
        const r = await api("/api/coevolucion/start", { method: "POST", body: JSON.stringify(body) });
        addLog(`Coevolución: job ${r.job_id} arrancado (${body.n_generaciones} generaciones)`, "info");
        pollCoevoJob(r.job_id);
      } catch (e) {
        addLog(`Coevolución: ${e.message}`, "error");
        ui.btnCoevoStart.disabled = false;
      }
    });

    ui.btnJamStart.addEventListener("click", async () => {
      try {
        const body = {
          direccion: +ui.jamDirectionSlider.value,
          potencia: +ui.jamPowerSlider.value,
          apertura_cono: +ui.jamApertureSlider.value,
        };
        const r = await api("/api/jam/start", { method: "POST", body: JSON.stringify(body) });
        addLog(r.message, "fire");
        wsClient?.requestStatus();
      } catch (e) { addLog(e.message, "error"); }
    });

    ui.btnJamStop.addEventListener("click", async () => {
      try {
        const r = await api("/api/jam/stop", { method: "POST" });
        addLog(r.message, "stop");
        wsClient?.requestStatus();
      } catch (e) { addLog(e.message, "error"); }
    });

    updateMissileAngleUI();
    setViewMode("tactical");
  }

  function updateMissileAngleUI() {
    const auto = ui.missileAutoAim.checked;
    ui.missileAngleSlider.disabled = auto;
    ui.missileAngleValue.textContent = auto ? "auto" : `${ui.missileAngleSlider.value}°`;
  }

  function init() {
    window.Render3D.init(canvas3d, state.field);
    bindControls();
    wsClient = new SimulationWebSocket({
      url: WS_URL,
      onConnect: () => { setConnectionStatus("connected"); addLog("WebSocket activo", "info"); },
      onDisconnect: () => setConnectionStatus("connecting"),
      onError: () => setConnectionStatus("disconnected"),
      onMessage: applySnapshot,
    });
    wsClient.connect();
    loadScenarios();
    loadInitialState().then(runAutoDemo);
    setInterval(() => { if (state.lastFireWallTime) updateMetrics({ conteo_estados: state.conteoEstados, tiempo: state.simTime }); }, 1000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
