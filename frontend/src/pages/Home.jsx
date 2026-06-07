// ─────────────────────────────────────────────────────────────────────────────
// Home page — responsive split-screen dashboard.
//
// Layout:
//  • Left panel  (default 50%): PhotoSlideshow plugin
//  • Right panel (default 50%): CalendarAgenda plugin
//  • Bottom bar: WeatherWidget (persistent) + nav buttons
//  • Divider is draggable on pointer devices; touch devices get equal halves.
//
// Live data:
//  • Events refetch on events.updated WS
//  • Weather updates on weather.updated WS
//  • Plugins list refreshes on plugin.state WS
//  • Plugin settings refetch on settings.updated WS (key "plugin.<name>")
//    so all connected devices re-render when settings change on any device.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import Icon from '../components/Icon';
import Button from '../components/Button';
import StatusDot from '../components/StatusDot';
import PluginSlot from '../plugins/PluginSlot';
import useWebSocket from '../hooks/useWebSocket';
import useIdle from '../hooks/useIdle';
import useSettings from '../hooks/useSettings';
import useApi from '../hooks/useApi';
import usePluginSettings from '../hooks/usePluginSettings';
import ApiClient from '../api/client';
import wsClient, { WS_STATE } from '../api/ws';

// ── WS connection indicator ────────────────────────────────────────────────────

const WSStatus = () => {
  const [state, setState] = useState(wsClient.state);

  useEffect(() => {
    const unsub = wsClient.on('_state', (msg) => setState(msg.payload?.state ?? msg.payload));
    return unsub;
  }, []);

  const status = state === WS_STATE.CONNECTED ? 'connected' : state === WS_STATE.CONNECTING ? 'connecting' : 'disconnected';
  return (
    <span
      title={`WebSocket: ${state}`}
      className="flex items-center"
      aria-label={`Connection: ${state}`}
    >
      <StatusDot status={status} size="sm" />
    </span>
  );
};

// ── Draggable split divider ────────────────────────────────────────────────────

/**
 * Horizontal drag handle that adjusts the left-panel width (as percent).
 */
const SplitDivider = ({ onDrag, containerRef }) => {
  const dragging = useRef(false);

  const handlePointerDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback((e) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct  = ((e.clientX - rect.left) / rect.width) * 100;
    // Clamp between 20% and 80%
    onDrag(Math.min(80, Math.max(20, pct)));
  }, [onDrag, containerRef]);

  const handlePointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  return (
    <div
      className="w-1.5 flex-shrink-0 cursor-col-resize relative group flex items-center justify-center"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panels"
      tabIndex={0}
      style={{ touchAction: 'none' }}
    >
      {/* Drag handle visual */}
      <div className="w-0.5 h-10 rounded-full bg-surface-5 group-hover:bg-accent-500 transition-colors duration-[200ms]" />
    </div>
  );
};

// ── Plugin panel wrapper ───────────────────────────────────────────────────────

const Panel = ({ children, style, className = '' }) => (
  <div
    className={`h-full overflow-hidden flex-shrink-0 ${className}`}
    style={style}
  >
    {children}
  </div>
);

// ── Main Home component ────────────────────────────────────────────────────────

