# EvilEye Frontend (React)

Vite + React + TypeScript SPA for the EvilEye REST API.

## Build

```bash
cd evileye/api/frontend
npm install
npm run build
```

Output is written to `evileye/api/static/`. FastAPI serves the SPA with client-side routing fallback.

## Dev

```bash
npm run dev
```

Proxies `/api` and `/ready` to `http://127.0.0.1:8181`.
