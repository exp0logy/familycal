// ─────────────────────────────────────────────────────────────────────────────
// CalendarAgenda plugin UI — upcoming events list for the Home split-screen.
// Registers itself as "CalendarAgenda" in the plugin registry on import.
//
// Props (§6): { settings, ws, api, profiles, fullscreen }
// ─────────────────────────────────────────────────────────────────────────────

import React, { useCallback, useMemo } from 'react';
import { registerPlugin } from './registry';
import useApi from '../hooks/useApi';
import useWebSocket from '../hooks/useWebSocket';
import { groupEventsByDay, formatTimeRange } from '../lib/date';
import { hexToRgba } from '../lib/color';
import Spinner from '../components/Spinner';
import Icon from '../components/Icon';

// ── Sub-components ────────────────────────────────────────────────────────────

const EventRow = ({ event, profiles }) => {
  // Find matching profile to derive a color fallback
  const profileColor = useMemo(() => {
    if (event.profile_ids?.length > 0) {
      const p = profiles?.find((pr) => pr.id === event.profile_ids[0]);
      return p?.color ?? null;
    }
    return null;
  }, [event.profile_ids, profiles]);

  const color = event.color ?? profileColor ?? '#6366f1';
  const timeStr = formatTimeRange(event.start, event.end, event.all_day);

  return (
    <div
      className="flex items-start gap-3 py-3 border-b border-surface-4/40 last:border-0 group"
      role="listitem"
    >
      {/* Color indicator bar */}
      <span
        className="w-1 rounded-full flex-shrink-0 mt-0.5 self-stretch min-h-[1.5rem]"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />

      <div className="flex-1 min-w-0">
        <p className="text-body text-text-primary font-medium truncate-1 leading-snug">
          {event.title}
        </p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className="text-body-sm text-text-secondary">{timeStr}</span>
          {event.location && (
            <span className="flex items-center gap-1 text-body-sm text-text-muted truncate">
              <Icon name="map-pin" className="w-3 h-3 flex-shrink-0" />
              <span className="truncate">{event.location}</span>
            </span>
          )}
        </div>
        {/* Profile avatars */}
        {event.profile_ids?.length > 0 && profiles?.length > 0 && (
          <div className="flex items-center gap-1 mt-1.5">
            {event.profile_ids.map((pid) => {
              const p = profiles.find((pr) => pr.id === pid);
              if (!p) return null;
              return (
                <span
                  key={pid}
                  className="inline-flex items-center justify-center w-5 h-5 rounded-full text-caption font-bold flex-shrink-0"
                  style={{
                    backgroundColor: hexToRgba(p.color ?? '#6366f1', 0.2),
                    color: p.color ?? '#6366f1',
                  }}
                  title={p.name}
                  aria-label={p.name}
                >
                  {p.emoji || p.name.charAt(0).toUpperCase()}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

const DayGroup = ({ label, events, profiles }) => (
  <div className="mb-1" role="group" aria-label={label}>
    <div className="sticky top-0 bg-surface-1/90 backdrop-blur-xs py-2 z-10">
      <h3 className="section-label text-accent-400">{label}</h3>
    </div>
    <div role="list">
      {events.map((ev) => (
        <EventRow key={ev.id} event={ev} profiles={profiles} />
      ))}
    </div>
  </div>
);

// ── Main component ─────────────────────────────────────────────────────────────

const CalendarAgenda = ({ settings, api, profiles, fullscreen }) => {
  // agenda_days is defined in the calendar plugin manifest (default 7 per backend).
  // Falls back to 7 if absent (e.g. older backend version or plugin disabled).
  const days = settings?.agenda_days ?? 7;

  const fetcher = useCallback(
    () => api.getAgenda(days),
    [api, days]
  );
  const { data: events, loading, error, refetch } = useApi(fetcher, []);

  // Refetch when calendar events change via WS
  useWebSocket('events.updated', useCallback(() => { refetch(); }, [refetch]));

  const groups = useMemo(
    () => groupEventsByDay(events ?? []),
    [events]
  );

  return (
    <div className="h-full flex flex-col bg-surface-1 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Icon name="calendar" className="w-5 h-5 text-accent-400" />
          <h2 className="text-title font-semibold text-text-primary">Agenda</h2>
        </div>
        <button
          type="button"
          onClick={refetch}
          disabled={loading}
          className="text-text-muted hover:text-text-secondary transition-colors duration-[200ms] p-1"
          aria-label="Refresh agenda"
          title="Refresh"
        >
          <Icon
            name="refresh"
            className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
          />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 pb-5">
        {loading && events?.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <Spinner size="md" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-center">
            <Icon name="warning" className="w-8 h-8 text-warn" />
            <p className="text-body-sm text-text-secondary">{error}</p>
            <button
              type="button"
              onClick={refetch}
              className="text-accent-400 text-body-sm hover:underline"
            >
              Try again
            </button>
          </div>
        ) : groups.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-center">
            <Icon name="calendar" className="w-8 h-8 text-text-muted" />
            <p className="text-body-sm text-text-muted">No events in the next {days} days</p>
          </div>
        ) : (
          groups.map(({ label, date, events: dayEvents }) => (
            <DayGroup
              key={date.toISOString()}
              label={label}
              events={dayEvents}
              profiles={profiles}
            />
          ))
        )}
      </div>
    </div>
  );
};

// ── Register in global plugin registry ────────────────────────────────────────
registerPlugin('CalendarAgenda', { component: CalendarAgenda });

export default CalendarAgenda;
