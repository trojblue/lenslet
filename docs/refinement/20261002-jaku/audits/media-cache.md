# Media cache request ownership

Scope: the main gallery's shared Blob cache, thumbnail prefetch, and Viewer/Compare full-file prefetch. Ranking was not changed. This is a correctness and resource-ownership refinement discovered during the performance audit; it does not claim a measured frame-rate improvement.

The Better Code skill guided the concurrency fix. The existing presentation contract R8 requires superseded loads not to promote and cache resources to remain bounded. The jaku UI performance reference concerns compositing rather than request ownership; no additional motion or styling was introduced here.

## Findings and changes

| Severity | Location | Before | After | User impact |
| --- | --- | --- | --- | --- |
| High | `frontend/src/lib/blobCache.ts`, `getOrFetch` | An invalidated request could cache its late response and its `finally` could delete a replacement request for the same path. | Completion and cleanup require the original in-flight entry to remain the current owner. Cancellation detaches ownership before calling abort. | Folder refresh/source reset cannot be undone by late old bytes; replacement requests remain deduplicated. |
| High | `frontend/src/lib/blobCache.ts`, `prefetch` | Failed background requests returned a successful empty Blob to a foreground consumer that joined the request. Synchronous fetcher failure also escaped. | Prefetch shares `getOrFetch` and catches its own background error without changing the shared promise. | Foreground decoding receives the actual error instead of attempting to decode an empty image. |
| High | `frontend/src/api/client.ts`, `prefetchFile` | File prefetch bypassed the shared cache's in-flight ownership, allowing duplicate requests, ineffective cancellation, and writes after cache clearing. | File prefetch uses `getOrFetch` with the existing 40 MiB cache-entry limit. | Adjacent prefetch and immediate Viewer/Compare navigation reuse one request. Clear/cancel/refresh retire its cache ownership. |

## Preserved semantics

- A foreground consumer joining an in-flight prefetch receives the same Blob or actual error, with no extra request.
- Full-file prefetch retains its 40 MiB admission limit; the file cache's total budget remains 60 MiB, thumbnails 20 MiB. A consumer can still receive a larger Blob even when it is not admitted to cache.
- A non-abortable old request can still fulfill its original caller. It cannot mutate cache state after invalidation. Existing media presentation owners retain responsibility for latest-target checks.
- `cancelPrefetch` remains a key-wide cancellation operation, rather than introducing reference counting. There are currently no gallery callers of this exported API method; cache clear/refresh uses the same underlying abort ownership.
- BlobLRUCache creates no object URLs. `thumbnailObjectUrlCache` and existing media hooks retain their lease/URL disposal ownership; this fix does not revoke URLs out from under presented media.
- Abort callbacks run after all targeted entries are detached. Synchronous replacement requests created by an abort callback remain registered.

## Reproduction and verification

Before changing cache code, all nine new cache tests failed: three invalidation forms, successful/failed old request cleanup, old response overwriting a completed replacement, prefetch failure propagation, synchronous failure, and abort-callback replacement ownership.

Before changing the API path, all four added API tests failed: shared prefetch/foreground request, clear during prefetch, cancellation signal, and the existing 40 MiB admission limit for a joined consumer.

After implementation:

- `npm --prefix frontend test -- --run src/lib/__tests__/blobCache.test.ts src/api/__tests__/client.prefetch.test.ts` — 23 tests passed across two files.
- `npx --prefix frontend tsc --noEmit -p frontend/tsconfig.json` — passed.
- The deduplication test verifies exactly one fetch for concurrent prefetch and foreground navigation. This is request-count evidence, not a throughput benchmark.

Integration browser acceptance, rebuilt packaged assets, full-suite verification, and painted-frame media continuity are coordinated by the main session. This isolated change does not itself establish those gates.
