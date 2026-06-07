// ─────────────────────────────────────────────────────────────────────────────
// ApiClient — typed fetch wrapper covering all REST endpoints from ARCHITECTURE §2.
// Uses VITE_API_BASE (defaults to /api) so the Vite dev proxy routes to the
// backend and the production nginx config can do the same.
// All methods return parsed JSON or throw an ApiError with a human-readable message.
// ─────────────────────────────────────────────────────────────────────────────

const BASE = import.meta.env.VITE_API_BASE ?? '/api';

// ── Error type ────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status  HTTP status code
   * @param {string} [detail] Backend "detail" field if present
   */
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail ?? message;
  }
}

// ── Internal fetch helper ─────────────────────────────────────────────────────

/**
 * Core fetch wrapper. Throws ApiError on non-2xx responses.
 *
 * @param {string} path      Path relative to BASE, e.g. "/profiles"
 * @param {RequestInit} [init]
 * @returns {Promise<any>}   Parsed JSON, or null for 204/empty responses
 */
async function request(path, init = {}) {
  const url = `${BASE}${path}`;

  const headers = { 'Content-Type': 'application/json', ...(init.headers ?? {}) };

  const res = await fetch(url, { ...init, headers });

  if (res.status === 204 || res.headers.get('Content-Length') === '0') {
    return null;
  }

  // Always try to parse JSON — backends return {"detail": "..."} on errors
  let body;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    const detail = body?.detail ?? `HTTP ${res.status}`;
    throw new ApiError(detail, res.status, detail);
  }

  return body;
}

// ── Convenience wrappers ──────────────────────────────────────────────────────

const get    = (path, params) => {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request(`${path}${qs}`);
};
const post   = (path, body)  => request(path, { method: 'POST',   body: JSON.stringify(body) });
const patch  = (path, body)  => request(path, { method: 'PATCH',  body: JSON.stringify(body) });
const put    = (path, body)  => request(path, { method: 'PUT',    body: JSON.stringify(body) });
const del    = (path)        => request(path, { method: 'DELETE' });

// ─────────────────────────────────────────────────────────────────────────────
// ApiClient object — one import, all endpoints
// ─────────────────────────────────────────────────────────────────────────────

