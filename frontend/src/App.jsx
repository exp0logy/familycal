// ─────────────────────────────────────────────────────────────────────────────
// App — root component.
// Owns the page-level router (hash-based, no external router dependency),
// WebSocket connection lifecycle, and the idle/screensaver timer.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useEffect, useState, useCallback } from 'react';
import wsClient from './api/ws';
import Home from './pages/Home';
import Screensaver from './pages/Screensaver';
import Settings from './pages/Settings';
import OnScreenKeyboard from './components/OnScreenKeyboard';
import useWakeLock from './hooks/useWakeLock';

// Pages the app can display
const PAGES = {
  home:       'home',
  screensaver:'screensaver',
  settings:   'settings',
};

const App = () => {
  // ── Page routing ───────────────────────────────────────────────────────────
  const [page, setPage] = useState(PAGES.home);

  // ── Connect WebSocket once on mount ───────────────────────────────────────
  useEffect(() => {
    wsClient.connect();
    return () => wsClient.disconnect();
  }, []);

  // ── Keep the display awake (no-op on insecure-context HTTP; see useWakeLock) ──
  useWakeLock(true);

  // ── Navigation helpers passed to child pages ───────────────────────────────
  const goHome     = useCallback(() => setPage(PAGES.home),       []);
  const goSettings = useCallback(() => setPage(PAGES.settings),   []);
  const goSaver    = useCallback(() => setPage(PAGES.screensaver), []);

  // ── Screensaver: any user input returns to home ────────────────────────────
  const exitSaver = useCallback(() => {
    if (page === PAGES.screensaver) setPage(PAGES.home);
  }, [page]);

  return (
    <div className="min-h-dvh bg-surface-0 text-text-primary overflow-hidden">
      {page === PAGES.home && (
        <Home
          onSettings={goSettings}
          onScreensaver={goSaver}
        />
      )}
      {page === PAGES.screensaver && (
        <Screensaver
          onExit={exitSaver}
        />
      )}
      {page === PAGES.settings && (
        <Settings
          onBack={goHome}
        />
      )}

      {/* Global touch keyboard — auto-shows when a text field is tapped on a touchscreen. */}
      <OnScreenKeyboard />
    </div>
  );
};

export default App;
