# PageSpeed Insights Report (Lighthouse)

Captured at **Feb 13, 2026, 12:20 PM EST**  
Environment: **Emulated Moto G Power**, **Lighthouse 13.0.1**  
Session: **Single page session**, **Initial page load**  
Network: **Slow 4G throttling**  
Runtime: **HeadlessChromium 144.0.7559.132**

---

## Summary Deltas (as recorded)
- **FCP:** +7  
- **LCP:** +0  
- **TBT:** +30  
- **CLS:** +25  
- **SI:** +0  

---

## Performance
Values are estimated and may vary. The performance score is calculated directly from these metrics (per PSI/Lighthouse).

Performance score bands:
- **0–49**
- **50–89**
- **90–100**

---

## Metrics

### First Contentful Paint (FCP)
**2.6 s**  
First Contentful Paint marks the time at which the first text or image is painted.

### Largest Contentful Paint (LCP)
**8.6 s**  
Largest Contentful Paint marks the time at which the largest text or image is painted.

### Total Blocking Time (TBT)
**0 ms**  
Sum of all time periods between FCP and Time to Interactive where task length exceeded 50 ms.

### Cumulative Layout Shift (CLS)
**0**  
Measures the movement of visible elements within the viewport.

### Speed Index (SI)
**17.9 s**  
Shows how quickly the contents of a page are visibly populated.

---

## Audits / Insights

### Render blocking requests (Estimated savings: **1,150 ms**)
Requests are blocking the page's initial render, which may delay LCP. Deferring or inlining can move these requests out of the critical path.

| URL / Resource | Party | Transfer Size | Duration |
|---|---|---:|---:|
| `/assets/index-CjvC5vhW.css` (`theta-relationship-sandy-copyrighted.trycloudflare.com`) | 1st party (`trycloudflare.com`) | 10.9 KiB | 160 ms |
| `https://fonts.googleapis.com/css2?family=…` | Google Fonts CDN | 1.7 KiB | 750 ms |

---

### Use efficient cache lifetimes (Estimated savings: **142 KiB**)
A long cache lifetime can speed up repeat visits to your page.

| Request | Cache TTL | Transfer Size |
|---|---|---:|
| `/assets/index-EQMvviTI.js` (`theta-relationship-sandy-copyrighted.trycloudflare.com`) | None | 131 KiB |
| `/assets/index-CjvC5vhW.css` (`theta-relationship-sandy-copyrighted.trycloudflare.com`) | None | 11 KiB |

---

## LCP Detail

### LCP breakdown
Each subpart has specific improvement strategies. Ideally, most of the LCP time should be spent on loading resources, not within delays.

| Subpart | Duration |
|---|---:|
| Time to first byte | 0 ms |
| Resource load delay | 34,160 ms |
| Resource load duration | 0 ms |
| Element render delay | 210 ms |

LCP element reference:
- `13fba7dca7-1049381324-d226415c.png`
- Example element snippet:
  ```html
  <img class="w-full h-full object-cover block pointer-events-none select-none opacity-0…" 
       src="blob:https://theta-relationship-sandy-copyrighted.trycloudflare.com/f201e4…" 
       alt="13fba7dca7-1049381324-d226415c.png" 
       loading="lazy" decoding="async" width="248" height="186">
  ```

### LCP request discovery

Optimize LCP by making the LCP image discoverable from the HTML immediately, and avoiding lazy-loading.

Notes recorded:

- `lazy load not applied`
- `fetchpriority=high should be applied`
- `Request is discoverable in initial document`

LCP image reference repeated:

- `13fba7dca7-1049381324-d226415c.png`

------

## Network dependency tree

Avoid chaining critical requests by reducing chain length, reducing download size, or deferring unnecessary resources.

**Maximum critical path latency:** **34,311 ms**

Critical chain (as recorded):

- Initial Navigation
  - `https://theta-relationship-sandy-copyrighted.trycloudflare.com` — 395 ms, 0.76 KiB
- Core assets / app load
  - `/assets/index-EQMvviTI.js` — 803 ms, 131.31 KiB
