# Gallery bundle and cache audit

Scope: main gallery startup, using the better-code frontend performance guidance
and Jaku better-ui performance guidance. Ranking implementation is excluded.

## Finding and change

The gallery entry bundled React, React DOM, scheduler, and TanStack with changing
application code. Every gallery deployment invalidated these stable libraries.
The production graph contains no unexpectedly eager spreadsheet, charting, or
export dependency to remove. Inspector and Compare already have dynamic imports.

`frontend/vite.config.ts` now gives the eagerly used framework dependencies one
content-addressed `framework` chunk. Optional drag-and-drop dependencies remain in
the existing optional chunk. Vite emits modulepreload links for every static
chunk, so the new boundaries do not require serial dependency discovery.

This improves cache reuse after application updates. It does **not** claim a
cold-start speedup or change when any component mounts, initializes query demand,
restores persisted state, or paints.

## Controlled evidence

Measurements used one source snapshot in `/tmp/lenslet-bundle-snapshot`, built
three ways: existing configuration, framework grouping, then the same grouping
with an unrelated `main.tsx` DOM dataset assignment. Shared `frontend/dist` and
packaged assets were not overwritten. The snapshot includes concurrent
refinement work; compare these controlled builds to each other, not to an older
release's byte count.

| Static startup JavaScript | Existing | Framework grouping |
| --- | ---: | ---: |
| Raw bytes, full static import closure | 572,911 | 572,859 |
| Gzip bytes, Python gzip level 9 | 169,450 | 169,412 |
| Requests | 2 | 4 |
| Application entry raw bytes | 563,065 | 377,188 |
| Independently cacheable framework raw bytes | — | 192,869 |
| Independently cacheable framework gzip bytes | — | 59,969 |

The grouping adds two parallel requests. Cold compressed bytes are essentially
unchanged in this snapshot. About 60 kB compressed (35% of the static startup JS)
can survive an application-only deployment once immutable asset caching is
available. Cache reuse requires the same dependency versions and unchanged
framework exports; upgrades or new export usage may legitimately change the hash.

The unrelated app edit changed `index-Bgm0fJNB.js` to `index-Ci9qzvsA.js` while
`framework-A64fDfx-.js`, `rolldown-runtime-Bh1tDfsg.js`, and
`fetcher-DW3jrRUR.js` retained identical names and bytes. Framework imports only
the stable bundler runtime, not any application module.

## Browser and type validation

A fresh Chromium context loaded each controlled build over the existing synthetic
18-image demo using Playwright static-asset interception. Both rendered 18 grid
cells with zero page errors. In the grouped build, the entry, runtime, framework,
and fetcher requests began at 9.2, 9.3, 9.3, and 9.5 ms respectively. Health began
after module execution at 58.9 ms; there was no added dependency-discovery
waterfall. These local timings verify request ordering, not a network speed claim.

`npx tsc --noEmit` passed. Full integrated browser acceptance remains the main
session's final gate after all changes are assembled and packaged assets rebuilt.

Raw diagnostics for this run are `/tmp/lenslet-bundle-controlled.json`,
`/tmp/lenslet-bundle-browser.json`, and `/tmp/lenslet-bundle-measure.mjs`.

## Deliberately deferred

- Lazily mounting Metrics/Derived would conflict with existing hidden-but-mounted
  draft, query demand, and persisted presentation ownership. Their combined
  footprint is worth future investigation only with explicit continuity tests.
- Viewer/Similarity code splitting trades relatively modest byte savings for a
  cold-open fetch. No measured interaction benefit justifies that change here.
- React/vendor chunking is not a substitute for the measured tree/grid work in
  the performance audit. Most first-visit JavaScript still executes.
