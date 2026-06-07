// ─────────────────────────────────────────────────────────────────────────────
// useWebSocket — subscribe to a WS message type and receive the envelope.
//
// Usage:
//   const lastMsg = useWebSocket('events.updated', (envelope) => { ... });
//
// The handler is called with the full envelope { type, channel, payload, ts }.
// Pass null/undefined as handler to only receive the latest envelope via the
// return value.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef, useState } from 'react';
import wsClient from '../api/ws';

/**
 * @param {string}    type     WS message type from ARCHITECTURE §4, or "any"
 * @param {Function}  [handler] Optional callback. Stable reference preferred.
 * @returns {object|null}       Last received envelope for this type
 */
const useWebSocket = (type, handler) => {
  const [last, setLast] = useState(null);
  // Keep handler ref stable so the effect doesn't re-subscribe on every render
  const handlerRef = useRef(handler);
  useEffect(() => { handlerRef.current = handler; }, [handler]);

  useEffect(() => {
    const listener = (envelope) => {
      setLast(envelope);
      handlerRef.current?.(envelope);
    };
    return wsClient.on(type, listener);
  }, [type]);

  return last;
};

export default useWebSocket;
