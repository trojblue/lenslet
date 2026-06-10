# Lenslet Phase 1 Ownership Contracts

This file is the Sprint 0 contract lock for the Phase 1 ease-of-use work. It defines the facts that must have a single owner before later UI and backend behavior changes land.

## Ownership Matrix

| Fact | Owner | Display/cache only | Phase 1 rule |
| --- | --- | --- | --- |
| Source image bytes and source Parquet table | External dataset | Lenslet storage adapters, workspace cache, frontend | Source datasets are read-only by default. Lenslet may read source bytes and table rows, but must not rewrite source Parquet unless an explicit source-write policy is selected. |
| Workspace cache and Lenslet sidecars | Backend workspace | Frontend React Query/local component state | Workspace files own Lenslet-generated dimensions, thumbnails, sidecars, labels, and saved analysis artifacts. Source identity must be part of cache keys when values depend on a source column or source path. |
| Table source column, path mode, root/base-dir mode | Backend launch pipeline | CLI banner, health/status UI | Backend launch status owns the selected source/path contract. Frontend and CLI disclose it; they do not infer it from row strings. |
| Browse membership, order, totals, and windows | Backend browse/query route | React Query, grid state | Backend owns normal browse membership, filtered totals, sort order, and page windows. Loaded frontend rows are never full-population truth. |
| Canonical analysis query identity | Shared query contract, implemented in backend/frontend helpers | React Query, URL router, facets/capabilities clients | `analysisQueryKey` includes semantic browse intent only: folder/scope, `q`, filters, sort, active random seed, derived metric spec intent, and unsupported metric intent. It excludes offset, limit, request generation, and transport-only fields. |
| Window request identity | Backend/frontend query helpers | React Query page state | `windowRequestToken` includes `analysisQueryKey`, offset, limit, and optionally generation. It is not the identity for facets, URL state, capabilities, or derived metric summaries. |
| Facets and count provenance | Backend | Metrics panels | Facets must declare whether counts are scope population, query-filtered backend counts, or loaded-window counts. Frontend panels may hide unavailable counts but must not relabel loaded-window counts as global. |
| Original media policy | Backend media/storage policy | Thumbnail/viewer/compare rendering | Backend owns whether an original can stream locally, proxy through Lenslet, render browser-direct, prefer direct with proxy fallback, or is unsupported. Frontend rendering may choose among allowed URLs but must not infer policy from `http` strings. |
| Media failure category | Backend media route/storage errors | UI media resource state | Backend classifies failures as local missing, remote missing, permission, timeout, decode, upstream, unsupported, or cancelled. Fast-scroll thumbnail cancellations are normal and should not become visible item errors. |
| URL analysis state | URL router using canonical query identity | localStorage, React state | Explicit URL state wins over localStorage for folder/hash, `q`, filters, sort, active random seed, derived metric spec, and unsupported metric intent. |
| Personal display preferences | Workspace-scoped localStorage | URL router, backend | localStorage owns absent personal preferences such as pane state, display density, and shell settings. It may not override explicit analysis state in the URL. |
| Selection | App selection/viewer hook | Grid, inspector, compare, sidecar editor | Selection is scoped to the active folder/query context. Folder scope changes clear or revalidate selected paths before dependent surfaces use them. |
| Inspector and sidecar edit target | App selection/inspector state with backend sidecar writes | Inspector UI | Inspector targets must be valid for the active scope. Sidecar writes go through backend ownership and must not write to source datasets. |
| Compare state | App compare state | Compare viewer UI | Compare state derives from current valid selection. Folder scope changes, selection invalidation, or compare ineligibility close or revalidate compare state. |
| Derived metric display/status in normal browse | Backend browse/query evaluation | Frontend authoring drafts, metrics panels | Backend owns applied/unavailable/invalid status, score scope, valid/invalid counts, missing inputs, normalization stats, and page item scores for committed browse. Frontend may evaluate drafts and similarity-only previews. |

## Contract Notes

- Source, path, and dimension identity must include the selected source column and path/root/base-dir mode. Reusing dimensions across source-column switches is invalid unless the cache key proves the same row/source identity.
- Shareable analysis state must be small and reproducible. Do not place large selections, vectors, or transport-only request data in URLs.
- UI status surfaces may summarize backend-owned facts, but a status message is not a substitute for enforcing the backend behavior.
