import { describe, expect, it } from 'vitest'
import {
  buildSelectionExportHandler,
  buildFindSimilarMenuItem,
  buildRefreshMenuItem,
  FIND_SIMILAR_UNAVAILABLE_LABEL,
  REFRESH_UNAVAILABLE_LABEL,
} from '../AppContextMenuItems'
import type { BrowseItemPayload, StarRating } from '../../../lib/types'

function browseItem(path: string, star: StarRating = null): BrowseItemPayload {
  return {
    path,
    name: path.split('/').pop() || 'image.jpg',
    mime: 'image/jpeg',
    width: 10,
    height: 8,
    size: 123,
    has_thumbnail: true,
    has_metadata: true,
    star,
    notes: null,
  }
}

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

describe('buildSelectionExportHandler', () => {
  it('returns a synchronous handler that exports selected items and closes the menu', async () => {
    const states: Array<'csv' | 'json' | null> = []
    const downloads: Array<{ blob: Blob; name: string }> = []
    let closeCalls = 0
    const handler = buildSelectionExportHandler({
      format: 'json',
      selectedPaths: ['/gallery/a.jpg'],
      items: [browseItem('/gallery/a.jpg', 5), browseItem('/gallery/b.jpg')],
      setExporting: (format) => states.push(format),
      closeMenu: () => {
        closeCalls += 1
      },
      download: (blob, name) => {
        downloads.push({ blob, name })
      },
      timestamp: () => '2026-05-31T00-00-00-000Z',
    })

    const result = handler()
    const exportedText = await downloads[0].blob.text()

    expect(result).toBeUndefined()
    expect(states).toEqual(['json', null])
    expect(closeCalls).toBe(1)
    expect(downloads[0].name).toBe('metadata_selection_2026-05-31T00-00-00-000Z.json')
    expect(exportedText).toContain('/gallery/a.jpg')
    expect(exportedText).not.toContain('/gallery/b.jpg')
  })
})
