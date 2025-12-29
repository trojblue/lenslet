# Issues



**Drag-and-drop leaks internal paths**

- You’re exposing file paths via `dataTransfer.setData('text/plain', …)`.
- 🔥 If a user drags onto another website, that site gets your internal paths.
- **Fix:** remove the `text/plain` line. Keep only your custom MIME types.

**Untrusted URL hash → folder selection**

- You directly trust `window.location.hash` for folder paths.
- An attacker could craft a huge or weird hash to spam your backend.
- **Fix:** sanitize on the client (allow `/[a-zA-Z0-9._\-/]`, max length ~512).

**Blob URL memory leaks**

- You create many `URL.createObjectURL` references but don’t always `revokeObjectURL`.
- Attackers can flood memory with repeated loads.
- **Fix:** centralize blob handling with a hook that auto-revokes on change/unmount.

**Missing CSP / clickjacking headers (backend responsibility, but FE relies on it)**

- Without CSP, a future `dangerouslySetInnerHTML` = instant XSS.
- Without `X-Frame-Options` / `frame-ancestors`, your UI can be clickjacked.
- **Fix:** add CSP + `frame-ancestors 'none'` headers from backend.



------

# Fix Plan (overview)

1. **Drag-and-drop path leak**
   - Remove all `text/*` payloads. Use a single **app-scoped** custom MIME: `application/x-lenslet-paths` (JSON array).
   - Update both producer (Grid) and consumers (Tree) accordingly.
2. **Untrusted `window.location.hash`**
   - Sanitize before use: allow only `/[a-zA-Z0-9._\-/]`, collapse `//`, cap at 512 chars.
   - Apply on initial load and on `hashchange`.
   - When writing a hash, write only the sanitized form.
3. **Blob URL lifetime (memory leaks)**
   - Centralize preview URL revocation in `Grid`.
   - Add a tiny LRU for thumbnail blob URLs in `Thumb` with revocation on eviction.
   - Add defensive “revoke on change/unmount” guards in `Viewer` and `Inspector`.
4. **CSP + clickjacking** (backend)
   - Set a strict but practical CSP and deny framing via `frame-ancestors 'none'` (and `X-Frame-Options: DENY` for legacy).
   - Keep it data-driven for `connect-src` (self + optional API origin), no wrappers, simple middleware.

------

## 1) Drag-and-drop path leak

### `components/Grid.tsx` — remove text/plain and text/* payloads

**Before** (excerpt):

```ts
e.dataTransfer?.setData('application/x-lenslet-paths', JSON.stringify(paths))
e.dataTransfer?.setData('text/lenslet-path', paths[0])
e.dataTransfer?.setData('text/plain', paths.join('\n'))
```

**After**:

```ts
e.dataTransfer?.setData('application/x-lenslet-paths', JSON.stringify(paths))
if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove'
```

No other types. This prevents other sites from trivially reading your internal paths via `text/plain` (or any `text/*`).

### `components/FolderTree.tsx` — only accept your custom type

**Before** (multiple places):

```ts
const types = Array.from(e.dataTransfer?.types || [])
if (types.includes('text/lenslet-path') || types.includes('application/x-lenslet-paths')) { ... }
```

**After**:

```ts
const types = Array.from(e.dataTransfer?.types || [])
if (types.includes('application/x-lenslet-paths')) { ... }
```

**Before** (drop handler):

```ts
const multi = dt.getData('application/x-lenslet-paths')
const paths: string[] = multi ? JSON.parse(multi) : [dt.getData('text/lenslet-path') || dt.getData('text/plain')]
```

**After**:

```ts
const multi = dt.getData('application/x-lenslet-paths')
const paths: string[] = multi ? JSON.parse(multi) : []
```

That’s it. One MIME, one code path.

------

## 2) Sanitize URL hash → folder selection

### `App.tsx` — add sanitizer and apply everywhere you read/write the hash

Add near top-level of `App.tsx` (above component bodies is fine):

```ts
const ALLOWED_PATH = /^[\/a-zA-Z0-9._\-\/]{1,512}$/;

// Normalize, validate, and cap length. Falls back to '/'.
function sanitizePath(raw: string | null | undefined): string {
  try {
    const decoded = decodeURI(raw || '')
    const withLeading = decoded.startsWith('/') ? decoded : `/${decoded}`
    const squashed = withLeading.replace(/\/{2,}/g, '/')
    if (!ALLOWED_PATH.test(squashed)) return '/'
    return squashed
  } catch {
    return '/'
  }
}
```

