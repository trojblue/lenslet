import type { BrowseItemPayload } from '../../lib/types'

export function isHttpOriginalUrl(value: string | null | undefined): value is string {
  if (!value) return false
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function directOriginalImageUrl(
  item: BrowseItemPayload | null | undefined,
  proxyHttpOriginals: boolean,
): string | null {
  if (proxyHttpOriginals || !item) return null
  if (isHttpOriginalUrl(item.url)) return item.url
  if (isHttpOriginalUrl(item.source)) return item.source
  return null
}
