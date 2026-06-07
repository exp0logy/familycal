// ─────────────────────────────────────────────────────────────────────────────
// usePluginSettings — fetch a plugin's settings and keep them live via WS.
//
// The backend broadcasts { type: "settings.updated", payload: { key: "plugin.<name>" } }
// whenever a plugin's settings are saved (loader.py PUT handler).  This hook
// subscribes to that event and refetches when the key matches, so all connected
// devices re-render with the new settings automatically.
//
// Usage:
//   const { settings, loading } = usePluginSettings('weather');
//   const { settings, loading } = usePluginSettings('slideshow');
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useEffect, useCallback } from 'react';
import ApiClient from '../api/client';
import wsClient from '../api/ws';

/**
 * @param {string|null} pluginName  Backend plugin name (e.g. "weather", "slideshow").
 *                                  Pass null/undefined to skip fetching.
 * @returns {{ settings: object|null, loading: boolean, error: string|null }}
 */
const usePluginSettings = (pluginName) => {
  const [settings, setSettings] = useState(null);
  const [loading,  setLoading]  = useState(!!pluginName);
  const [error,    setError]    = useState(null);

  const fetch = useCallback(async () => {
    if (!pluginName) return;
    setLoading(true);
    try {
      const data = await ApiClient.getPluginSettings(pluginName);
      setSettings(data);
      setError(null);
    } catch (e) {
      // 404 = plugin has no settings schema — treat as empty, not an error
      if (e.status !== 404) {
        setError(e.detail ?? e.message ?? 'Failed to load plugin settings');
      }
      setSettings(null);
    } finally {
      setLoading(false);
    }
  }, [pluginName]);

  // Initial fetch
  useEffect(() => {
    fetch();
  }, [fetch]);

  // Live sync — backend emits settings.updated with { key: "plugin.<name>" }
  // when a plugin's settings are updated via PUT /api/plugins/<name>/settings.
  useEffect(() => {
    if (!pluginName) return;
    const expectedKey = `plugin.${pluginName}`;
    const unsub = wsClient.on('settings.updated', (envelope) => {
      if (envelope?.payload?.key === expectedKey) {
        fetch();
      }
    });
    return unsub;
  }, [pluginName, fetch]);

  return { settings, loading, error };
};

export default usePluginSettings;
