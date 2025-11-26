# Frontend Overhaul Plan

## 1. Polish Left Navigation (FolderTree)

- **Problem**: "Padding too loose, default space too narrow." Truncation is arbitrary.
- **Fix**:
    - **Compact Layout**: Reduce item padding (`py-2` -> `py-0.5` or `py-1`) for higher information density.
    - **Sizing**: Increase default sidebar width (160px -> 250px) and min-width.
    - **Typography**: Use `text-sm` (13px) and consistent colors.
    - **Truncation**: Remove `middleTruncate`; use CSS `truncate` (ellipsis) to fill available width.
    - **Visuals**: Improve hover states (full width rounded), explicit drop targets, and clear resize handle.

## 2. Add Thumbnail Size Control

- **Problem**: Thumbnail size is hardcoded to `220px`.
- **Fix**:
    - **AppShell**: Add `gridItemSize` state (range 80px - 500px), persisted in `localStorage`.
    - **Toolbar**: Add a slider to control `gridItemSize` (visible when Viewer is not active).
    - **VirtualGrid**: Accept `targetCellSize` prop and use it to calculate columns/layout dynamically.

## 3. General UI Polish (Whimsical & Performant)

- **Problem**: "Messy" text sizes, inconsistent heights, lack of polish.
- **Fix**:
    - **Toolbar Standardization**: 
        - Enforce `h-8` (32px) for all controls (buttons, inputs, selects).
        - Layout: [View Mode | Size Slider] ... [Sort | Filter] ... [Search].
        - **Whimsical Touches**: Subtle transitions (`transition-all duration-200`), nice active/hover states (`active:scale-95`), refined borders/shadows.
    - **Typography**: Consistent `text-sm` throughout the UI chrome.
    - **Performance**: Ensure purely CSS-based layout changes where possible to avoid thrashing.

## 4. Implementation Details

- **Files to Edit**:
    - `frontend/src/app/layout/useSidebars.ts`: Update default/min widths.
    - `frontend/src/app/AppShell.tsx`: State management for grid size.
    - `frontend/src/features/folders/FolderTree.tsx`: Density and truncation fixes.
    - `frontend/src/features/browse/components/VirtualGrid.tsx`: Dynamic sizing support.
    - `frontend/src/shared/ui/Toolbar.tsx`: UI overhaul, new slider, standardized heights.
    - `frontend/src/styles.css`: Tweaks for scrollbars and sliders.

This aligns with "minimal, fast, boring" by keeping the tech stack simple but elevating the "feel" through precise CSS and interaction design.


---


current UI. (looks better now! but still it feels a bit amateur / less polished)
reference UI. (I want the feel of this one).

can you make changes to further polish the feel overall, and match the usability of p2. 

---

current UI. reference (changed to a new theme to match current website).

- sidebar does look MUCH better, but I think the second image has better readabilty for text.
- "root" root folder on display is not necessary as all folders will be under root anyways and this introduces extra padding and reduces available width.
- filename should still be displayed instead of hidden (that was an oversight). the reference app had an option to toggle on / off but for now website just have them on by default is good enough.
- after the change, the "selection" box is not clear enough so it might confuse what got selected and what did not. revert the selection box to the old way (its not great but it worked, and its tricky to get it right better).
- remove the bottom bar "x selected" because right bar will have that info anyways.
- remove the top "address bar" as we can just infer from the current url anyways too. (just comment out, we might need that later).
- overall: the proportion of the things (spacings, UI elements, text, etc) still feel kind of off-balance so maybe you could further polish it on that.