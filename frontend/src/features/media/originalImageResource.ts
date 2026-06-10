import type { BrowseItemPayload, OriginalMediaPolicy } from '../../lib/types'

export type DirectOriginalFailureRegistry = ReadonlySet<string> | ((path: string) => boolean)

export function isHttpOriginalUrl(value: string | null | undefined): value is string {
  if (!value) return false
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function originalMediaAllowsDirect(policy: OriginalMediaPolicy | null | undefined): boolean {
  return policy?.source_kind === 'http'
    && (
      policy.mode === 'browser_direct_allowed'
      || policy.mode === 'browser_direct_preferred_with_proxy_fallback'
    )
}

function hasDirectOriginalFailure(
  path: string,
  failedDirectOriginals?: DirectOriginalFailureRegistry,
): boolean {
  if (!failedDirectOriginals) return false
  if (typeof failedDirectOriginals === 'function') return failedDirectOriginals(path)
  return failedDirectOriginals.has(path)
}

export function directOriginalImageUrl(
  item: BrowseItemPayload | null | undefined,
  proxyHttpOriginals: boolean,
  failedDirectOriginals?: DirectOriginalFailureRegistry,
): string | null {
  if (proxyHttpOriginals || !item) return null
  if (hasDirectOriginalFailure(item.path, failedDirectOriginals)) return null
  if (!originalMediaAllowsDirect(item.original_media)) return null
  if (isHttpOriginalUrl(item.url)) return item.url
  if (isHttpOriginalUrl(item.source)) return item.source
  return null
}
