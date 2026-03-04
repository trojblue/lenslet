import { describe, expect, it } from 'vitest'
import {
  buildFindSimilarMenuItem,
  buildRefreshMenuItem,
  FIND_SIMILAR_UNAVAILABLE_LABEL,
  REFRESH_UNAVAILABLE_LABEL,
} from '../AppContextMenuItems'

describe('buildRefreshMenuItem', () => {
  it('disables refresh when unavailable', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: false,
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe(REFRESH_UNAVAILABLE_LABEL)
  })

  it('prefers backend-provided refresh disabled reason', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: false,
      refreshDisabledReason: 'table mode is static',
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe('table mode is static')
  })

  it('shows refreshing label when active', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: true,
      refreshing: true,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe('Refreshing…')
  })

  it('shows refresh when enabled and idle', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: true,
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(false)
    expect(item.label).toBe('Refresh')
  })
})

describe('buildFindSimilarMenuItem', () => {
  it('returns null when no callback is configured', () => {
    const item = buildFindSimilarMenuItem({
      selectedPaths: ['/a.png'],
      canFindSimilar: true,
      findSimilarDisabledReason: null,
      onFindSimilar: undefined,
    })

    expect(item).toBeNull()
  })

  it('builds enabled find-similar item for a single selected path', () => {
    const paths: string[] = []
    const item = buildFindSimilarMenuItem({
      selectedPaths: ['/a.png'],
      canFindSimilar: true,
      findSimilarDisabledReason: null,
      onFindSimilar: (path) => paths.push(path),
    })

    expect(item).not.toBeNull()
    expect(item?.disabled).toBe(false)
    expect(item?.label).toBe('Find similar')
    item?.onClick()
    expect(paths).toEqual(['/a.png'])
  })

  it('keeps disabled reason parity when embeddings are unavailable', () => {
    const item = buildFindSimilarMenuItem({
      selectedPaths: ['/a.png'],
      canFindSimilar: false,
      findSimilarDisabledReason: 'No embeddings detected.',
      onFindSimilar: () => {},
    })

    expect(item).not.toBeNull()
    expect(item?.disabled).toBe(true)
    expect(item?.label).toBe('No embeddings detected.')
  })

  it('falls back to single-select guidance for multi-selection context menus', () => {
    const item = buildFindSimilarMenuItem({
      selectedPaths: ['/a.png', '/b.png'],
      canFindSimilar: false,
      findSimilarDisabledReason: null,
      onFindSimilar: () => {},
    })

    expect(item).not.toBeNull()
    expect(item?.disabled).toBe(true)
    expect(item?.label).toBe('Select a single image to search.')
  })

  it('uses generic unavailable fallback when disabled reason is missing', () => {
    const item = buildFindSimilarMenuItem({
      selectedPaths: ['/a.png'],
      canFindSimilar: false,
      findSimilarDisabledReason: null,
      onFindSimilar: () => {},
    })

    expect(item).not.toBeNull()
    expect(item?.disabled).toBe(true)
    expect(item?.label).toBe(FIND_SIMILAR_UNAVAILABLE_LABEL)
  })
})
