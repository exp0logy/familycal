// ─────────────────────────────────────────────────────────────────────────────
// PhotoSlideshow plugin UI — fullscreen/panel photo carousel.
// Registers itself as "PhotoSlideshow" in the plugin registry on import.
//
// Props (§6): { settings, ws, api, profiles, fullscreen }
//
// Photos are loaded from /api/plugins/slideshow/photos.
// WS event "photos.updated" triggers a reload of the photo list.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { registerPlugin } from './registry';
import useWebSocket from '../hooks/useWebSocket';
import Icon from '../components/Icon';

// ── Photo data fetching ────────────────────────────────────────────────────────

async function fetchPhotos() {
  try {
    const res = await fetch('/api/plugins/slideshow/photos');
    if (res.ok) return await res.json();
    return [];
  } catch {
    return [];
  }
}

// ── Main component ─────────────────────────────────────────────────────────────

const PhotoSlideshow = ({ settings, fullscreen }) => {
  // Canonical slideshow manifest keys (team-lead locked spec):
  //   display_duration_ms  — per-photo dwell time   (default 8000 ms)
  //   transition_speed_ms  — crossfade duration      (default 1200 ms)
  const intervalMs    = settings?.display_duration_ms ?? 8_000;
  const transitionMs  = settings?.transition_speed_ms ?? 1_200;

  const [photos, setPhotos]         = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loaded, setLoaded]         = useState(false);
  const [fading, setFading]         = useState(false);
  const timerRef = useRef(null);

  // Load photos on mount
  useEffect(() => {
    fetchPhotos().then((list) => {
      setPhotos(list);
      setCurrentIdx(0);
      setLoaded(false);
    });
  }, []);

  // Reload when photos cache changes
  useWebSocket('photos.updated', useCallback(() => {
    fetchPhotos().then((list) => {
      setPhotos(list);
    });
  }, []));

  // Auto-advance timer — crossfade takes transitionMs, then swap the photo
  const advance = useCallback(() => {
    setFading(true);
    setTimeout(() => {
      setCurrentIdx((i) => (photos.length > 0 ? (i + 1) % photos.length : 0));
      setLoaded(false);
      setFading(false);
    }, transitionMs);
  }, [photos.length, transitionMs]);

  useEffect(() => {
    if (photos.length <= 1) return;
    timerRef.current = setInterval(advance, intervalMs);
    return () => clearInterval(timerRef.current);
  }, [advance, intervalMs, photos.length]);

  const goTo = useCallback((idx) => {
    clearInterval(timerRef.current);
    setFading(true);
    // Use half the transition duration for manual nav (feels snappier)
    setTimeout(() => {
      setCurrentIdx(idx);
      setLoaded(false);
      setFading(false);
    }, Math.round(transitionMs / 2));
  }, [transitionMs]);

  const goPrev = useCallback(() => {
    goTo((currentIdx - 1 + photos.length) % photos.length);
  }, [currentIdx, photos.length, goTo]);

  const goNext = useCallback(() => {
    goTo((currentIdx + 1) % photos.length);
  }, [currentIdx, photos.length, goTo]);

  // ── Empty state ────────────────────────────────────────────────────────────
  if (photos.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 bg-surface-0">
        <Icon name="photos" className="w-14 h-14 text-surface-4" />
        <p className="text-body-sm text-text-muted text-center px-6">
          No photos yet. Connect a Google Photos album in Settings.
        </p>
      </div>
    );
  }

  const photo = photos[currentIdx];
  const imgSrc = photo?.url ?? photo?.src ?? '';
  const caption = photo?.filename ?? photo?.caption ?? '';

  return (
    <div className="relative h-full overflow-hidden bg-black select-none">
      {/* ── Photo ──────────────────────────────────────────────────────────── */}
      <div
        className="absolute inset-0 ease-out"
        style={{
          opacity: fading || !loaded ? 0 : 1,
          transition: `opacity ${transitionMs}ms ease-out`,
        }}
      >
        <img
          key={imgSrc}
          src={imgSrc}
          alt={caption}
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(true)}
          className="w-full h-full object-cover"
          draggable={false}
        />
        {/* Subtle gradient overlay for readability */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent pointer-events-none" />
      </div>

      {/* ── Caption ────────────────────────────────────────────────────────── */}
      {caption && (
        <div className="absolute bottom-0 left-0 right-0 px-5 py-3 pointer-events-none">
          <p className="text-body-sm text-white/70 truncate-1">{caption}</p>
        </div>
      )}

      {/* ── Navigation arrows ──────────────────────────────────────────────── */}
      {photos.length > 1 && (
        <>
          <button
            type="button"
            onClick={goPrev}
            className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-black/30 hover:bg-black/60 text-white transition-colors duration-[200ms] touch-target"
            aria-label="Previous photo"
          >
            <Icon name="chevron-left" className="w-5 h-5" />
          </button>
          <button
            type="button"
            onClick={goNext}
            className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-black/30 hover:bg-black/60 text-white transition-colors duration-[200ms] touch-target"
            aria-label="Next photo"
          >
            <Icon name="chevron-right" className="w-5 h-5" />
          </button>

          {/* ── Dot indicators ─────────────────────────────────────────────── */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 pointer-events-none">
            {photos.slice(0, 10).map((_, i) => (
              <span
                key={i}
                className={`rounded-full transition-all duration-[300ms] ${
                  i === currentIdx
                    ? 'w-4 h-1.5 bg-white'
                    : 'w-1.5 h-1.5 bg-white/40'
                }`}
                aria-hidden="true"
              />
            ))}
            {photos.length > 10 && (
              <span className="text-white/50 text-caption ml-1">
                {currentIdx + 1}/{photos.length}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
};

// ── Register in global plugin registry ────────────────────────────────────────
registerPlugin('PhotoSlideshow', { component: PhotoSlideshow });

export default PhotoSlideshow;
