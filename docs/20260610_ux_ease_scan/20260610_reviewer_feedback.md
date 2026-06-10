## Overall verdict

I would **approve this plan directionally**, but I would not start implementation until a few contracts are tightened. The plan is already much stronger than a generic UX polish roadmap: it correctly prioritizes **truth ownership, source immutability, media reliability, bounded payloads, URL/share state, and selection continuity** over visual cleanup.

The main risk is not that the plan is too broad. The main risk is that several tasks still leave room for implementers to create **parallel truths**:

* one query identity for browse, another for facets, another for URL, another for metrics;
* one media policy in launch status, another in frontend image logic;
* one source/path identity for table rows, another for dimension cache;
* one selected item in UI state, another stale inspector/compare/sidecar target;
* one derived score shown in the metric rail, another computed from a loaded subset.

So my review feedback is: **keep the plan, but add a small contract-lock step before Sprint 1, split Sprint 3, and make several state/media/query boundaries explicit.**

I inspected the uploaded repo enough to ground this in current code paths. I did not run the full validation suite.

---

# Highest-priority changes I would make

## 1. Add a tiny “Sprint 0: Contract Lock + Fixture Baseline”

Before Sprint 1, I would add a short non-feature sprint whose only job is to freeze contracts and baseline fixtures. This should be small, but it will prevent a lot of regressions.

Add something like:

```md
### Sprint 0: Contract Lock and Fixture Baseline

Demo outcome: implementers have one shared source of truth for query identity,
media policy, source/dimension identity, selection boundaries, and URL ownership
before behavior changes begin.

- S0-T1: Write an ownership matrix for source data, workspace cache, browse query,
  facets, media originals, URL state, localStorage preferences, selection, and
  derived metrics.

- S0-T2: Define canonical query identity and separate it from window/request tokens.
  Canonical analysis identity must not include offset/limit. Window request tokens may.

- S0-T3: Define media policy enums and redaction rules before frontend fallback work.

- S0-T4: Create fixture/baseline tests for:
  Parquet with missing dimensions,
  multiple source/path columns,
  local and HTTP media,
  direct-browser media failure,
  large table metric sorting,
  URL-vs-localStorage precedence,
  folder-scope selection clearing.
```

Why this matters: the current repo already has several places where identity is close but not identical. For example, backend browse request token generation currently includes `offset` and `limit` in `src/lenslet/browse/query.py`. That is fine for a **window request token**, but dangerous if reused as the **canonical analysis/query identity** for facets, derived metrics, URL round-trips, and summaries.

I would explicitly define two concepts:

```txt
analysisQueryKey:
  folder/scope + q + filters + sort intent + random seed + derived spec intent
  no offset
  no limit
  no transport-only fields

windowRequestToken:
  analysisQueryKey + offset + limit + request generation
```

That split will save you from subtle cache bugs.

---

## 2. Split Sprint 3 into two sprints

Sprint 3 is the riskiest part of the plan. It combines:

* canonical query identity,
* query-shaped facets,
* backend derived metric truth,
* field capabilities,
* bounded metric sort,
* metric rail redesign,
* derived score authoring polish,
* URL round-tripping.

That is a lot of cross-system work. I would split it.

Recommended split:

```md
### Sprint 3A: Canonical Query Identity, Facets, and Capabilities

- Define canonical analysis query identity.
- Make facets query-shaped or explicitly provenance-labeled.
- Add backend field capability metadata.
- Make URL state round-trip the core query state.
- Preserve URL > localStorage precedence.

### Sprint 3B: Backend Derived Metrics and Bounded Metric Navigation

- Move normal-browse derived score truth to backend.
- Replace 50k metric-sort hydration.
- Feed metric rail from backend summaries or mark unavailable.
- Add seek/window-by-metric-value only if needed.
- Polish derived score authoring after backend status is trustworthy.
```

I would not start derived score authoring polish until backend-derived score status is solid. Otherwise you risk polishing a workflow whose truth model is still unstable.

---

## 3. Make S1-T1 more explicit: replace the current default, do not wrap it

