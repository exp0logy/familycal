# Plugin Development Guide

The Family Organiser is **plugin-first**. The calendar, photo slideshow, and weather
widgets are themselves plugins — the core has no special knowledge of them. Anything
they can do, your plugin can do, with **zero changes to core code**.

This guide is the practical companion to the contract in [`ARCHITECTURE.md`](./ARCHITECTURE.md)
(§5 backend, §6 frontend). Read that first.

---

## 1. Anatomy of a plugin

A backend plugin is a Python package under `backend/plugins/<your_plugin>/`:

```
backend/plugins/myplugin/
├── __init__.py        # exports `plugin` (a Plugin instance) or `get_plugin(ctx)`
├── manifest.py        # optional split-out; or define inline
├── service.py         # your async business logic
└── router.py          # optional FastAPI APIRouter
```

The loader (`app/plugins/loader.py`) scans this directory on startup, imports each
package, finds a module-level `plugin` object (or calls `get_plugin(context)`),
reads its enabled flag from the DB, mounts its router at `/api/plugins/<name>`, and
runs its lifecycle hooks.

A frontend plugin registers a React component in the shared registry so the dashboard
can render it (see §5).

---

## 2. The manifest

```python
from app.plugins.base import PluginManifest

manifest = PluginManifest(
    name="myplugin",                     # unique, lowercase, url-safe; used in routes
    version="1.0.0",
    description="What this plugin does",
    frontend_component="MyPluginWidget", # name registered in the frontend registry (or None)
    settings_schema={                    # drives the auto-generated settings form
        "type": "object",
        "properties": {
            "refresh_seconds": {"type": "integer", "title": "Refresh interval (s)", "default": 300},
            "api_url": {"type": "string", "title": "Endpoint URL"},
        },
    },
    default_settings={"refresh_seconds": 300, "api_url": ""},
    requires_secrets=[],                 # secret keys this plugin reads (documented, optional)
)
```

`settings_schema` is a JSON-Schema-shaped dict. The Settings UI renders a form from it;
values are persisted per-plugin and returned to your code via `ctx.get_settings()`.

---

## 3. The Plugin class & lifecycle

```python
from fastapi import APIRouter
from app.plugins.base import Plugin, PluginContext
from .manifest import manifest
from .router import build_router
from .service import MyService

class MyPlugin(Plugin):
    manifest = manifest

    def __init__(self) -> None:
        self._service: MyService | None = None

    # Mounted at /api/plugins/myplugin  (return None if you expose no HTTP API)
    def register_router(self) -> APIRouter | None:
        return build_router(self)

    # Called once when the plugin is enabled (app start, or toggled on at runtime).
    async def start(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._service = MyService(ctx)
        # Register a periodic background task with the shared scheduler:
        ctx.schedule(self._service.refresh, interval_seconds=300, run_immediately=True)

    # Called when disabled or on app shutdown. Cancel tasks, close resources.
    async def stop(self) -> None:
        if self._service:
            await self._service.aclose()

plugin = MyPlugin()
```

Lifecycle guarantees:

- `start()` runs only for **enabled** plugins. Disabling a plugin calls `stop()` and
  its router returns 404 until re-enabled.
- Exceptions in `start()` are caught and logged; one bad plugin never prevents the app
  (or other plugins) from booting. The plugin is marked `status: "error"`.
- Background tasks registered via `ctx.schedule(...)` are wrapped so a single failed run
  is logged and retried next interval — the loop never dies.

---

## 4. PluginContext API

Your plugin receives a `PluginContext` in `start()`. It is the **only** interface you
need to the core — this is what keeps plugins decoupled.

| Member | Description |
|---|---|
| `await ctx.broadcast(type, channel, payload)` | Push a WebSocket envelope to all connected clients (see ARCHITECTURE §4). |
| `await ctx.get_settings() -> dict` | This plugin's persisted settings merged over `default_settings`. |
| `await ctx.set_settings(dict)` | Persist (partial) settings; broadcasts `settings.updated`. |
| `ctx.db_session()` | Async context manager yielding an `AsyncSession`. |
| `ctx.http` | Shared `httpx.AsyncClient` (connection pooling, sane timeouts). |
| `await ctx.get_secret(key) / ctx.set_secret(key, value)` | Encrypted secret storage (Fernet). Never exposed to the frontend. |
| `ctx.config` | The app `Settings` (env-derived). |
| `ctx.data_dir` | `Path` to the writable data dir (cache files here). |
| `ctx.logger` | A namespaced logger. |
| `ctx.schedule(coro_fn, interval_seconds, run_immediately=False)` | Register a periodic async task; auto-cancelled on `stop()`. |
| `ctx.register_capability(name, fn)` / `ctx.resolve_capability(name)` | Publish a named callable that other plugins or core routers can invoke **without importing your package**; `resolve_capability` returns the callable (or `None`). Auto-deregistered on `stop()`. This is how the built-in calendar plugin exposes `"calendar.write_event"` / `"calendar.sync_all"` / `"calendar.store_caldav_credentials"` to the core events/calendar routers — and the same mechanism a Home Assistant plugin would use to expose `"homeassistant.call_service"`. |

