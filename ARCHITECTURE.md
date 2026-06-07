# Family Organiser — Architecture & Shared Contract

This document is the **authoritative contract** between the backend and frontend.
Both sides MUST conform to the interfaces defined here. Changes to this file must be
agreed by the team lead before implementation diverges.

---

## 1. High-level layout

```
familycal/
├── backend/                 # FastAPI + asyncio + SQLModel
│   ├── app/
│   │   ├── main.py          # app factory, lifespan, router mount, WS endpoint
│   │   ├── config.py        # pydantic-settings, reads .env
│   │   ├── database.py      # async engine + session dependency
│   │   ├── models.py        # SQLModel tables
│   │   ├── schemas.py       # Pydantic request/response DTOs
│   │   ├── websocket.py     # ConnectionManager (broadcast hub)
│   │   ├── core/            # crypto, oauth, scheduler, settings store
│   │   ├── plugins/         # plugin base, loader, registry, context
│   │   └── routers/         # profiles, events, settings, plugins, oauth, system
│   └── plugins/             # built-in plugins (calendar, slideshow, weather)
├── frontend/                # React 18 + Vite + Tailwind
│   └── src/
│       ├── api/             # REST client + WS client
│       ├── hooks/           # useWebSocket, useSettings, useIdle, etc.
│       ├── components/      # bespoke UI primitives
│       ├── pages/           # Home, Screensaver, Settings
│       └── plugins/         # frontend plugin registry + built-in plugin UIs
├── docker-compose.yml
├── .env.example
├── README.md
└── PLUGIN_DEVELOPMENT.md
```

All backend I/O is async. No blocking calls in route handlers or background tasks
(wrap unavoidable sync SDK calls with `anyio.to_thread.run_sync`).

---

## 2. REST API surface

Base path: `/api`. All responses JSON. All list endpoints return arrays.
Errors use `{"detail": "<message>"}` with appropriate HTTP status.

### Profiles
- `GET    /api/profiles` → `Profile[]`
- `POST   /api/profiles` → `Profile`            body: `ProfileCreate`
- `PATCH  /api/profiles/{id}` → `Profile`       body: `ProfileUpdate`
- `DELETE /api/profiles/{id}` → `204`

### Events
- `GET    /api/events?start=<iso>&end=<iso>&profile_id=<id>` → `Event[]`
- `GET    /api/events/agenda?days=<n>` → `Event[]` (today + next n days, ordered)
- `POST   /api/events` → `Event`                body: `EventCreate` (writes to source calendar if `source != "local"`)
- `PATCH  /api/events/{id}` → `Event`           body: `EventUpdate`
- `DELETE /api/events/{id}` → `204`

### Settings (generic key/value, namespaced)
- `GET    /api/settings` → `{ [key: string]: any }`  (all settings, secrets redacted)
- `GET    /api/settings/{key}` → `{ key, value }`
- `PUT    /api/settings/{key}` → `{ key, value }`     body: `{ value: any }`

### Calendar sources
- `GET    /api/calendar/sources` → `CalendarSource[]`  (status, enabled, last_sync)
- `PATCH  /api/calendar/sources/{id}` → `CalendarSource`  body: `{ enabled?: bool, primary?: bool }`
- `POST   /api/calendar/sync` → `{ started: true }`   (triggers immediate background sync)
- `POST   /api/calendar/sources/caldav` → `CalendarSource`  body: `CalDAVCreate`

### Plugins
- `GET    /api/plugins` → `PluginInfo[]`
- `PATCH  /api/plugins/{name}` → `PluginInfo`   body: `{ enabled: bool }`
- `GET    /api/plugins/{name}/settings` → settings object (per plugin schema)
- `PUT    /api/plugins/{name}/settings` → settings object
- Plugin-mounted routers live under `/api/plugins/{name}/...`

### OAuth (server-side only; secrets never sent to client)
- `GET    /api/oauth/{provider}/authorize` → `{ url }`  (provider ∈ google, microsoft)
- `GET    /api/oauth/{provider}/callback?code=...&state=...` → redirect to `/settings?oauth={provider}`
- `GET    /api/oauth/{provider}/status` → `{ connected: bool, account?: string }`
- `DELETE /api/oauth/{provider}` → `204`  (revoke + delete stored token)

### System
- `GET    /api/system/health` → `{ status: "ok", version, time }`
- `GET    /api/system/status` → `{ sync, plugins, websocket_clients }` (dashboard health)

### WebSocket
- `WS /ws` — see §4.

---

## 3. Data models (SQLModel tables → JSON shapes)

