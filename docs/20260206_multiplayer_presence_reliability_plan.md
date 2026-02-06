# Multiplayer Presence and Realtime Reliability Plan


## Purpose / Big Picture


This plan defines the implementation sequence to make Lenslet multiplayer behavior trustworthy in daily use, specifically for online and editing counts, realtime sync consistency, refresh/tab lifecycle correctness, and visibility of remote edits under filtered and recursive views. After completion, users should be able to open multiple tabs and browsers, move between folders, refresh pages, and edit metadata while seeing stable, low-latency, non-duplicated presence counts and clear remote edit signals that match the current scope.

The finished behavior is observable by running two or more clients against one server and verifying that online and editing indicators converge within a short bounded window, do not permanently inflate after refresh, and remain coherent across scope changes, reconnects, and filter modes.


## Progress


- [x] 2026-02-06 05:22:36Z Investigated current backend and frontend multiplayer flows without code changes.
- [x] 2026-02-06 05:22:36Z Identified concrete failure modes with file-level evidence and line references.
- [x] 2026-02-06 05:22:36Z Drafted a sprinted implementation plan with atomic tasks and validation per task.
- [x] 2026-02-06 05:45:00Z Reviewed task sizing, hidden dependencies, and validation gaps; split oversized work and tightened acceptance bounds.
- [x] 2026-02-06 12:06:30Z Completed Sprint 1 server-side presence model hardening (T1-T6), including lifecycle routes (`join/move/leave`), lease validation, periodic stale-prune loop, legacy `/presence` compatibility wiring, API docs update, and passing backend tests.
- [x] 2026-02-06 12:10:09Z Completed T1-T6 implementation in code: `src/lenslet/server_sync.py`, `src/lenslet/server.py`, `src/lenslet/server_models.py`, and `docs/20260123_collaboration_sync_api.md`.
- [x] 2026-02-06 12:10:09Z Added Sprint 1 backend lifecycle coverage in `tests/test_presence_lifecycle.py` (join/move/leave/invariants/invalid-lease/stale-prune/legacy heartbeat compatibility).
- [x] 2026-02-06 12:10:09Z Validation pass completed in `/home/ubuntu/dev/lenslet-2`: `PYTHONPATH=src pytest -q` => `30 passed`.
- [x] 2026-02-06 12:31:15Z Completed Sprint 2 client lifecycle and identity hardening implementation (T7-T11): tab-scoped refresh-stable `client_id`, `join/move/leave` lifecycle wiring with lease handling, unload-safe leave via beacon/keepalive, reconnect-triggered presence resync, and coalesced rapid scope transitions in `frontend/src/api/client.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/lib/constants.ts`, and `frontend/vite.config.ts`.
- [x] 2026-02-06 12:31:15Z Added Sprint 2 frontend lifecycle tests in `frontend/src/api/__tests__/client.presence.test.ts` covering tab identity behavior and unload leave transport fallback.
- [x] 2026-02-06 12:31:15Z Validation pass completed in `/home/ubuntu/dev/lenslet-2`: `cd frontend && npm test` => `12 passed`, `cd frontend && npm run build` => success, `PYTHONPATH=src pytest -q` => `30 passed`.
- [x] 2026-02-06 12:46:59Z Updated handover notes for Sprint 3 continuation with implemented Sprint 2 artifacts, current behavioral assumptions, and remaining reliability test gaps.
- [x] 2026-02-06 12:58:04Z Completed a code-simplifier maintainability pass on touched Sprint 2 frontend files (`frontend/src/api/client.ts`, `frontend/src/app/AppShell.tsx`, `frontend/vite.config.ts`, `frontend/src/api/__tests__/client.presence.test.ts`) with behavior-preserving helper extraction and reduced duplication; validated with `cd frontend && npm test` => `12 passed` and `cd frontend && npm run build` => success.
- [x] 2026-02-06 13:13:21Z Completed Sprint 3 UI coherence and update visibility (T12-T15): deterministic indicator precedence helper + unit tests, local typing cue separate from server editing counts, off-view update summary/reveal/clear behavior, and event-id keyed minimum-window grid highlights in `frontend/src/app/AppShell.tsx`, `frontend/src/app/presenceUi.ts`, `frontend/src/app/__tests__/presenceUi.test.ts`, `frontend/src/shared/ui/SyncIndicator.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/app/components/StatusBar.tsx`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/browse/components/ThumbCard.tsx`, `frontend/src/styles.css`, and `frontend/src/lib/constants.ts`.
- [x] 2026-02-06 13:13:21Z Validation pass completed in `/home/ubuntu/dev/lenslet-2`: `cd frontend && npm test` => `17 passed`, `cd frontend && npm run build` => success, `PYTHONPATH=src pytest -q` => `30 passed`.
- [x] 2026-02-06 13:18:03Z Updated handover notes for Sprint 4 continuation with Sprint 3 implementation artifacts, current interface/state assumptions, and recommended T16-T22 execution order.
- [x] 2026-02-06 13:27:01Z Completed a code-simplifier maintainability pass on Sprint 3 frontend artifacts with behavior-preserving refactors: extracted presence activity tracking/highlight logic into `frontend/src/app/presenceActivity.ts`, simplified `frontend/src/app/AppShell.tsx` orchestration, deduplicated viewport visibility notifications in `frontend/src/features/browse/components/VirtualGrid.tsx`, consolidated local typing handlers in `frontend/src/features/inspector/Inspector.tsx`, and shared off-view summary typing in `frontend/src/app/components/StatusBar.tsx`.
- [x] 2026-02-06 13:27:01Z Validation pass completed in `/home/ubuntu/dev/lenslet-2`: `cd frontend && npm test` => `17 passed`, `cd frontend && npm run build` => success, `PYTHONPATH=src pytest -q` => `30 passed`.
- [x] 2026-02-06 13:28:37Z Added helper-level frontend coverage for extracted Sprint 3 activity module in `frontend/src/app/__tests__/presenceActivity.test.ts`; validation rerun: `cd frontend && npm test` => `20 passed`, `cd frontend && npm run build` => success.
- [x] 2026-02-06 13:43:12Z Completed Sprint 4 backend reliability hardening (T17/T19/T20/T22 backend portions): added thread-safety race coverage, multi-client convergence integration test, runtime diagnostics counters (`active_clients`, `active_scopes`, `stale_pruned_total`, `invalid_lease_total`, `replay_miss_total`), `/presence/diagnostics` endpoint, health payload presence diagnostics, and lifecycle-v2 rollout gate (`presence_lifecycle_v2`) with legacy heartbeat fallback behavior.
- [x] 2026-02-06 13:43:12Z Completed Sprint 4 frontend reliability tests (T18): added EventSource reconnect/backoff/polling-fallback and replay-last-event-id coverage in `frontend/src/api/__tests__/client.events.test.ts`.
- [x] 2026-02-06 13:43:12Z Completed Sprint 4 docs/runbook updates (T21/T22 docs): refreshed `docs/20260123_collaboration_sync_api.md` and `docs/20260124_collaboration_sync_ops.md` with diagnostics payloads, convergence bounds, lifecycle-v2 gate semantics, and rollback smoke checklist.
- [x] 2026-02-06 13:43:12Z Sprint 4 validation pass completed in `/home/ubuntu/dev/lenslet-2`: `PYTHONPATH=src pytest -q tests/test_presence_lifecycle.py` => `8 passed`, `PYTHONPATH=src pytest -q tests/test_collaboration_sync.py` => `4 passed`, `cd frontend && npm test` => `23 passed`, `cd frontend && npm run build` => success, `PYTHONPATH=src pytest -q` => `34 passed`.
- [x] 2026-02-06 13:52:08Z Updated this plan document with post-Sprint-4 progress state and final handover notes for rollout/operations follow-through.
- [x] Execute Sprint 3 UI signal coherence and scope-aware remote-update visibility.
- [x] Execute Sprint 4 reliability tests, ops instrumentation, and docs updates.


## Surprises & Discoveries


Presence cleanup is event-driven rather than time-driven. Stale entries are only pruned when another touch occurs in the same gallery scope, so abandoned sessions can persist until a new event for that scope arrives. Evidence: `src/lenslet/server_sync.py:201` through `src/lenslet/server_sync.py:220`.

The client heartbeats presence every 30 seconds but does not send an explicit leave signal on unmount, refresh, or tab close. This leaves old sessions to age out via TTL and can produce temporary ghost users after refresh. Evidence: `frontend/src/app/AppShell.tsx:606` through `frontend/src/app/AppShell.tsx:625`.

Presence scope resolution diverges between “current gallery heartbeat” and “edit-derived gallery id.” The UI heartbeats `current`, but edit events publish to parent-of-item gallery (`_gallery_id_from_path`), which causes mismatched counts in recursive and filtered usage. Evidence: `frontend/src/app/AppShell.tsx:608`, `frontend/src/app/AppShell.tsx:696`, `src/lenslet/server_sync.py:29`, and `src/lenslet/server.py:914`.

Editing semantics are write-triggered, not interaction-triggered. Notes and tags update on blur, so active typing can still show as non-editing. Evidence: `frontend/src/features/inspector/Inspector.tsx:745` and `frontend/src/features/inspector/Inspector.tsx:757`.

The indicator state can show editing for up to 15 minutes due to local hold behavior, even when server editing count is zero, creating a possible mismatch between dot state and numeric editing count. Evidence: `frontend/src/lib/constants.ts:2` and `frontend/src/app/AppShell.tsx:711`.

The current client lifecycle has no pagehide/visibility/unload leave path. Presence requests are timer-driven only, and browsers do not guarantee asynchronous fetch completion during unload. Without a beacon or keepalive strategy, immediate leave semantics can be flaky if not designed explicitly. Evidence: `frontend/src/app/AppShell.tsx:606` through `frontend/src/app/AppShell.tsx:625`.

Presence state and SSE replay are process-local (`PresenceTracker()` and `EventBroker(buffer_size=500)` are instantiated in-memory per app process), so reliability assumptions depend on single-worker deployment and a bounded replay window. This must be treated as an explicit operational dependency. Evidence: `src/lenslet/server.py:797` through `src/lenslet/server.py:800`, `src/lenslet/server_sync.py:139` through `src/lenslet/server_sync.py:142`, and `src/lenslet/cli.py:585` through `src/lenslet/cli.py:598`.


## Decision Log


2026-02-06, author: assistant and user context. Presence truth will remain server-authoritative, but session lifecycle transitions must be explicit and fast-bounded rather than relying only on passive TTL expiry. This decision directly targets refresh-as-extra-user inflation.

2026-02-06, author: assistant and user context. Presence must be modeled as one active scope per client session, with deterministic move semantics when a client changes scope. This prevents one session being counted in multiple galleries simultaneously.

2026-02-06, author: assistant and user context. UI editing state will be tied to server editing signal plus a short visual smoothing window only, removing long local hold that can conflict with displayed editing counts.

2026-02-06, author: assistant and user context. Remote update visibility must include both “currently visible item blink” and “off-screen/off-filter update summary” so collaboration feedback is still available under filters and recursive browsing.

2026-02-06, author: assistant and user context. Reliability changes are not complete without targeted multiplayer tests for presence lifecycle, scope switching, reconnect behavior, and stale-entry pruning.

2026-02-06, author: assistant and user context. Presence lifecycle routes will use a server-issued `lease_id` token on join, and move/leave calls must include it. This prevents one client from accidentally or maliciously evicting another client by reusing only `client_id`.

2026-02-06, author: assistant and user context. Rollout will keep legacy `POST /presence` heartbeat behavior behind compatibility wiring until new lifecycle routes are validated; removal is a separate follow-up change, not part of initial reliability hardening.

2026-02-06, author: assistant and user context. Acceptance bounds are explicit: explicit move/leave convergence target is <=5 seconds, crash/no-leave convergence target is <=(view_ttl + prune_interval + 5 seconds) at default config.

2026-02-06, author: assistant and user context. Presence correctness remains single-worker scoped in this iteration; multi-worker/shared-state presence is out of scope and must be documented as an operational constraint.


## Outcomes & Retrospective


Sprint 1 through Sprint 4 are implemented and validated in this branch. Backend presence accounting now includes explicit lifecycle transitions with lease validation, periodic stale cleanup, diagnostics counters, replay-window visibility, and an operator gate to roll back lifecycle-v2 semantics safely. Frontend now includes tab-scoped identity, explicit lifecycle wiring, deterministic indicator precedence, local-typing signaling, off-view update summaries, event-id keyed highlight behavior, and reconnect/backoff reliability tests. Ops/API docs now reflect actual payloads, convergence bounds, and rollback procedures.

The main lesson from investigation is that most observed “half-baked” behavior is not a single bug but interaction between scope modeling, lifecycle timing, and UI state precedence.


## Context and Orientation


Relevant backend files are `src/lenslet/server_sync.py` for broker and presence tracking, and `src/lenslet/server.py` for route wiring and per-edit presence publishing. Relevant frontend files are `frontend/src/api/client.ts` for EventSource and client identity, `frontend/src/app/AppShell.tsx` for presence heartbeat and indicator derivation, `frontend/src/shared/ui/SyncIndicator.tsx` for presentation, `frontend/src/features/inspector/Inspector.tsx` for write timing semantics, and `frontend/src/features/browse/components/VirtualGrid.tsx` plus `frontend/src/features/browse/components/ThumbCard.tsx` for update blink behavior.

No `PLANS.md` file is present in this repository, so this document is the canonical execution plan for this effort.

In this plan, “scope” means the gallery path for which presence is aggregated. “Session” means one browser tab instance lifecycle. “Ghost user” means a stale session still counted as online after disconnect or refresh. “Realtime coherence” means numeric counts, dot state, and visible update cues agree within bounded delay.


## Plan of Work


The implementation sequence starts by fixing server-side presence lifecycle semantics so the backend can serve as a reliable truth source. It then tightens frontend session lifecycle and reconnect behavior so client actions map accurately to server state, including browser page lifecycle realities. Once data-plane correctness is stable, the UI signal layer is adjusted to remove contradictory states and to preserve collaborator feedback under filtered views. The final sprint formalizes reliability through automated tests, operational counters, explicit rollout gates, and documentation updates.

### Sprint Plan


1. Sprint S1: Presence State Model Hardening.
The goal is to make backend presence accounting deterministic, explicitly handle join/move/leave with lease validation, and bound stale data independently of incidental touches. The demo outcome is that one session cannot appear in multiple scopes, stale sessions age out predictably, legacy heartbeat remains compatible, and scope move immediately updates counts. Linked tasks are T1 through T6.

2. Sprint S2: Client Lifecycle and Identity Reliability.
The goal is to map browser tab lifecycle to explicit presence transitions and preserve tab-scoped identity through refresh/reconnect paths. The demo outcome is that refresh no longer inflates online counts beyond the convergence bound, reconnects recover without presence drift, and unload behavior is handled with beacon/keepalive fallbacks. Linked tasks are T7 through T11.

3. Sprint S3: UI Coherence and Update Visibility.
The goal is to ensure indicator state and counts do not contradict each other and that remote updates are visible even when filtered out of the active grid. The demo outcome is a deterministic indicator precedence model, separate local-typing vs remote-editing cues, and explicit “updates outside current view” feedback. Linked tasks are T12 through T15.

4. Sprint S4: Reliability Tests, Ops Signals, and Docs.
The goal is to lock behavior with automated tests and operational introspection so regressions are detectable early. The demo outcome is reproducible test evidence for lifecycle/reconnect race edges, explicit observability counters, and rollout-safe docs/checklists. Linked tasks are T16 through T22.


## Concrete Steps


Implementation should run from `/home/ubuntu/dev/lenslet`.

    cd /home/ubuntu/dev/lenslet

Create a feature branch before code changes.

    git checkout -b fix/multiplayer-presence-reliability

Run fast targeted tests after each sprint and full tests after Sprint 4.

    pytest tests/test_collaboration_sync.py -q
    pytest -q

### Task/Ticket Details


1. T1: Refactor `PresenceTracker` to explicit lifecycle state with invariant-friendly indexes.
Goal: maintain one active scope per `client_id` using both client-centric and scope-centric indexes, enabling deterministic join/move/leave without scanning all scopes.
Affected areas: `src/lenslet/server_sync.py`.
Validation: backend unit tests prove invariants: one client belongs to at most one scope, counts never go negative, and duplicate transitions are idempotent.

2. T2: Add `POST /presence/join` route and schema.
Goal: create session membership explicitly and return canonical scope counts plus a server-issued `lease_id`.
Affected areas: `src/lenslet/server_models.py`, `src/lenslet/server.py`, and `docs/20260123_collaboration_sync_api.md`.
Validation: integration test verifies join increments once and repeated join with same lease is idempotent.

3. T3: Add `POST /presence/move` route and schema.
Goal: move one active session from old scope to new scope atomically, guarded by `lease_id`.
Affected areas: `src/lenslet/server_models.py`, `src/lenslet/server.py`, and `src/lenslet/server_sync.py`.
Validation: integration test verifies old scope decrements, new scope increments, and replayed move converges without duplication.

4. T4: Add `POST /presence/leave` route and invalid-lease handling.
Goal: support immediate session removal while rejecting stale/forged leave operations.
Affected areas: `src/lenslet/server_models.py`, `src/lenslet/server.py`, and `src/lenslet/server_sync.py`.
Validation: integration test verifies valid leave decrements immediately and wrong lease returns a deterministic error payload.

5. T5: Add periodic stale-prune loop with startup/shutdown lifecycle wiring.
Goal: remove stale sessions even when scopes are idle and publish corrected presence counts for affected scopes.
Affected areas: `src/lenslet/server.py` and `src/lenslet/server_sync.py`.
Validation: timed test simulates crash/no-leave and verifies stale cleanup occurs without any extra presence traffic.

6. T6: Preserve legacy `POST /presence` compatibility with normalized schema.
Goal: keep existing clients functional while routing heartbeat behavior through the new lifecycle model and emitting a consistent presence payload shape.
Affected areas: `src/lenslet/server.py`, `src/lenslet/server_sync.py`, and `docs/20260123_collaboration_sync_api.md`.
Validation: existing heartbeat path tests continue passing while lifecycle-route tests pass in the same run.

7. T7: Make client identity tab-scoped and refresh-stable.
Goal: use `sessionStorage` as primary scope for `client_id`, with controlled migration from legacy `localStorage`.
Affected areas: `frontend/src/api/client.ts`.
Validation: automated test verifies two tabs produce different `client_id` values while hard refresh preserves each tab’s own id.

8. T8: Implement join/move/leave wiring in AppShell lifecycle.
Goal: send join on mount, move on scope change, and leave on unmount/pagehide with deterministic cleanup of local presence cache.
Affected areas: `frontend/src/app/AppShell.tsx` and `frontend/src/api/client.ts`.
Validation: automated lifecycle test verifies correct API call sequence during mount, scope switch, and unmount.

9. T9: Add unload-safe leave transport.
Goal: use `navigator.sendBeacon` when available and `fetch(..., { keepalive: true })` fallback for pagehide/unload reliability.
Affected areas: `frontend/src/api/client.ts`.
Validation: unit tests mock browser APIs and verify leave payload dispatch path selection.

10. T10: Reconnect reconciliation and immediate resync.
Goal: after SSE reconnect, force immediate presence refresh and prevent stale local presence cache from overriding server truth.
Affected areas: `frontend/src/api/client.ts` and `frontend/src/app/AppShell.tsx`.
Validation: reconnect simulation confirms convergence to server counts within <=5 seconds after connection resumes.

11. T11: Rate-limit lifecycle transitions without hiding state changes.
Goal: coalesce rapid scope transitions to reduce request bursts while guaranteeing final scope correctness.
Affected areas: `frontend/src/app/AppShell.tsx` and `frontend/src/lib/constants.ts`.
Validation: test with rapid folder changes shows bounded request count and correct final presence scope.

12. T12: Define deterministic indicator precedence matrix.
Goal: codify precedence rules for offline/unstable/recent/editing/live and remove long local-edit hold conflicts.
Affected areas: `frontend/src/app/AppShell.tsx`, `frontend/src/shared/ui/SyncIndicator.tsx`, and `frontend/src/lib/constants.ts`.
Validation: pure-function unit tests cover all precedence branches and guarantee `editing` dot aligns with displayed counts.

13. T13: Separate local typing cue from remote editing count.
Goal: represent local in-progress typing separately from server-reported collaborator editing, avoiding overloaded semantics.
Affected areas: `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/app/AppShell.tsx`, and `frontend/src/shared/ui/SyncIndicator.tsx`.
Validation: interaction test confirms local typing cue appears before blur while remote editing number remains server-driven.

14. T14: Add off-view remote update summary with explicit clear behavior.
Goal: show non-intrusive summary for updates outside current filter/viewport and define when summary clears.
Affected areas: `frontend/src/app/AppShell.tsx` and `frontend/src/app/components/StatusBar.tsx`.
Validation: filtered-view scenario verifies summary appears, links contextually, and clears only after user dismissal or visibility.

15. T15: Stabilize visible-item highlight under virtualization churn.
Goal: key highlight timing by event id and ensure minimum visible pulse window to avoid flicker.
Affected areas: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/browse/components/ThumbCard.tsx`, and `frontend/src/styles.css`.
Validation: repeated updates on visible cards produce one stable pulse per event id in deterministic test playback.

