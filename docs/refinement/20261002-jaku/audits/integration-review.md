# Independent integration review

Scope: main-gallery refinement from `122df55`, including committed cache changes and responsive/modal/folder implementations. Final verdict: no unresolved confirmed findings. Earlier sections preserve chronological review checkpoints; the final resolution below supersedes their pending status. Source files are actively changing; no transient compile failures are treated as final findings. Review uses the Code Review skill and canonical `docs/DESIGN_SYSTEM.md`.

## Actionable integration findings

### Medium — modal ownership excludes existing utility menus

At this checkpoint, `frontend/src/shared/hooks/modalFocusScope.ts:6-16` discovers owned portals only through expanded `aria-controls` relationships. The new responsive Browse sheet contains triggers for two existing menus without that relationship:

- Folder actions: `frontend/src/features/folders/FolderTreeRows.tsx:130-134` invokes the app context menu rendered outside the sheet by `frontend/src/app/AppShell.tsx` (near line 1897). The action trigger has `aria-haspopup` but no controls relationship.
- Settings: `frontend/src/shared/ui/ThemeSettingsMenu.tsx` portals its panel directly to `document.body`; the trigger has `aria-expanded` but no `aria-controls`, and the panel lacks an ID.

`refreshInert` therefore marks these panels (or an ancestor) inert. Users can open the menus from the phone Browse sheet but cannot operate their controls. Explicitly associate each menu with its triggering modal scope; validate both click actions and keyboard/Escape ownership. Reported to root and accessibility owner before final implementation.

### Medium — sibling dismiss backdrop initially becomes inert

Initial `ResponsivePanel.tsx` registered the inner surface, excluding its sibling backdrop. The shared inert traversal marked the backdrop inert, preventing its dismiss click. Root independently identified this earlier; layout/accessibility owners are already correcting the registration boundary. Similarity currently registers its outer overlay and does not have this issue. Keep a real click validation for responsive backdrop dismissal.

## Reviewed without actionable findings

- Cache commit `a6b2b9d`: request identity guards protect both writes and cleanup; clear/cancel/prefix eviction detach ownership before invoking abort callbacks; prefetch errors remain real errors for foreground joiners. Independent targeted rerun passed 23 tests across `blobCache.test.ts` and `client.prefetch.test.ts`.
- Foundational responsive retention approach: one mounted child tree remains under a stable wrapper; overlay intent is separate from persisted inline preferences. Final browser verification remains required.

## Pending final review

Folder virtualization and retained observer ownership are still evolving. Final integration review must inspect settled changes and exercise modal-owned Dropdown, Settings and folder context menu paths, responsive state retention, source reset and offscreen keyboard traversal. The review does not establish full browser acceptance or performance improvement by itself.

## Second source checkpoint

- The modal owner now includes the backdrop; Settings has an ID/controls relationship; ContextMenu registers its own specific surface with the current modal. These changes address the first checkpoint's ownership findings. No other caller of the popup registration was found; unrelated background interactions remain inert. Runtime validation is still pending.
- **Medium, fixed during review:** Inspector sheet used z-index 120 while Find Similar opened a z-index 60 modal without closing the sheet (`AppShell.tsx` Find Similar callback). The visible sheet could obscure the new dialog. Layout owner now closes the sheet before opening Similarity, matching the Compare path. Packaged runtime confirmation remains pending.
- **Performance/resource finding under correction:** `useFolderTreeData.ts` retains every demanded path in an ever-growing Set and keeps both folder/count query observers for all of them. Collapsing branches never permits those query payloads to be garbage collected; a long session can accumulate thousands of disabled observers. Folder owner acknowledged the issue and is working on bounded observer ownership plus a hard-scope reset. This does not negate the measured initial DOM reduction, but must not become an unbounded-session tradeoff.
- Count refresh now invalidates the shared count query key rather than changing its identity, preserving settled counts during refresh. No new count-refresh regression found in that revision.

## Final source pass (before packaged build 4)

Reviewed the complete non-generated source diff against `122df55`, including delivery caching, histogram bounds, facet recovery, controlled desktop/mobile search, shared keyboard menus, Similarity form behavior, Inspector metadata accessibility, theme changes and responsive pane wiring.

Previously reported ownership and nested-overlay findings are corrected. Folder observers now cover roots, expanded paths and current path rather than every previously visited path; tree-owned settled records retire on workspace/source reset. Count queries use shared identity and invalidation. No additional actionable issue found in those changes.

One targeted validation question remains with the folder owner: an expanded folder request completing while the tree is hidden changes the logical row-array identity. The retained virtual window currently requires an identical row array, so the first re-exposed frame needs explicit validation under this hidden-completion case, beyond a settled hide/show trace. This is a review hypothesis until reproduced, not a confirmed failing gate.

## Independent packaged modal verification

Build 4 passed an independent Playwright run on a fresh synthetic fixture and isolated server at a 390px phone viewport:

- Settings keyboard entry, active modal ownership, Escape trigger restoration, and Tab dismissal remaining inside the sheet.
- Folder context-menu ownership, Tab dismissal, Escape trigger restoration, and parent sheet persistence.
- Sheet Escape returns focus to its toolbar trigger.
- Inspector Find Similar closes the sheet before showing the modal; its close button is unobscured.
- The embedding Dropdown accepts input inside its portal; the first Escape closes the Dropdown and the second closes Similarity.
- No visible inert elements remain after modal closure.

Raw independent evidence: `/tmp/jaku-review-final.json`; reproduction: `/tmp/jaku-review-final.py`. The isolated server was stopped by its harness. The final source review has no unresolved confirmed findings; the folder hidden-completion hypothesis remains under the performance owner's focused validation.


## Final resolution — packaged build 5

The hidden-completion question is resolved. The folder implementation now preserves nonzero viewport and row measurements while hidden, synchronously remeasures on activation, and attaches the virtualizer to the actual callback-ref scroll node. It no longer relies on equality with a cached row-array identity.

The performance owner's final packaged folder gate passed twice. Its delayed-request telemetry verifies that an unvisited folder request completes while Metrics is visible; all 12 earliest return frames retain a nonempty settled folder presentation. The settled hide/show trace also passed across 12 frames, including row text, actions and scroll. The durable [performance evidence](../evidence/performance.json) records both passes, 29 mounted rows, full-model End navigation to `/folder_09999`, and no page errors.

The main session reports the final full browser acceptance and Inspector, toolbar, grid and Metrics continuity gates passing, along with 719 frontend tests. These broader results were coordinated by the main session; this reviewer independently ran the 23 cache tests and the packaged build 4 modal checks described above. No heavy validation was repeated during this documentation closeout.

**Final review verdict: no unresolved confirmed correctness or performance regressions found in the reviewed scope.** All actionable integration findings raised here were addressed. Browser evidence uses synthetic fixtures and Chromium on one host; it is not exhaustive cross-browser/device coverage or a guarantee for every dataset. The timing measurements and their warm/cold conditions remain those documented in the performance evidence.
