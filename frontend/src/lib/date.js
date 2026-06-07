// ─────────────────────────────────────────────────────────────────────────────
// Date/time formatting helpers used across the dashboard.
// No external library dependency — all native Intl.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Format a time string for the big clock display.
 * @param {Date} date
 * @returns {{ hours: string, minutes: string, seconds: string, ampm: string|null }}
 */
export function formatClock(date) {
  const h = date.getHours();
  const m = date.getMinutes();
  const s = date.getSeconds();
  return {
    hours:   String(h).padStart(2, '0'),
    minutes: String(m).padStart(2, '0'),
    seconds: String(s).padStart(2, '0'),
    ampm:    null, // 24-hour display
  };
}

/**
 * Long weekday + date, e.g. "Saturday 7 June 2026".
 * @param {Date} [date]
 * @returns {string}
 */
export function formatLongDate(date = new Date()) {
  return date.toLocaleDateString(undefined, {
    weekday: 'long',
    year:    'numeric',
    month:   'long',
    day:     'numeric',
  });
}

/**
 * Short date for event rows, e.g. "7 Jun" or "Today" / "Tomorrow".
 * @param {string|Date} isoOrDate
 * @returns {string}
 */
export function formatEventDate(isoOrDate) {
  const d = typeof isoOrDate === 'string' ? new Date(isoOrDate) : isoOrDate;
  const today = startOfDay(new Date());
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const target = startOfDay(d);

  if (target.getTime() === today.getTime())    return 'Today';
  if (target.getTime() === tomorrow.getTime()) return 'Tomorrow';

  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

/**
 * Short time string, e.g. "9:30 am" or "All day".
 * @param {string} iso ISO 8601 datetime string
 * @param {boolean} [allDay]
 * @returns {string}
 */
export function formatEventTime(iso, allDay = false) {
  if (allDay) return 'All day';
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, {
    hour:   'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Compact time range, e.g. "9:00 – 10:30 am".
 * @param {string} startIso
 * @param {string} endIso
 * @param {boolean} [allDay]
 * @returns {string}
 */
export function formatTimeRange(startIso, endIso, allDay = false) {
  if (allDay) return 'All day';
  const s = new Date(startIso);
  const e = new Date(endIso);
  const fmtTime = (d) =>
    d.toLocaleTimeString(undefined, {
      hour:   'numeric',
      minute: '2-digit',
      hour12: true,
    });
  const st = fmtTime(s);
  const et = fmtTime(e);
  // If both share the same am/pm we can strip the first
  return `${st} – ${et}`;
}

/**
 * Relative label: "in 2 hours", "3 days ago", etc.
 * @param {string|Date} isoOrDate
 * @returns {string}
 */
export function formatRelative(isoOrDate) {
  const d = typeof isoOrDate === 'string' ? new Date(isoOrDate) : isoOrDate;
  const diff = d.getTime() - Date.now(); // ms, positive = future
  const abs  = Math.abs(diff);
  const rtf  = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

  if (abs < 60_000)        return rtf.format(Math.round(diff / 1_000),   'second');
  if (abs < 3_600_000)     return rtf.format(Math.round(diff / 60_000),  'minute');
  if (abs < 86_400_000)    return rtf.format(Math.round(diff / 3_600_000),'hour');
  if (abs < 7 * 86_400_000) return rtf.format(Math.round(diff / 86_400_000),'day');
  return formatEventDate(d);
}

/**
 * Return a Date set to midnight of the given date.
 * @param {Date} d
 * @returns {Date}
 */
export function startOfDay(d) {
  const out = new Date(d);
  out.setHours(0, 0, 0, 0);
  return out;
}

/**
 * Group an array of events by date label (Today, Tomorrow, "7 Jun", …).
 * Returns an ordered array of { label, date, events[] }.
 * @param {import('../api/client').Event[]} events
 * @returns {Array<{ label: string, date: Date, events: import('../api/client').Event[] }>}
 */
export function groupEventsByDay(events) {
  const map = new Map();
  for (const event of events) {
    const d = startOfDay(new Date(event.start));
    const key = d.toISOString();
    const label = formatEventDate(d);
    if (!map.has(key)) {
      map.set(key, { label, date: d, events: [] });
    }
    map.get(key).events.push(event);
  }
  return Array.from(map.values()).sort((a, b) => a.date - b.date);
}
