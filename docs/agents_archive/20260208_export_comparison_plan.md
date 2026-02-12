# Export Comparison Inspector Plan (Single Sprint)


## Purpose / Big Picture


No `PLANS.md` or `plan.md` file exists in this repository, so this document is the canonical implementation plan for this change set. After this sprint, a user in compare mode can open a new `Export Comparison` block inside the inspector, enter two compact labels where line 1 maps to A and line 2 maps to B, keep metadata embedding enabled by default, and export a generated side-by-side PNG in normal or reversed order. The feature is complete when a non-developer can run the app, click export, and receive a downloadable PNG that contains annotation text and optional embedded metadata.


## Progress


- [x] 2026-02-08 03:51:59Z Captured product decisions from user confirmation: metadata checkbox default on, line 1 maps to A, line 2 maps to B, and reverse-order export button retained.
- [x] 2026-02-08 03:52:40Z Confirmed implementation touch points and constraints in `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/app/AppShell.tsx`, `frontend/src/api/client.ts`, `src/lenslet/server.py`, and `/home/ubuntu/dev/unibox/src/unibox/utils/image_utils.py`.
- [x] 2026-02-08 03:54:37Z Completed mandatory subagent review pass and incorporated task-level recommendations for security parity, payload limits, error UX, and tighter validation coverage.
- [x] 2026-02-08 04:05:48Z Implemented backend `POST /export-comparison` with `v=1` contract enforcement, canonical path/image validation parity, bounded label sanitization, reverse-order semantics, metadata embedding toggle and bounds, filename headers, and explicit `400/404/415/500` error taxonomy.
- [x] 2026-02-08 04:05:48Z Implemented frontend API and inspector integration: new `Export Comparison` UI block in compare mode with two-line label input, metadata checkbox default on, normal/reverse export actions, in-flight disable states, inline error handling, and timestamped download filenames.
- [x] 2026-02-08 04:05:48Z Added regression coverage and validated: `pytest -q tests/test_compare_export_endpoint.py`, `pytest -q tests/test_metadata_endpoint.py`, and `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/client.exportComparison.test.ts` all pass.


## Surprises & Discoveries


The frontend already exposes `api.exportIntent` at `frontend/src/api/client.ts:729`, but the backend route set in `src/lenslet/server.py:1322` through `src/lenslet/server.py:1470` has no `/export-intent` endpoint. A new comparison export endpoint must therefore be implemented explicitly.

Current compare pair selection is derived from filtered and sorted `items` order, not click order, as shown by `compareItems = items.filter(...)` in `frontend/src/app/AppShell.tsx:445`. Future “selection-order compare” requires a separate ordering model rather than only UI changes.

The required Unibox stitch utility creates an `RGB` canvas (`/home/ubuntu/dev/unibox/src/unibox/utils/image_utils.py:32`), so transparent pixels are flattened in output. This is acceptable for v1 but must be documented and tested.

Unibox text sizing can raise `ValueError` on very small images when computed font size collapses to zero. Server-side fallback annotation logic was added so export remains stable for tiny sources.


## Decision Log


1. 2026-02-08, user plus Codex: implement as one sprint with atomic tickets because scope is bounded to compare inspector export.
2. 2026-02-08, user: add a new inspector component titled `Export Comparison` in compare context, with one multiline input and two buttons for normal and reverse export.
3. 2026-02-08, user: map labels by line index for v1, where line 1 annotates A and line 2 annotates B.
4. 2026-02-08, user: include `Embed metadata` checkbox defaulted to on.
5. 2026-02-08, Codex: backend generation is authoritative so Unibox helpers and PNG metadata embedding are consistent and browser-independent.
6. 2026-02-08, Codex: API contract accepts arrays (`paths`, `labels`) with exact length-two enforcement in v1 to preserve forward compatibility for future multi-image export.
7. 2026-02-08, Codex: reverse export swaps image order and label mapping together, and embedded metadata order must match swapped visual order.
8. 2026-02-08, Codex: label policy is deterministic and bounded: max two lines, each line max 120 characters after trim and control-character stripping.
9. 2026-02-08, Codex: export bounds are explicit for reliability: each source image max 64 megapixels, combined stitched canvas max 120 megapixels, embedded metadata JSON max 32 KB.
10. 2026-02-08, Codex: runtime Unibox absence must fail with an actionable dependency message aligned with existing optional dependency behavior in `src/lenslet/cli.py:47`.
11. 2026-02-08, Codex: frontend must show inline export failure state with retry affordance instead of silent console-only failures.