Current behavior appears to default toward writing missing dimensions back into source Parquet. In the repo, `--no-cache-dimensions` disables dimension caching, but the default remains `cache_dimensions=True`, and `write_missing_dimensions(...)` eventually rewrites the Parquet source.

Your plan says:

> Source Parquet files are immutable by default.

That is the right product decision. I would make the implementation language more forceful:

```md
- S1-T1: Replace default in-source Parquet dimension caching with workspace-backed
  dimension cache.

  The default must never rewrite source Parquet. Rename the opt-in flag to make
  mutation explicit, for example `--write-source-dimensions` or
  `--dimension-cache=source`. Avoid preserving `--no-cache-dimensions` as the
  primary user-facing model because it frames source mutation as the normal path.
```

Also define the cache key carefully. I would not key only by file path or row index.

Suggested cache namespace:

```txt
table_fingerprint:
  source parquet path
  file size
  mtime or content hash where affordable
  schema hash
  row count

source_identity:
  selected source column
  selected path/root/base-dir mode
  workspace id

row_identity:
  stable row id if configured
  else row index + normalized source/path value
```

Special care: switching source columns must invalidate or namespace dimensions. A dimension measured for `thumbnail_url` should not silently apply to `original_url`.

---

## 4. Define media policy as a backend-owned contract

The media plan is good, but I would make it more formal. Right now there are several overlapping concepts: direct HTTP original, backend proxy, local file serving, thumbnail blob fetching, viewer resource state, and fallback behavior.

Add a backend media policy object, either at launch/status level and/or item level:

```ts
type MediaOriginalPolicy =
  | "local_file_stream"
  | "backend_proxy_required"
  | "browser_direct_allowed"
  | "browser_direct_preferred_with_proxy_fallback"
  | "unsupported";
```

And include reasons:

```ts
{
  originalPolicy: "browser_direct_preferred_with_proxy_fallback",
  sourceKind: "http",
  proxyAvailable: true,
  directAllowed: true,
  redactedOrigin: "https://example.com",
  warnings: [...]
}
```

Important: frontend should not independently infer too much from `url.startsWith("http")`. It can choose rendering mode, but the backend should own policy.

Current code has a direct-original helper in `frontend/src/features/media/originalImageResource.ts`, while backend media reads/proxy behavior live separately under `src/lenslet/web/media.py` and `src/lenslet/storage/source/media.py`. The plan should prevent those from drifting.

---

## 5. Add streaming-specific acceptance criteria

S1-T3 says backend proxy mode should stream rather than fully buffer large originals. I would make that acceptance test concrete:

```md
Acceptance:
- HTTP proxy path does not call full `response.content` for large originals.
- Range requests are passed through or handled safely where supported.
- Content-Type and Content-Length/Transfer-Encoding are preserved when safe.
- Client disconnect cancels upstream read.
- Timeouts and max-byte policies are enforced.
- Local FileResponse fast path remains unchanged.
```

Current backend behavior appears to stream local files well, but non-local reads can fully buffer bytes before returning a response. That is exactly the kind of regression-prone fix that needs a focused test.

Also take care with browser direct failures: a direct `<img>` can fail because of CORS, hotlink protection, expired signed URLs, mixed content, auth, or transient network behavior. That does **not** always mean the backend cannot fetch it. Direct failure should be tracked per item/session and fall back to proxy without globally changing source policy unless the user explicitly changes a setting.

---

## 6. Convert `useBlobUrl` into a real media resource state

S1-T4 is exactly right. The current pattern of returning only `string | null` makes it impossible to distinguish:

* not requested yet,
* loading,
* aborted,
* failed,
* unsupported,
* no media,
* successful but empty,
* stale previous image.

I would change the frontend contract to something like:

```ts
type MediaResourceState =
  | { status: "idle" }
  | { status: "loading"; requestId: string }
  | { status: "ready"; url: string; source: "blob" | "direct" | "proxy" }
  | { status: "error"; error: MediaError; retry: () => void }
  | { status: "unsupported"; reason: string };
```

One special warning: **do not surface aborted/cancelled thumbnail requests as user-visible errors.** During fast scrolling, aborted requests are normal. Show errors only for committed visible media or viewer media.

