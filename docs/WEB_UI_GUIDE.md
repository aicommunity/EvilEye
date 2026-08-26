# EvilEye Web UI

React SPA (Vite) served by FastAPI from `evileye/api/static/`.

## Runtime vs build

| Need | What to install |
|------|-----------------|
| API + serve existing SPA | `pip install evileye` (or `-e .`) — FastAPI/uvicorn are main deps; static ships in the package when present |
| Fast JPEG live preview | Python `PyTurboJPEG` (main dep) **and** system `libturbojpeg` (`sudo apt install libturbojpeg`) |
| Rebuild / first-time SPA from sources | Node.js + `npm` → `evileye setup-web` or manual `npm run build` |

Recommended:

```bash
pip install evileye   # или: pip install -e . для разработки
# optional: sudo apt install libturbojpeg
evileye deploy
evileye install-server
# open http://127.0.0.1:8181 (or https://… if TLS was configured)
# login as admin with bootstrap password from first-start log
# change password → complete Basic Setup in Configure
```

See [`CLI_SETUP_WEB.md`](CLI_SETUP_WEB.md).

Deployment with or without a reverse proxy (Traefik, direct `:8181` TLS/HTTP): [`WEB_UI_REVERSE_PROXY.md`](WEB_UI_REVERSE_PROXY.md).

### Playback diagnostics

On `/playback`, enable verbose seek/play diagnostics:

```js
localStorage.setItem('playbackDebug', '1'); location.reload();
// or: window.__playbackDebug.setEnabled(true)
window.__playbackDebug.snapshot();
```

## Routes

| Path | Permission | Description |
|------|------------|-------------|
| `/live` | `live:view` | Compact camera grid (WS preview / snapshot fallback); expand opens MJPEG + metadata overlays (pre-warm `stream` demand, loading/error/retry) |
| `/events` | `journal:view` | Journals + export + detail drawer (letterbox overlays) |
| `/playback` | `journal:view` | Live-like grid + bottom timeline; logical cameras from run config; split crop |
| `/configure` | `config:view` | Settings: **Basic** mode by default (data dir, JSON/DB, sources, analytics, recording); Advanced = full Config Studio. Works without an active run (`system.json`) |
| `/admin/runs` | `runtime:view` | Read-only active/current runs (create/start also via Basic «Save and run» with `runtime:control`) |
| `/admin/configs` | `config:view` | Config file list; open Studio or Raw JSON |
| `/admin/configs/:name` | `config:view` | Config Studio / Basic for a chosen file (forms, ROI/Zones, history) |
| `/admin/logs` | `logs:view` | Log files + Follow (SSE tail) |
| `/admin/users` | `users:manage` | User management (credentials.json + web_users.json; role/password/disable/delete; **camera ACL** by `source_name`) |
| `/admin/bans` | `bans:manage` | IP ban list (auto + manual add/remove) |
| `/settings` | authenticated | Language, date format, visible cameras (prefs), change password |
| `/admin/overview` | — | Redirect → `/live` |
| `/admin/history` | — | Redirect → `/admin/runs` |
| `/m/live`, `/m/events` | — | Compact mobile views |

Language and date format live on **Settings** (`/settings`) and sync to the server via `PUT /api/v1/auth/prefs` when auth is enabled (localStorage keys `evileye.ui.lang` / `evileye.ui.dateFormat` still used as client cache).
Config mode Basic/Advanced is stored in `localStorage` key `evileye.config.mode` (default **basic**).

### Camera ACL and visible cameras

- **Admin ACL** (`allowed_cameras` on the user record): which `source_name` values a non-admin may access. Empty list → **no cameras**. Role `admin` always bypasses ACL.
- **User prefs** (`prefs.visible_cameras`): subset of allowed cameras to show in Live/Playback/Events lists. `null` → all allowed; `[]` → none in UI lists.
- Hard enforcement (403) on streams / WS / playback media uses ACL only; list endpoints also apply visible prefs.
- Events journal always keeps `source_name=System` rows.
- After upgrading, legacy users without `allowed_cameras` default to **empty** — assign cameras under `/admin/users`.

## First-run / Basic setup

1. Choose a dedicated site directory and run `evileye deploy` there. EvilEye uses the current working directory as site root (`credentials.json`, `configs/`, `logs/`, `monitor/`).
2. `evileye deploy` prepares site files and monitor assets (no prompts) — этого достаточно для локальной работы. Если нужен сервер Web UI, `evileye install-server` при необходимости запускает `setup-web`, затем HTTPS и OS-сервис.
3. Start the backend via OS service or manually:
   ```bash
   evileye server --host 0.0.0.0 --port 8181 --no-reload
   ```
   If `server.ssl_*` is set, the same command listens with TLS (or pass `--ssl-certfile` / `--ssl-keyfile`). Open `https://127.0.0.1:8181` (`curl -k` until `certs/ca.crt` is trusted).