## Outcomes & Retrospective


Sprint implementation is complete and validated. The final delivery preserved the original product scope and incorporated review improvements around safety limits, strict error handling, and inline failure UX. No unresolved product ambiguity remains for v1.


## Context and Orientation


The new inspector UI belongs in the existing compare section in `frontend/src/features/inspector/Inspector.tsx:1053`, which already renders A and B compare metadata. Compare inputs arrive via `compareA` and `compareB` props. Pair construction currently occurs in `frontend/src/app/AppShell.tsx:445` through `frontend/src/app/AppShell.tsx:450`.

Frontend HTTP calls are centralized in `frontend/src/api/client.ts`, where new API methods must be added under `api`. Existing download flow already uses blobs and `downloadBlob` in `frontend/src/app/utils/appShellHelpers.ts:80`.

Backend routes are registered in `_register_common_api_routes` in `src/lenslet/server.py`. Existing image-safe access logic uses `_canonical_path` and `_ensure_image` before serving bytes (`src/lenslet/server.py:1460`). The new route must reuse this validation path.

Metadata extraction helpers already exist in `src/lenslet/metadata.py:235` for PNG and peers for JPEG and WebP. These can produce compact summaries for embedded comparison metadata.

Required composition utilities are in `/home/ubuntu/dev/unibox/src/unibox/utils/image_utils.py`, specifically `concatenate_images_horizontally`, `add_annotation`, and `add_annotations`.

In this document, “embedded metadata” means PNG ancillary text written into exported bytes, not sidecar files. “Reverse order” means B left and A right in both rendered image and embedded metadata arrays.


## Plan of Work


The sprint begins by defining a strict contract and backend safety checks so the endpoint is secure, bounded, and deterministic. The backend then delivers image stitching, annotation, reverse-order semantics, and optional metadata embedding in small separable tasks. Once backend behavior is stable, frontend API and inspector UI wiring add controls and robust error states. The sprint ends with backend and frontend regression tests plus a manual demo script that validates user-visible behavior.

### Sprint Plan


1. S1: Export Comparison end-to-end delivery.
   Goal: deliver one complete compare inspector export path with annotation, reverse-order support, and optional metadata embedding.
   Demo outcome: from compare mode with two selected images, user enters two lines, keeps metadata checkbox on, clicks both export buttons, receives two downloadable PNGs, and can see order/label correctness; then toggles metadata off and confirms metadata omission.
   Linked tasks: T0 path validation parity, T1 request/response contract, T2 backend route and error code policy, T3a stitch core, T3b annotation and fallback labels, T3c metadata embedding with bounds, T4 frontend API wiring, T5 inspector controls and UX state, T6 backend tests, T7 frontend tests, T8 manual demo and acceptance script.


## Concrete Steps


All commands below run from the repository root unless explicitly noted.

    Working directory: /home/ubuntu/dev/lenslet

    rg -n "compareActive|Compare Metadata|compareA|compareB" frontend/src/features/inspector/Inspector.tsx
    rg -n "compareItems|compareA|compareB" frontend/src/app/AppShell.tsx
    rg -n "getMetadata|getFile|exportIntent" frontend/src/api/client.ts
    rg -n "@app.get\(\"/metadata\"|@app.get\(\"/file\"" src/lenslet/server.py

    pytest -q tests/test_metadata_endpoint.py

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run test -- src/api/__tests__/client.prefetch.test.ts

### Task/Ticket Details


1. T0: Add server-side validation parity with existing image routes.
   Goal: ensure `/export-comparison` uses the same canonicalization and image access checks as `/file` and `/thumb` to prevent path traversal and non-image access.
   Affected files and areas: `src/lenslet/server.py`.
   Validation: add backend tests asserting rejected invalid paths and accepted canonical image paths.

