import type { BrowseItemPayload, SavedView, StarRating } from '../../lib/types'

export function makeUniqueViewId(name: string, views: SavedView[]): string {
  const base = slugify(name) || 'view'
  const existing = new Set(views.map((view) => view.id))
  if (!existing.has(base)) return base

  let suffix = 2
  while (existing.has(`${base}-${suffix}`)) {
    suffix += 1
  }
  return `${base}-${suffix}`
}

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function formatStarValues(values: number[]): string {
  const stars = values.filter((value) => value > 0).sort((a, b) => b - a)
  const hasNone = values.includes(0)
  const parts = [...stars.map((value) => String(value))]
  if (hasNone) parts.push('None')
  return parts.join(', ')
}

export function formatDateRange(from?: string, to?: string): string {
  if (from && to) return `${from} to ${to}`
  if (from) return `from ${from}`
  if (to) return `to ${to}`
  return ''
}

export function formatScopeLabel(path: string): string {
  if (path === '/' || path === '') return 'Root'
  const segments = path.split('/').filter(Boolean)
  if (!segments.length) return 'Root'
  if (segments.length <= 2) return `/${segments.join('/')}`
  const tail = segments.slice(-2).join('/')
  return `.../${tail}`
}

export function resolveScopeFromHashTarget(
  previousScope: string,
  folderTarget: string,
  imageTarget: string | null,
  isInitialHashSync: boolean
): string {
  if (!imageTarget) return folderTarget
  if (isInitialHashSync) return folderTarget
  if (previousScope === '/' || previousScope === '') return previousScope || '/'
  if (imageTarget === previousScope || imageTarget.startsWith(`${previousScope}/`)) {
    return previousScope
  }
  return folderTarget
}

export function formatRange(min: number, max: number): string {
  return `${formatNumber(min)}–${formatNumber(max)}`
}

function formatNumber(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}

function guessMimeFromPath(path: string): BrowseItemPayload['mime'] {
  const lower = path.toLowerCase()
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.webp')) return 'image/webp'
  return 'image/jpeg'
}

export function buildFallbackItem(path: string, starOverride?: StarRating): BrowseItemPayload {
  const name = path.split('/').pop() ?? path
  return {
    path,
    name,
    mime: guessMimeFromPath(path),
    width: 0,
    height: 0,
    size: 0,
    hasThumbnail: true,
    hasMetadata: false,
    star: starOverride ?? null,
  }
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