16. T16: Add backend lifecycle invariant tests.
Goal: cover join, move, leave, prune, invalid lease, and compatibility heartbeat behavior.
Affected areas: `tests/test_presence_lifecycle.py` and/or `tests/test_collaboration_sync.py`.
Validation: `pytest tests/test_presence_lifecycle.py -q` passes and fails deterministically when invariants are intentionally broken.

17. T17: Add backend concurrency/race tests.
Goal: verify thread-safety and deterministic outcomes under concurrent move/leave/touch operations.
Affected areas: `tests/test_presence_lifecycle.py`.
Validation: stress-style test runs repeatedly without flaky failures and confirms no negative or duplicated counts.

18. T18: Add frontend presence lifecycle and reconnect tests.
Goal: test client lifecycle routing, reconnect backoff recovery, and unload dispatch with fake timers/mocks.
Affected areas: frontend tests under `frontend/src/api` and `frontend/src/app`.
Validation: `cd frontend && npm run test` includes new presence suites and passes locally.

19. T19: Add multi-client integration scenario test in Python.
Goal: simulate multiple clients against one ASGI app to verify refresh, move, and reconnect convergence end to end.
Affected areas: `tests/test_collaboration_sync.py` or `tests/test_presence_lifecycle.py`.
Validation: test asserts explicit convergence bounds for explicit leave/move and crash/no-leave paths.

