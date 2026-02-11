# S2 / T7 - FileResponse Stat Reuse Optimization

Timestamp: 2026-02-11T05:10:38Z

## Goal

Reduce avoidable blocking filesystem work on local `/file` responses while preserving headers, fallback behavior, and response semantics.

## Change Summary

- Updated `src/lenslet/server_media.py` local file resolution to return `(path, stat_result)` instead of path only.
- `_file_response(...)` now passes `stat_result` into `FileResponse(...)` for local streaming responses.
- This keeps `/file` on the fast streaming path and avoids an extra stat phase during response preparation.
- Added a parity assertion in `tests/test_hotpath_sprint_s2.py` that local streaming responses carry a populated `FileResponse.stat_result`.

## Performance Snapshot

Command (before/after harness):

```bash
python - <<'PY'
import os
import tempfile
from pathlib import Path
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import FileResponse
import lenslet.server_media as media

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / 'a.jpg'
    Image.new('RGB', (8, 8), color=(1, 2, 3)).save(p, format='JPEG')

    class Storage:
        def __init__(self, source):
            self.source = source

        def get_source_path(self, _path):
            return self.source

        def _guess_mime(self, _path):
            return 'image/jpeg'

        def read_bytes(self, _path):
            raise AssertionError('read_bytes should not be called')

    storage = Storage(str(p))

    def measure(app: FastAPI) -> int:
        counts = {'stat': 0}
        orig_stat = os.stat

        def counting_stat(path, *args, **kwargs):
            counts['stat'] += 1
            return orig_stat(path, *args, **kwargs)

        os.stat = counting_stat
        try:
            with TestClient(app) as client:
                r = client.get('/')
                assert r.status_code == 200
                assert r.content
        finally:
            os.stat = orig_stat
        return counts['stat']

    old_app = FastAPI()

    @old_app.get('/')
    def old_route():
        source = str(p)
        if not os.path.isfile(source):
            return FileResponse(path=source, media_type='image/jpeg')
        return FileResponse(path=source, media_type='image/jpeg')

    new_app = FastAPI()

    @new_app.get('/')
    def new_route():
        return media._file_response(storage, '/logical/a.jpg')

    print(f'old_route_os_stat_calls={measure(old_app)}')
    print(f'new_route_os_stat_calls={measure(new_app)}')
PY
```

Result:

- `old_route_os_stat_calls=4`
- `new_route_os_stat_calls=3`

Interpretation:

- The refactored local `/file` path removes one filesystem stat call in the same request harness while preserving local streaming behavior.

## Validation

- `pytest -q tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py tests/test_metadata_endpoint.py tests/test_import_contract.py` -> `18 passed`
- `pytest -q --durations=10 tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py` -> `14 passed`
- Import probe (`python - <<'PY' ...`) -> `import-contract-ok`
