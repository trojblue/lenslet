Put it **outside**. One repo, two siblings. Don’t stuff a Python backend inside your frontend like a turducken—tastes weird and is hard to carve.

## Why a single repo (monorepo-lite), but not nested

- **Clear boundaries:** `frontend/` (Vite/React) and `backend/` (FastAPI) ship independently. No mystery `cd src/server` rabbit holes.
- **Shared contracts without ceremony:** a tiny `shared/` folder for JSON Schemas/OpenAPI so TS + Python agree. No npm workspaces, no poetry-of-poetry.
- **Simpler CI/CD:** build/deploy each dir separately; version/tag the repo once.
- **No path hell:** local dev runs both with clean CORS and `.env` per side.

## Suggested layout

```
lenscat/
├─ frontend/           # your Lenscat-lite UI (what we already scaffolded)
├─ backend/            # FastAPI + workers (Python)
├─ shared/             # OpenAPI spec + JSON Schemas (source of truth)
├─ infra/              # docker-compose for MinIO (S3), nginx, etc. (optional)
├─ .env.frontend       # VITE_API_BASE, etc.
├─ .env.backend        # S3 creds, bind host/port
└─ Makefile            # boring one-liners to run stuff
```

### Minimal Makefile (so nobody invents scripts)

```make
.PHONY: fe be up down

fe:
\tcd frontend && npm run dev

be:
\tcd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 7070

up:
\tcd infra && docker compose up -d   # starts MinIO etc.

down:
\tcd infra && docker compose down
```

### Frontend config

- Point to backend via `.env.frontend`:
  - `VITE_API_BASE=http://127.0.0.1:7070`
- Don’t import backend code. Treat it like a web service (because it is).

### Backend config

- `.env.backend` with `S3_ENDPOINT`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ROOT_PATH`, etc.
- Enable CORS for `http://localhost:5173`.

### Shared contracts (tiny, useful, not bloat)

- Put `openapi.yaml` and JSON Schemas in `shared/`.
- Frontend: manually type the key responses (you already did), or generate types from schema if you must (but don’t start a tool circus).
- Backend: validate request bodies against the same schemas using Pydantic models referenced from `shared/`.

## When to split repos

- Separate teams w/ separate release cycles.
- You plan to open-source frontend and keep backend private (or vice versa).
- The backend grows real infra (DB, auth, multi-service) and you want different governance. Spoiler: you’re not there yet.

## TL;DR

- **One repo, siblings**: `frontend/` and `backend/`.
- Keep a **tiny `shared/`** folder for schemas/contracts.
- Avoid clever tooling. A Makefile and two `.env` files are enough.
- If someone proposes nesting backend inside frontend, gently take their keyboard away and hand them this message.