---

## 7. Make the folder-scope reset list explicit

S2-T1 is important, but I would make it more mechanical. “Clear or revalidate state” can be interpreted too loosely.

Add a checklist:

```md
On folder/scope/source change, clear or revalidate:

- selectedPaths
- inspector target
- compare set and compare eligibility
- sidecar edit target
- hover preview target
- context menu target
- viewer path unless opened from an explicit viewer hash
- similarity/ranking target where path-scoped
- pending media prefetches for old scope
- metric rail jump target
- top-anchor restore token
- stale query/facet/metric request tokens
```

Current `openFolder` behavior appears to reset viewer state and update current folder, but does not fully clear every path-scoped UI surface. Table source switching clears more, but has swallowed error paths. The plan should make scope-boundary behavior uniform.

---

## 8. Be careful with viewer “non-blank” behavior

S2-T3 is good, but it is easy to implement incorrectly.

You do **not** want to simply keep the old image bound as if it were current. That would create a worse trust bug: the URL, metadata, and selection say item B, while the image still visibly appears as item A.

The safe model is two-layer state:

```txt
targetPath:
  the current selected/viewer path

displayedResource:
  last successfully decoded image resource

pendingResource:
  resource currently loading for targetPath
```

When navigating:

* metadata, title, URL, next/prev state update to the new target immediately;
* old image remains visible but clearly marked as transitioning/non-current;
* once the new image decodes, swap/crossfade;
* if the new image fails, show an error state for the new item, not a silent old image.

Add a test that asserts there is no blank interval **and** no stale image is exposed as the current item.

---

## 9. Clarify derived metric score scope

The plan says:

> z-normalized derived scores display backend full-scope values

But elsewhere it emphasizes query-shaped truth. You need to define exactly what “full-scope” means for derived scores.

Possible scopes:

1. entire folder/table population;
2. current query-filtered population before pagination;
3. currently loaded window;
4. valid-input subset only.

For trust, I would recommend:

```txt
Normal browse derived scores:
  compute over the query-filtered population before offset/limit,
  using only rows with valid inputs,
  and report valid/invalid/missing counts.

The UI must label the score scope.
```

If you truly want full-folder z-normalization even after filters, say that explicitly. Otherwise users will see filtered results whose score distribution does not match the visible/query population.

Backend response should include at least:

```ts
{
  derivedMetric: {
    key: string,
    displayName: string,
    status: "applied" | "unavailable" | "invalid",
    scoreScope: "query_filtered" | "folder_scope" | "loaded_window",
    validCount: number,
    invalidCount: number,
    missingInputs: string[],
    unavailableCategoricals: string[],
    zMean?: number,
    zStd?: number
  }
}
```

Returning only a derived key and item values is not enough; the frontend needs provenance.

---

## 10. Tighten URL/localStorage precedence

The plan’s ownership rule is good:

> URL state owns shareable analysis context; localStorage owns personal workspace preferences; backend owns durable data.

Keep that. It is one of the best design decisions in the plan.

I would add an explicit invariant:

```md
Explicit URL state always wins over localStorage.
LocalStorage must never overwrite q, filters, sort, random seed, derived metric spec,
or unsupported metric intent provided by the URL.
```

Also add workspace-scoped storage keys earlier than backlog if possible. Current persisted shell settings appear globally keyed. That is likely to create confusing cross-workspace state bleed.

Suggested storage key shape:

```txt
lenslet:{workspaceId}:viewMode
lenslet:{workspaceId}:thumbSize
lenslet:{workspaceId}:leftTool
lenslet:{workspaceId}:personalBrowsePrefs
```

For URL state, be careful with derived metric specs. A full JSON formula can make URLs long and brittle. For Phase 1, that may be acceptable, but enforce:

* stable/canonical JSON ordering;
* length cap;
* fail-closed import;
* clear unsupported-intent behavior when fields are missing.

---

# Cross-system regression traps

## Media

Most likely regressions:

* proxy fallback loops after direct image failure;
* showing cancelled thumbnail requests as errors;
* buffering huge HTTP originals and increasing RSS;
* leaking signed URLs or local paths in error messages;
* breaking the local `FileResponse` fast path;
* decoding stale viewer image as if it belongs to the current item.

