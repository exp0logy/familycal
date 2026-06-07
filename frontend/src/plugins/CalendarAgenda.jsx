// ─────────────────────────────────────────────────────────────────────────────
// CalendarAgenda plugin UI — month-grid calendar (with an Agenda toggle) for the
// Home split-screen. Registers itself as "CalendarAgenda" in the plugin registry.
//
// Props (§6): { settings, ws, api, profiles, fullscreen }
// ─────────────────────────────────────────────────────────────────────────────

import React, { useCallback, useMemo, useState } from 'react';
import { registerPlugin } from './registry';
import useApi from '../hooks/useApi';
import useWebSocket from '../hooks/useWebSocket';
import { groupEventsByDay, formatTimeRange, startOfDay } from '../lib/date';
import { hexToRgba } from '../lib/color';
import Spinner from '../components/Spinner';
import Icon from '../components/Icon';

// ── Date helpers (local to the calendar) ──────────────────────────────────────

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);

/** Stable local-date key, e.g. "2026-6-7" (used to bucket events by day). */
const dateKey = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

const sameDay = (a, b) => dateKey(a) === dateKey(b);

/** Build a 6-row × 7-col (Monday-first) month grid covering `anchor`'s month. */
function buildMonthGrid(anchor) {
  const first = startOfMonth(anchor);
  const mondayOffset = (first.getDay() + 6) % 7; // 0 = Monday … 6 = Sunday
  const start = new Date(first);
  start.setDate(first.getDate() - mondayOffset);
  start.setHours(0, 0, 0, 0);

  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    cells.push(d);
  }
  const end = new Date(cells[41]);
  end.setHours(23, 59, 59, 999);
  return { cells, start, end };
}

/**
 * Bucket events into every day they cover within the grid range. Multi-day
 * events (e.g. holidays) appear on each day they span. Returns a Map keyed by
 * dateKey → events[], each bucket sorted (all-day first, then by start time).
 */
function bucketEventsByDay(events, grid) {
  const map = new Map();
  for (const ev of events) {
    const s = new Date(ev.start);
    // For all-day events the stored end is typically the next midnight (exclusive);
    // subtract 1ms so a single all-day event doesn't bleed into the next cell.
    let e = new Date(ev.end || ev.start);
    if (ev.all_day) e = new Date(e.getTime() - 1);
    if (e < s) e = s;

    let day = startOfDay(s);
    const lastDay = startOfDay(e);
    if (day < grid.start) day = new Date(grid.start);

    let guard = 0;
    while (day <= lastDay && day <= grid.end && guard < 60) {
      const k = dateKey(day);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(ev);
      day = new Date(day);
      day.setDate(day.getDate() + 1);
      guard++;
    }
  }
  for (const list of map.values()) {
    list.sort((a, b) => {
      if (a.all_day !== b.all_day) return a.all_day ? -1 : 1;
      return new Date(a.start) - new Date(b.start);
    });
  }
  return map;
}

/** Resolve an event's display colour: explicit colour → first profile → accent. */
function eventColor(event, profiles) {
  if (event.color) return event.color;
  if (event.profile_ids?.length > 0) {
    const p = profiles?.find((pr) => pr.id === event.profile_ids[0]);
    if (p?.color) return p.color;
  }
  return '#6366f1';
}

// ── Shared sub-components (used by Agenda + the selected-day detail) ───────────

