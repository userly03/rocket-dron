/**
 * Reproductor 2D de una réplica capturada (Monte Carlo P1-A / coevolución
 * P3-B). Consume la MISMA lista de fotogramas que sirve
 * GET /experiments/{id}/preview y GET /coevolucion/preview/{job_id} —
 * cada fotograma es un `_build_snapshot()` del motor real (mismo formato
 * que /ws en vivo). No es una animación inventada: es la réplica que ya
 * corrió, mostrada fotograma a fotograma.
 *
 * Deliberadamente 2D y liviano (no reusa render3d.js): ese motor es un
 * singleton de Three.js atado a un solo canvas (window.Render3D.init).
 * Montar un segundo panel de mapa ahí exigiría refactorizarlo primero a
 * algo instanciable — evaluamos esto después de ver si el 2D alcanza.
 *
 * Colores calcados de render3d.js::COLOR y frontend/css/style.css (ver el
 * comentario de :root ahí para el racional completo) — se migraron juntos,
 * como estaba previsto acá desde que se escribió este archivo.
 */
(function (global) {
  "use strict";

  const COLOR = {
    bg: "#0a0d11",
    grid: "#1c232b",
    activo: "#4caf6e",
    danado: "#d9a53d",
    neutralizado: "#8f3a34",
    interferido: "#9a7fd1",
    riesgo: "#e0a23d",
    missile: "#d9573a",
    hpmCone: "#d9772e",
    hpmOrigin: "#4f8fc4",
    text: "#838f9b",
    textBright: "#e9edf1",
  };

  const MARGIN = 22;
  const instancias = [];

  // Fábrica, no singleton: Monte Carlo y coevolución tienen cada uno su
  // propio canvas y su propia réplica cargada — dos instancias
  // independientes, cada una con su estado de reproducción.
  function crearReproductor(canvas) {
    const player = {
      _canvas: canvas,
      _ctx: canvas.getContext("2d"),
      _frames: [],
      _idx: 0,
      _timer: null,
      _onTick: null,
    };
    Object.setPrototypeOf(player, Replay2DProto);
    player.resize();
    instancias.push(player);
    return player;
  }

  const Replay2DProto = {

    resize() {
      if (!this._canvas) return;
      const parent = this._canvas.parentElement;
      if (!parent) return;
      const width = parent.clientWidth;
      if (width > 0) this._canvas.width = width - 16;
      this._draw(this._idx);
    },

    load(frames) {
      this.stop();
      this._frames = frames || [];
      this._idx = 0;
      this._draw(0);
    },

    clear() {
      this.stop();
      this._frames = [];
      this._idx = 0;
      if (this._ctx && this._canvas) {
        this._ctx.fillStyle = COLOR.bg;
        this._ctx.fillRect(0, 0, this._canvas.width, this._canvas.height);
      }
    },

    frameCount() {
      return this._frames.length;
    },

    currentIndex() {
      return this._idx;
    },

    play(fps, onTick) {
      this.pause();
      if (!this._frames.length) return;
      this._onTick = onTick || null;
      const stepMs = 1000 / (fps || 12);
      this._timer = setInterval(() => {
        this._idx += 1;
        if (this._idx >= this._frames.length) this._idx = 0;
        this._draw(this._idx);
        if (this._onTick) this._onTick(this._idx, this._frames.length);
      }, stepMs);
    },

    pause() {
      if (this._timer) {
        clearInterval(this._timer);
        this._timer = null;
      }
    },

    isPlaying() {
      return this._timer !== null;
    },

    stop() {
      this.pause();
    },

    seek(idx) {
      if (!this._frames.length) return;
      this._idx = Math.max(0, Math.min(this._frames.length - 1, idx));
      this._draw(this._idx);
    },

    _worldToCanvas(field, w, h, x, y) {
      const fw = field?.width || 1000;
      const fh = field?.height || 1000;
      const sx = MARGIN + (x / fw) * (w - MARGIN * 2);
      const sy = MARGIN + (y / fh) * (h - MARGIN * 2);
      return [sx, sy];
    },

    _draw(idx) {
      const ctx = this._ctx;
      const canvas = this._canvas;
      if (!ctx || !canvas) return;
      const snap = this._frames[idx];
      const w = canvas.width;
      const h = canvas.height;

      ctx.fillStyle = COLOR.bg;
      ctx.fillRect(0, 0, w, h);

      if (!snap) {
        ctx.fillStyle = COLOR.text;
        ctx.font = "11px Courier New";
        ctx.fillText("Sin réplica capturada todavía", 10, h / 2);
        return;
      }

      const field = snap.field || { width: 1000, height: 1000 };

      // grilla de referencia, igual de espíritu que el mapa 3D
      ctx.strokeStyle = COLOR.grid;
      ctx.lineWidth = 1;
      const divisions = 4;
      for (let i = 0; i <= divisions; i++) {
        const gx = MARGIN + (i / divisions) * (w - MARGIN * 2);
        const gy = MARGIN + (i / divisions) * (h - MARGIN * 2);
        ctx.beginPath();
        ctx.moveTo(gx, MARGIN);
        ctx.lineTo(gx, h - MARGIN);
        ctx.moveTo(MARGIN, gy);
        ctx.lineTo(w - MARGIN, gy);
        ctx.stroke();
      }

      // cono del cañón HPM: solo se dibuja si ya disparó en esta réplica
      // (antes del primer disparo no hay nada que mostrar, y dibujarlo
      // igual sugeriría un haz activo que todavía no existió).
      const hpm = snap.hpm;
      if (hpm && hpm.disparos > 0) {
        const [ox, oy] = this._worldToCanvas(field, w, h, hpm.origen_x, hpm.origen_y);
        const dirRad = (hpm.direccion * Math.PI) / 180;
        const aperturaRad = ((hpm.apertura_cono || 20) * Math.PI) / 180;
        const largo = Math.max(w, h);
        const a1 = dirRad - aperturaRad / 2;
        const a2 = dirRad + aperturaRad / 2;
        ctx.fillStyle = "rgba(217, 119, 46, 0.15)";
        ctx.beginPath();
        ctx.moveTo(ox, oy);
        ctx.lineTo(ox + Math.cos(a1) * largo, oy + Math.sin(a1) * largo);
        ctx.lineTo(ox + Math.cos(a2) * largo, oy + Math.sin(a2) * largo);
        ctx.closePath();
        ctx.fill();
      }
      if (hpm) {
        const [ox, oy] = this._worldToCanvas(field, w, h, hpm.origen_x, hpm.origen_y);
        ctx.fillStyle = COLOR.hpmOrigin;
        ctx.beginPath();
        ctx.arc(ox, oy, 4, 0, Math.PI * 2);
        ctx.fill();
      }

      // misiles
      (snap.missiles?.misiles || []).forEach((m) => {
        if (m.estado === "listo" || m.estado === "detonado") return;
        const [mx, my] = this._worldToCanvas(field, w, h, m.x, m.y);
        ctx.fillStyle = COLOR.missile;
        ctx.beginPath();
        ctx.arc(mx, my, 3.5, 0, Math.PI * 2);
        ctx.fill();
      });

      // drones
      (snap.drones || []).forEach((d) => {
        const [dx, dy] = this._worldToCanvas(field, w, h, d.x, d.y);
        let color = COLOR.activo;
        if (d.estado === "neutralizado") color = COLOR.neutralizado;
        else if (d.estado === "danado") color = COLOR.danado;
        else if (d.estado === "interferido") color = COLOR.interferido;
        else if ((d.riesgo_latente_severidad ?? 0) > 0) color = COLOR.riesgo;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(dx, dy, 3, 0, Math.PI * 2);
        ctx.fill();
      });

      // rótulo de tiempo simulado, para orientarse dentro de la réplica
      ctx.fillStyle = COLOR.textBright;
      ctx.font = "10px Courier New";
      ctx.fillText(`t=${(snap.tiempo ?? 0).toFixed(2)}s`, 8, 14);
      ctx.fillStyle = COLOR.text;
      ctx.textAlign = "right";
      ctx.fillText(`fotograma ${idx + 1}/${this._frames.length}`, w - 8, 14);
      ctx.textAlign = "left";
    },
  };

  global.Replay2D = { crear: crearReproductor };
  global.addEventListener("resize", () => instancias.forEach((p) => p.resize()));
})(window);