20. T20: Add presence observability counters and replay-window diagnostics.
Goal: expose debug-safe counters (`active_clients`, `active_scopes`, `stale_pruned_total`, `invalid_lease_total`, `replay_miss_total`) to make runtime drift detectable.
Affected areas: `src/lenslet/server.py` and docs.
Validation: counter values change predictably in scripted multi-tab scenarios.

21. T21: Update collaboration API and ops docs with hard bounds and constraints.
Goal: document lifecycle payloads, expected convergence windows, single-worker requirement, and tuning knobs (`view_ttl`, `edit_ttl`, prune interval).
Affected areas: `docs/20260123_collaboration_sync_api.md`, `docs/20260124_collaboration_sync_ops.md`, and README notes if needed.
Validation: docs examples match implemented payloads and ops checklist reproduces expected behavior.

22. T22: Add rollout and rollback gate for lifecycle-v2 behavior.
Goal: provide a feature flag and runbook so operators can switch between legacy heartbeat and lifecycle routes during staged rollout.
Affected areas: `src/lenslet/server.py`, frontend config wiring (if needed), and ops docs.
Validation: smoke tests pass in both flag states, and rollback procedure restores legacy behavior without restart surprises.


## Validation and Acceptance


Sprint S1 acceptance requires deterministic backend behavior under four scenarios: join, move, leave, and crash/no-leave prune. Explicit move/leave convergence target is <=5 seconds from request completion to corrected counts in emitted presence payloads. Crash/no-leave convergence target is <=(`view_ttl` + prune interval + 5 seconds) at default configuration.

