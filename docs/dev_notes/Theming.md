

# Minimal Theming (inspired by Eagle, but light enough to not kill performance)

Think of it as **“Eagle aesthetic diet edition.”** It gives you the *vibe* but doesn’t add heavy UI libraries or expensive rendering overhead.

### Layout

- **Dark neutral background** (hex `#1E1E1E` or `#121212`). Lighter dark for panels, slightly darker for canvas → subtle contrast.
- **3-pane layout**:
  - **Left Sidebar**: folder tree, slim, collapsible.
  - **Main**: grid (virtualized).
  - **Right Sidebar**: inspector (preview, tags, notes, EXIF, URL).

### Grid Styling

- **Thumb cells**:
  - Background: mid-dark gray (`#2A2A2A`).
  - Rounded corners: 8px.
  - Subtle shadow (`box-shadow: 0 1px 3px rgba(0,0,0,0.4)` for hover).
  - On hover: border highlight (`1px solid #3A8FFF`) + subtle scale transform (`transform: scale(1.02)`).
- **Image fit**: `object-fit: cover`, no stretching.
- **Aspect ratio placeholders**: use intrinsic sizes from manifest, fill space before load.

### Sidebar Styling

- **Left (folders)**:
  - Tree lines optional → use indentation only.
  - Active folder: highlighted row (`background: rgba(58,143,255,0.2)`), left accent stripe (`2px solid #3A8FFF`).
- **Right (inspector)**:
  - Panel background slightly lighter than grid background.
  - Section titles in small caps, muted gray (`#AAA`).
  - Inputs (tags/notes): flat dark fields, no borders, highlight on focus.

### Text & Icons

- **Font**: system UI font stack (San Francisco/Segoe/Roboto). Avoid custom fonts for perf.
- **Color**: high-contrast white (`#EEE`) on dark background, muted gray for secondary (`#AAA`).
- **Icons**: SVG inline, stroke-based, 1.5px line width, single muted-gray color until active.

### Transitions (cheap & smooth)

- **Hover effects**: use `transform: scale` and `opacity`, avoid animating `width/height/top/left`.
- **Inspector open/close**: `translateX` + opacity fade.
- **Theme toggles**: none for MVP. Stick to dark.

### Performance-friendly CSS tricks

- **`content-visibility: auto`** on grid items (prevents painting offscreen).
- **`contain-intrinsic-size`** for grid thumbs to prevent layout jumps.
- **GPU-friendly animations** (`transform`, `opacity` only).
- **Use CSS vars** for theme colors (easy expansion later).

------

### Color Palette (minimal)

- Background dark: `#1E1E1E`
- Panel dark: `#252525`
- Accent blue: `#3A8FFF`
- Hover gray: `#2A2A2A`
- Text primary: `#EEEEEE`
- Text secondary: `#AAAAAA`
- Border subtle: `rgba(255,255,255,0.08)`

------

This gets you an **Eagle-like dark workspace**: clean grid, dark chrome, blue accents — without loading Tailwind themes or animating shadows everywhere. It’s performant because:

- No reflow-heavy animations.
- No custom fonts.
- No expensive background blurs.
- Grid placeholders avoid layout shifts.