const ApiClient = {
  // ── Profiles ───────────────────────────────────────────────────────────────

  /** @returns {Promise<Profile[]>} */
  getProfiles: () => get('/profiles'),

  /** @param {ProfileCreate} data @returns {Promise<Profile>} */
  createProfile: (data) => post('/profiles', data),

  /** @param {number} id @param {ProfileUpdate} data @returns {Promise<Profile>} */
  updateProfile: (id, data) => patch(`/profiles/${id}`, data),

  /** @param {number} id @returns {Promise<null>} */
  deleteProfile: (id) => del(`/profiles/${id}`),

  // ── Events ─────────────────────────────────────────────────────────────────

  /**
   * @param {{ start?: string, end?: string, profile_id?: number }} [params]
   * @returns {Promise<Event[]>}
   */
  getEvents: (params) => get('/events', params),

  /**
   * Upcoming agenda (today + next n days, ordered).
   * @param {number} [days=7]
   * @returns {Promise<Event[]>}
   */
  getAgenda: (days = 7) => get('/events/agenda', { days }),

  /** @param {EventCreate} data @returns {Promise<Event>} */
  createEvent: (data) => post('/events', data),

  /** @param {number} id @param {EventUpdate} data @returns {Promise<Event>} */
  updateEvent: (id, data) => patch(`/events/${id}`, data),

  /** @param {number} id @returns {Promise<null>} */
  deleteEvent: (id) => del(`/events/${id}`),

  // ── Settings ───────────────────────────────────────────────────────────────

  /** @returns {Promise<Record<string, any>>} All settings, secrets redacted */
  getAllSettings: () => get('/settings'),

  /** @param {string} key @returns {Promise<{ key: string, value: any }>} */
  getSetting: (key) => get(`/settings/${key}`),

  /** @param {string} key @param {any} value @returns {Promise<{ key: string, value: any }>} */
  setSetting: (key, value) => put(`/settings/${key}`, { value }),

  // ── Calendar sources ───────────────────────────────────────────────────────

  /** @returns {Promise<CalendarSource[]>} */
  getCalendarSources: () => get('/calendar/sources'),

  /**
   * @param {string} id
   * @param {{ enabled?: boolean, primary?: boolean }} data
   * @returns {Promise<CalendarSource>}
   */
  updateCalendarSource: (id, data) => patch(`/calendar/sources/${id}`, data),

  /** Trigger an immediate background sync. @returns {Promise<{ started: true }>} */
  triggerSync: () => post('/calendar/sync', {}),

  /** @param {CalDAVCreate} data @returns {Promise<CalendarSource>} */
  addCalDAVSource: (data) => post('/calendar/sources/caldav', data),

  // ── Plugins ────────────────────────────────────────────────────────────────

  /** @returns {Promise<PluginInfo[]>} */
  getPlugins: () => get('/plugins'),

  /** @param {string} name @param {boolean} enabled @returns {Promise<PluginInfo>} */
  setPluginEnabled: (name, enabled) => patch(`/plugins/${name}`, { enabled }),

  /** @param {string} name @returns {Promise<object>} */
  getPluginSettings: (name) => get(`/plugins/${name}/settings`),

  /** @param {string} name @param {object} settings @returns {Promise<object>} */
  setPluginSettings: (name, settings) => put(`/plugins/${name}/settings`, settings),

  /**
   * Fetch a plugin's live data endpoint at /api/plugins/{name}/{path}.
   * Prefer this over raw fetch() so VITE_API_BASE is always honoured.
   *
   * @param {string} name   Plugin name, e.g. "weather"
   * @param {string} [path] Sub-path, e.g. "current"  (default: "")
   * @returns {Promise<any>}
   */
  getPluginData: (name, path = '') => get(`/plugins/${name}${path ? `/${path}` : ''}`),

  // ── OAuth ──────────────────────────────────────────────────────────────────

  /**
   * Get the OAuth authorisation URL for a provider.
   * The caller should navigate the browser to the returned URL;
   * secrets are handled entirely server-side.
   *
   * @param {'google'|'microsoft'} provider
   * @returns {Promise<{ url: string }>}
   */
  getOAuthUrl: (provider) => get(`/oauth/${provider}/authorize`),

  /** @param {'google'|'microsoft'} provider @returns {Promise<{ connected: boolean, account?: string }>} */
  getOAuthStatus: (provider) => get(`/oauth/${provider}/status`),

  /** @param {'google'|'microsoft'} provider @returns {Promise<null>} */
  revokeOAuth: (provider) => del(`/oauth/${provider}`),

  // ── System ─────────────────────────────────────────────────────────────────

  /** @returns {Promise<{ status: string, version: string, time: string }>} */
  getHealth: () => get('/system/health'),

  /** @returns {Promise<{ sync: any, plugins: any, websocket_clients: number }>} */
  getStatus: () => get('/system/status'),
};

export default ApiClient;

// ── JSDoc type aliases (kept here for co-location with the client) ─────────────
/**
 * @typedef {{ id: number, name: string, color: string, emoji: string, created_at: string }} Profile
 * @typedef {{ name: string, color?: string, emoji?: string }} ProfileCreate
 * @typedef {Partial<ProfileCreate>} ProfileUpdate
 *
 * @typedef {{
 *   id: number, uid: string, source: string, calendar_id: string,
 *   title: string, description: string|null, location: string|null,
 *   start: string, end: string, all_day: boolean,
 *   profile_ids: number[], color: string|null,
 *   created_at: string, updated_at: string
 * }} Event
 * @typedef {{ title: string, start: string, end: string, all_day?: boolean, source?: string, calendar_id?: string, description?: string, location?: string, profile_ids?: number[], color?: string }} EventCreate
 * @typedef {Partial<EventCreate>} EventUpdate
 *
 * @typedef {{ id: string, kind: string, label: string, enabled: boolean, primary: boolean, status: string, last_sync: string|null, last_error: string|null }} CalendarSource
 * @typedef {{ url: string, username: string, password: string, label?: string }} CalDAVCreate
 *
 * @typedef {{ name: string, version: string, description: string, enabled: boolean, has_router: boolean, has_background_tasks: boolean, frontend_component: string|null, settings_schema: object|null }} PluginInfo
 */
