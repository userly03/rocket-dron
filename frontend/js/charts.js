/**
 * Gráficos: efectividad, heatmap, espectro e historial de disparos.
 */
(function (global) {
  "use strict";

  const Charts = {
    resizeCanvas(canvas) {
      const parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth - 16;
    },

    drawEffectiveness(canvas, data) {
      if (!canvas) return;
      this.resizeCanvas(canvas);
      const ctx = canvas.getContext("2d");
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      if (!data?.length) {
        ctx.fillStyle = "#6a8f6a";
        ctx.font = "11px Courier New";
        ctx.fillText("Sin datos de disparos", 10, h / 2);
        return;
      }

      const maxVal = 100;
      const barW = (w - 40) / data.length;
      const chartH = h - 30;

      data.forEach((d, i) => {
        const barH = (d.tasa_exito / maxVal) * chartH;
        const x = 30 + i * barW;
        const y = h - 20 - barH;
        const grad = ctx.createLinearGradient(0, y, 0, h - 20);
        grad.addColorStop(0, "#00ff41");
        grad.addColorStop(1, "#006622");
        ctx.fillStyle = grad;
        ctx.fillRect(x + 4, y, barW - 8, barH);
        ctx.fillStyle = "#6a8f6a";
        ctx.font = "9px Courier New";
        ctx.textAlign = "center";
        ctx.fillText(d.distancia, x + barW / 2, h - 6);
        ctx.fillStyle = "#d4ffd4";
        ctx.fillText(`${d.tasa_exito}%`, x + barW / 2, y - 4);
      });
    },

    drawHeatmap(canvas, heatmapData) {
      if (!canvas || !heatmapData?.values) return;
      this.resizeCanvas(canvas);
      const ctx = canvas.getContext("2d");
      const w = canvas.width;
      const h = canvas.height;
      const grid = heatmapData.values;
      const rows = grid.length;
      const cols = grid[0]?.length || 0;
      const cellW = w / cols;
      const cellH = h / rows;
      const max = heatmapData.max || 1;

      ctx.clearRect(0, 0, w, h);
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const v = grid[r][c] / max;
          const red = Math.floor(v * 255);
          const green = Math.floor(v * 180);
          ctx.fillStyle = `rgba(${red}, ${green}, 30, ${0.15 + v * 0.75})`;
          ctx.fillRect(c * cellW, r * cellH, cellW + 1, cellH + 1);
        }
      }
    },


    drawSpectrum(canvas, spectrumData) {
      if (!canvas || !spectrumData) return;
      this.resizeCanvas(canvas);
      const ctx = canvas.getContext("2d");
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const freqs = spectrumData.frequencies_ghz;
      const amps = spectrumData.amplitudes;
      if (!freqs?.length) return;

      const maxAmp = Math.max(...amps, 0.01);
      const pad = 30;
      const chartW = w - pad * 2;
      const chartH = h - 30;

      ctx.strokeStyle = "rgba(0, 212, 255, 0.3)";
      ctx.beginPath();
      freqs.forEach((f, i) => {
        const x = pad + (i / (freqs.length - 1)) * chartW;
        const y = h - 20 - (amps[i] / maxAmp) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.lineTo(pad + chartW, h - 20);
      ctx.lineTo(pad, h - 20);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "rgba(0, 212, 255, 0.3)");
      grad.addColorStop(1, "rgba(0, 212, 255, 0)");
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.fillStyle = "#6a8f6a";
      ctx.font = "9px Courier New";
      ctx.fillText(`${freqs[0]} GHz`, pad, h - 4);
      ctx.fillText(`${freqs[freqs.length - 1]} GHz`, w - pad - 30, h - 4);
      ctx.fillStyle = "#00d4ff";
      ctx.fillText(`Δ ${spectrumData.center_ghz} GHz`, w / 2 - 20, 14);
    },

    updateShotHistory(listEl, shots) {
      if (!listEl) return;
      listEl.innerHTML = "";
      if (!shots?.length) {
        listEl.innerHTML = '<li class="shot-empty">Sin disparos registrados</li>';
        return;
      }
      shots.slice().reverse().forEach((s) => {
        const li = document.createElement("li");
        const icon = s.tipo === "misil" ? "🚀" : "🔥";
        li.innerHTML = `${icon} #${s.id} · ${s.tipo} · t=${s.tiempo}s · ` +
          `${s.neutralizados}/${s.afectados} neutralizados · ${Math.round(s.tasa_exito * 100)}%`;
        listEl.appendChild(li);
      });
    },

    updatePhysicsPanel(panel, physics) {
      if (!panel || !physics) return;
      const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };
      set("physics-formula", physics.formula);
      set("phys-power", `${physics.potencia_kw} kW`);
      set("phys-freq", `${physics.frecuencia_ghz} GHz`);
      set("phys-radius", `${physics.radio_efecto_m} m`);
      set("phys-k", physics.coupling_k);
      set("phys-energy", `${physics.energia_pulso_mj} mJ`);
      set("phys-intensity", `${physics.intensidad_campo_w_m2} W/m²`);
    },
  };

  global.Charts = Charts;
})(window);
