// ─────────────────────────────────────────────────────────────────────────────
// Screensaver — fullscreen photo slideshow with time/date overlay.
// Any user input (mouse, touch, keyboard) returns to the Home page.
//
// • Shows photos from the PhotoSlideshow plugin (via /api/plugins/slideshow/photos)
// • Falls back to a pure clock display if no photos are available
// • Clock ticks every second; photos advance on the configured interval
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { formatClock, formatLongDate } from '../lib/date';
import useWebSocket from '../hooks/useWebSocket';
import useApi from '../hooks/useApi';
import ApiClient from '../api/client';

// ── Photo fetching ────────────────────────────────────────────────────────────

async function fetchPhotos() {
  try {
    const res = await fetch('/api/plugins/slideshow/photos');
    if (res.ok) return await res.json();
    return [];
  } catch {
    return [];
  }
}

// ── Clock display ─────────────────────────────────────────────────────────────

const Clock = ({ date }) => {
  const { hours, minutes } = formatClock(date);
  const dateStr = formatLongDate(date);

  return (
    <div className="text-center select-none pointer-events-none">
      <div className="font-mono font-bold text-white leading-none tracking-tighter"
           style={{ fontSize: 'clamp(4rem, 18vw, 14rem)' }}>
        {hours}<span className="opacity-70 animate-pulse">:</span>{minutes}
      </div>
      <p className="text-white/60 font-light mt-3"
         style={{ fontSize: 'clamp(1rem, 2.5vw, 2rem)' }}>
        {dateStr}
      </p>
    </div>
  );
};

// ── Main screensaver component ─────────────────────────────────────────────────

const Screensaver = ({ onExit }) => {
  // Read display_duration_ms from the slideshow plugin manifest — the same
  // key PhotoSlideshow.jsx uses — so there is one source of truth.
  const slideshowSettingsFetcher = useCallback(
    () => ApiClient.getPluginSettings('slideshow'),
    []
  );
  const { data: slideshowSettings } = useApi(slideshowSettingsFetcher, null);
  // Canonical manifest defaults: display_duration_ms=8000, transition_speed_ms=1200
  const intervalMs   = slideshowSettings?.display_duration_ms ?? 8_000;
  const transitionMs = slideshowSettings?.transition_speed_ms ?? 1_200;

  const [now, setNow]               = useState(new Date());
  const [photos, setPhotos]         = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [prevIdx, setPrevIdx]       = useState(null);
  const [transitioning, setTransitioning] = useState(false);
  const [imgLoaded, setImgLoaded]   = useState(false);

  const slideTimer = useRef(null);
  const clockTimer = useRef(null);

  // ── Tick clock every second ────────────────────────────────────────────────
  useEffect(() => {
    clockTimer.current = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(clockTimer.current);
  }, []);

  // ── Load photos ────────────────────────────────────────────────────────────
  useEffect(() => {
    fetchPhotos().then((list) => {
      setPhotos(list);
      setCurrentIdx(0);
      setImgLoaded(false);
    });
  }, []);

  // ── Reload on photos.updated WS event ─────────────────────────────────────
  useWebSocket('photos.updated', useCallback(() => {
    fetchPhotos().then(setPhotos);
  }, []));

  // ── Auto-advance photos ────────────────────────────────────────────────────
  const advance = useCallback(() => {
    if (photos.length <= 1) return;
    setTransitioning(true);
    setPrevIdx(currentIdx);
    setTimeout(() => {
      setCurrentIdx((i) => (i + 1) % photos.length);
      setImgLoaded(false);
      setTransitioning(false);
    }, transitionMs);
  }, [photos.length, currentIdx, transitionMs]);

  useEffect(() => {
    if (photos.length <= 1) return;
    slideTimer.current = setInterval(advance, intervalMs);
    return () => clearInterval(slideTimer.current);
  }, [advance, intervalMs, photos.length]);

  // ── Exit on any interaction ────────────────────────────────────────────────
  useEffect(() => {
    const USER_EVENTS = ['mousedown', 'touchstart', 'keydown'];
    let lastMoveTime = 0;

    const handleMove = () => {
      const t = Date.now();
      if (t - lastMoveTime > 300) {
        lastMoveTime = t;
        onExit();
      }
    };

    const handleInput = () => onExit();

    document.addEventListener('mousemove', handleMove, { passive: true });
    USER_EVENTS.forEach((ev) => document.addEventListener(ev, handleInput, { passive: true }));

    return () => {
      document.removeEventListener('mousemove', handleMove);
      USER_EVENTS.forEach((ev) => document.removeEventListener(ev, handleInput));
    };
  }, [onExit]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const currentPhoto = photos[currentIdx];
  const prevPhoto    = prevIdx !== null ? photos[prevIdx] : null;
  const hasPhotos    = photos.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black cursor-none"
      style={{ touchAction: 'none' }}
    >
      {/* ── Background photos ────────────────────────────────────────────── */}
      {hasPhotos && (
        <>
          {/* Outgoing photo (crossfade out) */}
          {prevPhoto && transitioning && (
            <img
              key={`prev-${prevIdx}`}
              src={prevPhoto.url ?? prevPhoto.src ?? ''}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
              style={{ opacity: 0, transition: `opacity ${transitionMs}ms ease-out` }}
              aria-hidden="true"
              draggable={false}
            />
          )}

          {/* Current photo (crossfade in) */}
          {currentPhoto && (
            <img
              key={`cur-${currentIdx}`}
              src={currentPhoto.url ?? currentPhoto.src ?? ''}
              alt=""
              onLoad={() => setImgLoaded(true)}
              className="absolute inset-0 w-full h-full object-cover"
              style={{
                opacity: imgLoaded && !transitioning ? 1 : 0,
                transition: `opacity ${transitionMs}ms ease-out`,
              }}
              aria-hidden="true"
              draggable={false}
            />
          )}

          {/* Darkening vignette for clock legibility */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.5) 100%)',
            }}
            aria-hidden="true"
          />
        </>
      )}

      {/* ── Clock / date overlay ─────────────────────────────────────────── */}
      <div className="absolute inset-0 flex items-center justify-center">
        <Clock date={now} />
      </div>

      {/* ── "Tap to wake" hint (fades in after 3s) ───────────────────────── */}
      <p
        className="absolute bottom-6 left-0 right-0 text-center text-white/30 text-body-sm pointer-events-none select-none animate-fade-in"
        style={{ animationDelay: '3s', animationFillMode: 'backwards' }}
        aria-hidden="true"
      >
        Tap anywhere to continue
      </p>
    </div>
  );
};

export default Screensaver;
