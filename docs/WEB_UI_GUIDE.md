# EvilEye Web UI

React SPA (Vite) served by FastAPI from `evileye/api/static/`.

## Routes

| Path | Permission | Description |
|------|------------|-------------|
| `/live` | `live:view` | Camera grid, lazy MJPEG (focused), snapshot for visible tiles, WS overlays |
| `/events` | `journal:view` | Journals + export + detail drawer (letterbox overlays) |
| `/playback` | `journal:view` | Streams timeline, event markers, multi-cam sync |
| `/configure` | `config:view` | Config studio forms, ROI/Zone canvas, class mapping, history restore/compare |
| `/admin/*` | varies | Overview, runs, configs, logs (SSE live), users, history |
| `/m/live`, `/m/events` | — | Compact mobile views |

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
- Config editors: `/api/v1/configs/{name}/sections|validate|…/roi|zones|class-mapping`
- Config history: `GET …/journals/config-history`, `GET …/compare?a=&b=` (side-by-side left/right), `POST …/{job_id}/restore?target_name=`
- Journals export: `/api/v1/journals/export`
- Logs SSE: `/api/v1/logs/{filename}/stream`

Mobile: `/m/live` — one camera carousel; `/m/events` — event feed (not desktop grid wrappers).

Env: `EVILEYE_MAX_MJPEG_CLIENTS` (default 8), `EVILEYE_DATA_DIR` (default `EvilEyeData`).

## Disk layout (playback)

```
EvilEyeData/
  Streams/YYYY-MM-DD/<camera|/CamA-CamB>/*.mp4
  Events/…
```

Composite split folders (`Cam2-Cam3`) are exposed as logical cameras `Cam2` / `Cam3`.
