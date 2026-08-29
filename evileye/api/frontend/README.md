# EvilEye Frontend (React)

Vite + React + TypeScript SPA for the EvilEye REST API.

## Preferred: CLI

```bash
evileye web build          # check Python web deps; build SPA if static missing
evileye web build --check
evileye web build --build  # force npm install && npm run build
```

See [`docs/CLI_SETUP_WEB.md`](../../../docs/CLI_SETUP_WEB.md).

## Manual build

```bash
cd evileye/api/frontend
npm install
npm run build
```

Output is written to `evileye/api/static/`. FastAPI serves the SPA with client-side routing fallback.

Prebuilt `api/static/` may already be present in the package/repo; npm is required only to rebuild after frontend changes.

## Dev

```bash
npm run dev
```

Proxies `/api` and `/ready` to `http://127.0.0.1:8181`.

## Test

```bash
npm test
```