const Home = ({ onSettings, onScreensaver }) => {
  // ── Split panel state ────────────────────────────────────────────────────────
  const [splitPct, setSplitPct] = useState(50);
  const containerRef = useRef(null);

  // ── Screensaver idle timer ────────────────────────────────────────────────────
  // Passing 0 disables the timer (useIdle no-ops on <= 0) when the screensaver
  // is turned off in Settings.
  const { value: idleTimeout } = useSettings('display.screensaver_timeout_s', 300);
  const { value: saverEnabled } = useSettings('display.screensaver_enabled', true);
  useIdle(saverEnabled === false ? 0 : idleTimeout * 1000, onScreensaver);

  // ── Profile list ──────────────────────────────────────────────────────────────
  const profileFetcher = useCallback(() => ApiClient.getProfiles(), []);
  const { data: profiles = [] } = useApi(profileFetcher, []);

  // ── Plugins list ──────────────────────────────────────────────────────────────
  const pluginFetcher = useCallback(() => ApiClient.getPlugins(), []);
  const { data: plugins = [], refetch: refetchPlugins } = useApi(pluginFetcher, []);

  // Refresh plugin list on plugin.state WS event
  useWebSocket('plugin.state', useCallback(() => { refetchPlugins(); }, [refetchPlugins]));

  // Resolve enabled plugins with frontend components
  const enabledPlugins = useMemo(
    () => plugins.filter((p) => p.enabled && p.frontend_component),
    [plugins]
  );

  // The split-screen expects exactly two panels.
  // Primary: first enabled plugin with a component (fallback PhotoSlideshow)
  // Secondary: second enabled plugin (fallback CalendarAgenda)
  const leftPlugin  = enabledPlugins[0] ?? { name: 'slideshow',  frontend_component: 'PhotoSlideshow', enabled: true };
  const rightPlugin = enabledPlugins[1] ?? { name: 'calendar',   frontend_component: 'CalendarAgenda', enabled: true };
  const weatherPlugin = useMemo(
    () => plugins.find((p) => p.frontend_component === 'WeatherWidget'),
    [plugins]
  );

  // Per-plugin settings — usePluginSettings handles initial fetch + live WS
  // sync on settings.updated { key: "plugin.<name>" } for cross-device updates.
  const { settings: leftSettings  } = usePluginSettings(leftPlugin.name  ?? null);
  const { settings: rightSettings } = usePluginSettings(rightPlugin.name ?? null);
  const { settings: weatherSettings } = usePluginSettings(
    weatherPlugin?.name ?? null
  );

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-dvh bg-surface-0 overflow-hidden">
      {/* ── Top chrome ───────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 pt-3 pb-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <WSStatus />
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="icon"
            size="md"
            onClick={onSettings}
            title="Settings"
            aria-label="Open settings"
            icon={<Icon name="settings" className="w-5 h-5" />}
          />
        </div>
      </header>

      {/* ── Split panel content area ──────────────────────────────────────── */}
      <main
        ref={containerRef}
        className="flex-1 min-h-0 flex"
        style={{ userSelect: 'none' }}
      >
        {/* Left panel */}
        <Panel
          className="rounded-card overflow-hidden m-1 mr-0 shadow-card"
          style={{ width: `calc(${splitPct}% - 2px)` }}
        >
          <PluginSlot
            name={leftPlugin.frontend_component}
            settings={leftSettings}
            ws={wsClient}
            api={ApiClient}
            profiles={profiles}
            fullscreen={false}
          />
        </Panel>

        {/* Drag divider */}
        <SplitDivider onDrag={setSplitPct} containerRef={containerRef} />

        {/* Right panel */}
        <Panel
          className="rounded-card overflow-hidden m-1 ml-0 shadow-card"
          style={{ width: `calc(${100 - splitPct}% - 2px)` }}
        >
          <PluginSlot
            name={rightPlugin.frontend_component}
            settings={rightSettings}
            ws={wsClient}
            api={ApiClient}
            profiles={profiles}
            fullscreen={false}
          />
        </Panel>
      </main>

      {/* ── Weather bar (persistent, pinned to bottom) ────────────────────── */}
      {weatherPlugin && (
        <footer className="flex-shrink-0 mx-2 mb-2 rounded-card overflow-hidden bg-surface-1 border border-surface-4/50 shadow-card">
          <PluginSlot
            name="WeatherWidget"
            settings={weatherSettings}
            ws={wsClient}
            api={ApiClient}
            profiles={profiles}
            fullscreen={false}
          />
        </footer>
      )}
    </div>
  );
};

export default Home;