const EventRow = ({ event, profiles }) => {
  const color = eventColor(event, profiles);
  const timeStr = formatTimeRange(event.start, event.end, event.all_day);

  return (
    <div
      className="flex items-start gap-3 py-3 border-b border-surface-4/40 last:border-0"
      role="listitem"
    >
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

// ── Month grid ────────────────────────────────────────────────────────────────

const MAX_CHIPS = 3;

const DayCell = ({ date, inMonth, isToday, isSelected, events, profiles, onSelect }) => {
  const shown = events.slice(0, MAX_CHIPS);
  const extra = events.length - shown.length;

  return (
    <button
      type="button"
      onClick={() => onSelect(date)}
      className={[
        'flex flex-col items-stretch text-left p-1.5 min-h-0 overflow-hidden',
        'border-t border-l border-surface-4/30 transition-colors duration-150',
        inMonth ? 'bg-surface-1' : 'bg-surface-2/40',
        isSelected ? 'ring-2 ring-inset ring-accent-500/60 z-10' : 'hover:bg-surface-3/40',
      ].join(' ')}
      aria-label={date.toDateString()}
      aria-pressed={isSelected}
    >
      <div className="flex items-center justify-end flex-shrink-0">
        <span
          className={[
            'inline-flex items-center justify-center text-body-sm font-semibold w-6 h-6 rounded-full',
            isToday
              ? 'bg-accent-500 text-white'
              : inMonth
                ? 'text-text-primary'
                : 'text-text-muted/60',
          ].join(' ')}
        >
          {date.getDate()}
        </span>
      </div>

      <div className="flex-1 min-h-0 mt-1 flex flex-col gap-0.5 overflow-hidden">
        {shown.map((ev) => {
          const color = eventColor(ev, profiles);
          return (
            <div
              key={`${ev.id}-${dateKey(date)}`}
              className="flex items-center gap-1 rounded px-1 py-0.5 leading-none"
              style={{ backgroundColor: hexToRgba(color, 0.18) }}
              title={ev.title}
            >
              {!ev.all_day && (
                <span
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: color }}
                  aria-hidden="true"
                />
              )}
              <span
                className="truncate text-caption font-medium"
                style={{ color }}
              >
                {ev.title}
              </span>
            </div>
          );
        })}
        {extra > 0 && (
          <span className="text-caption text-text-muted px-1">+{extra} more</span>
        )}
      </div>
    </button>
  );
};

