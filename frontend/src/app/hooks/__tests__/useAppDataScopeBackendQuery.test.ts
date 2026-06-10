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

  it('requests query-shaped facets during backend text search', () => {
    expect(APP_SHELL_SOURCE).toContain(
      'textQuery: normalizedQ,',
    )
    expect(APP_SHELL_SOURCE).not.toContain('&& !similarityState && !searching')
  })

  it('threads shared URL unsupported metric intent into backend analysis identity', () => {
    expect(APP_SHELL_SOURCE).toContain('urlUnsupportedMetricIntent')
    expect(APP_SHELL_SOURCE).toContain('unsupportedMetricIntent: analysisUnsupportedMetricIntent')
    expect(APP_SHELL_SOURCE).toContain('unsupportedToken: analysisUnsupportedMetricIntent')
    expect(SOURCE).toContain('analysisUnsupportedMetricIntent = browseQueryUnavailableReason')
    expect(SOURCE).toContain('unsupportedToken: analysisUnsupportedMetricIntent')
  })
})
