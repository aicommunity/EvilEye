# EvilEye Web UI

React SPA (Vite) served by FastAPI from `evileye/api/static/`.

## Routes

| Path | Permission | Description |
|------|------------|-------------|
| `/live` | `live:view` | Compact camera grid (WS preview / snapshot fallback); expand opens MJPEG + metadata overlays (pre-warm `stream` demand, loading/error/retry) |
| `/events` | `journal:view` | Journals + export + detail drawer (letterbox overlays) |
| `/playback` | `journal:view` | Live-like grid + bottom timeline; logical cameras from run config; split crop |
| `/configure` | `config:view` | Config Studio for the **current run** config only |
| `/admin/runs` | `runtime:view` | Read-only active/current runs (no start/stop/create) |
| `/admin/configs` | `config:view` | Config file list; open Studio or Raw JSON |
| `/admin/configs/:name` | `config:view` | Config Studio for a chosen file (forms, ROI/Zones, history) |
| `/admin/logs` | `logs:view` | Log files + Follow (SSE tail) |
| `/admin/users` | `users:manage` | User management (credentials.json + web_users.json; role/password/disable/delete) |
| `/admin/bans` | `bans:manage` | IP ban list (auto + manual add/remove) |
| `/admin/overview` | — | Redirect → `/live` |
| `/admin/history` | — | Redirect → `/admin/runs` |
| `/m/live`, `/m/events` | — | Compact mobile views |

Language switcher (RU/EN) is in the sidebar footer (`localStorage` key `evileye.ui.lang`).

## Build & test

```bash
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

### Users API (admin)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/users` | Merged list: `credentials.json` (`source=credentials`) + `web_users.json` (`source=store`) |
| POST | `/api/v1/users` | Create store user (approved) |
| PATCH | `/api/v1/users/{id}` | role / disabled / status / password reset |
| DELETE | `/api/v1/users/{id}` | Guards: no self-delete, no last-admin delete |
| POST | `/api/v1/auth/change-password` | Self-service (`current_password` + `new_password`) |

Sidebar: **Change password** for the logged-in user.

## Env vars (preview / streaming)

| Env | Default | Meaning |
|-----|---------|---------|
| `EVILEYE_PREVIEW_HEARTBEAT_FPS` | `0` | Encode while server alive but no UI demand |
| `EVILEYE_PREVIEW_GRID_FPS` | `2.0` | Encode FPS for grid / snapshot / live WS demand |
| `EVILEYE_MAX_LIVE_WS_CLIENTS` | `32` | Cap for `/ws/live` subscribers (close `4429` when full) |
| `EVILEYE_WS_PREVIEW_MODE` | `binary` | `binary` = JPEG over WS; `notify` = JSON notify + client fetches snapshot |
| `EVILEYE_MAX_MJPEG_CLIENTS` | `8` | Cap concurrent MJPEG streams |
| `EVILEYE_MJPEG_IDLE_SEC` | `8` | Close MJPEG if no frames |
| `EVILEYE_DATA_DIR` | `EvilEyeData` | Streams / Events root |

Config: `server.publish_fps` (stream level), `server.preview_encode_workers`, `server.preview_max_edge`.

## Performance notes

- **Tiered demand:** `idle` / `grid` / `stream`. Closing the Live tab drops encode to idle after demand TTL (~20s).
- **Live camera health:** `GET /api/v1/state/cameras` includes `is_working`, `last_frame_age_sec`, `reconnecting`.
- **MJPEG refcount:** each stream connection acquires a broker ref; soft `stream:stop` is a no-op (disconnect releases). On MJPEG release demand is forced back to `grid`.
- **Playback:** logical cameras from run config (`Cam2`/`Cam3`, not composite `Cam2-Cam3`); split crop via canvas + `src_coords`; selection in `localStorage` (`evileye.playback.layout.v1`); auto-load segments; timeline segment blocks.
- **Journals / logs / WS metadata:** unchanged cadence (poll/SSE/backoff).

## Disk layout (playback)

```
EvilEyeData/
  Streams/YYYY-MM-DD/<camera|/CamA-CamB>/*.mp4
  Events/…
```

Composite split folders (`Cam2-Cam3`) map to logical cameras `Cam2` / `Cam3` with prefix-filtered segments (`Cam2_*.mp4`).
