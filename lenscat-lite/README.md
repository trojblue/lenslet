# Lenscat-lite (Frontend Boilerplate)
Fast, minimal gallery UI. Bring your own FastAPI.

## Why this is not bloat
- No global store, no UI kit, no CSS-in-JS.
- Query cache + virtual grid only.
- CSS variables for theming.
- Abortable fetch helper, 30 lines total infra.

## Env
- `VITE_API_BASE` -> backend base URL

## Perf checklist
- Thumbnails only in grid (server should serve `<file>.thumbnail`).
- Use folder manifests (`_index.json`) for aspect boxes to avoid CLS.
- Overscan small (4 rows), AbortController cancels offscreen fetches.

## Extend
- Add more sources by extending backend; UI stays the same.
- Drop-in Tauri later by swapping `api/client.ts` with host bridge.

---

The boilerplate is complete and ready for development:

1. `npm install` to install dependencies

2. Set VITE_API_BASE environment variable

3. `npm run dev` to start development server

4. Backend should serve the API endpoints defined in the PRD

5. (run: )`npm run build` to build the frontend