**Async rule:** never block the event loop. For unavoidable sync SDK calls
(`google-api-python-client`, `caldav`, `msal`), wrap them:
`await anyio.to_thread.run_sync(blocking_call, arg)`.

---

## 5. Frontend side

Register a component in `frontend/src/plugins/registry.js`:

```jsx
import { registerPlugin } from "./registry";
import MyPluginWidget from "./MyPluginWidget";

registerPlugin("MyPluginWidget", {
  component: MyPluginWidget,        // matches manifest.frontend_component
  settingsPanel: null,             // optional custom settings UI; else schema-driven form
});
```

Your component receives these props (ARCHITECTURE §6):

```ts
{ settings: object, ws: WSClient, api: ApiClient, profiles: Profile[], fullscreen: boolean }
```

- Subscribe to your channel: `ws.on("myplugin.updated", payload => ...)`.
- Call your router: `api.getPluginData("myplugin", "data")` → `GET /api/plugins/myplugin/data`.
- `fullscreen` is `true` when rendered as the screensaver, `false` in the split layout.

Unknown component names render a graceful fallback card, so a backend plugin without a
matching frontend component still appears (just inert).

### Third-party runtime bundles (optional)

For plugins shipped outside this repo, expose an ESM bundle from your router at
`/api/plugins/<name>/bundle.js` that default-exports `{ name, component }`. The frontend
will `import()` it at runtime and register it. Built-in plugins use the static registry
above (simpler, tree-shakeable).

---

## 6. Worked example: a "name day" plugin

```python
# backend/plugins/nameday/__init__.py
from fastapi import APIRouter
from app.plugins.base import Plugin, PluginManifest, PluginContext

manifest = PluginManifest(
    name="nameday", version="1.0.0",
    description="Shows whose name day it is today",
    frontend_component="NameDayCard",
    settings_schema={"type": "object", "properties": {
        "country": {"type": "string", "title": "Country code", "default": "se"}}},
    default_settings={"country": "se"},
)

class NameDayPlugin(Plugin):
    manifest = manifest

    def register_router(self) -> APIRouter:
        r = APIRouter()
        @r.get("/today")
        async def today():
            s = await self.ctx.get_settings()
            resp = await self.ctx.http.get(
                f"https://nameday.abalin.net/api/V2/today?country={s['country']}")
            return resp.json()
        return r

    async def start(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.schedule(self._tick, interval_seconds=3600, run_immediately=True)

    async def _tick(self) -> None:
        s = await self.ctx.get_settings()
        resp = await self.ctx.http.get(
            f"https://nameday.abalin.net/api/V2/today?country={s['country']}")
        await self.ctx.broadcast("nameday.updated", "nameday", resp.json())

    async def stop(self) -> None: ...

plugin = NameDayPlugin()
```

That is a complete, working plugin — no core files were touched.

---

## 7. Future plugins (pattern only — not yet built)

The plugin API is intentionally capable enough for richer integrations **without any
core changes**:

### Home Assistant
- **REST**: in `start()`, read the HA base URL + long-lived token via `ctx.get_secret()`,
  poll `GET /api/states` through `ctx.http`, broadcast `homeassistant.state` envelopes.
- **WebSocket**: open a long-lived client to HA's `/api/websocket` inside a task spawned
  from `start()`, authenticate, `subscribe_events`, and relay state-changed events to the
  dashboard via `ctx.broadcast(...)`. Expose a router `POST /api/plugins/homeassistant/service`
  to call HA services (e.g. toggle a light) — the frontend component renders controls.

### MQTT
- In `start()`, connect an async MQTT client (e.g. `aiomqtt`) to the broker (creds from
  `ctx.get_secret()`), subscribe to topics from settings, and broadcast incoming messages
  as `mqtt.message` envelopes. A router endpoint publishes commands back to topics for
  direct device control.

Both fit the existing `Plugin` + `PluginContext` model: background tasks via `ctx.schedule`
or a task spawned in `start()`, secrets via the encrypted store, real-time push via
`ctx.broadcast`, HTTP via `ctx.http`, and a mounted router for actions. No core modification
is required — which is the whole point of the architecture.
