# Lenslet UI Theme Variants

This document records the different UI themes we've explored and applied to Lenslet, so we can easily revert or iterate on them in the future.

These values map directly to the CSS custom properties in `frontend/src/theme.css`.

## 1. Original (Warm Blue)
The baseline theme. It has a slightly warm, brownish tint to the background and borders, paired with a standard bright blue accent.

```css
  /* Core backgrounds */
  --bg: #0e0d0b;
  --panel: #181613;
  --hover: #23211e;
  --border: #2b2924;
  
  /* Elevated surfaces */
  --surface: #1c1a17;
  --surface-hover: #25231f;
  --surface-active: #2e2b26;
  --surface-overlay: #131210;
  --surface-inset: #0f0e0c;
  
  /* Text colors */
  --text: #e9e5df;
  --text-secondary: #d3cec6;
  --muted: #918b82;

  /* Accent colors */
  --accent: #3b82f6;
  --accent-hover: #5a9bff;
  --accent-muted: rgba(59, 130, 246, 0.18);
  --accent-strong: rgba(59, 130, 246, 0.32);

  /* Subtle warmth */
  --bg-gradient: radial-gradient(1200px 600px at 10% -10%, rgba(255, 175, 110, 0.05), transparent 60%),
    radial-gradient(900px 500px at 100% -20%, rgba(59, 130, 246, 0.08), transparent 55%),
    var(--bg);
```

---

## 2. Teal (Warm background, Teal accent)
Same warm brownish base as the original, but the accent is swapped to a teal hue.

```css
  /* Core backgrounds & Text match Original */

  /* Accent colors (Teal) */
  --accent: #2dd4bf;
  --accent-hover: #5eead4;
  --accent-muted: rgba(45, 212, 191, 0.18);
  --accent-strong: rgba(45, 212, 191, 0.32);

  /* Subtle warmth */
  --bg-gradient: radial-gradient(1200px 600px at 10% -10%, rgba(255, 175, 110, 0.05), transparent 60%),
    radial-gradient(900px 500px at 100% -20%, rgba(45, 212, 191, 0.08), transparent 55%),
    var(--bg);
```

---

## 3. Charcoal Enterprise
A conservative, formal dark theme with blue-leaning grey surfaces and a soft, restrained blue accent. Adapted from the `charcoal-enterprise` preset.

```css
  /* Core backgrounds */
  --bg: #111215;
  --panel: #181b20;
  --hover: #20252d;
  --border: #3a434f;
  
  /* Elevated surfaces */
  --surface: #20252d;
  --surface-hover: #2a313c;
  --surface-active: #323b47;
  --surface-overlay: rgba(24, 27, 32, 0.95);
  --surface-inset: #0e0f12;
  
  /* Text colors */
  --text: #f1f5f9;
  --text-secondary: #cbd5e1;
  --muted: #94a3b8;
  
  /* Accent colors (Charcoal Enterprise Blue) */
  --accent: #86b7ff;
  --accent-hover: #a5cbff;
  --accent-muted: rgba(134, 183, 255, 0.18);
  --accent-strong: rgba(134, 183, 255, 0.32);

  /* Border variants */
  --border-subtle: rgba(255, 255, 255, 0.06);
  --border-strong: #556275;
  --border-hover: #67778c;

  /* Subtle warmth */
  --bg-gradient: radial-gradient(1200px 600px at 10% -10%, rgba(255, 175, 110, 0.04), transparent 60%),
    radial-gradient(900px 500px at 100% -20%, rgba(134, 183, 255, 0.06), transparent 55%),
    var(--bg);
```

---

## 4. Monochrome Utility
A highly neutral, pure dark-grey theme that minimizes color distraction. Adapted from the `monochrome-utility` preset.

```css
  /* Core backgrounds */
  --bg: #0f0f10;
  --panel: #17181a;
  --hover: #212327;
  --border: #3a3e47;
  
  /* Elevated surfaces */
  --surface: #212327;
  --surface-hover: #2b2f35;
  --surface-active: #32373e;
  --surface-overlay: rgba(23, 24, 26, 0.95);
  --surface-inset: #0a0a0b;
  
  /* Text colors */
  --text: #f1f2f4;
  --text-secondary: #d0d4da;
  --muted: #a7adb8;
  
  /* Accent colors (Muted Slate Blue) */
  --accent: #9cb2d5;
  --accent-hover: #b5c6e3;
  --accent-muted: rgba(156, 178, 213, 0.18);
  --accent-strong: rgba(156, 178, 213, 0.32);

  /* Border variants */
  --border-subtle: rgba(255, 255, 255, 0.04);
  --border-strong: #525865;
  --border-hover: #6a7182;

  /* Subtle warmth */
  --bg-gradient: radial-gradient(1200px 600px at 10% -10%, rgba(255, 255, 255, 0.02), transparent 60%),
    radial-gradient(900px 500px at 100% -20%, rgba(156, 178, 213, 0.04), transparent 55%),
    var(--bg);
```

---

## 5. Monochrome Indigo (Current)
Retains the highly neutral grey foundations of Monochrome Utility, but swaps the accent color for a vibrant cool violet/indigo to make interactive elements pop.

```css
  /* Core backgrounds & Text match Monochrome Utility */
  
  /* Accent colors (Cool violet/indigo) */
  --accent: #7B6EF6;
  --accent-hover: #8A7DF8;
  --accent-muted: rgba(123, 110, 246, 0.18);
  --accent-strong: rgba(123, 110, 246, 0.32);

  /* Subtle warmth */
  --bg-gradient: radial-gradient(1200px 600px at 10% -10%, rgba(255, 255, 255, 0.02), transparent 60%),
    radial-gradient(900px 500px at 100% -20%, rgba(123, 110, 246, 0.05), transparent 55%),
    var(--bg);
```

---

### Shared Semantic Colors
In newer themes (Monochrome and Monochrome Indigo), we shifted away from the original generic semantic colors to more disciplined status colors:

```css
  /* Newer Semantic colors */
  --danger: #ff6d73;
  --success: #35c88a;
  --warning: #f0b660;
  --info: #55b8ff;
```
