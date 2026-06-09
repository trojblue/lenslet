import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SOURCE = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../useAppDataScope.ts'),
  'utf8',
)
const APP_SHELL_SOURCE = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../AppShell.tsx'),
  'utf8',
)

describe('useAppDataScope backend browse-query boundary', () => {
  it('keeps normal browse membership and ordering out of local loaded-page helpers', () => {
    expect(SOURCE).toContain('useBrowseQuery')
    expect(SOURCE).toContain('fetchNextPage')
    expect(SOURCE).not.toContain('useSearch(')
    expect(SOURCE).not.toContain('applySort(')
    expect(SOURCE).not.toContain('api.getFolder(')
    expect(SOURCE).not.toContain('applyFilters(poolItems')
    expect(SOURCE).toContain('enabled: !similarityActive && browseQueryUnavailableReason === null')
    expect(SOURCE).toContain('getBackendBrowseDerivedMetricUnsupportedReason(')
    expect(SOURCE).toContain('sort: viewState.sort,')
    expect(SOURCE).not.toContain('backendBrowseSort')
    expect(SOURCE).not.toContain('scanStableMode')
  })

  it('does not request raw folder facets while backend text search is active', () => {
    expect(APP_SHELL_SOURCE).toContain(
      "enabled: leftOpen && (leftTool === 'metrics' || leftTool === 'derived') && !similarityState && !searching",
    )
  })
})