Sprint S2 acceptance requires browser lifecycle correctness for mount/scope-switch/pagehide/refresh/reconnect. In a two-tab scenario with one hard refresh and rapid folder switching, no inflated count may persist beyond 10 seconds after the refreshed tab returns live.

Sprint S3 acceptance requires UI coherence checks backed by tests for the precedence matrix. Dot state, `viewing/editing` text, local typing cue, and recent-update signal must remain non-contradictory across offline, reconnecting, idle, and active-edit states. Under filters, off-view updates must produce explicit summary feedback until dismissed or surfaced.

Sprint S4 acceptance requires green automated suites across backend and frontend presence scenarios (`pytest -q`, targeted presence tests, and `cd frontend && npm run test`), plus documentation and ops notes updated to match actual payloads and convergence bounds.

Overall acceptance requires this end-to-end scenario: start server, open three clients, perform edits across two folders with one filtered view active, refresh one client, temporarily disrupt SSE, recover connection, and observe stable counts and update signals without manual page reload as a recovery mechanism, staying within the explicit convergence bounds above.


## Idempotence and Recovery


Presence transitions must be idempotent by `client_id` and transition type, so repeated join or leave calls do not double-count or underflow counters. Move operations should be safe to replay and should converge to a single active scope per client.

If a deploy introduces regressions, recovery is straightforward because this effort is protocol and runtime behavior hardening rather than data migration. Rollback means reverting the feature branch and redeploying the previous server and frontend bundle. Since presence is ephemeral, rollback does not require metadata repair.

