# EvilEye Web UI

React SPA (Vite) served by FastAPI from `evileye/api/static/`.

## Routes

| Path | Permission | Description |
|------|------------|-------------|
| `/live` | `live:view` | Camera grid, lazy MJPEG (focused), snapshot for visible tiles, WS overlays |
| `/events` | `journal:view` | Journals + export + detail drawer (letterbox overlays) |
| `/playback` | `journal:view` | Streams timeline; camera list loads with date; multi-cam sync |
| `/configure` | `config:view` | Config Studio for the **current run** config only |
| `/admin/runs` | `runtime:view` | Read-only active/current runs (no start/stop/create) |
| `/admin/configs` | `config:view` | Config file list; open Studio or Raw JSON |
| `/admin/configs/:name` | `config:view` | Config Studio for a chosen file (forms, ROI/Zones, history) |
| `/admin/logs` | `logs:view` | Log files + Follow (SSE tail) |
| `/admin/users` | `users:manage` | User management |
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
```

## Key APIs

- Streaming: `/api/v1/runs/{rid}/snapshot|stream.mjpg|stream:status|metadata`, WS `/api/v1/runs/{rid}/ws`
- Internal relay: `POST /api/v1/internal/frames/{rid}` accepts JPEG or multipart (`metadata` JSON + `frame`) with objects/zones
- Playback: `/api/v1/playback/cameras|segments|events|media` (`EVILEYE_DATA_DIR/Streams/{date}/…`)
- Config sections: `GET/PUT /api/v1/configs/{name}/sections` returns `sections` + ordered `tabs`; section id may be a dotted path (`pipeline.sources`)
- Config editors: `/api/v1/configs/{name}/validate|…/roi|zones|class-mapping`
- Config history: `GET …/journals/config-history`, `GET …/compare?a=&b=` (side-by-side left/right), `POST …/{job_id}/restore?target_name=`
- Journals export: `/api/v1/journals/export`
- Logs SSE: `/api/v1/logs/{filename}/stream`

Mobile: `/m/live` — one camera carousel (snapshot by default; MJPEG only in fullscreen); `/m/events` — event feed (not desktop grid wrappers).

Env: `EVILEYE_MAX_MJPEG_CLIENTS` (default 8), `EVILEYE_DATA_DIR` (default `EvilEyeData`), `EVILEYE_MJPEG_IDLE_SEC` (default 8).

## Performance notes

- **Live camera health:** `GET /api/v1/state/cameras` includes `is_working`, `last_frame_age_sec`, `reconnecting`. Tiles stop snapshot polling and show “no signal” when stale.
- **MJPEG refcount:** each stream connection acquires a broker ref; soft `stream:stop` is a no-op (disconnect releases). Idle without frames closes the multipart stream.
- **Demand-driven encode:** preview JPEG encode runs only with local MJPEG or preview demand (not merely because the web server/relay is alive). Config: `server.preview_encode_workers` (default 2 when `server.enabled`), `server.preview_max_edge` (default 960).
- **Playback:** heavy discovery runs in `asyncio.to_thread`; duration cache; batch `?cameras=a,b`; UI clock throttled ~200ms; max 4 cams; timeline markers clustered.
- **Journals:** poll ~12s (15s mobile) and pause when the tab is hidden; thumbs use `?w=96`; grouped pages are group-then-paginate; export may set `X-Export-Truncated: 1`.
- **WS metadata:** pushes on change or at most ~2 Hz; client reconnects with backoff.
- **Logs SSE:** seeds with a tail, then follows by byte offset.

## Disk layout (playback)

```
EvilEyeData/
  Streams/YYYY-MM-DD/<camera|/CamA-CamB>/*.mp4
  Events/…
```

Composite split folders (`Cam2-Cam3`) are exposed as logical cameras `Cam2` / `Cam3`.
