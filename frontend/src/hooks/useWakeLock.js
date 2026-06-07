// ─────────────────────────────────────────────────────────────────────────────
// useWakeLock — keep the display awake while the dashboard is shown.
//
// Uses the Screen Wake Lock API to stop the OS from dimming/sleeping the screen.
//
// IMPORTANT: the Wake Lock API only works in a SECURE CONTEXT — HTTPS, or
// http://localhost / 127.0.0.1. Over a plain-HTTP LAN IP (e.g. http://192.168.x.x)
// the API is unavailable and this hook no-ops. In that case use the OS-level
// fallback (disable the display timeout in Windows power settings) — see README.
// The hook also re-acquires the lock when the tab becomes visible again, since
// the browser releases it whenever the page is hidden.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect } from 'react';

/**
 * @param {boolean} active  Whether to hold a wake lock (default true).
 */
export default function useWakeLock(active = true) {
  useEffect(() => {
    if (!active) return;
    if (typeof navigator === 'undefined' || !('wakeLock' in navigator)) return;

    let sentinel = null;
    let cancelled = false;

    const request = async () => {
      if (cancelled || sentinel || document.visibilityState !== 'visible') return;
      try {
        sentinel = await navigator.wakeLock.request('screen');
        sentinel.addEventListener('release', () => {
          sentinel = null;
        });
      } catch {
        // Denied (insecure context, low battery, permissions) — silently ignore.
        sentinel = null;
      }
    };

    // The lock is auto-released when the page is hidden; re-acquire on return.
    const onVisibility = () => {
      if (document.visibilityState === 'visible') request();
    };

    request();
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisibility);
      if (sentinel) {
        sentinel.release().catch(() => {});
        sentinel = null;
      }
    };
  }, [active]);
}
