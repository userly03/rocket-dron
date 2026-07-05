/**
 * Cliente WebSocket con reconexión automática para el simulador EW.
 */
(function (global) {
  "use strict";

  const DEFAULT_WS_URL = "ws://localhost:8000/ws";
  const RECONNECT_BASE_MS = 1000;
  const RECONNECT_MAX_MS = 15000;
  const PING_INTERVAL_MS = 30000;

  class SimulationWebSocket {
    constructor(options = {}) {
      this.url = options.url || DEFAULT_WS_URL;
      this.onMessage = options.onMessage || (() => {});
      this.onConnect = options.onConnect || (() => {});
      this.onDisconnect = options.onDisconnect || (() => {});
      this.onError = options.onError || (() => {});

      this._ws = null;
      this._reconnectAttempts = 0;
      this._reconnectTimer = null;
      this._pingTimer = null;
      this._manualClose = false;
      this.connected = false;
    }

    connect() {
      if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) {
        return;
      }

      this._manualClose = false;
      this._clearReconnectTimer();

      try {
        this._ws = new WebSocket(this.url);
      } catch (err) {
        this.onError(err);
        this._scheduleReconnect();
        return;
      }

      this._ws.onopen = () => {
        this.connected = true;
        this._reconnectAttempts = 0;
        this.onConnect();
        this._startPing();
      };

      this._ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "pong") return;
          this.onMessage(data);
        } catch (err) {
          this.onError(err);
        }
      };

      this._ws.onerror = (event) => {
        this.onError(event);
      };

      this._ws.onclose = () => {
        this.connected = false;
        this._stopPing();
        this.onDisconnect();

        if (!this._manualClose) {
          this._scheduleReconnect();
        }
      };
    }

    disconnect() {
      this._manualClose = true;
      this._clearReconnectTimer();
      this._stopPing();

      if (this._ws) {
        this._ws.close();
        this._ws = null;
      }

      this.connected = false;
    }

    send(text) {
      if (this._ws && this._ws.readyState === WebSocket.OPEN) {
        this._ws.send(text);
      }
    }

    requestStatus() {
      this.send("status");
    }

    _startPing() {
      this._stopPing();
      this._pingTimer = setInterval(() => {
        this.send("ping");
      }, PING_INTERVAL_MS);
    }

    _stopPing() {
      if (this._pingTimer) {
        clearInterval(this._pingTimer);
        this._pingTimer = null;
      }
    }

    _scheduleReconnect() {
      this._clearReconnectTimer();
      const delay = Math.min(
        RECONNECT_BASE_MS * Math.pow(2, this._reconnectAttempts),
        RECONNECT_MAX_MS
      );
      this._reconnectAttempts += 1;

      this._reconnectTimer = setTimeout(() => {
        this.connect();
      }, delay);
    }

    _clearReconnectTimer() {
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer);
        this._reconnectTimer = null;
      }
    }
  }

  global.SimulationWebSocket = SimulationWebSocket;
})(window);