For operational retries, clients should safely resend join or heartbeat after transient network failures. Server should tolerate duplicate lifecycle events and publish corrected counts.

Rollout recovery should include a configuration gate for lifecycle-v2 routes, allowing operators to temporarily route clients through legacy heartbeat semantics while preserving SSE item updates. The runbook in Sprint 4 must include exact flag values, restart expectations, and post-rollback smoke checks.


## Artifacts and Notes


Current scope mismatch evidence sample.

    Heartbeat scope source: frontend/src/app/AppShell.tsx:608
    Display lookup scope: frontend/src/app/AppShell.tsx:696
    Edit-publish scope derivation: src/lenslet/server_sync.py:29 and src/lenslet/server.py:914

Current stale-prune behavior sample.

    Prune is executed inside _counts_locked during touch operations only:
    src/lenslet/server_sync.py:201-220

Proposed lifecycle payload examples.

    POST /presence/join
    {"gallery_id":"/animals","client_id":"<tab-id>"}
    Response: {"gallery_id":"/animals","client_id":"<tab-id>","lease_id":"<lease-id>","viewing":2,"editing":0}

    POST /presence/move
    {"from_gallery_id":"/animals","to_gallery_id":"/animals/cats","client_id":"<tab-id>","lease_id":"<lease-id>"}

    POST /presence/leave
    {"gallery_id":"/animals/cats","client_id":"<tab-id>","lease_id":"<lease-id>"}

