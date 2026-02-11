# Post-S4 High-Impact Simplification Scan

Date: 2026-02-11
Context: Audit after S4/T13d completion to identify high-impact simplifications not yet implemented.

## Legend
- `Covered later by original plan`: explicitly or strongly implied by remaining tickets in `docs/20260211_foundational_long_file_refactor_plan.md`.
- `Not covered by original plan`: no remaining ticket clearly owns this work.

## Findings

| Priority | Candidate Simplification | Primary Files | Why High Impact | Plan Coverage | Plan Ticket Mapping |
|---|---|---|---|---|---|
| P1 | Extract AppShell preference persistence/hydration into a dedicated hook (`useAppPreferences`) | `frontend/src/app/AppShell.tsx:755`, `frontend/src/app/AppShell.tsx:875` | Large inline effects with parsing/validation logic increase cognitive load and risk of settings regressions | Covered later by original plan | S4 `T14` (selectors/helpers), S4 `T15` (effect churn) |
| P1 | Extract device/input behavior effects (zoom heuristic, viewport listeners, ctrl-wheel, pinch resize) into a dedicated hook | `frontend/src/app/AppShell.tsx:842`, `frontend/src/app/AppShell.tsx:897`, `frontend/src/app/AppShell.tsx:917`, `frontend/src/app/AppShell.tsx:932` | Several unrelated global listeners in one component increase bug surface and complicate cleanup correctness | Covered later by original plan | S4 `T15` |
| P1 | Simplify presence transition state machine internals (`join/move/flush/schedule`) into smaller units | `frontend/src/app/hooks/useAppPresenceSync.ts:199` | Current flow is hard to reason about under reconnect/race conditions; refactor would reduce lifecycle brittleness | Covered later by original plan | S4 `T15` (effect/churn and lifecycle cleanup) |
| P2 | Replace long filter-chip `if/else` chain with declarative rule map/renderer | `frontend/src/app/AppShell.tsx:620` | High branching density for one UI derivation path; hard to extend safely | Covered later by original plan | S4 `T14` |
| P2 | Remove dead breadcrumb block guarded by constant false | `frontend/src/app/AppShell.tsx:1287` | Dead UI code in the largest component creates maintenance noise and review overhead | Not covered by original plan | None |
| P1 | Split `server_sync.py` by domain (`events`, `presence`, `persistence`) while preserving import/facade contracts | `src/lenslet/server_sync.py:141`, `src/lenslet/server_sync.py:244`, `src/lenslet/server_sync.py:510`, `src/lenslet/server_sync.py:590` | Single file currently mixes multiple runtime subsystems; high coupling and difficult change isolation | Not covered by original plan | None |
| P2 | Split `register_common_api_routes` into smaller registration units (read routes, mutation routes, stream/media routes) | `src/lenslet/server_routes_common.py:80` | Monolithic registration function raises regression risk when touching unrelated endpoints | Not covered by original plan | None |
| P2 | Break `scan_rows` into explicit row-stage helpers to reduce branch density and improve testability | `src/lenslet/storage/table_index.py:123` | Core ingestion/index hot path is dense and hard to validate in small units | Not covered by original plan | None |
| P2 | Remove or formally deprecate dataset-mode embedding params that are intentionally ignored | `src/lenslet/server_factory.py:417` | Public API confusion: params exist but behavior unavailable in dataset mode | Not covered by original plan | None |

## Summary by Plan Coverage
- Covered later by original plan: 4 items
- Not covered by original plan: 5 items

## Notes on Plan Mapping
- The original plan still has explicit AppShell work in S4 `T14` and `T15`, so frontend AppShell simplifications above can be completed without changing plan scope.
- Remaining original sprints S5/S6 focus on `Inspector` and `MetricsPanel` domains; they do not currently include additional backend modularization for `server_sync.py`, `server_routes_common.py`, or `table_index.py`.
