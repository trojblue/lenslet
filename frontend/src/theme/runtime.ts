export type ThemePresetId = 'default' | 'teal' | 'charcoal'

type ThemeTokenMap = Record<string, string>

export type ThemePreset = {
  id: ThemePresetId
  label: string
  tokens: ThemeTokenMap
}

const DEFAULT_THEME_TOKENS: ThemeTokenMap = {
  '--bg': '#0e0d0b',
  '--panel': '#181613',
  '--hover': '#23211e',
  '--border': '#2b2924',
  '--surface': '#1c1a17',
  '--surface-hover': '#25231f',
  '--surface-active': '#2e2b26',
  '--surface-overlay': '#131210',
  '--surface-inset': '#0f0e0c',
  '--text': '#e9e5df',
  '--text-secondary': '#d3cec6',
  '--muted': '#918b82',
  '--accent': '#3b82f6',
  '--accent-hover': '#5a9bff',
  '--accent-muted': 'rgba(59, 130, 246, 0.18)',
  '--accent-strong': 'rgba(59, 130, 246, 0.32)',
  '--highlight': '#e6a23c',
  '--sync-recent': '#b08bff',
  '--danger': '#ff6b6b',
  '--success': '#9ad4b5',
  '--warning': '#f0b660',
  '--info': '#55b8ff',
  '--border-subtle': 'rgba(255, 255, 255, 0.06)',
  '--border-strong': '#3a3833',
  '--border-hover': '#4a463e',
  '--bg-gradient': 'radial-gradient(1200px 600px at 10% -10%, rgba(255, 175, 110, 0.05), transparent 60%), radial-gradient(900px 500px at 100% -20%, rgba(59, 130, 246, 0.08), transparent 55%), var(--bg)',
}

const TEAL_THEME_TOKENS: ThemeTokenMap = {
  ...DEFAULT_THEME_TOKENS,
  '--accent': '#2dd4bf',
  '--accent-hover': '#5eead4',
  '--accent-muted': 'rgba(45, 212, 191, 0.18)',
  '--accent-strong': 'rgba(45, 212, 191, 0.32)',
  '--bg-gradient': 'radial-gradient(1200px 600px at 10% -10%, rgba(255, 175, 110, 0.05), transparent 60%), radial-gradient(900px 500px at 100% -20%, rgba(45, 212, 191, 0.08), transparent 55%), var(--bg)',
}

const CHARCOAL_THEME_TOKENS: ThemeTokenMap = {
  ...DEFAULT_THEME_TOKENS,
  '--bg': '#111215',
  '--panel': '#181b20',
  '--hover': '#20252d',
  '--border': '#3a434f',
  '--surface': '#20252d',
  '--surface-hover': '#2a313c',
  '--surface-active': '#323b47',
  '--surface-overlay': 'rgba(24, 27, 32, 0.95)',
  '--surface-inset': '#0e0f12',
  '--text': '#f1f5f9',
  '--text-secondary': '#cbd5e1',
  '--muted': '#94a3b8',
  '--accent': '#86b7ff',
  '--accent-hover': '#a5cbff',
  '--accent-muted': 'rgba(134, 183, 255, 0.18)',
  '--accent-strong': 'rgba(134, 183, 255, 0.32)',
  '--border-subtle': 'rgba(255, 255, 255, 0.06)',
  '--border-strong': '#556275',
  '--border-hover': '#67778c',
  '--bg-gradient': 'radial-gradient(1200px 600px at 10% -10%, rgba(255, 175, 110, 0.04), transparent 60%), radial-gradient(900px 500px at 100% -20%, rgba(134, 183, 255, 0.06), transparent 55%), var(--bg)',
}

export const THEME_PRESETS: Record<ThemePresetId, ThemePreset> = {
  default: {
    id: 'default',
    label: 'Original',
    tokens: DEFAULT_THEME_TOKENS,
  },
  teal: {
    id: 'teal',
    label: 'Teal',
    tokens: TEAL_THEME_TOKENS,
  },
  charcoal: {
    id: 'charcoal',
    label: 'Charcoal',
    tokens: CHARCOAL_THEME_TOKENS,
  },
}

const DYNAMIC_FAVICON_ATTR = 'data-lenslet-dynamic-favicon'
const DYNAMIC_FAVICON_SELECTOR = `link[${DYNAMIC_FAVICON_ATTR}="1"]`

function getDocument(doc?: Document | null): Document | null {
  if (doc !== undefined) return doc
  if (typeof document === 'undefined') return null
  return document
}

export function isThemePresetId(value: string | null | undefined): value is ThemePresetId {
  return value === 'default' || value === 'teal' || value === 'charcoal'
}

export function resolveThemePresetId(value: string | null | undefined): ThemePresetId {
  return isThemePresetId(value) ? value : 'default'
}

function normalizeColor(color: string): string {
  const trimmed = color.trim()
  return trimmed || DEFAULT_THEME_TOKENS['--accent']
}

function buildFaviconSvg(fillColor: string): string {
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">',
    '<defs><clipPath id="a"><rect x="10" y="10" width="44" height="44" rx="12"/></clipPath></defs>',
    '<rect width="64" height="64" fill="#111114"/>',
    `<rect x="10" y="10" width="44" height="44" rx="12" fill="${fillColor}"/>`,
    '<g clip-path="url(#a)">',
    '<path d="M20 22h24v6H26v8h16v6H26v10h-6z" fill="#f7f8fa"/>',
    '</g>',
    '</svg>',
  ].join('')
}

export function buildThemedFaviconHref(color: string): string {
  const fill = normalizeColor(color)
  const svg = buildFaviconSvg(fill)
  return `data:image/svg+xml,${encodeURIComponent(svg)}#accent=${encodeURIComponent(fill)}`
}

export function upsertThemedFavicon(color: string, doc?: Document | null): string {
  const activeDocument = getDocument(doc)
  const href = buildThemedFaviconHref(color)
  if (!activeDocument) return href
  const head = activeDocument.head
  if (!head) return href
  let link = head.querySelector(DYNAMIC_FAVICON_SELECTOR) as HTMLLinkElement | null
  if (!link) {
    link = activeDocument.createElement('link')
    link.setAttribute(DYNAMIC_FAVICON_ATTR, '1')
    link.setAttribute('rel', 'icon')
    link.setAttribute('type', 'image/svg+xml')
    head.appendChild(link)
  }
  if (link.getAttribute('href') !== href) {
    link.setAttribute('href', href)
  }
  return href
}

export function applyThemePreset(themeId: string | null | undefined, doc?: Document | null): ThemePresetId {
  const resolvedThemeId = resolveThemePresetId(themeId)
  const preset = THEME_PRESETS[resolvedThemeId]
  const activeDocument = getDocument(doc)
  if (!activeDocument) return resolvedThemeId
  const root = activeDocument.documentElement
  for (const [token, value] of Object.entries(preset.tokens)) {
    root.style.setProperty(token, value)
  }
  root.setAttribute('data-lenslet-theme', resolvedThemeId)
  upsertThemedFavicon(preset.tokens['--accent'], activeDocument)
  return resolvedThemeId
}