const MonthGrid = ({ grid, byDay, today, selected, profiles, onSelect }) => {
  // The "current" month is whichever month most of the grid belongs to — cell 15
  // (3rd week) is always inside the anchored month.
  const currentMonth = grid.cells[15].getMonth();
  return (
    <div className="flex-1 min-h-0 flex flex-col border-r border-b border-surface-4/30">
      {/* Weekday header */}
      <div className="grid grid-cols-7 flex-shrink-0">
        {WEEKDAYS.map((w) => (
          <div
            key={w}
            className="text-center py-1.5 text-caption font-semibold uppercase tracking-wide text-text-muted border-l border-surface-4/30 first:border-l-0"
          >
            {w}
          </div>
        ))}
      </div>
      {/* 6 week rows filling available height */}
      <div
        className="grid grid-cols-7 flex-1 min-h-0"
        style={{ gridTemplateRows: 'repeat(6, minmax(0, 1fr))' }}
      >
        {grid.cells.map((date) => (
          <DayCell
            key={dateKey(date)}
            date={date}
            inMonth={date.getMonth() === currentMonth}
            isToday={sameDay(date, today)}
            isSelected={sameDay(date, selected)}
            events={byDay.get(dateKey(date)) ?? []}
            profiles={profiles}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────────────

const CalendarAgenda = ({ settings, api, profiles, fullscreen }) => {
  const [view, setView] = useState('month'); // 'month' | 'agenda'
  const [anchor, setAnchor] = useState(() => startOfMonth(new Date()));
  const [selected, setSelected] = useState(() => startOfDay(new Date()));

  const days = settings?.agenda_days ?? 7;
  const grid = useMemo(() => buildMonthGrid(anchor), [anchor]);

  const fetcher = useCallback(() => {
    if (view === 'agenda') return api.getAgenda(days);
    return api.getEvents({
      start: grid.start.toISOString(),
      end: grid.end.toISOString(),
    });
  }, [view, days, api, grid.start, grid.end]);

  const { data: events, loading, error, refetch } = useApi(fetcher, []);
  useWebSocket('events.updated', useCallback(() => { refetch(); }, [refetch]));

  const today = useMemo(() => startOfDay(new Date()), []);
  const byDay = useMemo(
    () => bucketEventsByDay(events ?? [], grid),
    [events, grid]
  );
  const agendaGroups = useMemo(
    () => groupEventsByDay(events ?? []),
    [events]
  );
  const selectedEvents = byDay.get(dateKey(selected)) ?? [];

  const monthLabel = anchor.toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  });
  const selectedLabel = selected.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });

  const shiftMonth = (delta) => {
    setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + delta, 1));
  };
  const goToday = () => {
    const now = new Date();
    setAnchor(startOfMonth(now));
    setSelected(startOfDay(now));
  };

  return (
    <div className="h-full flex flex-col bg-surface-1 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3 flex-shrink-0 gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <Icon name="calendar" className="w-5 h-5 text-accent-400 flex-shrink-0" />
          <h2 className="text-title font-semibold text-text-primary truncate">
            {view === 'month' ? monthLabel : 'Agenda'}
          </h2>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {view === 'month' && (
            <>
              <button
                type="button"
                onClick={() => shiftMonth(-1)}
                className="text-text-muted hover:text-text-primary p-1.5 rounded-md hover:bg-surface-3/50 transition-colors"
                aria-label="Previous month"
              >
                <Icon name="chevron-left" className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={goToday}
                className="text-body-sm text-text-secondary hover:text-text-primary px-2.5 py-1 rounded-md hover:bg-surface-3/50 transition-colors"
              >
                Today
              </button>
              <button
                type="button"
                onClick={() => shiftMonth(1)}
                className="text-text-muted hover:text-text-primary p-1.5 rounded-md hover:bg-surface-3/50 transition-colors"
                aria-label="Next month"
              >
                <Icon name="chevron-right" className="w-4 h-4" />
              </button>
            </>
          )}

          {/* View toggle */}
          <div className="flex items-center bg-surface-3/60 rounded-lg p-0.5 ml-1">
            {['month', 'agenda'].map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={[
                  'px-2.5 py-1 rounded-md text-body-sm font-medium capitalize transition-colors',
                  view === v
                    ? 'bg-accent-500 text-white'
                    : 'text-text-muted hover:text-text-secondary',
                ].join(' ')}
                aria-pressed={view === v}
              >
                {v}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={refetch}
            disabled={loading}
            className="text-text-muted hover:text-text-secondary transition-colors p-1.5"
            aria-label="Refresh"
            title="Refresh"
          >
            <Icon name="refresh" className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Body */}
      {error ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-5">
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
      ) : loading && (events?.length ?? 0) === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <Spinner size="md" />
        </div>
      ) : view === 'month' ? (
        <div className="flex-1 min-h-0 flex flex-col px-3 pb-3">
          <MonthGrid
            grid={grid}
            byDay={byDay}
            today={today}
            selected={selected}
            profiles={profiles}
            onSelect={setSelected}
          />

          {/* Selected-day detail strip */}
          <div className="flex-shrink-0 mt-3 max-h-[28%] overflow-y-auto px-2">
            <h3 className="section-label text-accent-400 sticky top-0 bg-surface-1/90 backdrop-blur-xs py-1">
              {selectedLabel}
            </h3>
            {selectedEvents.length === 0 ? (
              <p className="text-body-sm text-text-muted py-2">No events</p>
            ) : (
              <div role="list">
                {selectedEvents.map((ev) => (
                  <EventRow key={`${ev.id}-detail`} event={ev} profiles={profiles} />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Agenda view */
        <div className="flex-1 min-h-0 overflow-y-auto px-5 pb-5">
          {agendaGroups.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2 text-center">
              <Icon name="calendar" className="w-8 h-8 text-text-muted" />
              <p className="text-body-sm text-text-muted">
                No events in the next {days} days
              </p>
            </div>
          ) : (
            agendaGroups.map(({ label, date, events: dayEvents }) => (
              <DayGroup
                key={date.toISOString()}
                label={label}
                events={dayEvents}
                profiles={profiles}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

// ── Register in global plugin registry ────────────────────────────────────────
registerPlugin('CalendarAgenda', { component: CalendarAgenda });

export default CalendarAgenda;