4. Open Web UI → log in as `admin` with the bootstrap password from the first-start log → forced password change when `must_change_password` is set.
5. **Настройка**: Basic form → data directory, JSON vs PostgreSQL, sources, analytics, recording → Save / Save and run.
6. APIs: `GET /api/v1/setup/status`, `GET|PUT /api/v1/setup/basic`, `POST /api/v1/setup/check-data-dir`, `POST /api/v1/setup/test-database`.

`evileye run configs/system.json --no-gui` is the next step after setup when you want to launch the runtime/pipeline itself. It is not required just to bring up the Web UI/backend.

Advanced Config Studio remains available after setup (or when a data directory is already present).

## Build & test

```bash
evileye setup-web --build
# or manually:
cd evileye/api/frontend && npm install && npm run build
npm test   # vitest (journalMath)
# optional e2e (server must be up):
npx playwright test tests/e2e/web_smoke.spec.ts
# optional WS load smoke (server must be up, auth off or cookie jar):
python scripts/ws_live_preview_load.py --run-id 1 --clients 20
```

## Key APIs

- Streaming: `/api/v1/runs/{rid}/snapshot|stream.mjpg|stream:status|metadata`
  - `GET` / `POST /stream:status` with body `{ "level": "grid"|"stream" }` (demand keepalive)
  - Snapshot supports `ETag` / `If-None-Match` → `304`
- Preview WS: `/api/v1/runs/{rid}/ws/live` (grid JPEG push; auth `live:view`)
- Metadata WS: `/api/v1/runs/{rid}/ws` (objects/zones for expand/MJPEG)
- Internal relay: `POST /api/v1/internal/frames/{rid}` accepts JPEG or multipart (`metadata` JSON + `frame`)
- Playback: `/api/v1/playback/cameras?run_id=&date=` (logical cameras), `segments`, `events?cameras=`, `media`
- Config sections / editors / history / journals / logs SSE — unchanged

Mobile: `/m/live` — one camera carousel (snapshot by default; MJPEG only in fullscreen); `/m/events` — event feed.

## Live transport matrix

| Mode | Transport | Demand level |
|------|-----------|--------------|
| Live grid | WS `/ws/live` binary JPEG (default) | `grid` (~2 fps encode) |
| Live grid (WAN) | WS notify + GET snapshot + ETag | `grid` |
| Live expand / fullscreen | MJPEG `stream.mjpg` + metadata WS | `stream` (`publish_fps`) |
| Live fallback | GET snapshot (+ ETag) when WS down | `grid` |
| Playback | file URL `/playback/media` | none |
| Tab closed / idle | no demand | `idle` (encode off; `EVILEYE_PREVIEW_HEARTBEAT_FPS` default `0`) |

Grid click = select only (no MJPEG). Double-click / expand button opens in-grid MJPEG; Esc collapses.

Expand flow: UI posts `stream:status` with `level=stream` (pre-warm), polls until `has_frame` (or ~5s timeout), then attaches `<img src=…/stream.mjpg>`. Loading / error + Retry are shown if the stream fails. MJPEG no longer returns 409 when the broker is still empty — the generator waits for the first JPEG up to `EVILEYE_MJPEG_IDLE_SEC`.

### Camera status dots (Live grid)

| Color | Mode | Meaning |
|-------|------|---------|
| Green | `live` | Preview frame age within hysteresis window |
| Yellow | `stale` / `error` | Preview lagging, capture reconnect, or image load error |
| Grey | `offline` | Run not `running` |

UI thresholds (client): enter yellow when effective frame age **> 12 s**; return to green only when age **< 5 s** (hysteresis). Metadata WS stays subscribed while the run is active; overlays stay visible (dimmed) during brief stale and are cleared on offline / hard error / capture reconnect.

**WAN tip:** set `EVILEYE_WS_PREVIEW_MODE=notify` so the hub sends small JSON notifies and clients fetch snapshots via HTTP (avoids large binary JPEG over a high-latency link). Hub fan-out uses per-client latest-wins queues and `EVILEYE_WS_PREVIEW_SEND_TIMEOUT_SEC` so one slow client cannot stall others.