Special care:

* separate direct browser failure from backend fetch failure;
* preserve backend error categories;
* treat abort/cancel as neutral;
* test delayed image decode and failed direct image fallback.

---

## Query/facet/metric identity

Most likely regressions:

* facets computed over full folder while filters imply query-shaped results;
* metric rail based on loaded rows while UI implies full population;
* random seed omitted from URL/query identity;
* offset/limit accidentally included in canonical identity;
* derived metric filter/sort shown even when backend could not evaluate it;
* local frontend derived score sneaking back into normal browse.

Special care:

* one normalized query identity helper;
* separate analysis identity from window token;
* include provenance in responses;
* do not allow loaded-window summaries to masquerade as population summaries.

---

## Source tables and dimensions

Most likely regressions:

* mutating source Parquet through an old default flag;
* reusing dimension cache after source-column switch;
* stale dimensions after table schema/content changes;
* row identity drift if row index changes;
* source path or local filesystem details leaking to shared clients.

Special care:

* opt-in source mutation only;
* workspace cache namespaced by table fingerprint and source/path mode;
* explicit launch status redaction policy;
* tests assert source file hash/mtime unchanged.

---

## Selection and app state

Most likely regressions:

* inspector shows item from old folder;
* compare remains enabled with old paths;
* sidecar edit target points to stale path;
* viewer hash opens a path but folder change clears it incorrectly;
* top-anchor restore scrolls to a wrong item after sort/filter;
* pending old media requests populate new scope.

Special care:

* define scope-generation tokens;
* discard old async results when generation changes;
* clear path-scoped state on folder/source change;
* only restore selected/top anchor when backend confirms the item exists in the new query.

---

## URL and persistence

Most likely regressions:

* localStorage overrides explicit shared URL;
* old global preferences bleed across workspaces;
* unsupported metric intent disappears silently;
* random sort changes across reload because seed was not owned by URL;
* derived spec references fields unavailable in the opened workspace.

Special care:

* URL wins;
* workspace-scoped personal settings;
* canonical encode/decode tests;
* fail-closed formula import;
* visible “some URL state could not be applied” status.

---

# Maintainability recommendations

The plan correctly identifies large coordination files as danger zones. I would be stricter here.

Avoid adding more ad hoc logic to:

* `frontend/src/app/AppShell.tsx`
* `frontend/src/features/browse/components/VirtualGrid.tsx`
* `frontend/src/styles.css`
* `src/lenslet/storage/table/storage.py`

Instead, create small seam modules.

Suggested backend seams:

```txt
src/lenslet/browse/identity.py
  canonical query identity normalization

src/lenslet/storage/table/dimension_cache.py
  workspace-backed dimension persistence

src/lenslet/storage/table/launch_status.py
  launch summary/status model construction

src/lenslet/web/media_policy.py
  direct/proxy/local/unsupported media policy

src/lenslet/storage/table/capabilities.py
  field capability metadata
```

Suggested frontend seams:

```txt
frontend/src/features/media/useMediaResource.ts
  loading/ready/error/retry resource state

frontend/src/app/model/scopeBoundary.ts
  clear/revalidate path-scoped state on folder/source changes

frontend/src/app/routing/browseQueryUrl.ts
  canonical URL encode/decode for q/filters/sort/random/derived

frontend/src/features/metrics/metricRailData.ts
  loaded-window vs backend-summary rail provenance

frontend/src/app/state/actionFeedback.ts
  small action result/error channel, probably not a new global state manager
```

I would **not** introduce a new frontend state manager. The plan is right to keep React Query and existing hooks. The issue is not insufficient state technology; the issue is state ownership boundaries.

Also, reuse the existing `GridTopStack` action error/status surface if possible. I noticed the component already accepts an action error prop, but some current call paths swallow errors or pass `null`. That is a good low-cost place to start instead of introducing a toast framework.

---

# Things I would keep exactly as-is

These are good design decisions and should not be diluted:

1. **Backend-owned truth for normal browse.**
   Do not let the frontend loaded window pretend to know population truth.

2. **Hard cutovers in alpha.**
   Do not preserve confusing behavior merely for compatibility.

3. **Source Parquet immutable by default.**
   This is a trust decision, not only a technical one.

4. **URL owns shareable analysis state; localStorage owns personal preferences.**
   This is the right separation.

5. **Scenario-driven validation.**
   Unit tests alone will miss the failures users actually feel.

6. **No full design-system rewrite in Phase 1.**
   That would consume energy without fixing the trust bugs.

7. **No general expression language.**
   Derived score authoring should be clearer, not more powerful yet.

8. **No custom virtualizer.**
   Fix truth, loading, and context first.

9. **Broad accessibility compliance deferred, but interaction resilience retained.**
   This distinction is good. I would only add that focus restoration and visible action errors are not optional polish; they are core interaction correctness.

---

# Specific additions to validation

I would add these acceptance tests to the existing list:

```md
- URL precedence:
  Open a URL with q/filter/sort/random seed while localStorage contains conflicting
  values. Assert URL state wins.

- Query identity:
  Browse query, facet query, metric summary, and derived metric status report the
  same analysisQueryKey. Assert offset/limit are not part of analysisQueryKey.

- Source-column switch:
  Switch table source column and assert dimension cache, facets, media policy,
  selection, viewer, compare, and inspector state do not reuse old source state.

- Media abort:
  Fast-scroll thumbnails, abort queued requests, and assert aborted requests do not
  render visible error states.

- Direct-to-proxy fallback:
  Simulate browser direct image failure while backend fetch succeeds. Assert viewer
  and thumbnail recover through proxy without flipping unrelated items globally.

- Viewer stale-image safety:
  Navigate from item A to delayed item B. Assert old image may remain visually
  retained as loading context, but metadata/selection/current path are B and the old
  image is not presented as B.

- Derived score scope:
  Apply a filter, compute derived score, and assert valid/invalid counts and score
  scope match backend query-filtered truth.

- Large metric rail:
  Assert metric sort first payload stays near normal page size and rail does not use
  50k item hydration.
```

---

# Suggested small wording changes

I would change this line:

> S3-T1: Define one canonical browse query identity.

To:

> S3-T1: Define one canonical **analysis query identity**, separate from window/request identity. The analysis identity is shared by browse membership/order intent, facets, derived metric status, metric summaries, URL round-trips, and request invalidation. It excludes offset/limit. Window request tokens may include offset/limit.

I would change this line:

> S1-T3: Define and implement a narrow HTTP original media policy.

To:

> S1-T3: Define and implement a backend-owned original media policy covering local stream, direct browser handoff, backend proxy stream, direct-with-proxy-fallback, and unsupported states. Frontend rendering may choose presentation, but must not invent policy from URL shape alone.

I would change this line:

> S2-T1: Treat folder scope changes as a selection boundary.

To:

> S2-T1: Treat folder, source-column, workspace, and query-generation changes as explicit path-state boundaries. Clear or revalidate selected paths, inspector, compare, viewer, sidecar edit target, hover/context menu, metric jump target, pending media requests, and top-anchor restore tokens.

I would change this line:

> S3-T6: Polish derived score authoring without adding an expression engine.

To:

> S3-T6: Polish derived score authoring only after backend derived metric status is authoritative for normal browse. Frontend derived evaluation remains draft-only and similarity-only.

---

# Bottom line

This is a strong Phase 1 plan. I would not replace it. I would **tighten it**.

The most important edits are:

1. add a small Sprint 0 contract/fixture step;
2. split Sprint 3;
3. separate canonical analysis query identity from window request tokens;
4. make source mutation opt-in with clearer CLI semantics;
5. define backend-owned media policy before frontend fallback;
6. make folder/source scope resets mechanical, not interpretive;
7. define derived score scope/provenance precisely;
8. preserve URL-over-localStorage precedence with tests.

The plan’s center of gravity is right: make Lenslet feel trustworthy by making the system truthful. Keep that. The product will feel smoother because users stop encountering contradictions, not because the interface has been cosmetically softened.
