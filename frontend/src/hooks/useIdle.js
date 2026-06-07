// ─────────────────────────────────────────────────────────────────────────────
// useIdle — call a callback after a period of user inactivity.
//
// Monitors mouse movement, mouse clicks, keyboard, and touch events.
// Resets the timer on any activity.
//
// Usage:
//   useIdle(300_000, () => setPage('screensaver'));  // 5 minutes
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef } from 'react';

const IDLE_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll'];

/**
 * @param {number}   timeoutMs  Idle threshold in milliseconds
 * @param {Function} onIdle     Called once when idle threshold is crossed
 */
const useIdle = (timeoutMs, onIdle) => {
  const timerRef = useRef(null);
  const onIdleRef = useRef(onIdle);
  useEffect(() => { onIdleRef.current = onIdle; }, [onIdle]);

  useEffect(() => {
    if (!timeoutMs || timeoutMs <= 0) return;

    const reset = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        onIdleRef.current?.();
      }, timeoutMs);
    };

    // Start the timer immediately
    reset();

    IDLE_EVENTS.forEach((ev) =>
      document.addEventListener(ev, reset, { passive: true })
    );

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      IDLE_EVENTS.forEach((ev) => document.removeEventListener(ev, reset));
    };
  }, [timeoutMs]);
};

export default useIdle;