2. T1: Define explicit request and response contract.
   Goal: add `v: 1` request version, exact field semantics, and shared frontend type alignment.
   Affected files and areas: `src/lenslet/server_models.py`, `frontend/src/lib/types.ts`, `frontend/src/api/client.ts`.
   Validation: tests confirm backend accepts only `v=1` and frontend request builder emits matching shape.

3. T2: Implement route shell with strict error taxonomy.
   Goal: add `POST /export-comparison` returning `image/png`, with explicit 400 for shape issues, 404 for missing files, 415 for unsupported source formats, and 500 for missing Unibox dependency.
   Affected files and areas: `src/lenslet/server.py`.
   Validation: tests assert status codes and message fragments for each failure class.

4. T3a: Implement image loading and horizontal stitching core.
   Goal: open validated A and B source images and stitch with `concatenate_images_horizontally`.
   Affected files and areas: `src/lenslet/server.py` or helper module under `src/lenslet/`.
   Validation: backend test decodes output PNG and asserts expected stitched width and height constraints.

5. T3b: Implement label parsing, sanitation, and annotation mapping.
   Goal: parse multiline text into two labels, sanitize labels, enforce max two lines and 120 chars per line, apply fallback names when missing, and keep reverse-order label mapping correct.
   Affected files and areas: `src/lenslet/server.py`, `frontend/src/features/inspector/Inspector.tsx`.
   Validation: backend tests for sanitation and line-limit errors; frontend tests for line mapping and reverse payload behavior.

6. T3c: Implement optional metadata embedding with bounded payload.
   Goal: when `embed_metadata` is true, embed compact JSON metadata into PNG text chunks, bounded to 32 KB, and omit metadata when false.
   Affected files and areas: `src/lenslet/server.py`, optional helper in `src/lenslet/metadata.py` if reusable utilities are extracted.
   Validation: readback tests using Pillow and `read_png_info` confirm metadata presence or absence and order correctness.

7. T4: Add frontend API method and download integration.
   Goal: add `api.exportComparison` blob call and wire result to `downloadBlob` with ASCII-safe filename convention `comparison[_reverse]_YYYYMMDD_HHMMSS.png`.
   Affected files and areas: `frontend/src/api/client.ts`, `frontend/src/app/utils/appShellHelpers.ts` (reuse).
   Validation: frontend API tests verify endpoint, payload, and blob handling; backend tests verify `Content-Disposition` filename format.

8. T5: Add `Export Comparison` inspector UI and failure UX.
   Goal: render textarea, metadata checkbox default on, normal and reverse export buttons, pending/disabled states, inline error message, and retry behavior.
   Affected files and areas: `frontend/src/features/inspector/Inspector.tsx`, optional styles in `frontend/src/styles.css`.
   Validation: component tests verify control visibility, default checkbox state, disabled while exporting, and inline error rendering.

9. T6: Add backend regression test suite for comparison export.
   Goal: lock successful normal and reverse behavior, bounds enforcement, metadata readback, alpha flatten expectation, and error taxonomy.
   Affected files and areas: `tests/test_compare_export_endpoint.py`.
   Validation: `pytest -q tests/test_compare_export_endpoint.py` passes with success and failure coverage.

10. T7: Add frontend regression tests for API and inspector behavior.
    Goal: lock request construction, label mapping semantics, reverse-order payload, and error UX.
    Affected files and areas: `frontend/src/features/inspector/__tests__/exportComparison.test.tsx`, `frontend/src/api/__tests__/client.exportComparison.test.ts`.
    Validation: targeted Vitest run passes for both new test files.

11. T8: Produce demo and acceptance script artifacts.
    Goal: document exact manual runbook for reviewer execution in one pass.
    Affected files and areas: this plan file and implementation PR notes.
    Validation: reviewer follows script and reproduces expected outputs without code changes.


## Validation and Acceptance


Sprint validation is behavior-first and includes automated checks plus one manual proof run.

1. S1 backend acceptance is met when valid requests return PNG bytes with expected visual order, labels, and metadata policy, while invalid inputs return deterministic status codes and messages.
2. S1 frontend acceptance is met when compare inspector shows the new block only for compare-ready state, metadata checkbox defaults to checked, and both export buttons deliver downloadable files.
3. Reverse-order acceptance is met only if visual order and embedded metadata arrays both invert consistently and tests assert this explicitly.
4. Safety acceptance is met when path validation parity, line-count and label-length limits, and pixel-size bounds all enforce correctly under tests.

