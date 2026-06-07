# 🏡 Family Organiser

A locally-hosted, always-on **family organiser & smart-home dashboard** for large screens
and tablets. It merges everyone's calendars, runs a Google Photos slideshow, shows the
weather, and falls back to a beautiful photo screensaver when idle — all on your LAN, with
no public internet exposure.

Built **plugin-first**: the calendar, slideshow, and weather are themselves plugins, so new
modules (smart-home controls, Home Assistant, MQTT, …) drop in without touching core code.

![dark-mode dashboard](docs/screenshot.png) <!-- optional; add your own -->

---

## Features

- **Split-screen home** — 50% Google Photos slideshow with crossfades + 50% colour-coded
  family agenda. Ratio adjustable.
- **Unified calendar** — Google Calendar, Apple/iCloud CalDAV, and Outlook / Microsoft 365,
  each independently toggleable, merged into one timeline. Background sync + create events.
- **Google Photos slideshow** — pulls from shared albums, caches photos locally so it keeps
  working if the internet drops. Shows date + caption; tap to pause.
- **Weather** — current conditions + 3-day forecast via Open-Meteo (no API key).
- **Screensaver** — full-screen photo slideshow with a time/date overlay after a
  configurable idle period; any touch/click/key returns home.
- **Family profiles** — no logins; each member has a colour + emoji; events are tagged and
  shown in their colour.
- **Real-time** — every connected device updates live over WebSockets.
- **Plugin system** — self-contained Python + React plugins, enable/disable in settings.
  See [`PLUGIN_DEVELOPMENT.md`](./PLUGIN_DEVELOPMENT.md).
- **Premium dark-mode UI** — bespoke components, large legible type, smooth animations,
  touch-friendly.

---

## Architecture

- **Backend** — Python 3.11+, FastAPI, fully async (uvicorn). SQLite via SQLModel/aiosqlite.
- **Frontend** — React 18 + Vite + TailwindCSS (no UI component libraries).
- **Real-time** — native FastAPI WebSockets, single broadcast hub shared with plugins.
- **Deployment** — Docker Compose: an Nginx-served frontend + a Uvicorn backend, sharing a
  `./data` volume (SQLite db + photo cache).

The full interface contract lives in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Quickstart (Docker — recommended)

Prerequisites: Docker + Docker Compose on an always-on machine (PC / Mac / NAS).

```bash
git clone <this-repo> familycal && cd familycal
cp .env.example .env

# Generate the secret used to encrypt stored OAuth tokens / passwords:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → paste the value into SECRET_KEY in .env

# Set PUBLIC_BASE_URL to the DASHBOARD origin — the frontend address, NOT port 8000.
# OAuth redirects land back on the SPA, which is served by the frontend (:80), so:
#   PUBLIC_BASE_URL=http://192.168.1.50          # Docker: the LAN IP on port 80
# (used for OAuth redirect URIs — must match what you register with Google/Microsoft)

docker compose up -d --build
```

Open `http://<machine-LAN-IP>/` from any device on the network. The dashboard is served on
`:80` (this is the URL you use, including for OAuth). The backend is also exposed directly on
`:8000` for debugging/direct API access, but **OAuth must go through the `:80` dashboard origin**
(the backend port does not serve the web app, so an OAuth redirect to `:8000` would 404).

> You can use the dashboard immediately with just the weather widget. Calendars and photos
> light up once you connect them in **Settings** (see OAuth guides below).

### Find your LAN IP
- Linux/macOS: `ip addr` / `ifconfig` (look for `192.168.x.x` or `10.x.x.x`)
- Windows: `ipconfig`

---

## Local development (without Docker)

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env   # edit as needed; backend reads ../.env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev      # Vite dev server on http://localhost:5173, proxies /api + /ws to :8000
```

Run the backend tests:
```bash
cd backend && pytest
```

---

## Connecting your accounts

All OAuth secrets are stored **server-side only**, encrypted at rest, and are never sent to
the browser.

### Google (Calendar + Photos)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) → create/select a project.
2. **APIs & Services → Library** → enable **Google Calendar API** and **Photos Library API**.
3. **APIs & Services → OAuth consent screen** → choose *External* (or *Internal* for Workspace),
   add yourself as a test user, and add the scopes:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/photoslibrary.readonly`
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → *Web application*.
   - Authorized redirect URI: `${PUBLIC_BASE_URL}/api/oauth/google/callback`
     (e.g. `http://192.168.1.50/api/oauth/google/callback` for Docker on port 80, or
     `http://localhost:5173/api/oauth/google/callback` for local dev — use the **dashboard**
     origin, not `:8000`)
