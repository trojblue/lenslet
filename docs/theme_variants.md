# Lenslet Browse Theme Presets

Lenslet currently ships three browse-mode theme presets. Runtime tokens live in `frontend/src/theme/runtime.ts` and are applied via CSS custom properties on `<html data-lenslet-theme="...">`.

## Shipped Presets

### 1. Original (`default`)

Baseline warm dark palette with blue accent (`--accent: #3b82f6`). This is the default when no workspace theme has been saved.

### 2. Teal (`teal`)

Original warm base surfaces with teal accent (`--accent: #2dd4bf`).

### 3. Charcoal (`charcoal`)

Cooler charcoal surfaces with soft blue accent (`--accent: #86b7ff`).

## Workspace Persistence Behavior

Theme selection is scoped per browse workspace and stored in localStorage under hashed keys:

- Key shape: `lenslet.v2.theme.<64-bit-hex-hash>`
- Seed source: backend-provided opaque `workspace_id` when available
- Fallback seed: deterministic `mode + location` scope when `workspace_id` is absent
- Raw workspace paths are never written to storage keys

## Favicon Behavior

The active theme also updates the browser tab favicon color:

- Runtime injects/updates a dynamic SVG favicon link tagged with `data-lenslet-dynamic-favicon="1"`
- Favicon fill uses the active preset accent (`--accent`)
- Updates are idempotent (re-applying the same theme keeps one dynamic favicon link)
- Static `.ico` remains available as baseline fallback in the HTML shell
