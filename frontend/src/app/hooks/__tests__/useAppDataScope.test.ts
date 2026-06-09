import { describe, expect, it } from 'vitest'
import {
  resolveBrowseCapabilityKeys,
  type BrowseCapabilityKeys,
} from '../useAppDataScope'

const EMPTY_ROOT_KEYS: BrowseCapabilityKeys = {
  path: '/',
  metricKeys: [],
  categoricalKeys: [],
  ready: false,
}

describe('resolveBrowseCapabilityKeys', () => {
  it('keeps known scope metric keys while a same-scope browse query refetches', () => {
    const loaded = resolveBrowseCapabilityKeys('/', {
      path: '/',
      metric_keys: ['quality_score'],
      categorical_keys: ['source_column'],
    }, EMPTY_ROOT_KEYS)

    expect(loaded.ready).toBe(true)

    const refetching = resolveBrowseCapabilityKeys('/', undefined, loaded)

    expect(refetching).toBe(loaded)
    expect(refetching.metricKeys).toEqual(['quality_score'])
    expect(refetching.categoricalKeys).toEqual(['source_column'])
    expect(refetching.ready).toBe(true)
  })

  it('does not carry stale metric keys across folder changes', () => {
    const loaded = resolveBrowseCapabilityKeys('/', {
      path: '/',
      metric_keys: ['quality_score'],
      categorical_keys: ['source_column'],
    }, EMPTY_ROOT_KEYS)

    const nextFolder = resolveBrowseCapabilityKeys('/other', undefined, loaded)

    expect(nextFolder).toEqual({
      path: '/other',
      metricKeys: [],
      categoricalKeys: [],
      ready: false,
    })
  })

  it('treats a returned empty key list as ready backend metadata', () => {
    const loaded = resolveBrowseCapabilityKeys('/empty', {
      path: '/empty',
      metric_keys: [],
      categorical_keys: [],
    }, EMPTY_ROOT_KEYS)

    expect(loaded).toEqual({
      path: '/empty',
      metricKeys: [],
      categoricalKeys: [],
      ready: true,
    })
  })
})