5. Copy the **Client ID** and **Client secret** into `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).
6. Restart, open **Settings → Calendar / Photos**, click **Connect Google**, and approve.
7. Pick your shared album(s) for the slideshow in **Settings → Photos**.

> Note: Google's Photos Library API only returns albums/media the connected account can see;
> use a shared album the family account owns or has joined.

### Microsoft 365 / Outlook

1. [Entra admin center](https://entra.microsoft.com/) → **App registrations → New registration**.
2. Supported account types: pick what suits your family (single-tenant or
   *Accounts in any organizational directory and personal Microsoft accounts*).
3. **Redirect URI** (platform *Web*): `${PUBLIC_BASE_URL}/api/oauth/microsoft/callback`
   (the **dashboard** origin — e.g. `http://192.168.1.50/...` on Docker, not `:8000`).
4. **Certificates & secrets → New client secret** → copy the *Value*.
5. **API permissions → Microsoft Graph → Delegated** → add `Calendars.ReadWrite`,
   `offline_access`, `User.Read` → *Grant admin consent* if required.
6. Put **Application (client) ID**, the **secret value**, and your **Directory (tenant) ID**
   (or `common`) into `.env` (`MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT_ID`).
7. Restart, **Settings → Calendar → Connect Microsoft**, approve.

### Apple iCloud / CalDAV

1. For iCloud, create an **app-specific password** at [appleid.apple.com](https://appleid.apple.com/)
   (Sign-In & Security → App-Specific Passwords).
2. In **Settings → Calendar → Add CalDAV**, enter:
   - Server URL: `https://caldav.icloud.com/` (or your provider's CalDAV URL)
   - Username: your Apple ID email
   - Password: the app-specific password
3. The credential is encrypted and stored server-side. Toggle the source on and sync.

---

## Settings overview

Reachable via the discreet gear icon on the dashboard:

- **Profiles** — add/edit/remove family members, colour, emoji.
- **Calendar** — connect sources, toggle each on/off, pick the primary calendar for new
  events, manual *Sync now*, live status indicators.
- **Photos** — choose Google Photos album(s), transition speed, per-photo duration.
- **Weather** — location (lat/lon + label), units.
- **Screensaver** — idle timeout (default 5 min).
- **Plugins** — enable/disable installed plugins, per-plugin settings.
- **Display** — split-screen ratio, transition speeds.

---

## Configuration reference

All configuration is via `.env` (see [`.env.example`](./.env.example) for the annotated list).
Key variables:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Fernet key encrypting stored secrets. **Required.** Rotating it invalidates stored tokens. |
| `PUBLIC_BASE_URL` | Externally-reachable backend URL; must match registered OAuth redirect URIs. |
| `DATA_DIR` | Where the SQLite db + photo cache live (the Docker volume). |
| `CORS_ORIGINS` | Allowed browser origins. `*` is acceptable on a trusted LAN. |
| `CALENDAR_SYNC_INTERVAL_MINUTES` | Background sync cadence (default 15). |
| `GOOGLE_*`, `MS_*` | OAuth app credentials. |
| `WEATHER_*` | Default weather location/units. |

---

## Troubleshooting

- **OAuth redirect mismatch** — the redirect URI registered with Google/Microsoft must
  *exactly* equal `${PUBLIC_BASE_URL}/api/oauth/<provider>/callback`, including scheme, host,
  and port. Update `PUBLIC_BASE_URL` if your LAN IP changes (consider a static lease).
- **OAuth succeeds but lands on a blank/404 page** — `PUBLIC_BASE_URL` is pointing at the
  backend port (`:8000`) instead of the dashboard origin. The post-login redirect goes to the
  SPA, which is served by the frontend (`:80` in Docker, `:5173` in dev), so set
  `PUBLIC_BASE_URL` to that origin (no `:8000`) and re-register the redirect URI to match.
- **Photos not showing** — confirm the album is selected in Settings and the connected
  account can access it; check backend logs for the slideshow plugin. Cached photos still
  show if Google is unreachable.
- **A calendar won't sync** — its source card shows the last error. Other sources keep
  working; the app never crashes on a sync failure.
- **Can't reach it from a tablet** — ensure the device is on the same LAN and use the
  machine's IP, not `localhost`. Check firewall rules for ports 80/8000.
- **WebSocket keeps reconnecting** — verify the Nginx proxy forwards the `Upgrade`/`Connection`
  headers (handled in the provided `nginx.conf`).

---

## Security notes

This app is designed for a **trusted LAN only** — do not expose it directly to the public
internet. Secrets are encrypted at rest and never leave the server. If you must reach it
remotely, put it behind a VPN (e.g. WireGuard/Tailscale) rather than port-forwarding.

---

## License

MIT — see `LICENSE`.
