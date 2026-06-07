// ─────────────────────────────────────────────────────────────────────────────
// useSettings — fetch a single settings key from the backend, keep it
// updated via the settings.updated WebSocket event.
//
// Usage:
//   const { value, loading, error, set } = useSettings('display.theme', 'dark');
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useEffect, useCallback } from 'react';
import ApiClient from '../api/client';
import wsClient from '../api/ws';

/**
 * @param {string} key           Setting key (namespaced with dots)
 * @param {any}    [defaultValue] Returned while loading or on error
 * @returns {{ value: any, loading: boolean, error: string|null, set: (val: any) => Promise<void> }}
 */
const useSettings = (key, defaultValue = null) => {
  const [value, setValue] = useState(defaultValue);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    try {
      const res = await ApiClient.getSetting(key);
      setValue(res?.value ?? defaultValue);
      setError(null);
    } catch (e) {
      // 404 = key not yet stored; use default
      if (e.status !== 404) {
        setError(e.detail ?? e.message);
      }
      setValue(defaultValue);
    } finally {
      setLoading(false);
    }
  }, [key, defaultValue]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  // Listen for settings.updated WS events and refetch if our key changed
  useEffect(() => {
    const unsub = wsClient.on('settings.updated', (envelope) => {
      if (envelope?.payload?.key === key) {
        fetch();
      }
    });
    return unsub;
  }, [key, fetch]);

  /** Update the setting on the backend. */
  const set = useCallback(async (newValue) => {
    const prev = value;
    setValue(newValue); // optimistic
    try {
      const res = await ApiClient.setSetting(key, newValue);
      setValue(res?.value ?? newValue);
    } catch (e) {
      setValue(prev); // rollback
      setError(e.detail ?? e.message);
      throw e;
    }
  }, [key, value]);

  return { value, loading, error, set };
};

export default useSettings;
