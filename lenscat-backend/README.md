# Lenscat Backend (Boilerplate)
Flat-file FastAPI backend for Lenscat-lite. No database. JSON + thumbnails next to originals.

## Quickstart
```bash
cd /home/ubuntu/dev/lenslet/lenscat-backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp env.example .env  # adjust ROOT_PATH or S3 vars
make dev   # starts FastAPI at http://127.0.0.1:7070
```

## Endpoints
- `GET /folders?path=/subdir` → `_index.json` (builds if missing)
- `GET /item?path=/subdir/foo.webp` → sidecar (creates minimal on the fly)
- `PUT /item?path=/subdir/foo.webp` → update sidecar
- `GET /thumb?path=/subdir/foo.webp` → returns/generates `foo.webp.thumbnail`
- `GET /search?q=term` → quick search via `_rollup.json`
- `GET /health` → health check

## Worker
```bash
make worker  # walks tree, builds indexes & rollup
```

## Notes
- Keep logic tiny. If you need a helper, write a 10–30 line function, not a framework.
- Sidecars and thumbnails are the source of truth. Browser caches are disposable.
- Swap `LocalStorage` for `S3Storage` by setting env vars—no code changes.