Sprint 1 implementation artifacts.

    Updated files:
    src/lenslet/server_sync.py
    src/lenslet/server.py
    src/lenslet/server_models.py
    tests/test_presence_lifecycle.py
    docs/20260123_collaboration_sync_api.md

    Verification commands:
    PYTHONPATH=src pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py
    PYTHONPATH=src pytest -q

### Handover Notes


Sprint S4 is complete and validated. The next handoff target is rollout hardening and operational adoption, not core implementation.

Final implementation artifacts relevant to operations:

    Backend runtime diagnostics + lifecycle gate:
    src/lenslet/server_sync.py
    src/lenslet/server.py
    src/lenslet/cli.py
    - diagnostics counters available via `GET /presence/diagnostics` and `GET /health` -> `presence`.
    - lifecycle-v2 rollout gate is configurable via CLI:
      `--presence-lifecycle-v2` (default) / `--no-presence-lifecycle-v2`.

    Frontend reliability coverage:
    frontend/src/api/__tests__/client.events.test.ts
    frontend/src/api/__tests__/client.presence.test.ts
    - reconnect backoff, offline polling fallback, replay-last-event-id URL behavior.
    - tab-scoped identity + unload-safe leave transport.

    Backend reliability + convergence coverage:
    tests/test_presence_lifecycle.py
    - race stress for concurrent move/leave/touch paths.
    - multi-client refresh/move/reconnect/crash-no-leave convergence scenario.
    - diagnostics counters assertions + lifecycle-v2 rollback smoke checks.

    Documentation updates:
    docs/20260123_collaboration_sync_api.md
    docs/20260124_collaboration_sync_ops.md
    README.md