**Initialize from hash (was trusting raw):**

```diff
-  useEffect(() => {
-    try {
-      const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
-      const initial = raw ? decodeURI(raw) : '/'
-      if (initial && typeof initial === 'string') setCurrent(initial.startsWith('/') ? initial : `/${initial}`)
-    } catch {}
+  useEffect(() => {
+    try {
+      const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
+      const initial = sanitizePath(raw)
+      setCurrent(initial)
+    } catch {}
```

**On hashchange:**

```diff
-    const onHash = () => {
-      try {
-        const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
-        const next = raw ? decodeURI(raw) : '/'
-        const norm = next.startsWith('/') ? next : `/${next}`
-        setViewer(null)
-        setCurrent(prev => (prev === norm ? prev : norm))
-      } catch {}
-    }
+    const onHash = () => {
+      try {
+        const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
+        const norm = sanitizePath(raw)
+        setViewer(null)
+        setCurrent(prev => (prev === norm ? prev : norm))
+      } catch {}
+    }
```

**When writing the hash (navigation):**

```diff
  const openFolder = (p: string) => {
    setViewer(null)
-    setCurrent(p)
+    const safe = sanitizePath(p)
+    setCurrent(safe)
    try {
-      const nextHash = `#${encodeURI(p)}`
+      const nextHash = `#${encodeURI(safe)}`
      if (window.location.hash !== nextHash) window.location.hash = nextHash
    } catch {}
  }
```

This blocks weird/huge hashes from ever hitting the backend.

------

## 3) Blob URL lifetime

### A) `components/Grid.tsx` — revoke preview object URLs

At top of component:

```ts
const previewUrlRef = React.useRef<string | null>(null)
React.useEffect(() => () => {
  if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} }
}, [])
```

When creating the preview URL (inside the 🔍 hover handlers):

```diff
- const blob = await api.getFile(it.path)
- setPreviewUrl(URL.createObjectURL(blob))
+ const blob = await api.getFile(it.path)
+ const u = URL.createObjectURL(blob)
+ if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} }
+ previewUrlRef.current = u
+ setPreviewUrl(u)
```

On mouse leave (and anywhere you clear it):

```diff
- onMouseLeave={()=>{ if (hoverTimer) window.clearTimeout(hoverTimer); setHoverTimer(null); setPreviewFor(null); setPreviewUrl(null) }}
+ onMouseLeave={()=>{
+   if (hoverTimer) window.clearTimeout(hoverTimer)
+   setHoverTimer(null)
+   setPreviewFor(null)
+   if (previewUrlRef.current) { try { URL.revokeObjectURL(previewUrlRef.current) } catch {} ; previewUrlRef.current = null }
+   setPreviewUrl(null)
+}}
```

### B) `components/Thumb.tsx` — small LRU with revocation on eviction

Replace the top of the file with this minimal cache:

```ts
const blobUrlCache = new Map<string, string>()
const order: string[] = []
const MAX_BLOBS = 400  // ~400 thumbs; tune as needed

function remember(key: string, url: string) {
  blobUrlCache.set(key, url)
  order.push(key)
  if (order.length > MAX_BLOBS) {
    const old = order.shift()
    if (old) {
      const u = blobUrlCache.get(old)
      if (u) { try { URL.revokeObjectURL(u) } catch {} }
      blobUrlCache.delete(old)
    }
  }
}

// Defensive: clear all on unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    for (const u of blobUrlCache.values()) { try { URL.revokeObjectURL(u) } catch {} }
    blobUrlCache.clear()
  }, { once: true })
}
```

Then, where the URL is created:

```diff
- const u = URL.createObjectURL(b); blobUrlCache.set(path, u); setUrl(u)
+ const u = URL.createObjectURL(b); remember(path, u); setUrl(u)
```

This keeps memory bounded without adding a global wrapper or dependency.

### C) `components/Inspector.tsx` — ensure revoke on unmount

Add a cleanup tied to `thumbUrl`:

```ts
useEffect(() => {
  return () => { if (thumbUrl) { try { URL.revokeObjectURL(thumbUrl) } catch {} } }
}, [thumbUrl])
```

(You already revoke on change; this covers the unmount path.)

### D) `components/Viewer.tsx` — belt-and-suspenders revoke

Add:

```ts
useEffect(() => {
  return () => { if (url) { try { URL.revokeObjectURL(url) } catch {} } }
}, [url])
```

You do revoke on path-change cleanup; this makes it robust against timing.

------

## 4) CSP + clickjacking (backend)

Assuming FastAPI (as per guide). Add one simple middleware module (e.g., `server/security_headers.py`) and include it in app startup. No heavy libs.

```py
# server/security_headers.py
import os
from urllib.parse import urlparse
from starlette.types import ASGIApp, Receive, Scope, Send

