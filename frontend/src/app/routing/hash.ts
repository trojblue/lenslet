import { sanitizePath } from '../../lib/paths'

const IMAGE_HASH_PREFIX = '!'

export type HashTargets = {
  folderTarget: string
  imageTarget: string | null
}

export function readHash(): string {
  return (window.location.hash || '').replace(/^#/, '')
}

export function writeHash(p: string): void {
  const normalized = sanitizePath(p)
  const h = `#${encodeURI(normalized)}`
  if (window.location.hash !== h) {
    window.location.hash = h
  }
}

/**
 * Write a viewer path to the URL hash.
 *
 * Folder hashes are plain paths. Viewer hashes use a hashbang marker so
 * extensionless image ids cannot be mistaken for folders.
 */
export function writeImageHash(p: string): void {
  const normalized = sanitizePath(p)
  const h = `#!${encodeURI(normalized)}`
  if (window.location.hash !== h) {
    window.location.hash = h
  }
}

export function replaceHash(p: string): void {
  const normalized = sanitizePath(p)
  const h = `#${encodeURI(normalized)}`
  if (window.location.hash !== h) {
    const url = `${window.location.pathname}${window.location.search}${h}`
    window.history.replaceState(window.history.state, '', url)
  }
}

export function replaceImageHash(p: string): void {
  const normalized = sanitizePath(p)
  const h = `#!${encodeURI(normalized)}`
  if (window.location.hash !== h) {
    const url = `${window.location.pathname}${window.location.search}${h}`
    window.history.replaceState(window.history.state, '', url)
  }
}

export function getParentPath(path: string): string {
  const normalized = sanitizePath(path)
  const parts = normalized.split('/').filter(Boolean)
  if (parts.length <= 1) return '/'
  return '/' + parts.slice(0, -1).join('/')
}

/**
 * Resolve a raw hash into the browse scope and optional viewer image.
 *
 * Viewer URLs are explicit (`#!/path`). Plain hashes always target folders.
 */
export function resolveHashTargets(raw: string): HashTargets {
  if (raw.startsWith(IMAGE_HASH_PREFIX)) {
    const imageTarget = sanitizePath(raw.slice(IMAGE_HASH_PREFIX.length))
    if (imageTarget === '/') {
      return { folderTarget: '/', imageTarget: null }
    }
    return { folderTarget: getParentPath(imageTarget), imageTarget }
  }

  const normalized = sanitizePath(raw)
  return {
    folderTarget: normalized,
    imageTarget: null,
  }
}

export function getPathName(path: string): string {
  const normalized = sanitizePath(path)
  return normalized.split('/').filter(Boolean).pop() || ''
}

export function isTrashPath(path: string): boolean {
  return path.endsWith('/_trash_')
}
