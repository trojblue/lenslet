# Lenslet Frontend

React + Vite frontend for Lenslet browse and ranking mode.

## Structure

- `src/app/` owns the app shell, mode switching, presence wiring, and layout state.
- `src/features/` contains browse, inspector, metrics, compare, and ranking feature slices.
- `src/api/` contains the browser API client, SSE handling, and request-budget logic.
- `src/shared/` and `src/theme/` hold reusable UI primitives, hooks, and theme/storage helpers.

## Development

```bash
npm install
npm run dev
```

Set `VITE_API_BASE` only when the frontend is talking to a backend on a different origin. The default local dev flow is the Vite app proxied to the Lenslet server running on `127.0.0.1:7070`.

## Build

```bash
npm run build
cp -r dist/* ../src/lenslet/frontend/
```

`src/lenslet/frontend/` is the packaged static bundle served by the Python app.