- Long chain of folder pagination calls
  - `/folders?path=%2Fexpansion&page=3&page_size=200&recursive=1` — 7,967 ms, 11.51 KiB
  - `/folders?path=%2Fexpansion&page=4&page_size=200&recursive=1` — 9,078 ms, 11.52 KiB
  - `/folders?path=%2Fexpansion&page=5&page_size=200&recursive=1` — 10,969 ms, 11.62 KiB
  - `/folders?path=%2Fexpansion&page=6&page_size=200&recursive=1` — 11,574 ms, 11.74 KiB
  - `/folders?path=%2Fexpansion&page=7&page_size=200&recursive=1` — 12,555 ms, 11.86 KiB
  - `/folders?path=%2Fexpansion&page=8&page_size=200&recursive=1` — 13,460 ms, 11.69 KiB
  - `/folders?path=%2Fexpansion&page=9&page_size=200&recursive=1` — 14,449 ms, 11.56 KiB
  - `/folders?path=%2Fexpansion&page=10&page_size=200&recursive=1` — 14,920 ms, 11.78 KiB
  - `/folders?path=%2Fexpansion&page=11&page_size=200&recursive=1` — 15,438 ms, 11.59 KiB
  - `/folders?path=%2Fexpansion&page=12&page_size=200&recursive=1` — 16,234 ms, 11.56 KiB
  - `/folders?path=%2Fexpansion&page=13&page_size=200&recursive=1` — 19,645 ms, 11.85 KiB
  - `/folders?path=%2Fexpansion&page=14&page_size=200&recursive=1` — 23,104 ms, 11.79 KiB
  - `/folders?path=%2Fexpansion&page=15&page_size=200&recursive=1` — 23,521 ms, 11.89 KiB
  - `/folders?path=%2Fexpansion&page=16&page_size=200&recursive=1` — 23,869 ms, 11.81 KiB
  - `/folders?path=%2Fexpansion&page=17&page_size=200&recursive=1` — 24,483 ms, 11.46 KiB
  - `/folders?path=%2Fexpansion&page=18&page_size=200&recursive=1` — 25,156 ms, 11.52 KiB
  - `/folders?path=%2Fexpansion&page=19&page_size=200&recursive=1` — 25,585 ms, 11.80 KiB
  - `/folders?path=%2Fexpansion&page=20&page_size=200&recursive=1` — 26,032 ms, 11.93 KiB
  - `/folders?path=%2Fexpansion&page=21&page_size=200&recursive=1` — 26,390 ms, 11.95 KiB
  - `/folders?path=%2Fexpansion&page=22&page_size=200&recursive=1` — 27,340 ms, 11.51 KiB
  - `/folders?path=%2Fexpansion&page=23&page_size=200&recursive=1` — 29,678 ms, 11.56 KiB
  - `/folders?path=%2Fexpansion&page=24&page_size=200&recursive=1` — 30,943 ms, 11.93 KiB
  - `/folders?path=%2Fexpansion&page=25&page_size=200&recursive=1` — 31,305 ms, 11.91 KiB
  - `/folders?path=%2Fexpansion&page=26&page_size=200&recursive=1` — 31,983 ms, 11.89 KiB
  - `/folders?path=%2Fexpansion&page=27&page_size=200&recursive=1` — 32,979 ms, 11.46 KiB
  - `/folders?path=%2Fexpansion&page=28&page_size=200&recursive=1` — 33,321 ms, 12.07 KiB
  - `/folders?path=%2Fexpansion&page=29&page_size=200&recursive=1` — 33,681 ms, 5.19 KiB
- Presence / join
  - `/presence/join` — 34,311 ms, 0.37 KiB

Additional recorded requests near the tail:

- Multiple `/thumb?path=…` entries — ~33,721–33,739 ms, 0.00 KiB each
- `/folders?path=%2F` — 3,948 ms, 0.38 KiB
- `/folders?path=%2F&page=1&page_size=200&recursive=1` — 4,373 ms, 7.09 KiB
- `/embeddings` — 4,021 ms, 0.23 KiB
- `/presence/join` — 5,334 ms, 0.37 KiB
- `/health` — 4,450 ms, 0.73 KiB
- `/views` — 3,923 ms, 0.22 KiB
- `/folders?path=%2Fexpansion&page=1&page_size=200&recursive=1` — 5,558 ms, 11.67 KiB
- `/presence/move` — 5,633 ms, 0.39 KiB
- `/folders?path=%2Fexpansion&page=2&page_size=200&recursive=1` — 6,569 ms, 11.77 KiB
- `/assets/index-CjvC5vhW.css` — 3,528 ms, 10.89 KiB
- `https://fonts.googleapis.com/css2?family=…` — 3,538 ms, 1.69 KiB
- `…v23/zYXzKVElM….woff2` (`fonts.gstatic.com`) — 3,635 ms, 40.09 KiB

------

## Preconnect

No origins were preconnected.

Preconnect candidates:

- No additional origins are good candidates for preconnecting.

------

## Diagnostics

### Reduce unused JavaScript (Estimated savings: **60 KiB**)

Reduce unused JavaScript and defer loading scripts until they are required.

| URL / Resource                                               | Party                           | Transfer Size | Est. Savings |
| ------------------------------------------------------------ | ------------------------------- | ------------- | ------------ |
| `/assets/index-EQMvviTI.js` (`theta-relationship-sandy-copyrighted.trycloudflare.com`) | 1st party (`trycloudflare.com`) | 130.9 KiB     | 60.0 KiB     |

