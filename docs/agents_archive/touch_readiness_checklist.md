# Touch Readiness Checklist (Sprint S3)

Last updated: 2026-02-08

## Device Matrix

| Device Profile | Browser | Status | Notes |
|---|---|---|---|
| iPhone 12/13 class (390x844) | iOS Safari | Pending hardware validation | Manual run still required on physical iOS device. |
| Pixel 7 class (412x915) | Android Chrome | Pending hardware validation | Manual run still required on physical Android device. |

## Scenario Checklist

Use `Pass` / `Fail` / `N/A` in each browser column during manual execution.

| Scenario | iOS Safari | Android Chrome | Notes |
|---|---|---|---|
| Grid item actions reachable without right-click (long-press + action button) | Pending | Pending | Verify context menu anchor and close behavior. |
| Tap behavior in grid: first tap selects, second tap opens selected image | Pending | Pending | Validate no accidental open on first tap. |
| Mobile select mode toggle (`Select` / `Done`) works and supports multi-select | Pending | Pending | Validate move/delete actions from selected set. |
| Upload fallback via explicit file picker works | Pending | Pending | Validate read-only error message path as well. |
| Move-to flow works without drag-and-drop | Pending | Pending | Test single and multi-selection moves. |
| Viewer pan + pinch zoom remains stable under pointer cancel/interruption | Pending | Pending | Test pinch start/end and resume pan. |
| Viewer next/prev controls reachable at phone width (`<=480px`) | Pending | Pending | Validate both directions and disabled states. |
| Compare mode pan + pinch zoom still works | Pending | Pending | Ensure split handle remains draggable. |
| Menus/dropdowns remain in viewport at left/right/top/bottom edges | Pending | Pending | Check 390px and 768px widths. |
| Critical controls are near 44px touch targets on mobile/tablet | Pending | Pending | Spot-check toolbar, tree actions, sidebar icons. |

## Automated Verification (Completed)

| Command | Result |
|---|---|
| `cd frontend && npm run test` | Passed (15 files, 58 tests) |
| `cd frontend && npm run build` | Passed |
| `pytest -q` | Passed (58 tests) |

## Notes

- This repository environment does not provide direct iOS/Android hardware access, so physical-device checklist rows remain pending.
- Once hardware validation is complete, update this file with per-scenario pass/fail results and issue links for any failures.