### Users API (admin)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/users` | Merged list: `credentials.json` (`source=credentials`) + `web_users.json` (`source=store`); includes `allowed_cameras` |
| GET | `/api/v1/users/camera-catalog` | Unique `source_name`s from active runs (for ACL UI) |
| POST | `/api/v1/users` | Create store user (approved); default `allowed_cameras: []` |
| PATCH | `/api/v1/users/{id}` | role / disabled / status / password / `allowed_cameras` |
| DELETE | `/api/v1/users/{id}` | Guards: no self-delete, no last-admin delete |
| GET | `/api/v1/auth/me` | Session + `allowed_cameras`, `camera_access`, `prefs` |
| PUT | `/api/v1/auth/prefs` | Self prefs: `visible_cameras`, `lang`, `date_format` |
| POST | `/api/v1/auth/change-password` | Self-service (`current_password` + `new_password`) |

Settings page (`/settings`): language, date format, visible cameras, change password.

## Env vars (preview / streaming)

| Env | Default | Meaning |
|-----|---------|---------|
| `EVILEYE_PREVIEW_HEARTBEAT_FPS` | `0` | Encode while server alive but no UI demand |
| `EVILEYE_PREVIEW_GRID_FPS` | `2.0` | Encode FPS for grid / snapshot / live WS demand |
| `EVILEYE_PREVIEW_DEMAND_TTL_SEC` | `45` | Drop encode to idle after last demand touch |
| `EVILEYE_MAX_LIVE_WS_CLIENTS` | `32` | Cap for `/ws/live` subscribers (close `4429` when full) |
| `EVILEYE_WS_PREVIEW_MODE` | `binary` | `binary` = JPEG over WS; `notify` = JSON notify + client fetches snapshot (**prefer `notify` on WAN**) |
| `EVILEYE_WS_PREVIEW_SEND_TIMEOUT_SEC` | `2.0` | Per-client WS send timeout; slow clients are dropped so they cannot block fan-out |
| `EVILEYE_MAX_MJPEG_CLIENTS` | `8` | Cap concurrent MJPEG streams |
| `EVILEYE_MAX_PLAYBACK_MEDIA_CLIENTS` | `96` | Warn-only threshold for `/playback/media` inflight (no hard 503 cap; browser limits connections) |
| `EVILEYE_MJPEG_IDLE_SEC` | `8` | Close MJPEG if no frames |
| `EVILEYE_PLAYBACK_ROUTE_TIMEOUT_SEC` | `15` | Max wait for playback cameras/segments/timeline; stale fallback when available |
| `EVILEYE_PLAYBACK_DETECTIONS_TIMEOUT_SEC` | `45` | Max wait for coalesced `/playback/detections` journal scans |
| `EVILEYE_STATE_ROUTE_TIMEOUT_SEC` | `8` | Max wait for `/state/*` heavy routes; on timeout serve in-process cache when available |
| `EVILEYE_DATA_DIR` | `EvilEyeData` | Streams / Events root |

Config: `server.publish_fps` (stream level), `server.preview_encode_workers`, `server.preview_max_edge`.

## Performance notes

- **Tiered demand:** `idle` / `grid` / `stream`. Closing the Live tab drops encode to idle after demand TTL (`EVILEYE_PREVIEW_DEMAND_TTL_SEC`, default 45s).
- **Live camera health:** `GET /api/v1/state/cameras` includes `is_working`, `last_frame_age_sec`, `reconnecting`. UI status dots use hysteresis (12s enter / 5s exit); metadata overlays are not torn down on brief stale.
- **Live preview hub:** per-client latest-wins queues; hub stats include `dropped`, `client_timeouts`, `client_replaced`, `clients_kicked`.
- **MJPEG refcount:** each stream connection acquires a broker ref; soft `stream:stop` is a no-op (disconnect releases). On MJPEG release demand is forced back to `grid`.
- **Playback:** logical cameras from run config (`Cam2`/`Cam3`, not composite `Cam2-Cam3`); split crop via canvas + `src_coords`; selection in `localStorage` (`evileye.playback.layout.v1`); auto-load segments; timeline segment blocks. Heavy routes use `EVILEYE_PLAYBACK_ROUTE_TIMEOUT_SEC` with stale segment-index / memory fallback (503 only when no data). Timeline indexes use stale-while-revalidate (serve stale ticks/events/segments and refresh in background), today soft TTL ~300s, singleflight rebuilds, and a short in-process happy-path cache (~45s). FE caches timeline responses ~60s and omits composite folder ids from timeline requests.
- **State routes:** `EVILEYE_STATE_ROUTE_TIMEOUT_SEC` with existing in-process cache fallback.
- **Journals / logs / WS metadata:** unchanged cadence (poll/SSE/backoff).

## Disk layout (playback)

```
EvilEyeData/
  Streams/YYYY-MM-DD/<camera|/CamA-CamB>/*.mp4
  Events/…
```

Composite split folders (`Cam2-Cam3`) map to logical cameras `Cam2` / `Cam3`. All parts share the same recording files (prefixed with the first source name); the UI crops via `src_coords`.
