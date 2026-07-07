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
