# EvilEye Web UI

React SPA (Vite) served by FastAPI from `evileye/api/static/`.

## Routes

| Path | Permission | Description |
|------|------------|-------------|
| `/live` | `live:view` | Camera grid, MJPEG focus, metadata overlays |
| `/events` | `journal:view` | Journals + export + detail drawer |
| `/playback` | `journal:view` | Streams timeline playback |
| `/configure` | `config:view` | Config studio, ROI/Zone, class mapping |
| `/admin/*` | varies | Overview, runs, configs, logs, users, history |
| `/m/live`, `/m/events` | — | Compact mobile views |

## Build

```bash
cd evileye/api/frontend && npm install && npm run build
```

## Key APIs

- Streaming: `/api/v1/runs/{rid}/snapshot|stream.mjpg|stream:status`, WS `/api/v1/runs/{rid}/ws`
- Playback: `/api/v1/playback/cameras|segments|events|media`
- Config editors: `/api/v1/configs/{name}/sections|.../roi|zones|class-mapping`
- Journals export: `/api/v1/journals/export`

Env: `EVILEYE_MAX_MJPEG_CLIENTS` (default 8), `EVILEYE_DATA_DIR` (default `EvilEyeData`).
