// ─────────────────────────────────────────────────────────────────────────────
// WSClient — WebSocket client for ARCHITECTURE §4 protocol.
//
// Features:
//  • Auto-reconnect with exponential back-off (capped at 30 s)
//  • Ping/pong heartbeat (configurable interval; server replies "pong")
//  • Optional channel subscription filter (§4 subscribe message)
//  • EventEmitter-style listeners: on(type, handler) / off(type, handler)
//  • "any" type receives every envelope regardless of type
//  • connect() / disconnect() lifecycle
// ─────────────────────────────────────────────────────────────────────────────

const WS_BASE = import.meta.env.VITE_WS_BASE ?? '/ws';

// Build the absolute WebSocket URL from the Vite var.
// In dev the Vite proxy maps /ws → ws://localhost:8000/ws.
// In production nginx proxies it to the backend container.
function buildWsUrl() {
  // If VITE_WS_BASE is already absolute (ws:// or wss://) use it directly.
  if (WS_BASE.startsWith('ws://') || WS_BASE.startsWith('wss://')) {
    return WS_BASE;
  }
  // Derive from current window location
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.host;
  return `${protocol}://${host}${WS_BASE}`;
}

// Reconnect back-off parameters
const BACKOFF_BASE_MS  = 1_000;  // 1 s initial wait
const BACKOFF_MAX_MS   = 30_000; // 30 s cap
const PING_INTERVAL_MS = 25_000; // send ping every 25 s

// Connection state enum
export const WS_STATE = {
  DISCONNECTED: 'disconnected',
  CONNECTING:   'connecting',
  CONNECTED:    'connected',
  CLOSING:      'closing',
};

class WSClient {
  constructor() {
    /** @type {Map<string, Set<Function>>} type → set of handler functions */
    this._listeners = new Map();
    /** @type {WebSocket|null} */
    this._socket = null;
    /** @type {string} */
    this.state = WS_STATE.DISCONNECTED;
    /** @type {number} reconnect attempt counter */
    this._attempt = 0;
    /** @type {ReturnType<typeof setTimeout>|null} */
    this._reconnectTimer = null;
    /** @type {ReturnType<typeof setInterval>|null} */
    this._pingTimer = null;
    /** @type {string[]|null} channels filter; null = subscribe to all */
    this._channels = null;
    // Set to true when the user explicitly calls disconnect() to prevent
    // the auto-reconnect from kicking back in.
    this._intentionalClose = false;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Connect (or reconnect) to the WebSocket endpoint.
   * Safe to call multiple times — no-ops if already connected/connecting.
   *
   * @param {string[]} [channels]  Optional list of channel names to subscribe to.
   */
  connect(channels) {
    if (
      this.state === WS_STATE.CONNECTED ||
      this.state === WS_STATE.CONNECTING
    ) {
      return;
    }
    if (channels !== undefined) {
      this._channels = channels;
    }
    this._intentionalClose = false;
    this._open();
  }

  /** Gracefully close the socket and stop reconnecting. */
  disconnect() {
    this._intentionalClose = true;
    this._clearTimers();
    if (this._socket) {
      this.state = WS_STATE.CLOSING;
      this._socket.close(1000, 'client disconnect');
      this._socket = null;
    }
    this.state = WS_STATE.DISCONNECTED;
  }

  /**
   * Register a listener for a message type.
   * Use type = "any" to receive all envelopes.
   *
   * @param {string}   type     Envelope type from §4, or "any"
   * @param {Function} handler  Called with the full envelope { type, channel, payload, ts }
   * @returns {() => void}      Unsubscribe function
   */
  on(type, handler) {
    if (!this._listeners.has(type)) {
      this._listeners.set(type, new Set());
    }
    this._listeners.get(type).add(handler);
    // Return a cleanup function for easy use in useEffect
    return () => this.off(type, handler);
  }

  /**
   * Remove a previously registered listener.
   *
   * @param {string}   type
   * @param {Function} handler
   */
  off(type, handler) {
    this._listeners.get(type)?.delete(handler);
  }

  /**
   * Send a raw message to the server.
   * Silently drops the message if not connected.
   *
   * @param {object} message
   */
  send(message) {
    if (this._socket?.readyState === WebSocket.OPEN) {
      this._socket.send(JSON.stringify(message));
    }
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  /** Open the WebSocket and wire up event handlers. */
  _open() {
    this.state = WS_STATE.CONNECTING;
    this._emit('_state', { state: this.state });

    const url = buildWsUrl();
    const socket = new WebSocket(url);
    this._socket = socket;

    socket.addEventListener('open', () => {
      this._attempt = 0;
      this.state = WS_STATE.CONNECTED;
      this._emit('_state', { state: this.state });

      // If the caller requested a channel filter, send the subscribe message
      if (this._channels && this._channels.length > 0) {
        this.send({ type: 'subscribe', channels: this._channels });
      }

      // Start the heartbeat ping timer
      this._startPing();
    });

    socket.addEventListener('message', (event) => {
      let envelope;
      try {
        envelope = JSON.parse(event.data);
      } catch {
        // Malformed frame — ignore
        return;
      }
      this._dispatch(envelope);
    });

    socket.addEventListener('close', (event) => {
      this._clearTimers();
      this._socket = null;
      this.state = WS_STATE.DISCONNECTED;
      this._emit('_state', { state: this.state, code: event.code });

      if (!this._intentionalClose) {
        this._scheduleReconnect();
      }
    });

    socket.addEventListener('error', () => {
      // The 'close' event always fires after 'error', so let that handler
      // manage state and reconnection. We just surface a notice here.
      this._emit('_error', { message: 'WebSocket error' });
    });
  }

  /** Dispatch a parsed envelope to registered listeners. */
  _dispatch(envelope) {
    const { type } = envelope;

    // Fire type-specific listeners
    this._listeners.get(type)?.forEach((h) => {
      try { h(envelope); } catch (e) { console.error('[WSClient] listener error', e); }
    });

    // Fire "any" catch-all listeners
    this._listeners.get('any')?.forEach((h) => {
      try { h(envelope); } catch (e) { console.error('[WSClient] any-listener error', e); }
    });
  }

  /** Internal emit for connection lifecycle events. */
  _emit(type, payload) {
    this._listeners.get(type)?.forEach((h) => {
      try { h({ type, payload }); } catch {}
    });
  }

  /** Start the periodic ping timer. */
  _startPing() {
    this._pingTimer = setInterval(() => {
      this.send({ type: 'ping' });
    }, PING_INTERVAL_MS);
  }

  /** Clear both the ping timer and the reconnect timer. */
  _clearTimers() {
    if (this._pingTimer) {
      clearInterval(this._pingTimer);
      this._pingTimer = null;
    }
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  /** Schedule a reconnection attempt with exponential back-off. */
  _scheduleReconnect() {
    const delay = Math.min(
      BACKOFF_BASE_MS * 2 ** this._attempt,
      BACKOFF_MAX_MS
    );
    this._attempt += 1;
    this._reconnectTimer = setTimeout(() => {
      if (!this._intentionalClose) {
        this._open();
      }
    }, delay);
  }
}

// Export a singleton so all hooks share the same connection
const wsClient = new WSClient();
export default wsClient;
