# Refinement browser regression gate

Issue-specific product fixes precede this probe. `scripts/browser/refinement.py` is a focused integration gate, not a reorganization of the existing smoke harness.

| Existing root cause | Expected issue reduction | Observable browser contract |
| --- | --- | --- |
| Shared controls suppress focus outlines | Keyboard users lose position on search and sizing controls | Actual Tab navigation exposes a visible focus treatment; arrow sizing updates its value |
| Metadata keys are pointer-only copy targets and large values cannot receive scroll focus | Keyboard users cannot copy values or scroll metadata regions | Named copy buttons work with Enter and clipboard result matches value; metadata region is keyboard reachable |
| Narrow viewport keeps large inline panes competing with gallery space | Folders/Inspector become unusable on 320/390px screens | Named pane controls reveal usable in-viewport sheets with unobscured actions; hiding/revealing retains draft and disclosure state from the first visible painted frame |
| Compare divider depends on pointer drag | Keyboard users cannot adjust comparison | Slider arrow/Home/End update split without changing image identity |
| Modal focus scope excludes owned dropdown portals | Keyboard selection/Escape can close the wrong layer or move behind modal | First Escape closes dropdown only, second closes modal, returning focus to trigger |
| Numeric facet errors have no local retry action | A transient error forces unrelated navigation to recover | Actual Retry values produces a new successful facet request while selected metric, Derived draft, and card geometry remain stable across painted frames |
| Desktop/mobile search inputs own independent drafts | Resizing shows an empty search box while the gallery remains filtered | Desktop input value survives phone breakpoint, hide/show, and desktop return |
| Theme changes trigger cosmetic transitions across controls | Theme switching smears old and new palettes | Theme mutation has no running color/background/border/shadow transitions |

Validation after rebuilding and mirroring assets:

`python -m scripts.browser.refinement --output-dir /tmp/lenslet-refinement`

The gate uses synthetic fixture images and writes compact JSON plus diagnostic screenshots. Existing GUI smoke and painted-frame continuity suites remain separate required integration gates. Full media-navigation continuity is not inferred from this focused probe.

`--scenario metrics` launches the table fixture alone; `--scenario desktop|mobile320|mobile390` isolates the other checks. With no flags, the probe uses a gallery server followed by a dedicated 1,585-row table server so local row completeness cannot mask facet failures. `--base-url` uses an existing matching synthetic fixture server; pair it with `--scenario metrics` for a table server.

## Final integration result

Passed against integration build 3 on 2026-10-02, with expanded phone menu keyboard checks also passing against build 4. Compact evidence is in `../evidence/refinement-browser.json`; full frame samples and screenshots are under `/tmp/lenslet-refinement-build3-final`.

- Native Tab navigation reaches search, thumbnail sizing, metadata region, metadata key buttons, and Compare's divider with visible focus. Enter on the nested `prompt` key copies `beta prompt` through the browser clipboard.
- Three actual theme changes cover 36 painted frames without palette-property transitions, and regular button transitions return afterward.
- Compare Home/Arrow/Shift+Arrow/End adjustments preserve the presented image pair. Similarity's portaled embedding search retains focus; Escape closes one layer at a time and restores the trigger.
- At 320px and 390px, Browse and Inspector are usable sheets. Primary toolbar hitboxes meet 24px minimum, their centers are unobscured, and their rectangles do not overlap. Root folder JSON export completes through the actual portaled menu.
- Each phone Inspector reveal checks eight frames beginning with the earliest visible paint: genuinely unsaved notes (save requests held and backend state independently checked), a closed/inert disclosure, fixed decoded image source/pixels/opacity, and in-viewport geometry all remain correct. A two-level pixel tolerance covers thumbnail codec conversion against the original synthetic color; every captured frame must still match the first frame exactly.
- Phone Settings and folder menus accept keyboard entry; menu focus, Home/End, Tab continuation, scoped Escape, and trigger restoration work without dismissing the underlying sheet prematurely.
- Desktop search survives phone resizing, closing/reopening search, and desktop return.
- The cold metric failure probe returns HTTP 503 for `zz_probe_metric_29`, then the actual Retry values action creates a new request and restores population 1,585. Twenty-four captured frames retain the selected metric and Derived draft, with zero card-height delta.

The original build-1 phone folder menu failure was reproduced before the portal ownership correction: a visible menu item could not receive a pointer click because the folder sheet intercepted it. The final probe uses no forced click to bypass that failure.

Validation: `python -m ruff check scripts/browser/refinement.py`, Python compilation, and `git diff --check` passed. Existing broad acceptance and continuity gates remain the main session's responsibility.

Build-4 phone menu evidence: `/tmp/lenslet-refinement-build4-mobile320` and `/tmp/lenslet-refinement-build4-mobile390`. Use distinct `--port` values when running fixture servers concurrently.
