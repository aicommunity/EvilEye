# EvilEye Frontend

Lightweight TypeScript SPA for the EvilEye REST API.

## Build

```bash
cd evileye/api/frontend
npm install
npm run build
```

Output is written to `evileye/api/static/`. The FastAPI app serves these files at `/` when the server runs.

## Dev

- `npm run watch` — recompile TypeScript on change (then copy `index.html` and `styles/main.css` to `../static` manually if needed).