Recommended handoff checklist for next owner:

    1) Run lifecycle-v2 mode smoke:
       `lenslet /path/to/images --presence-lifecycle-v2`
       Verify `GET /presence/diagnostics` reports `lifecycle_v2_enabled: true`.

    2) Run rollback mode smoke:
       `lenslet /path/to/images --no-presence-lifecycle-v2`
       Verify `GET /presence/diagnostics` reports `lifecycle_v2_enabled: false`.
       Verify `/presence/leave` payload includes `mode: "legacy_heartbeat"` and `removed: false`.

    3) Enforce single-worker deployment:
       `UVICORN_WORKERS=1`, `WEB_CONCURRENCY=1`.

Known constraints still in effect:

    Presence and replay remain process-local/in-memory in this iteration.
    SSE presence payloads remain aggregate-only (`gallery_id`, `viewing`, `editing`).

Current test coverage snapshot:

    Backend:
    tests/test_presence_lifecycle.py
    tests/test_collaboration_sync.py

    Frontend:
    frontend/src/api/__tests__/client.events.test.ts
    frontend/src/api/__tests__/client.presence.test.ts
    frontend/src/app/__tests__/presenceUi.test.ts
    frontend/src/app/__tests__/presenceActivity.test.ts


## Interfaces and Dependencies