```ts
// Profile
{ id: number, name: string, color: string /*hex*/, emoji: string, created_at: iso }

// Event (unified across all calendar sources)
{
  id: number,
  uid: string,              // stable source UID for dedupe
  source: "local"|"google"|"caldav"|"outlook",
  calendar_id: string,      // source calendar identifier
  title: string,
  description: string|null,
  location: string|null,
  start: iso,               // ISO8601 with tz
  end: iso,
  all_day: boolean,
  profile_ids: number[],    // tagged family members
  color: string|null,       // resolved display color (first profile or source)
  created_at: iso,
  updated_at: iso
}

// Setting
{ key: string, value: any /*JSON*/, updated_at: iso }

// CalendarSource
{ id: string, kind: "google"|"caldav"|"outlook", label: string,
  enabled: boolean, primary: boolean, status: "ok"|"error"|"syncing"|"unconfigured",
  last_sync: iso|null, last_error: string|null }

// PluginInfo
{ name: string, version: string, description: string, enabled: boolean,
  has_router: boolean, has_background_tasks: boolean,
  frontend_component: string|null, settings_schema: object|null }
```

Secrets (OAuth tokens, CalDAV passwords) live in a separate `secret` table,
encrypted at rest (Fernet). They are **never** serialized to the frontend.

---

## 4. WebSocket protocol

Single endpoint `/ws`. Server → client messages are JSON envelopes:

```ts
{ type: string, channel: string, payload: any, ts: iso }
```

Standard channels / types broadcast by core + plugins:
- `events.updated`     — calendar data changed; payload `{ count }` → client refetches agenda
- `sync.status`        — `{ source, status, last_sync, last_error }`
- `photos.updated`     — slideshow cache changed; payload `{ count }`
- `weather.updated`    — payload = full weather snapshot (see weather plugin)
- `plugin.state`       — `{ name, enabled }`
- `settings.updated`   — `{ key }`
- `pong`               — heartbeat reply

Client → server messages:
- `{ "type": "ping" }` → server replies `pong`
- `{ "type": "subscribe", "channels": string[] }` (optional filtering; default = all)

The broadcast hub is exposed to plugins via `PluginContext.broadcast(type, channel, payload)`.

---

## 5. Plugin contract (backend)

A plugin is a Python package under `backend/plugins/<pkg>/` exporting a module-level
`plugin` object (instance of `app.plugins.base.Plugin`) OR a `get_plugin(context)` factory.

```python
from app.plugins.base import Plugin, PluginManifest

manifest = PluginManifest(
    name="weather",
    version="1.0.0",
    description="Current conditions and 3-day forecast via Open-Meteo",
    frontend_component="WeatherWidget",     # name registered in frontend registry
    settings_schema={...},                  # JSON-schema-ish dict for settings UI
    default_settings={...},
)

class WeatherPlugin(Plugin):
    manifest = manifest
    def register_router(self) -> APIRouter | None: ...   # mounted at /api/plugins/<name>
    async def start(self, ctx: PluginContext) -> None:   # spawn background tasks
    async def stop(self) -> None:                        # cancel tasks, cleanup

plugin = WeatherPlugin()
```

`PluginContext` provides:
- `await broadcast(type, channel, payload)` — push a WS envelope to all clients
- `await get_settings() / set_settings(dict)` — per-plugin persisted settings (merged over defaults)
- `await get_secret(key) / set_secret(key, value)` — Fernet-encrypted secret store (never sent to frontend)
- `db_session()` — async context manager → `AsyncSession`
- `http` — shared `httpx.AsyncClient`
- `schedule(coro_fn, interval_seconds, run_immediately=False)` — register a periodic task (auto-cancelled on `stop()`)
- `register_capability(name, fn)` / `resolve_capability(name)` — publish/look up a named callable so plugins expose actions to core routers (or each other) **without imports**; auto-deregistered on `stop()`. This is how core delegates event write-back/sync to the calendar plugin (e.g. `"calendar.write_event"`) with no plugin-specific code in core — and how future Home Assistant/MQTT plugins expose control actions.
- `config` (app Settings), `data_dir` (Path), `logger`

The loader scans `backend/plugins/`, imports each, respects the `enabled` flag stored
in DB, mounts routers, and runs `start()` for enabled plugins during app lifespan.
Disabling a plugin calls `stop()` and unmounts (router 404s while disabled).

Full details in `PLUGIN_DEVELOPMENT.md`.

---

## 6. Plugin contract (frontend)

`frontend/src/plugins/registry.js` exports `registerPlugin(name, { component, settingsPanel })`
and `getPluginComponent(name)`. Built-in plugin UIs register themselves on import.
The Home page asks the registry for the component named by each enabled plugin's
`frontend_component`. Unknown component → graceful fallback card.

Frontend plugin components receive props:
```ts
{ settings: object, ws: WSClient, api: ApiClient, profiles: Profile[], fullscreen: boolean }
```

A runtime ESM bundle path (`/api/plugins/<name>/bundle.js`) is also supported for
third-party plugins (documented, optional). Built-ins use the static registry.

---

## 7. Environment / config keys

See `.env.example`. Backend reads everything via `app.config.Settings`.
Frontend reads only `VITE_*` public vars (API base, WS base). **No secrets in frontend.**