Automated validation commands and expected outcomes are:

    Working directory: /home/ubuntu/dev/lenslet
    pytest -q tests/test_compare_export_endpoint.py
    Expected: pass; includes normal export, reverse export, metadata on/off, bounds, invalid payload, and error code coverage.

    Working directory: /home/ubuntu/dev/lenslet/frontend
    npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/client.exportComparison.test.ts
    Expected: pass; includes default checkbox-on state, label mapping, reverse payload, and inline error UI assertions.

Manual demo script is:

    1) Start app with two images that include at least one PNG source.
    2) Enter compare mode with exactly two active images.
    3) In Export Comparison, enter two lines and click Export comparison.
    4) Confirm downloaded PNG shows A left and B right with matching labels.
    5) Click Export (reverse order) and confirm B left and A right with labels swapped accordingly.
    6) Repeat with metadata checkbox off and confirm metadata readback is absent.
    7) Repeat with intentionally invalid input (third line) and confirm inline error and no download.


## Idempotence and Recovery


Export requests are read-only against source image storage and do not mutate server state, so retrying the same request is safe and deterministic. Server work remains bounded by explicit pixel and metadata size limits.

Recovery is commit-scoped. If backend stitching regresses, revert only T3-series commits and keep UI scaffolding. If UI behavior regresses, revert T5 and T7 while retaining backend endpoint and tests. If Unibox availability causes runtime failures in deployment, keep route contract stable and return the explicit dependency error until environment dependency is corrected.


## Artifacts and Notes


Representative request body for normal export:

    {
      "v": 1,
      "paths": ["/a.png", "/b.png"],
      "labels": ["Prompt A", "Prompt B"],
      "embed_metadata": true,
      "reverse_order": false
    }

Representative compact metadata payload embedded into PNG text:

    {
      "tool": "lenslet.export_comparison",
      "version": 1,
      "paths": ["/a.png", "/b.png"],
      "labels": ["Prompt A", "Prompt B"],
      "reversed": false,
      "exported_at": "2026-02-08T03:54:37Z"
    }

Representative response headers:

    content-type: image/png
    content-disposition: attachment; filename="comparison_20260208_035437.png"

Representative explicit failure examples:

    400 invalid_labels: expected at most two lines of labeling text
    400 export_too_large: stitched output exceeds configured pixel limit
    500 unibox_missing: unibox is required for comparison export


## Interfaces and Dependencies


Backend interface additions are:

    POST /export-comparison
    Request JSON:
      v: 1
      paths: string[]            # required; must be exactly length 2 in v1
      labels?: string[]          # optional; max length 2, max 120 chars per label
      embed_metadata?: boolean   # default true
      reverse_order?: boolean    # default false

    Response:
      200 image/png (binary)
      400 JSON { error, message }
      404 JSON { error, message }
      415 JSON { error, message }
      500 JSON { error, message } for missing runtime dependency

Frontend interface additions are:

    api.exportComparison(body: {
      v: 1
      paths: string[]
      labels?: string[]
      embed_metadata?: boolean
      reverse_order?: boolean
    }): Promise<Blob>

Inspector behavior contract is:

    compareReady == true enables controls
    textarea line 1 -> A label
    textarea line 2 -> B label
    more than two lines -> client-side validation error
    embed_metadata checkbox default true
    export buttons disabled during in-flight request

Dependencies are `unibox.utils.image_utils.concatenate_images_horizontally`, `unibox.utils.image_utils.add_annotation` or `add_annotations`, Pillow plus `PngImagePlugin.PngInfo` for metadata writes, existing metadata readers in `src/lenslet/metadata.py`, and existing frontend blob download helper `downloadBlob`.

Revision note (2026-02-08): Updated after mandatory subagent review to split oversized tasks, add explicit security and limit tickets, define concrete error UX requirements, and tighten acceptance coverage for reverse-order semantics and metadata roundtrip behavior.
