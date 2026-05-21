# Jetbot Web UI

Vue 3 + Vite + TypeScript SPA for visualizing financial-PDF analysis results.

## Quickstart

```bash
# 1. start the FastAPI backend (default :8000)
cd ..
make dev

# 2. start the SPA (default :5173, proxies /v1 -> :8000)
cd web
npm ci
npm run dev
```

Open <http://localhost:5173>.

## Scripts

| Script | Description |
| --- | --- |
| `npm run dev` | Vite dev server with HMR + API proxy to backend on `:8000` |
| `npm run build` | Type-check + production build into `dist/` |
| `npm run typecheck` | Type-check only |
| `npm run lint` | ESLint over `src/` |
| `npm run preview` | Preview built assets locally |

## Production deployment

After `npm run build`, the FastAPI app automatically mounts `web/dist` at `/ui`
when present (see `src/api/main.py`). A request to `/` then 302s to `/ui/`.

Alternatively serve `dist/` from any static host (e.g. nginx) and set
`VITE_API_BASE` at build time:

```bash
VITE_API_BASE=https://api.example.com npm run build
```

## Architecture

- `views/` — top-level routes (list, upload, dashboard)
- `components/` — panels rendered inside the dashboard
- `api/` — typed axios client; `unwrap()` strips the `{ok,data,error}` envelope
- `stores/` — Pinia stores (API key persistence)
- `composables/` — `usePolling` for live task progress