Backend dependencies remain FastAPI and in-process synchronization primitives already used by Lenslet. No new external service is required.

Frontend dependencies remain native `EventSource`, React state, and React Query. Lifecycle leave reliability additionally depends on browser support for `navigator.sendBeacon` or `fetch` with `keepalive`.

Required backend interface changes are introduction of explicit lifecycle routes and normalized presence event schema. Expected server-side signatures include presence tracker methods equivalent to `join(gallery_id, client_id) -> lease_id`, `move(from_gallery_id, to_gallery_id, client_id, lease_id)`, `touch_view(gallery_id, client_id, lease_id)`, `touch_edit(gallery_id, client_id, lease_id)`, and `leave(gallery_id, client_id, lease_id)`.

Required frontend interface changes include API methods equivalent to `postPresenceJoin`, `postPresenceMove`, and `postPresenceLeave`, plus unload-safe variants (`sendBeacon`/`keepalive`) and AppShell lifecycle wiring that calls them during mount, scope change, and unmount/pagehide.

Where possible, keep existing `/presence` heartbeat compatibility for gradual rollout, then deprecate legacy behavior in docs once lifecycle routes are proven.

Operational dependency: presence and replay state are in-memory per process. The plan assumes single-worker deployment for correctness in this iteration (`UVICORN_WORKERS=1`, `WEB_CONCURRENCY=1`), and docs must call this out explicitly.


Plan change note: Revised on 2026-02-06 after automated review pass to split oversized tickets, add lifecycle security and compatibility tasks (`lease_id` and legacy heartbeat coexistence), and add explicit convergence bounds for validation.
Plan change note: Revised on 2026-02-06 12:10:09Z to record Sprint 1 implementation/test progress and add explicit handover notes for Sprint 2 continuation.
Plan change note: Revised on 2026-02-06 12:46:59Z to record Sprint 2 completion and replace handover guidance with Sprint 3-focused continuation notes.
Plan change note: Revised on 2026-02-06 12:58:04Z to record a behavior-preserving code simplifier round on Sprint 2 frontend artifacts and refreshed handover notes.
Plan change note: Revised on 2026-02-06 13:13:21Z to record Sprint 3 implementation completion and validation results.
Plan change note: Revised on 2026-02-06 13:18:03Z to refresh handover notes for Sprint 4 execution (T16-T22) with current artifacts and test gaps.
Plan change note: Revised on 2026-02-06 13:27:01Z to record a behavior-preserving code simplifier round on Sprint 3 frontend artifacts, updated validation run, and maintainability-focused handover additions.
Plan change note: Revised on 2026-02-06 13:28:37Z to record additional helper-level tests for `presenceActivity` and updated frontend validation totals.
Plan change note: Revised on 2026-02-06 13:43:12Z to record Sprint 4 completion: backend race/integration coverage, frontend reconnect coverage, observability counters + diagnostics endpoint, lifecycle-v2 rollout gate, and refreshed API/ops docs.
Plan change note: Revised on 2026-02-06 13:52:08Z to replace the stale pre-S4 handover block with post-S4 rollout-focused handover notes and operator checklist.