def _connect_src():
    base = os.getenv("API_BASE", "")  # align with VITE_API_BASE if cross-origin
    origins = ["'self'"]
    if base:
        u = urlparse(base)
        if u.scheme and u.netloc:
            origins.append(f"{u.scheme}://{u.netloc}")
    return " ".join(origins)

CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "img-src 'self' blob: data:; "
    "media-src 'self' blob:; "
    "font-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    f"connect-src {_connect_src()}; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "upgrade-insecure-requests"
)

class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = message.setdefault("headers", [])
                    def add(name: str, value: str):
                        headers.append((name.encode("latin-1"), value.encode("latin-1")))
                    add("content-security-policy", CSP)
                    add("x-frame-options", "DENY")  # legacy defense-in-depth
                    add("referrer-policy", "no-referrer")
                    add("x-content-type-options", "nosniff")
                    add("cross-origin-opener-policy", "same-origin")
                    # Add HSTS if you terminate TLS here. Be careful in dev.
                    if os.getenv("ENABLE_HSTS", "0") == "1":
                        add("strict-transport-security", "max-age=31536000; includeSubDomains; preload")
                await send(message)
            await self.app(scope, receive, send_wrapper)
```

Wire it up (where you create the FastAPI app):

```py
from fastapi import FastAPI
from server.security_headers import SecurityHeadersMiddleware

app = FastAPI()
app.add_middleware(SecurityHeadersMiddleware)
```

Notes:

- `style-src 'unsafe-inline'` keeps Vite/CSS simple. If you later hash CSS, you can tighten it.
- `connect-src` includes `self` and an optional `API_BASE` origin so your FE can talk to the backend when not same-origin.
- `frame-ancestors 'none'` + `X-Frame-Options: DENY` prevents clickjacking.

------

# Validation & Tests (lightweight)

- **Unit (TS):** Add tests for `sanitizePath` (valid paths, `//` squashing, too long, weird unicode, `..`, query/fragment noise).
   *Example cases:* `"/a/b" → "/a/b"`, `"a//b" → "/a/b"`, `"//x"` → "/x"`, `"../x"` → "/"`, `"#/x"` → "/"`, `"a"*600 → "/"`.
- **Manual Smoke:**
  1. Open app with `#/%2Fweird//path??#more` → lands at `/weird/path` or `/` (if invalid).
  2. Drag selection from grid to tree: moves correctly. Open a random site in another tab, attempt to paste → internal paths aren’t present.
  3. Open viewer; spin mouse-wheel zoom; navigate a few images; close viewer; watch Performance Memory tab for no unbounded growth.
  4. Hover 🔍 preview repeatedly across many items; memory should stabilize (no monotonic blob growth).
  5. Load app in an iframe (same origin) → request blocked by `frame-ancestors`.
- **Backend:** Hit any endpoint, confirm response headers contain CSP, XFO, etc.

------

# Rollout

- Ship FE changes behind a single PR (~<200 LOC net).
- Deploy backend headers with a toggle (`ENABLE_HSTS=0` in dev; `1` in prod if you terminate TLS).
- Watch error logs for CSP violations (`report-uri` can be added later if you want).

------

# Rationale (tie-back to risks)

- **DND leakage:** removing `text/plain` (and any `text/*`) closes the easy exfil path when users drag into hostile pages. Keeping only `application/x-lenslet-paths` is both sufficient and private.
- **Hash input:** strict allow-list + length cap prevents path-shaped payloads from becoming backend amplification/spam vectors.
- **Blob URLs:** object URLs are process-global; without revocation, repeated use is an unbounded leak. The tiny LRU + targeted revokes fixes this with <40 lines.
- **CSP & framing:** future slip-ups (e.g., `dangerouslySetInnerHTML`) won’t instantly become RCE/XSS, and the UI can’t be clickjacked.

